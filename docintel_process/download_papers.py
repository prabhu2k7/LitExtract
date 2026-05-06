"""Download PDFs for PMIDs from PMC Open Access + Unpaywall fallback."""
from __future__ import annotations
import argparse
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import requests

import config

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_OA_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "biomarker-rag@example.com")

STATUS_FILE = config.PROJECT_ROOT / "docintel_process" / "pipeline_status.json"


def _load_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_status(status: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2))


def pmid_to_pmcid(pmid: str) -> Optional[str]:
    r = requests.get(
        f"{NCBI_BASE}/elink.fcgi",
        params={"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "json"},
        timeout=30,
    )
    r.raise_for_status()
    try:
        links = r.json()["linksets"][0]["linksetdbs"][0]["links"]
        return f"PMC{links[0]}"
    except (KeyError, IndexError):
        return None


def download_from_pmc_oa(pmcid: str, out_dir: Path) -> Optional[Path]:
    r = requests.get(PMC_OA_BASE, params={"id": pmcid}, timeout=30)
    if r.status_code != 200:
        return None
    import re
    m = re.search(r'href="([^"]+\.tar\.gz)"', r.text)
    if not m:
        return None
    tgz_url = m.group(1).replace("ftp://", "https://")
    tgz_resp = requests.get(tgz_url, timeout=120)
    if tgz_resp.status_code != 200:
        return None
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
        tf.write(tgz_resp.content)
        tgz_path = tf.name
    try:
        with tarfile.open(tgz_path) as tar:
            pdf_members = [m for m in tar.getmembers() if m.name.lower().endswith(".pdf")]
            if not pdf_members:
                return None
            member = pdf_members[0]
            tar.extract(member, out_dir)
            return out_dir / member.name
    finally:
        Path(tgz_path).unlink(missing_ok=True)


def download_from_unpaywall(pmid: str, out_dir: Path) -> Optional[Path]:
    # Unpaywall is keyed on DOI; look up DOI from PubMed first.
    r = requests.get(
        f"{NCBI_BASE}/esummary.fcgi",
        params={"db": "pubmed", "id": pmid, "retmode": "json"},
        timeout=30,
    )
    r.raise_for_status()
    try:
        doi = None
        articleids = r.json()["result"][pmid]["articleids"]
        for aid in articleids:
            if aid.get("idtype") == "doi":
                doi = aid.get("value")
                break
        if not doi:
            return None
    except Exception:
        return None

    up = requests.get(f"https://api.unpaywall.org/v2/{doi}",
                       params={"email": UNPAYWALL_EMAIL}, timeout=30)
    if up.status_code != 200:
        return None
    data = up.json()
    best = data.get("best_oa_location") or {}
    pdf_url = best.get("url_for_pdf")
    if not pdf_url:
        return None

    pdf_resp = requests.get(pdf_url, timeout=120)
    if pdf_resp.status_code != 200:
        return None
    out_path = out_dir / f"{pmid}_1.pdf"
    out_path.write_bytes(pdf_resp.content)
    return out_path


def download_paper(pmid: str, out_dir: Path) -> Optional[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pmcid = pmid_to_pmcid(pmid)
    if pmcid:
        pdf = download_from_pmc_oa(pmcid, out_dir)
        if pdf:
            return pdf
    return download_from_unpaywall(pmid, out_dir)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid-file", required=False)
    ap.add_argument("--pmids", nargs="*")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    pmids: list[str] = []
    if args.pmid_file:
        pmids.extend(
            line.strip() for line in Path(args.pmid_file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    if args.pmids:
        pmids.extend(args.pmids)
    if args.limit:
        pmids = pmids[: args.limit]

    status = _load_status()
    out_dir = config.DOCINTEL_INPUT_DIR
    for pmid in pmids:
        if pmid in status and status[pmid].get("downloaded"):
            continue
        try:
            pdf = download_paper(pmid, out_dir)
            if pdf:
                status[pmid] = {"downloaded": True, "path": str(pdf)}
                print(f"[{pmid}] OK -> {pdf}")
            else:
                status[pmid] = {"downloaded": False, "error": "no source"}
                print(f"[{pmid}] NOT AVAILABLE")
        except Exception as exc:
            status[pmid] = {"downloaded": False, "error": str(exc)}
            print(f"[{pmid}] ERROR: {exc}")
        _save_status(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
