#!/usr/bin/env python3
"""
근거 점프 (Evidence Jump) — PoC Script
Harrison's Part 4 (Oncology and Hematology) scope only.

Displayed output for each question (output contract):
  (1) 근거 해설  — newly-written rationale (not copied from the textbook)
  (2) 정확한 위치 — Harrison chapter + printed page
  (3) 열람 링크   — AccessMedicine deep-link (PNU library) + open-source fallback

The verbatim OCR quote is extracted internally for future LLM use but is NOT
displayed — OCR artifacts (table numbers, figure captions, hyphenated line
breaks) make it unsuitable for a faculty demo without LLM cleanup.

Guardrails enforced (internal):
  G1. Quote length cap kept in code for when LLM mode is active.
  G2. Location required before any quote can be attached.
  G3. Full passage never printed.
  G4. Harrison-only rule; other sources handled separately.

Privacy:
  - Harrison raw text stays inside data_private/ (gitignored, never git-tracked).
  - Raw chunk text used only as grounding input; never printed in full.
  - LLM mode: tries Anthropic API (ANTHROPIC_API_KEY) then OpenAI (OPENAI_API_KEY).
  - Default mode is template (no API key required).

Usage:
    python3 scripts/evidence_jump_poc.py                   # both questions, template mode
    python3 scripts/evidence_jump_poc.py --question-id demo1
    python3 scripts/evidence_jump_poc.py --question-id demo2
    python3 scripts/evidence_jump_poc.py --use-llm         # attempt LLM, fall back to template
    python3 scripts/evidence_jump_poc.py --list-questions
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.rag_library import (
    _load_rag_index_from_path,
    clean_text,
    expand_query_terms,
    _score_chunk,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARRISON_PART4_INDEX = ROOT / "data_private" / "rag" / "harrison_part4" / "rag_index.json"
COURSE_ID = "harrison_part4"

# G1: Quote guardrails
QUOTE_MAX_CHARS = 600
QUOTE_MAX_SENTENCES = 3

# G3: Maximum raw text we ever send to external LLM for a single chunk
GROUNDING_MAX_CHARS = 2400

# Retrieval
TOP_K = 5

# LLM settings
CLAUDE_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o-mini"
LLM_TIMEOUT = 60  # seconds

# ---------------------------------------------------------------------------
# Access link configuration
# ---------------------------------------------------------------------------
# PNU 의생명과학도서관 subscribes to AccessMedicine (Harrison's online).
# Paste the library's EZproxy / reverse-proxy prefix below when known, e.g.:
#   "https://ezproxy.pusan.ac.kr/login?url="
# Leave empty to use the plain accessmedicine URL (unauthenticated landing).
PNU_PROXY_PREFIX = ""

_AM_BASE = "https://accessmedicine.mhmedical.com"

# Per-topic Harrison 22e search URLs.  Section IDs are edition-specific and
# must not be carried over from the legacy book, so use topic search only.
_AM_TOPIC_URLS: dict[str, str] = {
    "demo1": f"{_AM_BASE}/SearchResults.aspx?q=Chronic%20Myeloid%20Leukemia&searchType=1&book=3541",
    "demo2": f"{_AM_BASE}/SearchResults.aspx?q=Iron%20Deficiency%20Anemia&searchType=1&book=3541",
}

# Open-access fallback URLs (MSD Manual Professional — verified 2026-07-01)
_OPEN_TOPIC_URLS: dict[str, str] = {
    "demo1": "https://www.msdmanuals.com/professional/hematology-and-oncology/leukemias/chronic-myeloid-leukemia-cml",
    "demo2": "https://www.msdmanuals.com/professional/hematology-and-oncology/anemias-caused-by-deficient-erythropoiesis/iron-deficiency-anemia",
}


def _build_access_links(question_id: str, topic: str) -> tuple[str, str]:
    """Return (am_link, open_link) for the given question.

    am_link  — AccessMedicine URL, prefixed with PNU_PROXY_PREFIX if set.
    open_link — StatPearls/NCBI Bookshelf open-access URL.
    """
    am_url = _AM_TOPIC_URLS.get(question_id, f"{_AM_BASE}/searchresults.aspx?q={topic.replace(' ', '+')}")
    if PNU_PROXY_PREFIX:
        am_link = PNU_PROXY_PREFIX + am_url
    else:
        am_link = am_url

    open_link = _OPEN_TOPIC_URLS.get(
        question_id,
        f"https://www.ncbi.nlm.nih.gov/books/NBK/",
    )
    return am_link, open_link

# ---------------------------------------------------------------------------
# Demo questions (synthesized representative heme-onc MCQs for PoC)
# ---------------------------------------------------------------------------

DEMO_QUESTIONS: dict[str, dict] = {
    "demo1": {
        "question_id": "demo1",
        "source": "synthesized_demo",
        "stem": (
            "A 55-year-old man presents with fatigue, pallor, and splenomegaly. "
            "His CBC shows WBC 85,000/mm3 with a differential showing predominantly mature "
            "granulocytes across all stages of maturation, hemoglobin 9.2 g/dL, and platelets "
            "650,000/mm3. The Philadelphia chromosome is detected on cytogenetics. "
            "Which of the following is the MOST appropriate first-line treatment?"
        ),
        "choices": {
            "A": "Hydroxyurea",
            "B": "Imatinib (tyrosine kinase inhibitor)",
            "C": "Allogeneic hematopoietic stem cell transplantation",
            "D": "Conventional chemotherapy (cytarabine + daunorubicin)",
            "E": "Watchful waiting",
        },
        "answer": "B",
        "answer_text": "Imatinib (tyrosine kinase inhibitor)",
        "topic": "Chronic Myeloid Leukemia (CML) — first-line treatment",
    },
    "demo2": {
        "question_id": "demo2",
        "source": "synthesized_demo",
        "stem": (
            "A 68-year-old woman is found to have hemoglobin 7.8 g/dL, MCV 72 fL, "
            "serum iron 35 ug/dL, TIBC 480 ug/dL, ferritin 6 ng/mL, and reticulocyte "
            "count 0.8%. She reports no melena but has had menorrhagia for the past year. "
            "Which single laboratory finding BEST confirms the diagnosis of iron deficiency anemia?"
        ),
        "choices": {
            "A": "Low serum iron",
            "B": "Low ferritin",
            "C": "Elevated TIBC",
            "D": "Microcytic hypochromic RBCs on peripheral smear",
            "E": "Low reticulocyte count",
        },
        "answer": "B",
        "answer_text": "Low ferritin",
        "topic": "Iron deficiency anemia — confirmatory laboratory finding",
    },
}


# ---------------------------------------------------------------------------
# Output contract dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvidenceJumpOutput:
    question_id: str
    answer: str
    answer_text: str
    topic: str
    # Displayed output contract
    rationale: str = ""
    location: str = ""
    access_link_am: str = ""       # AccessMedicine (PNU library)
    access_link_open: str = ""     # StatPearls / NCBI Bookshelf
    # Internal guardrail state (quote not displayed; kept for LLM mode)
    short_quote: str = ""
    quote_source_label: str = ""
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    quote_char_count: int = 0
    quote_sentence_count: int = 0
    retrieval_score: float = 0.0
    generation_method: str = "template"


# ---------------------------------------------------------------------------
# Retrieval — load harrison_part4 index with full chapter metadata
# ---------------------------------------------------------------------------


def _load_harrison_index() -> dict:
    if not HARRISON_PART4_INDEX.exists():
        raise FileNotFoundError(
            f"Harrison Part 4 RAG index not found: {HARRISON_PART4_INDEX}\n"
            "Run: python3 scripts/build_harrison_part4_index.py"
        )
    stat = HARRISON_PART4_INDEX.stat()
    return _load_rag_index_from_path(
        str(HARRISON_PART4_INDEX.resolve()), stat.st_mtime_ns, stat.st_size
    )


def retrieve_passages(query: str, *, top_k: int = TOP_K) -> list[dict]:
    """Return top-k chunks from harrison_part4 index with chapter/page metadata."""
    index = _load_harrison_index()
    # Use hematology_oncology synonyms for better term expansion
    query_terms = expand_query_terms(query, course_id="hematology_oncology")
    chunks = index.get("chunks", [])
    document_frequency = index.get("document_frequency", {})
    chunk_count = max(1, len(chunks))

    scored: list[dict] = []
    for chunk in chunks:
        score = _score_chunk(
            chunk,
            query=query,
            query_terms=query_terms,
            chunk_count=chunk_count,
            document_frequency=document_frequency,
        )
        if score > 0:
            scored.append({"score": score, "chunk": chunk})

    scored.sort(key=lambda x: x["score"], reverse=True)

    results = []
    for item in scored[:top_k]:
        chunk = item["chunk"]
        results.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "score": item["score"],
                "chapter_num": chunk.get("chapter_num"),
                "chapter_title": chunk.get("chapter_title", ""),
                "printed_page": chunk.get("printed_page"),
                "location": chunk.get(
                    "location", "Harrison's Part 4, Oncology and Hematology"
                ),
                # Raw text — grounding only, never printed in full
                "_raw_text": chunk.get("text", ""),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Guardrail helpers
# ---------------------------------------------------------------------------


def _count_sentences(text: str) -> int:
    """Count sentence-like units."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return len([p for p in parts if p.strip()])


