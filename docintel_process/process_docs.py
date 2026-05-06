"""Upload PDFs -> Azure Blob, run Azure DI, save layout JSON back to blob."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import config

PROCESSED_FILE = config.PROJECT_ROOT / "docintel_process" / "processed.json"


def _load_processed() -> dict:
    if PROCESSED_FILE.exists():
        try:
            return json.loads(PROCESSED_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_processed(d: dict) -> None:
    PROCESSED_FILE.write_text(json.dumps(d, indent=2))


def _blob_service():
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(
        config.AZURE_STORAGE_CONNECTION_STRING
    )


def _di_client():
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    return DocumentIntelligenceClient(
        endpoint=config.DOCUMENTINTELLIGENCE_ENDPOINT,
        credential=AzureKeyCredential(config.DOCUMENTINTELLIGENCE_API_KEY),
    )


def upload_pdf(pdf_path: Path) -> str:
    svc = _blob_service()
    container = svc.get_container_client(config.INPUT_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass
    blob_name = pdf_path.name
    with pdf_path.open("rb") as f:
        container.upload_blob(blob_name, f, overwrite=True)
    return blob_name


def run_di(pdf_path: Path) -> dict:
    client = _di_client()
    with pdf_path.open("rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            analyze_request=f,
            content_type="application/octet-stream",
        )
    result = poller.result()
    return result.as_dict() if hasattr(result, "as_dict") else dict(result)


def save_layout(pubmed_id: str, layout: dict) -> str:
    svc = _blob_service()
    container = svc.get_container_client(config.OUTPUT_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass
    blob_name = f"{pubmed_id}.layout.json"
    container.upload_blob(blob_name, json.dumps(layout), overwrite=True)
    return blob_name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--pmid-file", required=False)
    args = ap.parse_args()

    processed = _load_processed()
    pdfs = sorted(config.DOCINTEL_INPUT_DIR.glob("*.pdf"))

    whitelist: set[str] | None = None
    if args.pmid_file:
        whitelist = {
            line.strip() for line in Path(args.pmid_file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }

    for pdf in pdfs:
        pmid = pdf.stem.split("_")[0]
        if whitelist and pmid not in whitelist:
            continue
        if not args.force and processed.get(pmid, {}).get("done"):
            continue
        try:
            upload_pdf(pdf)
            layout = run_di(pdf)
            save_layout(pmid, layout)
            processed[pmid] = {"done": True, "pdf": pdf.name}
            print(f"[{pmid}] processed -> {pmid}.layout.json")
        except Exception as exc:
            processed[pmid] = {"done": False, "error": str(exc)}
            print(f"[{pmid}] ERROR: {exc}")
        _save_processed(processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
