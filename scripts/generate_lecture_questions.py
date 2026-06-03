#!/usr/bin/env python3
"""
Lecture material -> PMA-style question draft JSON.

This is the first-stage pipeline for the RISE/P:accine workflow:

1. Extract text from lecture material.
2. Build a PMA-style question-generation prompt.
3. Optionally call OpenAI or Gemini when an API key is available.
4. Save reviewable JSON under data_private/lecture/generated/.

Privacy rule:
- Raw lecture text and generated drafts stay under data_private/.
- The sample output printed to stdout is truncated and does not include full
  source text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - import error is handled by extraction
    fitz = None


PIPELINE_VERSION = "0.1.0"
DEFAULT_OUTPUT_DIR = Path("data_private/lecture/generated")
DEFAULT_EXTRACTED_DIR = Path("data_private/lecture/extracted")


PMA_STYLE_GUIDE = """
[PMA 풀이 스타일 목표]
- 문제는 5지 선다 객관식으로 작성한다.
- 단순 암기보다 임상 상황, 검사 소견, 치료/진단 의사결정을 묻는다.
- 해설은 PMA 풀이집처럼 "풀이 -> 정답 -> 오답 선지별 포인트 -> 출제 포인트" 흐름을 따른다.
- 정답 근거와 오답 배제 이유를 분리한다.
- 강의록에 근거가 부족한 내용은 만들지 말고 needs_review=true로 표시한다.
- 실제 평가에 바로 쓰는 문항이 아니라 교수 검수용 초안이다.
"""

EVIDENCE_POLICY = """
[근거자료 활용 정책]
- 강의록을 1차 근거로 사용한다.
- 추가 근거자료는 사용자가 로컬로 제공한 승인/라이선스 자료만 사용한다.
- AMBOSS, UpToDate, NEJM 등 유료/저작권 자료는 원문을 무단 수집하지 않는다.
- PubMed/PMC, 학회 가이드라인, 학교 승인 자료 등 사용 가능한 근거는 요약 근거와 출처명만 남긴다.
- 강의록과 근거자료가 충돌하면 needs_review=true로 표시하고 교수 검수를 요청한다.
- 최신 진료지침이 필요한 치료/검사 문항은 source_anchor 또는 evidence_refs에 근거를 남긴다.
"""


def check_gitignore() -> None:
    gi_path = Path(".gitignore")
    if not gi_path.exists():
        raise SystemExit("ERROR: .gitignore not found. Add data_private/ before running.")
    content = gi_path.read_text(encoding="utf-8", errors="ignore")
    if "data_private" not in content:
        raise SystemExit("ERROR: data_private/ is not ignored. Add it to .gitignore first.")


def clean_text(text: str) -> str:
    text = str(text or "").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path, include_page_markers: bool = True) -> str:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not available. Install PyMuPDF first.")
    doc = fitz.open(str(path))
    parts: list[str] = []
    for idx, page in enumerate(doc):
        text = page.get_text("text")
        if include_page_markers:
            parts.append(f"\n=== page {idx + 1} ===\n{text}")
        else:
            parts.append(text)
    doc.close()
    return clean_text("\n".join(parts))


def extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts: list[str] = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return clean_text("\n".join(parts))


def extract_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    parts: list[str] = []
    for idx, slide in enumerate(prs.slides, 1):
        slide_parts = [f"=== slide {idx} ==="]
        for shape in slide.shapes:
            text = getattr(shape, "text", "")
            if text and text.strip():
                slide_parts.append(text.strip())
        if len(slide_parts) > 1:
            parts.append("\n".join(slide_parts))
    return clean_text("\n\n".join(parts))


def extract_hwp(path: Path) -> str:
    hwp5txt = shutil.which("hwp5txt")
    if not hwp5txt:
        raise RuntimeError("hwp5txt not found. Install pyhwp or convert HWP to PDF/DOCX first.")
    result = subprocess.run(
        [hwp5txt, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return clean_text(result.stdout)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext == ".pptx":
        return extract_pptx(path)
    if ext in {".txt", ".md"}:
        return clean_text(path.read_text(encoding="utf-8", errors="ignore"))
    if ext == ".hwp":
        return extract_hwp(path)
    raise ValueError(f"Unsupported file type: {ext}")


def slugify(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", str(value or "")).strip("_")
    return text[:120] or "lecture"


def truncate_for_prompt(text: str, max_chars: int) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[TRUNCATED]"


def collect_evidence_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for value in args.evidence or []:
        path = Path(value).expanduser()
        if path.exists() and path.is_file():
            paths.append(path)
    for value in args.evidence_dir or []:
        directory = Path(value).expanduser()
        if not directory.exists() or not directory.is_dir():
            continue
        for pattern in ("*.pdf", "*.docx", "*.pptx", "*.txt", "*.md", "*.hwp"):
            paths.extend(sorted(directory.glob(pattern)))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def build_evidence_context(paths: list[Path], *, max_chars_per_file: int, max_total_chars: int) -> str:
    if not paths:
        return ""
    chunks: list[str] = []
    total = 0
    for path in paths:
        try:
            text = truncate_for_prompt(extract_text(path), max_chars=max_chars_per_file)
        except Exception as exc:
            text = f"[근거자료 추출 실패: {exc}]"
        block = f"\n--- evidence: {path.name} ---\n{text}".strip()
        remaining = max_total_chars - total
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining].rstrip() + "\n[TRUNCATED]"
        chunks.append(block)
        total += len(block)
    return "\n\n".join(chunks).strip()


def build_generation_prompt(
    lecture_text: str,
    *,
    source_name: str,
    subject: str,
    unit: str,
    num_questions: int,
    difficulty: str,
    max_chars: int,
    evidence_context: str = "",
) -> str:
    source_excerpt = truncate_for_prompt(lecture_text, max_chars=max_chars)
    evidence_section = ""
    if evidence_context:
        evidence_section = f"""