def enforce_quote_guardrails(
    raw_quote: str, location: str
) -> tuple[str, bool, list[str]]:
    """Apply G1 (length cap) and G2 (source required) guardrails.

    Returns (safe_quote, needs_review, reasons).
    """
    needs_review = False
    reasons: list[str] = []

    # G2: block output entirely if no location citation
    if not location or not location.strip():
        return "", True, ["G2: 출처 없음 — 인용 차단"]

    text = clean_text(raw_quote)
    if not text:
        return "", False, []

    # G1: sentence cap
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > QUOTE_MAX_SENTENCES:
        text = " ".join(sentences[:QUOTE_MAX_SENTENCES]).strip()
        if not text.endswith((".", "!", "?")):
            text += "."
        needs_review = True
        reasons.append(
            f"G1: 인용이 {QUOTE_MAX_SENTENCES}문장으로 잘렸습니다 (원본 {len(sentences)}문장)"
        )

    # G1: char cap
    if len(text) > QUOTE_MAX_CHARS:
        text = text[:QUOTE_MAX_CHARS].rsplit(" ", 1)[0].strip()
        if not text.endswith((".", "!", "?")):
            text += "..."
        needs_review = True
        reasons.append(f"G1: 인용이 {QUOTE_MAX_CHARS}자로 잘렸습니다")

    return text, needs_review, reasons


