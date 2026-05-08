"""One-shot SQLite -> Neon Postgres migration.

Steps (each one fails loud and halts before touching anything destructive):

  1. Read DATABASE_URL (env or --url flag) and ping Neon
  2. Snapshot the local SQLite file (.bak alongside the original)
  3. Run init_db.init_db() against Neon -> creates the 5 tables
  4. For each table: SELECT * FROM SQLite, UPSERT into Postgres
     - extraction_log preserves log_id and bumps the BIGSERIAL afterwards
     - uploads / runs_openai / llm_comparison key on their TEXT PK
  5. Verify row counts match between source and target
  6. Print a summary; do NOT touch the SQLite file beyond the snapshot

After this script succeeds:
  - put DATABASE_URL into .env
  - restart the backend
  - the same /api/* endpoints now hit Neon

If anything below the row-copy step misbehaves, just unset DATABASE_URL
and you're back on SQLite — no data is removed.

    py -3.12 scripts/migrate_to_neon.py
    py -3.12 scripts/migrate_to_neon.py --url "postgresql://..."
    py -3.12 scripts/migrate_to_neon.py --dry-run
"""
from __future__ import annotations
import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# IMPORTANT: parse the URL BEFORE importing config / init_db, because both
# read DATABASE_URL at module-import time. We pre-populate the env var so
# init_db.init_db() automatically targets Neon when we call it later.
def _bootstrap_env() -> str:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--url")
    ap.add_argument("--dry-run", action="store_true")
    known, _ = ap.parse_known_args()
    raw = (known.url or os.getenv("DATABASE_URL", "")).strip()
    if raw:
        os.environ["DATABASE_URL"] = raw
    return raw


_BOOTSTRAP_URL = _bootstrap_env()

from sqlalchemy import create_engine, text  # noqa: E402

import config  # noqa: E402


TABLES = ("uploads", "runs_openai", "llm_comparison", "extraction_log")


def _normalise_url(raw: str) -> str:
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _ping_neon(pg_url: str) -> str:
    eng = create_engine(pg_url, future=True, pool_pre_ping=True)
    with eng.connect() as c:
        ver = c.execute(text("SELECT version()")).scalar() or ""
    return ver


def _snapshot_sqlite() -> Path | None:
    src = config.DB_PATH
    if not src.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dst = src.with_suffix(f".db.bak-{stamp}")
    shutil.copy2(src, dst)
    return dst


def _columns_for(eng, table: str) -> list[str]:
    """Get column names from a live engine — works on both dialects."""
    sqlite = eng.dialect.name == "sqlite"
    with eng.connect() as c:
        if sqlite:
            rows = c.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return [r[1] for r in rows]
        rows = c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t "
            "ORDER BY ordinal_position"
        ), {"t": table}).fetchall()
        return [r[0] for r in rows]


def _row_count(eng, table: str) -> int:
    with eng.connect() as c:
        return int(c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)


