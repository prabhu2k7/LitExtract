"""Load Azure DI output JSON from blob storage for a given PMID."""
from __future__ import annotations
import json
from typing import Any

import config
from table_parser import parse_markdown_tables, format_tables_for_llm


def _blob_client():
    from azure.storage.blob import BlobServiceClient
    if not config.AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
    return BlobServiceClient.from_connection_string(
        config.AZURE_STORAGE_CONNECTION_STRING
    )


def _list_layout_blobs(pubmed_id: str) -> list[str]:
    svc = _blob_client()
    container = svc.get_container_client(config.OUTPUT_CONTAINER)
    matches: list[str] = []
    for blob in container.list_blobs():
        name = blob.name
        if pubmed_id in name and name.endswith(".layout.json"):
            matches.append(name)
    return sorted(matches)


def _download_json(blob_name: str) -> dict[str, Any]:
    svc = _blob_client()
    container = svc.get_container_client(config.OUTPUT_CONTAINER)
    blob = container.get_blob_client(blob_name)
    data = blob.download_blob().readall()
    return json.loads(data)


def _extract_content_and_tables(layout: dict) -> tuple[str, str]:
    """Pull content + markdown tables out of DI layout JSON."""
    content = layout.get("content") or ""
    tables_md: list[str] = []
    for t in layout.get("tables") or []:
        if isinstance(t, str):
            tables_md.append(t)
        elif isinstance(t, dict):
            md = t.get("markdown") or t.get("content") or ""
            if md:
                tables_md.append(md)
    return content, "\n\n".join(tables_md)


def load_document(pubmed_id: str) -> dict[str, Any]:
    """Return {pubmed_id, text_data, table_data, structured_tables, structured_tables_text}."""
    blob_names = _list_layout_blobs(pubmed_id)
    if not blob_names:
        raise FileNotFoundError(
            f"No .layout.json blobs for PMID {pubmed_id} in {config.OUTPUT_CONTAINER}"
        )

    texts: list[str] = []
    tables_md: list[str] = []
    for name in blob_names:
        layout = _download_json(name)
        c, t = _extract_content_and_tables(layout)
        if c:
            texts.append(c)
        if t:
            tables_md.append(t)

    full_text = "\n\n".join(texts)
    full_tables_md = "\n\n".join(tables_md)
    structured = parse_markdown_tables(full_tables_md)

    return {
        "pubmed_id": pubmed_id,
        "text_data": full_text,
        "table_data": full_tables_md,
        "structured_tables": structured,
        "structured_tables_text": format_tables_for_llm(structured),
        "source_blobs": blob_names,
    }