# ---------------------------------------------------------------------------
# LLM generation — Anthropic API (primary), OpenAI API (secondary)
# ---------------------------------------------------------------------------


def _call_anthropic_api(prompt: str) -> str:
    """Call Anthropic Messages API. Requires ANTHROPIC_API_KEY env var."""
    import requests
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": 2048,
            "system": "Return only valid JSON. Do not include markdown fences.",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=LLM_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Anthropic API {response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    return "".join(
        b.get("text", "")
        for b in payload.get("content", [])
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


def _call_openai_api(prompt: str) -> str:
    """Call OpenAI Chat API. Requires OPENAI_API_KEY env var."""
    import requests
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only valid JSON. Do not include markdown fences.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 2048,
        },
        timeout=LLM_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenAI API {response.status_code}: {response.text[:300]}"
        )
    return response.json()["choices"][0]["message"]["content"].strip()


def _build_llm_prompt(question: dict, passages: list[dict]) -> tuple[str, str]:
    """Build the LLM prompt and return (prompt, best_location)."""
    stem = question["stem"]
    choices_text = "\n".join(
        f"  {k}. {v}" for k, v in question["choices"].items()
    )
    answer_text = question["answer_text"]
    topic = question["topic"]
    best_location = (
        passages[0].get("location", "Harrison's Part 4, Oncology and Hematology")
        if passages
        else "Harrison's Part 4, Oncology and Hematology"
    )

    # Build grounding blocks (truncated — G3 compliance)
    grounding_blocks = []
    for i, p in enumerate(passages[:3], start=1):
        raw = p["_raw_text"]
        snippet = raw[:GROUNDING_MAX_CHARS]
        # Try to cut at sentence boundary
        last_period = snippet.rfind(".")
        if last_period > int(GROUNDING_MAX_CHARS * 0.7):
            snippet = snippet[: last_period + 1]
        grounding_blocks.append(f"[Passage {i} | {p['location']}]\n{snippet}")

    grounding_text = "\n\n".join(grounding_blocks)

    prompt = (
        "You are a medical education assistant for the P:accine app.\n"
        "A student just answered a hematology/oncology MCQ.\n\n"
        f"QUESTION:\n{stem}\n\n"
        f"CHOICES:\n{choices_text}\n\n"
        f"CORRECT ANSWER: {answer_text}\n\n"
        f"TOPIC: {topic}\n\n"
        "TEXTBOOK GROUNDING (Harrison's Part 4 — use only to ground your explanation; "
        "do NOT copy verbatim):\n"
        f"{grounding_text}\n\n"
        "Produce a JSON object with EXACTLY these four keys:\n"
        '  "rationale": A newly-written 3-5 sentence explanation of WHY this answer is correct, '
        "in plain medical English. Explain the underlying mechanism/concept. "
        "Do NOT copy textbook sentences verbatim.\n"
        '  "location": The most precise Harrison location from the passages above '
        '(e.g., "Harrison\'s Part 4, Chapter 110: Chronic Myeloid Leukemia, ~p.348"). '
        "Use the passage location metadata provided.\n"
        '  "short_quote": A SHORT verbatim excerpt (2-3 sentences maximum) from the grounding '
        "passages that best supports this answer. Must be an exact quote.\n"
        '  "quote_source_label": Concise source citation, '
        'e.g., "Harrison\'s Part 4, Chapter 110: Chronic Myeloid Leukemia, ~p.348"\n\n'
        "Rules:\n"
        "- Rationale must be NEW writing — not a copy of textbook text.\n"
        "- short_quote must be genuinely short (2-3 sentences max).\n"
        "- Location must be specific. Never output an empty location.\n"
        "- Return ONLY a valid JSON object. No markdown fences, no extra text."
    )
    return prompt, best_location