def _copy_table(src_eng, dst_eng, table: str) -> tuple[int, int]:
    """Copy rows source -> target with **case-insensitive** column matching.

    The legacy SQLite DB has columns like `BM_Details` while Neon's fresh
    schema uses `bm_details`. We match on lowercase keys, SELECT using the
    source's actual case, and INSERT into the target's actual case.
    """
    src_cols = _columns_for(src_eng, table)
    dst_cols = _columns_for(dst_eng, table)
    src_by_lc = {c.lower(): c for c in src_cols}
    dst_by_lc = {c.lower(): c for c in dst_cols}
    common_lc = [k for k in src_by_lc if k in dst_by_lc]
    if not common_lc:
        raise RuntimeError(f"{table}: no overlapping columns between source and target")

    src_select = ", ".join(f'"{src_by_lc[k]}" AS "{k}"' for k in common_lc)
    dst_insert_cols = ", ".join(dst_by_lc[k] for k in common_lc)
    placeholders   = ", ".join(f":{k}" for k in common_lc)

    pk = {
        "uploads":        "upload_id",
        "runs_openai":    "run_id",
        "llm_comparison": "run_id",
        "extraction_log": "log_id",
    }[table]
    update_cols = [k for k in common_lc if k != pk]
    update_set = ", ".join(
        f"{dst_by_lc[k]} = EXCLUDED.{dst_by_lc[k]}" for k in update_cols
    ) or f"{pk} = EXCLUDED.{pk}"

    insert_sql = text(
        f"INSERT INTO {table} ({dst_insert_cols}) VALUES ({placeholders}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET {update_set}"
    )

    with src_eng.connect() as src:
        rows = src.execute(text(f"SELECT {src_select} FROM {table}")).mappings().all()

    if not rows:
        return 0, _row_count(dst_eng, table)

    with dst_eng.begin() as dst:
        for r in rows:
            dst.execute(insert_sql, dict(r))

    # Bump BIGSERIAL for extraction_log so future inserts don't collide
    if table == "extraction_log" and dst_eng.dialect.name == "postgresql":
        with dst_eng.begin() as dst:
            dst.execute(text(
                "SELECT setval(pg_get_serial_sequence('extraction_log','log_id'), "
                "(SELECT COALESCE(MAX(log_id), 1) FROM extraction_log))"
            ))

    return len(rows), _row_count(dst_eng, table)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="Postgres URL (overrides DATABASE_URL env)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Ping Neon + show row counts; copy nothing")
    args = ap.parse_args()

    raw = (args.url or os.getenv("DATABASE_URL", "")).strip()
    if not raw:
        print("ERROR: provide DATABASE_URL via env or --url")
        print("       e.g. py scripts/migrate_to_neon.py --url 'postgresql://...'")
        return 2

    pg_url = _normalise_url(raw)
    sqlite_url = f"sqlite:///{config.DB_PATH.as_posix()}"

    # Mask the password when echoing the URL
    masked = pg_url
    if "@" in masked and "//" in masked:
        head, tail = masked.split("@", 1)
        scheme, creds = head.rsplit("//", 1)
        user = creds.split(":", 1)[0] if ":" in creds else creds
        masked = f"{scheme}//{user}:****@{tail}"

    print("=" * 70)
    print("LitExtract  ·  SQLite -> Neon Postgres migration")
    print("=" * 70)
    print(f"  source : {sqlite_url}")
    print(f"  target : {masked}")
    print()

    print("[1/5] Pinging Neon ...")
    try:
        ver = _ping_neon(pg_url)
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Check the URL, your network, and that Neon's compute is awake.")
        return 1
    print(f"  OK  ·  {ver.splitlines()[0]}")

    print()
    print("[2/5] Snapshotting SQLite ...")
    if config.DB_PATH.exists():
        snap = _snapshot_sqlite()
        print(f"  OK  ·  backed up to {snap}")
    else:
        print("  SKIP  ·  no SQLite file exists yet (this is a fresh install)")

    print()
    print("[3/5] Building schema on Neon ...")
    # config + init_db were imported with DATABASE_URL already set, so
    # init_db.get_engine() points at Neon natively.
    import init_db
    init_db.init_db()
    print("  OK  ·  5 tables created (or already present)")

    src_eng = create_engine(sqlite_url, future=True,
                            connect_args={"check_same_thread": False})
    dst_eng = create_engine(pg_url, future=True, pool_pre_ping=True)

    if args.dry_run:
        print()
        print("[4/5] DRY-RUN  ·  comparing row counts ...")
        for t in TABLES:
            try:
                src_n = _row_count(src_eng, t)
            except Exception:
                src_n = "n/a (table missing)"
            try:
                dst_n = _row_count(dst_eng, t)
            except Exception:
                dst_n = "n/a"
            print(f"  {t:18s}  sqlite={src_n:>4}   neon={dst_n:>4}")
        print()
        print("Dry run complete — no data copied.")
        return 0

    print()
    print("[4/5] Copying rows ...")
    summary: list[tuple[str, int, int]] = []
    for t in TABLES:
        try:
            src_n_pre = _row_count(src_eng, t)
        except Exception:
            print(f"  {t:18s}  source missing — skipping")
            continue
        try:
            copied, dst_n = _copy_table(src_eng, dst_eng, t)
        except Exception as e:
            print(f"  {t:18s}  FAILED: {e}")
            return 1
        print(f"  {t:18s}  copied={copied:>4}   neon now has {dst_n} rows")
        summary.append((t, src_n_pre, dst_n))

    print()
    print("[5/5] Verifying parity ...")
    ok = True
    for t, src_n, dst_n in summary:
        ok_row = "OK" if dst_n >= src_n else "MISMATCH"
        if dst_n < src_n:
            ok = False
        print(f"  {t:18s}  source={src_n:>4}   target={dst_n:>4}   {ok_row}")

    print()
    if ok:
        print("DONE.  Add DATABASE_URL to your .env and restart the backend.")
        print(f'    DATABASE_URL="{raw}"')
    else:
        print("WARNING: target has fewer rows than source. Review above.")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
