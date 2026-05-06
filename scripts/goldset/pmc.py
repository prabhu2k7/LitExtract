"""PMC (PubMed Central) Open Access lookup + PDF downloader.

Two NCBI services we use:

  1. ID Converter — translates PMID -> PMCID
     https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=...&format=json

  2. OA service — tells us if a paper is in the Open Access subset and gives
     direct download URLs
     https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMCxxx

Only OA papers can be downloaded for free + redistributed within license terms.
"""
from __future__ import annotations
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import requests

NCBI_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
NCBI_OA = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"

# Europe PMC's `?pdf=render` returns the rendered PDF for any PMC OA paper.
# Verified working in 2026-05; NCBI's `pmc.ncbi.nlm.nih.gov/.../pdf/` now
# returns an HTML interstitial instead of the PDF, so EPMC is primary.
EPMC_PDF_RENDER = "https://europepmc.org/articles/{pmcid}?pdf=render"
PMC_PDF_WEB = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"

# Be polite: NCBI rate-limits to 3 req/s without API key, 10 req/s with.
NCBI_DELAY_S = 0.4

USER_AGENT = "Mozilla/5.0 LitExtract-goldset/0.4 (open-source; honours NCBI rate limits)"


@dataclass
class PmcRecord:
    pmid: str
    pmcid: str           # 'PMC1234567'
    is_oa: bool
    pdf_url: Optional[str] = None
    license: Optional[str] = None    # CC-BY, CC-BY-NC, etc.
    error: Optional[str] = None


def pmid_to_pmcid(pmids: list[str]) -> dict[str, Optional[str]]:
    """Batch-resolve a list of PMIDs to PMCIDs via NCBI ID converter.

    NCBI accepts up to ~200 IDs per call. Returns a dict mapping
    pmid -> 'PMC1234567' (or None if no PMCID).
    """
    out: dict[str, Optional[str]] = {p: None for p in pmids}
    # Chunk to be safe
    for i in range(0, len(pmids), 100):
        chunk = pmids[i : i + 100]
        params = {
            "ids": ",".join(chunk),
            "format": "json",
            "tool": "litextract-goldset",
            "email": "noreply@litextract.local",
        }
        r = requests.get(NCBI_IDCONV, params=params, timeout=30,
                         headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            pmid = str(rec.get("pmid", "")).strip()
            pmcid = str(rec.get("pmcid", "")).strip()
            if pmid in out and pmcid:
                out[pmid] = pmcid
        time.sleep(NCBI_DELAY_S)
    return out


def check_oa(pmcid: str) -> PmcRecord:
    """Query NCBI OA service: is the paper in the Open Access subset, and
    what's the canonical PDF URL?

    Response is XML. Parse for <link format="pdf" href="..."/> and the
    license attribute on <record>.
    """
    pmid_placeholder = ""  # filled by caller
    if not pmcid:
        return PmcRecord(pmid=pmid_placeholder, pmcid="", is_oa=False, error="no_pmcid")
    params = {"id": pmcid}
    try:
        r = requests.get(NCBI_OA, params=params, timeout=30,
                         headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        root = ET.fromstring(r.text)
        rec = root.find(".//record")
        if rec is None:
            err = root.find(".//error")
            msg = err.text if err is not None else "no_record"
            return PmcRecord(pmid=pmid_placeholder, pmcid=pmcid, is_oa=False, error=msg)
        license_ = rec.attrib.get("license")
        pdf_link = rec.find("./link[@format='pdf']")
        if pdf_link is None:
            return PmcRecord(pmid=pmid_placeholder, pmcid=pmcid, is_oa=True,
                             license=license_, error="no_pdf_format")
        pdf_url = pdf_link.attrib.get("href")
        # FTP URLs sometimes appear; normalise to https
        if pdf_url and pdf_url.startswith("ftp://"):
            pdf_url = "https://" + pdf_url[len("ftp://"):]
        return PmcRecord(pmid=pmid_placeholder, pmcid=pmcid, is_oa=True,
                         pdf_url=pdf_url, license=license_)
    except requests.HTTPError as e:
        return PmcRecord(pmid=pmid_placeholder, pmcid=pmcid, is_oa=False,
                         error=f"http_{e.response.status_code if e.response else '?'}")
    except Exception as e:
        return PmcRecord(pmid=pmid_placeholder, pmcid=pmcid, is_oa=False,
                         error=type(e).__name__)


def download_pdf(rec: PmcRecord, dest_dir: Path) -> Optional[Path]:
    """Download the PDF for a PmcRecord. Returns the Path on success.

    Tries Europe PMC's `?pdf=render` URL first (most reliable in 2026), then
    the NCBI OA-service-supplied URL, then the legacy PMC web URL as a final
    fallback. Validates that the response actually starts with `%PDF` before
    accepting it — many "200 OK" responses on these services serve HTML
    interstitials.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{rec.pmid}.pdf"
    if out.exists() and out.stat().st_size > 1024:
        return out

    candidates: list[str] = []
    # Primary: Europe PMC's render endpoint — verified working for PMC OA papers
    if rec.pmcid:
        candidates.append(EPMC_PDF_RENDER.format(pmcid=rec.pmcid))
    # Secondary: whatever NCBI's OA service handed back (FTP rewritten earlier)
    if rec.pdf_url and rec.pdf_url not in candidates:
        candidates.append(rec.pdf_url)
    # Tertiary: legacy NCBI web URL (often returns HTML in 2026, but worth one try)
    if rec.pmcid:
        candidates.append(PMC_PDF_WEB.format(pmcid=rec.pmcid))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }

    last_err: Optional[str] = None
    for url in candidates:
        try:
            r = requests.get(url, timeout=60, allow_redirects=True, headers=headers)
            r.raise_for_status()
            body = r.content
            if not body or len(body) < 1024:
                last_err = f"too_small({len(body)}b @ {url[:50]})"
                continue
            if not body.startswith(b"%PDF"):
                ct = r.headers.get("Content-Type", "")
                last_err = f"not_pdf(ct={ct[:30]} @ {url[:50]})"
                continue
            out.write_bytes(body)
            time.sleep(NCBI_DELAY_S)
            return out
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:50]} @ {url[:50]}"
            continue

    rec.error = last_err or "download_failed"
    return None