def _llm_generate(prompt: str) -> tuple[str, str]:
    """Try Anthropic then OpenAI. Returns (raw_response, method_name)."""
    for fn, name in [(_call_anthropic_api, "anthropic"), (_call_openai_api, "openai")]:
        try:
            return fn(prompt), name
        except RuntimeError:
            continue
    raise RuntimeError("No LLM API available (set ANTHROPIC_API_KEY or OPENAI_API_KEY)")


# ---------------------------------------------------------------------------
# Template-based fallback (no external API required)
# ---------------------------------------------------------------------------

# Sentence-skip pattern for extracting quotes (headers, page numbers, figures)
_SKIP_LINE_RE = re.compile(
    r"^(TABLE|FIGURE|CHAPTER|PART|\d+\.?\s*$|[A-Z]{3,}\s+[A-Z]{3,})", re.IGNORECASE
)


def _extract_short_quote_from_passage(raw_text: str) -> str:
    """Extract a short meaningful quote from a passage (no LLM)."""
    sentences = re.split(r"(?<=[.!?])\s+", raw_text.strip())
    good = []
    for s in sentences:
        s = s.strip()
        if len(s) < 50:
            continue
        if _SKIP_LINE_RE.match(s):
            continue
        good.append(s)
        if len(good) >= 2:
            break
    quote = " ".join(good)
    return re.sub(r"\s+", " ", quote).strip()


