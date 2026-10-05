#!/usr/bin/env python3
"""Search PubMed metadata for P:accine faculty review.

This harness stores citation metadata only by default. It is meant to suggest
reference candidates for faculty review, not to generate clinical advice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TOOL = "PaccineEvidenceHarness"
DEFAULT_EMAIL = ""   # NCBI_EMAIL 환경변수로 지정


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9가-힣]+", "_", value).strip("_").lower()
    if not slug:
        slug = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return slug[:80]


def _request_json(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(f"{EUTILS_BASE}/{endpoint}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _base_params() -> dict[str, str]:
    params = {
        "tool": os.getenv("NCBI_TOOL", DEFAULT_TOOL),
        "email": os.getenv("NCBI_EMAIL", DEFAULT_EMAIL),
        "retmode": "json",
    }
    api_key = os.getenv("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def search_pubmed(query: str, *, limit: int, sort: str, reldate: int | None) -> list[str]:
    params: dict[str, Any] = {
        **_base_params(),
        "db": "pubmed",
        "term": query,
        "retmax": max(1, min(limit, 100)),
        "sort": sort,
    }
    if reldate:
        params["reldate"] = reldate
        params["datetype"] = "pdat"

    data = _request_json("esearch.fcgi", params)
    return data.get("esearchresult", {}).get("idlist", [])


def summarize_pubmed(pmids: list[str]) -> list[dict[str, Any]]:
    if not pmids:
        return []

    params = {
        **_base_params(),
        "db": "pubmed",
        "id": ",".join(pmids),
    }
    data = _request_json("esummary.fcgi", params)
    result = data.get("result", {})
    rows: list[dict[str, Any]] = []

    for pmid in result.get("uids", []):
        item = result.get(pmid, {})
        article_ids = item.get("articleids") or []
        doi = ""
        pmcid = ""
        for article_id in article_ids:
            id_type = article_id.get("idtype")
            if id_type == "doi":
                doi = article_id.get("value", "")
            elif id_type == "pmc":
                pmcid = article_id.get("value", "")

        authors = [
            author.get("name", "")
            for author in item.get("authors", [])[:5]
            if author.get("name")
        ]
        pubdate = item.get("pubdate", "")
        year_match = re.search(r"(19|20)\d{2}", pubdate)
        year = year_match.group(0) if year_match else ""

        rows.append({
            "source_type": "pubmed",
            "source_id": pmid,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "title": item.get("title", ""),
            "journal_or_source": item.get("source", ""),
            "publication_year": year,
            "publication_date": pubdate,
            "authors": authors,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "evidence_role": "candidate",
            "review_status": "candidate",
            "student_visible": False,
        })

    return rows


def build_result(query: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "query": query,
        "provider": "pubmed",
        "created_at": now,
        "usage_note": (
            "Metadata-only reference candidates for faculty review. "
            "Do not treat search results as verified clinical recommendations."
        ),
        "references": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search PubMed and save metadata-only reference candidates."
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--sort",
        default="relevance",
        choices=["relevance", "pub_date", "Author", "JournalName"],
    )
    parser.add_argument(
        "--reldate",
        type=int,
        help="Limit results to items published within the last N days.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data_private/evidence_search"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pmids = search_pubmed(
        args.query,
        limit=args.limit,
        sort=args.sort,
        reldate=args.reldate,
    )
    time.sleep(0.34)
    rows = summarize_pubmed(pmids)
    result = build_result(args.query, rows)

    output_path = args.output_dir / f"pubmed_{_slugify(args.query)}.json"
    if not args.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "query": args.query,
        "pmid_count": len(pmids),
        "reference_count": len(rows),
        "output_path": str(output_path),
        "written": not args.dry_run,
        "preview": rows[:3],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"pubmed_evidence_harness error: {exc}", file=sys.stderr)
        raise SystemExit(1)