[추가 근거자료]
아래 근거자료는 사용자가 제공한 승인/라이선스 자료입니다. 강의록 내용을 보강하는 범위에서만 사용하세요.
{evidence_context}
"""
    return f"""
당신은 의과대학 임상 교수이자 문항 검수자입니다.
아래 강의록을 근거로 PMA/임상의학종합평가 스타일의 교수 검수용 객관식 문항 초안을 생성하세요.

{PMA_STYLE_GUIDE}
{EVIDENCE_POLICY}

[자료 메타데이터]
- source_name: {source_name}
- subject: {subject}
- unit: {unit}
- requested_questions: {num_questions}
- target_difficulty: {difficulty}

[출제 지침]
1. 정확히 {num_questions}개 문항을 생성한다.
2. 각 문항은 임상 증례형을 우선하되, 강의록이 기초/개념 중심이면 개념 적용형으로 작성한다.
3. 선지는 정확히 5개이며 서로 겹치지 않게 작성한다.
4. answer는 1~5 숫자다.
5. explanation은 학생이 바로 복습할 수 있게 작성한다.
6. pma_solution 필드에는 구조화된 풀이 정보를 넣는다.
7. source_anchor에는 강의록에서 근거가 되는 짧은 요약만 적고, 원문 긴 복사는 피한다.
8. 근거가 약하거나 AI 추론이 큰 문항은 needs_review=true로 표시한다.

[반드시 유효한 JSON 배열만 출력]
[
  {{
    "problem": "증례 기반 문항 본문",
    "options": ["선지1", "선지2", "선지3", "선지4", "선지5"],
    "answer": 1,
    "explanation": "풀이: ...\\n정답: ① ...\\n오답 포인트: ② ... ③ ... ④ ... ⑤ ...\\n출제 포인트: ...",
    "pma_solution": {{
      "reasoning_summary": "핵심 풀이 흐름",
      "correct_reason": "정답 근거",
      "choice_explanations": {{
        "1": "1번 선지 해설",
        "2": "2번 선지 해설",
        "3": "3번 선지 해설",
        "4": "4번 선지 해설",
        "5": "5번 선지 해설"
      }},
      "high_yield_point": "반드시 기억할 포인트",
      "trap": "오답을 유도하는 함정",
      "source_anchor": "강의록 근거 요약"
    }},
    "evidence_refs": [
      {{"source": "강의록 또는 근거자료명", "basis": "근거 요약", "source_type": "lecture|guideline|journal|textbook|database|other"}}
    ],
    "evidence_tier": "lecture_only|lecture_plus_guideline|lecture_plus_journal|needs_external_review",
    "subject": "{subject}",
    "unit": "{unit}",
    "difficulty": "{difficulty}",
    "question_type": "clinical_case",
    "cognitive_level": "L3 Clinical Reasoning",
    "needs_review": true
  }}
]