_TEMPLATE_RATIONALES: dict[str, str] = {
    "cml": (
        "Chronic Myeloid Leukemia (CML) is driven by the BCR::ABL1 fusion oncogene arising from "
        "the Philadelphia chromosome t(9;22)(q34;q11). This translocation creates a constitutively "
        "active tyrosine kinase that drives uncontrolled proliferation of myeloid progenitors. "
        "Imatinib, the first BCR::ABL1 tyrosine kinase inhibitor (TKI), competitively inhibits "
        "the ATP-binding domain of BCR::ABL1, blocking downstream signaling and restoring normal "
        "hematopoiesis. TKIs are now the standard first-line therapy for newly diagnosed CML in "
        "chronic phase, demonstrating superior response rates and survival compared to hydroxyurea "
        "or interferon, and are preferred over upfront allogeneic transplantation."
    ),
    "iron_deficiency": (
        "In iron deficiency anemia, iron stores are depleted before erythropoiesis is impaired, "
        "and serum ferritin directly reflects total body iron stores held in macrophages and "
        "hepatocytes. It is the earliest and most sensitive marker of iron depletion — a low "
        "ferritin is virtually diagnostic of iron deficiency regardless of other parameters. "
        "While serum iron is also low and TIBC elevated in iron deficiency, both can be altered "
        "by inflammation, hepatic disease, or other conditions, reducing their specificity. "
        "Low ferritin is therefore the single best confirmatory finding for iron deficiency anemia."
    ),
}


def _template_generate(question: dict, passages: list[dict]) -> dict:
    """Template-based generation fallback (PoC demo mode, no external API).

    In production this block is replaced by the LLM call above.
    """
    topic_lower = question["topic"].lower()
    answer_text = question["answer_text"]
    best = passages[0] if passages else {}
    location = best.get("location", "Harrison's Part 4, Oncology and Hematology")

    # Select rationale template
    if "cml" in topic_lower or "chronic myeloid" in topic_lower:
        rationale = _TEMPLATE_RATIONALES["cml"]
    elif "iron" in topic_lower or "ferritin" in topic_lower:
        rationale = _TEMPLATE_RATIONALES["iron_deficiency"]
    else:
        rationale = (
            f"The correct answer is {answer_text}. "
            f"This is the evidence-based approach for {question['topic']} "
            "as described in Harrison's Principles of Internal Medicine, Part 4. "
            "[In production, this rationale would be generated by the LLM from the "
            "retrieved Harrison passages above.]"
        )

    # Extract short quote from best passage
    short_quote = _extract_short_quote_from_passage(best.get("_raw_text", ""))

    return {
        "rationale": rationale,
        "location": location,
        "short_quote": short_quote,
        "quote_source_label": location,
    }


# ---------------------------------------------------------------------------
# Main generation dispatcher
# ---------------------------------------------------------------------------


