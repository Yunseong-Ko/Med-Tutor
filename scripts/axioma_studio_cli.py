from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.lecture_studio import (
    GENERATED_DIR,
    SavedUpload,
    extract_saved_upload,
    extract_visual_candidates,
    generate_studio_questions,
    slugify,
)


def make_upload(path: Path, kind: str) -> SavedUpload:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"Input not found: {resolved}")
    return SavedUpload(path=resolved, original_name=resolved.name, kind=kind)


def make_uploads(paths: Iterable[str], kind: str) -> list[SavedUpload]:
    return [make_upload(Path(path), kind) for path in paths]


def command_image_candidates(args: argparse.Namespace) -> None:
    lecture = make_upload(Path(args.lecture), "lecture")
    text = extract_saved_upload(lecture)
    source_slug = f"cli_{slugify(lecture.path.stem)}"
    candidates = extract_visual_candidates(lecture, source_slug, text, max_pages=args.max_pages)
    ranked = sorted(candidates, key=lambda item: item.get("visual_priority", 0), reverse=True)

    print(f"source: {lecture.path}")
    print(f"visual_candidates: {len(candidates)}")
    for candidate in ranked[: args.limit]:
        preview = str(candidate.get("text_preview") or "").replace("\n", " ")[:120]
        print(
            "- "
            f"{candidate.get('id')} | {candidate.get('locator_label')} | "
            f"priority={candidate.get('visual_priority')} | {candidate.get('url')} | {preview}"
        )


def command_generate(args: argparse.Namespace) -> None:
    lecture = make_upload(Path(args.lecture), "lecture")
    result = generate_studio_questions(
        lecture,
        subject=args.subject,
        unit=args.unit,
        num_questions=args.num_questions,
        difficulty=args.difficulty,
        question_type=args.question_type,
        reference_policy=args.reference_policy,
        image_policy=args.image_policy,
        provider=args.provider,
        model=args.model,
        style_uploads=make_uploads(args.style, "style"),
        evidence_uploads=make_uploads(args.evidence, "evidence"),
        image_uploads=make_uploads(args.image, "image"),
    )

    print(json.dumps({
        "status": result.get("status"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "question_count": result.get("question_count"),
        "output": result.get("paths", {}).get("output"),
        "prompt": result.get("paths", {}).get("prompt"),
        "image_candidate_count": result.get("context", {}).get("image_candidate_count"),
    }, ensure_ascii=False, indent=2))

    for item in result.get("sample", [])[: args.sample]:
        image_refs = item.get("image_refs") or []
        print()
        print(f"[{item.get('question_id')}] answer={item.get('answer')} review={item.get('needs_review')}")
        print(str(item.get("problem") or "")[:220].replace("\n", " "))
        for image in image_refs:
            print(
                f"  image: {image.get('locator_label')} "
                f"priority={image.get('visual_priority')} confidence={image.get('match_confidence')} "
                f"url={image.get('url')}"
            )


def command_latest(args: argparse.Namespace) -> None:
    files = sorted(GENERATED_DIR.glob("*.questions.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files[: args.limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, list):
            status = "generated"
            count = len(payload)
            image_count = sum(1 for item in payload if item.get("image_refs"))
        elif isinstance(payload, dict):
            status = payload.get("status")
            count = payload.get("question_count", 0)
            image_count = sum(1 for item in payload.get("sample", []) if item.get("image_refs"))
        else:
            status = "unknown"
            count = "?"
            image_count = "?"
        print(f"{path} | status={status} | questions={count} | image_refs={image_count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local CLI for Axioma Studio generation/debug tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    image_parser = subparsers.add_parser("image-candidates", help="Extract and rank visual candidates from a lecture file.")
    image_parser.add_argument("lecture")
    image_parser.add_argument("--max-pages", type=int, default=40)
    image_parser.add_argument("--limit", type=int, default=12)
    image_parser.set_defaults(func=command_image_candidates)

    generate_parser = subparsers.add_parser("generate", help="Generate question drafts from a lecture file.")
    generate_parser.add_argument("lecture")
    generate_parser.add_argument("--subject", default="General")
    generate_parser.add_argument("--unit", default="미분류")
    generate_parser.add_argument("--num-questions", type=int, default=2)
    generate_parser.add_argument("--difficulty", default="보통")
    generate_parser.add_argument(
        "--question-type",
        choices=["clinical_case", "image_based", "basic_concept", "mechanism", "diagnostic", "management", "mixed"],
        default="clinical_case",
    )
    generate_parser.add_argument("--reference-policy", choices=["local_open", "uploaded_only"], default="local_open")
    generate_parser.add_argument(
        "--image-policy",
        choices=["none", "clinical_visuals", "allow_slide_fallback"],
        default="none",
    )
    generate_parser.add_argument(
        "--provider",
        choices=["auto", "claude-cli", "anthropic", "openai", "gemini", "prompt-only"],
        default="auto",
    )
    generate_parser.add_argument("--model", default="auto")
    generate_parser.add_argument("--style", action="append", default=[])
    generate_parser.add_argument("--evidence", action="append", default=[])
    generate_parser.add_argument("--image", action="append", default=[])
    generate_parser.add_argument("--sample", type=int, default=5)
    generate_parser.set_defaults(func=command_generate)

    latest_parser = subparsers.add_parser("latest", help="Show recent generated question files.")
    latest_parser.add_argument("--limit", type=int, default=10)
    latest_parser.set_defaults(func=command_latest)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
