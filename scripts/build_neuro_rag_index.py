#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.rag_library import build_rag_index, rag_index_path, search_rag_evidence


COURSE_ID = "neuro_special_senses"
DEFAULT_SOURCE_CANDIDATES = [
    ROOT / "data_private" / "rag_sources" / "neuro_special_senses" / "20_PART 13 Neurologic Disorders.pdf",
    ROOT / "data_private" / "rag_sources" / "neuro_special_senses" / "harrison_neurologic_disorders.pdf",
]


def existing_default_sources() -> list[Path]:
    env_sources = os.environ.get("PACCINE_RAG_SOURCES", "")
    if env_sources.strip():
        return [Path(item).expanduser() for item in env_sources.split(os.pathsep) if item.strip()]
    course_dir = ROOT / "data_private" / "rag_sources" / "neuro_special_senses"
    discovered = sorted(course_dir.glob("*.pdf")) if course_dir.exists() else []
    return [path for path in DEFAULT_SOURCE_CANDIDATES if path.exists()] + [
        path for path in discovered if path not in DEFAULT_SOURCE_CANDIDATES
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local neurology/special-senses RAG index for P:accine.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help=(
            "PDF/TXT/MD source path. Can be passed multiple times. "
            "If omitted, uses PACCINE_RAG_SOURCES or data_private/rag_sources/neuro_special_senses/."
        ),
    )
    parser.add_argument("--course-id", default=COURSE_ID)
    parser.add_argument(
        "--output",
        default="",
        help="Optional output index path. Defaults to data_private/rag/<course-id>/rag_index.json.",
    )
    parser.add_argument("--chunk-size", type=int, default=1600)
    parser.add_argument("--overlap", type=int, default=180)
    parser.add_argument(
        "--sample-query",
        action="append",
        default=["ulnar nerve lesion", "myelomeningocele folic acid", "corticospinal tract"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_paths = [Path(item) for item in args.source] if args.source else existing_default_sources()
    if not source_paths:
        raise SystemExit(
            "근거자료를 찾지 못했습니다. --source 로 Harrison/정리족 PDF 경로를 직접 지정해주세요."
        )
    output_path = Path(args.output) if args.output else rag_index_path(args.course_id)
    index = build_rag_index(
        source_paths,
        course_id=args.course_id,
        output_path=output_path,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(f"[DONE] index: {output_path}")
    print(
        "[STATS]",
        f"documents={index['stats']['document_count']}",
        f"chunks={index['stats']['chunk_count']}",
        f"terms={index['stats']['term_count']}",
    )
    for query in args.sample_query[:5]:
        try:
            result = search_rag_evidence(query, course_id=args.course_id, limit=2, index_path=output_path)
        except Exception as exc:
            print(f"[SAMPLE] {query}: failed ({exc})")
            continue
        titles = [
            f"{item['title']} p.{item['page_start']} score={item['score']}"
            for item in result["results"]
        ]
        print(f"[SAMPLE] {query}: " + " | ".join(titles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