def generate_evidence_jump(
    question: dict, passages: list[dict], *, use_llm: bool = True
) -> EvidenceJumpOutput:
    """Generate Evidence Jump output.

    Tries LLM (Anthropic then OpenAI), falls back to template.
    """
    best_passage = passages[0] if passages else {}
    best_location = best_passage.get("location", "Harrison's Part 4, Oncology and Hematology")
    method = "template"

    if use_llm:
        prompt, _ = _build_llm_prompt(question, passages)
        try:
            raw_response, method = _llm_generate(prompt)
            # Strip markdown fences if model added them
            raw_response = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_response.strip(), flags=re.MULTILINE
            ).strip()
            data = json.loads(raw_response)
        except RuntimeError as exc:
            print(f"  [LLM unavailable — {exc}. Using template fallback.]")
            data = _template_generate(question, passages)
            method = "template_fallback"
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"  [LLM parse error — {exc}. Using template fallback.]")
            data = _template_generate(question, passages)
            method = "template_fallback"
    else:
        data = _template_generate(question, passages)
        method = "template"

    raw_quote = str(data.get("short_quote", "")).strip()
    location = str(data.get("location", best_location)).strip() or best_location
    quote_source_label = (
        str(data.get("quote_source_label", location)).strip() or location
    )

    # Apply guardrails G1 + G2 (internal — quote not displayed in demo output)
    safe_quote, needs_review, reasons = enforce_quote_guardrails(raw_quote, location)

    am_link, open_link = _build_access_links(question["question_id"], question["topic"])

    return EvidenceJumpOutput(
        question_id=question["question_id"],
        answer=question["answer"],
        answer_text=question["answer_text"],
        topic=question["topic"],
        rationale=str(data.get("rationale", "")).strip(),
        location=location,
        access_link_am=am_link,
        access_link_open=open_link,
        short_quote=safe_quote,
        quote_source_label=quote_source_label,
        needs_review=needs_review,
        review_reasons=reasons,
        quote_char_count=len(safe_quote),
        quote_sentence_count=_count_sentences(safe_quote) if safe_quote else 0,
        retrieval_score=best_passage.get("score", 0.0),
        generation_method=method,
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def print_evidence_jump(output: EvidenceJumpOutput, question: dict) -> None:
    DIVIDER = "=" * 72
    print(DIVIDER)
    print(f"근거 점프 (Evidence Jump)  |  Q: {output.question_id}")
    print(DIVIDER)
    print(f"Topic : {output.topic}")
    print(f"Answer: ({output.answer}) {output.answer_text}")
    print()

    print("1. 근거 해설 (Rationale)")
    print("-" * 50)
    print(output.rationale or "[empty]")
    print()

    print("2. 정확한 위치 (Harrison's Location)")
    print("-" * 50)
    print(output.location or "[MISSING]")
    print()

    print("3. 원문 열람 링크 (Access Links)")
    print("-" * 50)
    print(f"  정식 원문 (AccessMedicine · 도서관 로그인):")
    print(f"    {output.access_link_am}")
    print(f"  공개 자료 (MSD Manual Professional):")
    print(f"    {output.access_link_open}")
    print()

    status = "NEEDS REVIEW: True" if output.needs_review else "NEEDS REVIEW: False"
    print(status)
    for r in output.review_reasons:
        print(f"  - {r}")
    print(
        f"[method: {output.generation_method} | retrieval score: {output.retrieval_score}]"
    )
    print(DIVIDER)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evidence Jump PoC — heme-onc MCQ -> rationale + "
            "Harrison location + access links"
        )
    )
    parser.add_argument(
        "--question-id",
        default="all",
        choices=list(DEMO_QUESTIONS.keys()) + ["all"],
        help="Which demo question to run (default: all)",
    )
    parser.add_argument(
        "--list-questions",
        action="store_true",
        help="List available demo question IDs",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=TOP_K,
        help=f"Number of passages to retrieve (default: {TOP_K})",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Attempt LLM generation (requires ANTHROPIC_API_KEY or OPENAI_API_KEY); "
             "falls back to template if unavailable. Default: template only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list_questions:
        print("Available demo questions:")
        for qid, q in DEMO_QUESTIONS.items():
            print(f"  {qid}: {q['topic']}")
            print(f"         {q['stem'][:100]}...")
        return

    if not HARRISON_PART4_INDEX.exists():
        print(
            f"[ERROR] Harrison Part 4 index not found:\n  {HARRISON_PART4_INDEX}\n"
            "Run:  python3 scripts/build_harrison_part4_index.py",
            file=sys.stderr,
        )
        sys.exit(1)

    target_ids = (
        list(DEMO_QUESTIONS.keys())
        if args.question_id == "all"
        else [args.question_id]
    )

    for qid in target_ids:
        question = DEMO_QUESTIONS[qid]
        retrieval_query = f"{question['topic']} {question['answer_text']}"

        passages = retrieve_passages(retrieval_query, top_k=args.top_k)
        if not passages:
            print(f"[WARN] No passages retrieved for {qid}. Check index.")
            continue

        output = generate_evidence_jump(question, passages, use_llm=args.use_llm)
        print_evidence_jump(output, question)


if __name__ == "__main__":
    main()