[강의록]
{source_excerpt}
{evidence_section}
""".strip()


def extract_json_payload(text: str) -> Any:
    stripped = str(text or "").strip()
    if not stripped:
        raise ValueError("empty model response")
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(stripped):
        if ch not in "[{":
            continue
        try:
            obj, _ = decoder.raw_decode(stripped[idx:])
            return obj
        except Exception:
            continue
    raise ValueError("model response did not contain valid JSON")


def normalize_choice_explanations(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {str(i): "" for i in range(1, 6)}
    out: dict[str, str] = {}
    for i in range(1, 6):
        out[str(i)] = str(value.get(str(i)) or value.get(i) or "").strip()
    return out


def normalize_data_table(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    if isinstance(value, dict):
        columns_raw = value.get("columns") or []
        rows_raw = value.get("rows") or []
        columns = [str(item).strip() for item in columns_raw if str(item).strip()] if isinstance(columns_raw, list) else []
        rows: list[list[str]] = []
        if isinstance(rows_raw, list):
            for row in rows_raw:
                if isinstance(row, list):
                    cells = [str(cell).strip() for cell in row]
                elif isinstance(row, dict):
                    cells = [str(row.get(column) or "").strip() for column in columns]
                else:
                    cells = [str(row).strip()]
                if any(cells):
                    rows.append(cells)
        if columns and rows:
            return {
                "title": str(value.get("title") or "").strip(),
                "columns": columns,
                "rows": rows[:12],
            }
    if isinstance(value, list):
        rows = [[str(cell).strip() for cell in row] for row in value if isinstance(row, list)]
        rows = [row for row in rows if any(row)]
        if len(rows) >= 2:
            return {
                "title": "",
                "columns": rows[0],
                "rows": rows[1:13],
            }
    return None


def normalize_question(
    item: dict[str, Any],
    *,
    idx: int,
    source_name: str,
    subject: str,
    unit: str,
) -> dict[str, Any]:
    problem = str(item.get("problem") or item.get("stem") or item.get("question") or "").strip()
    options_raw = item.get("options") or item.get("choices") or []
    if isinstance(options_raw, dict):
        options = [str(options_raw.get(str(i)) or options_raw.get(i) or "").strip() for i in range(1, 6)]
    else:
        options = [str(opt).strip() for opt in list(options_raw)]
    options = [opt for opt in options if opt]
    while len(options) < 5:
        options.append(f"검수 필요 보기 {len(options) + 1}")
    options = options[:5]

    answer = item.get("answer")
    invalid_answer = False
    try:
        answer_num = int(answer)
    except Exception:
        invalid_answer = True
        answer_num = 1
    if answer_num < 1 or answer_num > 5:
        invalid_answer = True
        answer_num = 1

    pma_solution = item.get("pma_solution") if isinstance(item.get("pma_solution"), dict) else {}
    pma_solution = {
        "reasoning_summary": str(pma_solution.get("reasoning_summary") or "").strip(),
        "correct_reason": str(pma_solution.get("correct_reason") or "").strip(),
        "choice_explanations": normalize_choice_explanations(pma_solution.get("choice_explanations")),
        "high_yield_point": str(pma_solution.get("high_yield_point") or "").strip(),
        "trap": str(pma_solution.get("trap") or "").strip(),
        "source_anchor": str(pma_solution.get("source_anchor") or "").strip(),
    }
    evidence_refs = item.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    normalized_refs: list[dict[str, str]] = []
    allowed_source_types = {"lecture", "guideline", "journal", "textbook", "database", "other"}
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        source_type = str(ref.get("source_type") or "other").strip()
        if source_type not in allowed_source_types:
            source_type = "other"
        normalized_refs.append(
            {
                "source": str(ref.get("source") or "").strip(),
                "basis": str(ref.get("basis") or "").strip(),
                "source_type": source_type,
            }
        )
    evidence_tier = str(item.get("evidence_tier") or "lecture_only").strip()
    if evidence_tier not in {
        "lecture_only",
        "lecture_plus_guideline",
        "lecture_plus_journal",
        "lecture_plus_textbook",
        "lecture_plus_database",
        "lecture_plus_mixed",
        "needs_external_review",
    }:
        evidence_tier = "needs_external_review"

    explanation = str(item.get("explanation") or "").strip()
    if not explanation:
        explanation = (
            f"풀이: {pma_solution['reasoning_summary']}\n"
            f"정답: {answer_num}번. {pma_solution['correct_reason']}\n"
            f"출제 포인트: {pma_solution['high_yield_point']}"
        ).strip()

    review_reasons: list[str] = []
    if not problem:
        review_reasons.append("empty_problem")
    if invalid_answer:
        review_reasons.append("invalid_answer")
    if len([opt for opt in options if not opt.startswith("검수 필요 보기")]) < 5:
        review_reasons.append("choice_count_lt_5")
    if not pma_solution["correct_reason"]:
        review_reasons.append("missing_correct_reason")
    if not pma_solution["source_anchor"]:
        review_reasons.append("missing_source_anchor")
    if bool(item.get("needs_review")):
        review_reasons.append("model_marked_needs_review")
    if evidence_tier == "needs_external_review":
        review_reasons.append("needs_external_evidence_review")
    data_table = normalize_data_table(item.get("data_table") or item.get("table"))
    if data_table and bool(item.get("needs_review")):
        review_reasons.append("table_value_review_needed")

    record = {
        "question_id": f"LECTURE_{slugify(Path(source_name).stem)}_Q{idx:03d}",
        "source_name": source_name,
        "source_type": "lecture_material",
        "subject": str(item.get("subject") or subject or "General").strip() or "General",
        "unit": str(item.get("unit") or unit or "미분류").strip() or "미분류",
        "problem": problem,
        "options": options,
        "answer": answer_num,
        "explanation": explanation,
        "pma_solution": pma_solution,
        "evidence_refs": normalized_refs,
        "evidence_tier": evidence_tier,
        "reference_notes": item.get("reference_notes", []),
        "difficulty": str(item.get("difficulty") or "").strip(),
        "question_type": str(item.get("question_type") or "clinical_case").strip(),
        "cognitive_level": str(item.get("cognitive_level") or "L3 Clinical Reasoning").strip(),
        "review_status": "draft",
        "needs_review": bool(review_reasons),
        "review_reasons": sorted(set(review_reasons)),
        "generation_mode": "lecture_high_yield_pma_style",
        "pipeline_version": PIPELINE_VERSION,
    }
    if data_table:
        record["data_table"] = data_table
    return record


def normalize_questions(payload: Any, *, source_name: str, subject: str, unit: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("questions") or payload.get("items") or [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON payload must be a list or object containing questions/items")
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(payload, 1):
        if isinstance(item, dict):
            out.append(normalize_question(item, idx=idx, source_name=source_name, subject=subject, unit=unit))
    return out


def generate_openai(prompt: str, *, model: str, temperature: float) -> str:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return only valid JSON. Do not include markdown fences."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def generate_gemini(prompt: str, *, model: str, temperature: float) -> str:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(model)
    response = gemini_model.generate_content(
        prompt,
        generation_config={"temperature": temperature, "top_p": 1.0},
    )
    return response.text or ""


def resolve_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "prompt-only"


def print_sample(records: list[dict[str, Any]], limit: int) -> None:
    if limit <= 0:
        return
    print(f"\nSAMPLE {min(limit, len(records))}/{len(records)}")
    for record in records[:limit]:
        preview = record.get("problem", "")[:80].replace("\n", " ")
        if len(record.get("problem", "")) > 80:
            preview += "..."
        print(
            f"- {record.get('question_id')}: answer={record.get('answer')} "
            f"needs_review={record.get('needs_review')} stem={preview}"
        )


def process_file(path: Path, args: argparse.Namespace) -> Path:
    text = extract_text(path)
    if not text:
        raise RuntimeError(f"no text extracted from {path}")

    args.extracted_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(path.stem)
    extracted_path = args.extracted_dir / f"{slug}.txt"
    prompt_path = args.output_dir / f"{slug}.prompt.txt"
    output_path = args.output_dir / f"{slug}.questions.json"
    raw_response_path = args.output_dir / f"{slug}.model_response.txt"

    extracted_path.write_text(text, encoding="utf-8")
    evidence_paths = collect_evidence_paths(args)
    evidence_context = build_evidence_context(
        evidence_paths,
        max_chars_per_file=args.evidence_max_chars_per_file,
        max_total_chars=args.evidence_max_total_chars,
    )
    prompt = build_generation_prompt(
        text,
        source_name=path.name,
        subject=args.subject,
        unit=args.unit,
        num_questions=args.num_questions,
        difficulty=args.difficulty,
        max_chars=args.max_chars,
        evidence_context=evidence_context,
    )
    prompt_path.write_text(prompt, encoding="utf-8")

    provider = resolve_provider(args.provider)
    if provider == "prompt-only":
        packet = {
            "source_name": path.name,
            "provider": provider,
            "status": "prompt_ready",
            "prompt_path": str(prompt_path),
            "extracted_text_path": str(extracted_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": PIPELINE_VERSION,
        }
        output_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[prompt-only] {path.name} -> {prompt_path}", file=sys.stderr)
        if getattr(args, "validate", False):
            validate_output(output_path)
        return output_path

    model = args.openai_model if provider == "openai" else args.gemini_model
    if provider == "openai":
        raw_response = generate_openai(prompt, model=model, temperature=args.temperature)
    elif provider == "gemini":
        raw_response = generate_gemini(prompt, model=model, temperature=args.temperature)
    else:
        raise RuntimeError(f"Unsupported provider: {provider}")

    raw_response_path.write_text(raw_response, encoding="utf-8")
    payload = extract_json_payload(raw_response)
    records = normalize_questions(payload, source_name=path.name, subject=args.subject, unit=args.unit)
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print_sample(records, args.sample)
    print(f"[generated] {path.name} -> {output_path}", file=sys.stderr)
    if getattr(args, "validate", False):
        validate_output(output_path)
    return output_path


def validate_output(output_path: Path) -> None:
    """Validate output_path JSON against lecture_question.schema.json.

    - Skips prompt_ready packets (dict with status == "prompt_ready").
    - Raises jsonschema.ValidationError on schema failure.
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        print("[validate] jsonschema not installed — skipping validation.", file=sys.stderr)
        return

    schema_path = Path(__file__).parent.parent / "schemas" / "lecture_question.schema.json"
    if not schema_path.exists():
        print(f"[validate] schema not found: {schema_path}", file=sys.stderr)
        return

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(output_path.read_text(encoding="utf-8"))

    if isinstance(data, dict) and data.get("status") == "prompt_ready":
        print(
            f"[validate] skip — prompt_ready packet (no questions generated yet): {output_path.name}",
            file=sys.stderr,
        )
        return

    jsonschema.validate(instance=data, schema=schema)
    count = len(data) if isinstance(data, list) else 1
    print(f"[validate] OK — {count} records passed schema: {output_path.name}", file=sys.stderr)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate PMA-style MCQ draft JSON from lecture files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="+", help="Lecture file paths: pdf/docx/pptx/txt/md/hwp")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    parser.add_argument("--provider", choices=["auto", "prompt-only", "openai", "gemini"], default="auto")
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--gemini-model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--num-questions", type=int, default=5)
    parser.add_argument("--subject", default="General")
    parser.add_argument("--unit", default="미분류")
    parser.add_argument("--difficulty", default="보통")
    parser.add_argument("--max-chars", type=int, default=30000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--sample", type=int, default=5)
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Approved local evidence file to use as supplemental context. Repeatable.",
    )
    parser.add_argument(
        "--evidence-dir",
        action="append",
        default=[],
        help="Directory containing approved local evidence files. Repeatable.",
    )
    parser.add_argument("--evidence-max-chars-per-file", type=int, default=8000)
    parser.add_argument("--evidence-max-total-chars", type=int, default=20000)
    parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help=(
            "After generation, validate the output JSON against "
            "schemas/lecture_question.schema.json. "
            "prompt_ready packets are skipped automatically."
        ),
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    check_gitignore()
    for raw in args.inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            raise SystemExit(f"Input not found: {path}")
        process_file(path, args)


if __name__ == "__main__":
    main()
