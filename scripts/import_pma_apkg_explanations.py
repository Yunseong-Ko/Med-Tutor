#!/usr/bin/env python3
"""Conservatively import PMA explanation text from a P:accine Anki deck.

The APKG exported by this project is useful as a portable reference corpus, but
some local JSON files may already contain richer explanations, references, or
educational media. This importer fills weak/missing explanation fields without
discarding existing evidence, Harrison links, or media annotations.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import tempfile
import warnings
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import zstandard as zstd
from bs4 import BeautifulSoup
from bs4 import MarkupResemblesLocatorWarning


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = ROOT / "data_private" / "course_exams" / "extracted"

WEAK_PATTERNS = [
    "풀이 후 정답",
    "저장된 해설만으로",
    "교수 검토",
    "보강이 필요",
    "검토 필요",
    "같은 기준으로 대조",
    "이 문항은",
    "정답 선지와 나머지 선지",
    "문항으로 분류",
    "정답과 근거",
]


@dataclass
class ApkgExplanation:
    note_id: int
    deck_name: str
    source_exam: str
    period_label: str
    question_number: int
    source_meta: str
    key_info: dict[str, Any]
    answer_rationale: str
    choice_explanations: dict[str, dict[str, Any]]
    key_learning_points: list[str]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def text_only(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def strip_tags_keep_spaces(value: str) -> str:
    return text_only(value)


def is_weak_text(value: Any) -> bool:
    text = text_only(value)
    if not text:
        return True
    if len(text) < 45:
        return True
    return any(pattern in text for pattern in WEAK_PATTERNS)


def should_replace(existing: Any, candidate: Any) -> bool:
    existing_text = text_only(existing)
    candidate_text = text_only(candidate)
    if not candidate_text:
        return False
    if is_weak_text(existing_text):
        return True
    # If the current field is very short and the APKG field is materially richer,
    # treat the APKG field as a safer learning explanation.
    if len(existing_text) < 120 and len(candidate_text) >= max(120, int(len(existing_text) * 1.8)):
        return True
    return False


def normalize_exam_key(source_meta: str, period_label: str) -> str | None:
    if "2025.11" in source_meta:
        return f"PMA_202511_G3_B군_{period_label}"
    if "2023.06" in source_meta:
        return f"PMA_202306_G3_B군_{period_label}"
    if "2022.06" in source_meta or "2022 " in source_meta:
        return f"PMA_202206_G3_B군_{period_label}"
    return None


def find_sqlite_from_apkg(apkg_path: Path, work_dir: Path) -> Path:
    with zipfile.ZipFile(apkg_path) as archive:
        members = set(archive.namelist())
        preferred = "collection.anki21b" if "collection.anki21b" in members else "collection.anki2"
        extracted = Path(archive.extract(preferred, work_dir))

    header = extracted.read_bytes()[:16]
    if header.startswith(b"SQLite format 3"):
        return extracted

    decompressed = work_dir / f"{extracted.name}.sqlite"
    dctx = zstd.ZstdDecompressor()
    with extracted.open("rb") as src, decompressed.open("wb") as dst:
        dctx.copy_stream(src, dst)
    return decompressed


def deck_names(con: sqlite3.Connection) -> dict[int, str]:
    table_names = {
        row[0]
        for row in con.execute("select name from sqlite_master where type='table'")
    }
    if "decks" in table_names:
        return {
            int(deck_id): str(name or "")
            for deck_id, name in con.execute("select id, name from decks")
        }

    row = con.execute("select decks from col limit 1").fetchone()
    if not row:
        return {}
    if not row[0]:
        return {}
    payload = json.loads(row[0])
    return {int(key): value.get("name", "") for key, value in payload.items()}


def note_to_deck_ids(con: sqlite3.Connection) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for note_id, deck_id in con.execute("select nid, did from cards"):
        mapping[int(note_id)] = int(deck_id)
    return mapping


def extract_section(fragment: str, label: str, next_labels: list[str]) -> str:
    start = re.search(
        rf'<span[^>]*class="panel-title"[^>]*>\s*{re.escape(label)}\s*</span>',
        fragment,
        flags=re.I,
    )
    if not start:
        return ""
    rest = fragment[start.end() :]
    end_positions: list[int] = []
    for next_label in next_labels:
        match = re.search(
            rf'<span[^>]*class="panel-title"[^>]*>\s*{re.escape(next_label)}\s*</span>',
            rest,
            flags=re.I,
        )
        if match:
            end_positions.append(match.start())
    if end_positions:
        rest = rest[: min(end_positions)]
    return rest.strip()


def parse_key_info(fragment: str) -> dict[str, Any]:
    clues_html = extract_section(fragment, "핵심 단서", ["상황 요약", "핵심 개념"])
    summary_html = extract_section(fragment, "상황 요약", ["핵심 개념"])
    core_html = extract_section(fragment, "핵심 개념", [])
    clues: list[str] = []
    if clues_html:
        soup = BeautifulSoup(clues_html, "html.parser")
        clues = [text_only(li) for li in soup.find_all("li") if text_only(li)]
    return {
        "important_clues": clues,
        "summary": strip_tags_keep_spaces(summary_html),
        "core_explanation": strip_tags_keep_spaces(core_html),
    }


def parse_choice_explanations(fragment: str) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(fragment, "html.parser")
    parsed: dict[str, dict[str, Any]] = {}
    for div in soup.select("div.choice-exp"):
        bold = div.find("b")
        if not bold:
            continue
        header = text_only(bold)
        match = re.match(r"(\d+)\.\s*(.*)", header)
        if not match:
            continue
        number, choice_text = match.group(1), match.group(2).strip()
        bold.extract()
        rationale = text_only(div)
        parsed[number] = {
            "choice_text": choice_text,
            "rationale": rationale,
            "explanation": rationale,
            "is_correct": "correct" in (div.get("class") or []),
            "source": "paccine_pma_apkg_reference",
        }
    return parsed


def parse_learning_points(fragment: str) -> list[str]:
    soup = BeautifulSoup(fragment, "html.parser")
    points = [text_only(li) for li in soup.find_all("li") if text_only(li)]
    if points:
        return points
    text = text_only(fragment)
    return [text] if text else []


def parse_note(note_id: int, deck_name: str, fields_raw: str) -> ApkgExplanation | None:
    fields = fields_raw.split("\x1f")
    if len(fields) < 10:
        return None
    source_meta = text_only(fields[0])
    meta_match = re.search(r"(?P<period>[12]교시)\s*·\s*Q(?P<number>\d+)", source_meta)
    if not meta_match:
        return None
    period_label = meta_match.group("period")
    source_exam = normalize_exam_key(source_meta, period_label)
    if not source_exam:
        return None
    return ApkgExplanation(
        note_id=note_id,
        deck_name=deck_name,
        source_exam=source_exam,
        period_label=period_label,
        question_number=int(meta_match.group("number")),
        source_meta=source_meta,
        key_info=parse_key_info(fields[6]),
        answer_rationale=strip_tags_keep_spaces(fields[7]),
        choice_explanations=parse_choice_explanations(fields[8]),
        key_learning_points=parse_learning_points(fields[9]),
    )


def load_apkg_explanations(apkg_path: Path) -> dict[tuple[str, int], ApkgExplanation]:
    with tempfile.TemporaryDirectory(prefix="paccine_apkg_import_") as tmp:
        work_dir = Path(tmp)
        db_path = find_sqlite_from_apkg(apkg_path, work_dir)
        con = sqlite3.connect(db_path)
        decks = deck_names(con)
        note_decks = note_to_deck_ids(con)
        explanations: dict[tuple[str, int], ApkgExplanation] = {}
        for note_id, fields_raw in con.execute("select id, flds from notes"):
            deck_name = decks.get(note_decks.get(int(note_id), -1), "")
            parsed = parse_note(int(note_id), deck_name, fields_raw)
            if not parsed:
                continue
            key = (parsed.source_exam, parsed.question_number)
            # Prefer the first matching note for a source exam/question pair.
            explanations.setdefault(key, parsed)
        con.close()
        return explanations


def merge_key_info(question: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    if not candidate:
        return changed
    current = question.get("key_info") if isinstance(question.get("key_info"), dict) else {}
    merged = dict(current)
    for field in ("summary", "core_explanation"):
        if should_replace(current.get(field), candidate.get(field)):
            merged[field] = candidate.get(field)
            changed.append(f"key_info.{field}")
    candidate_clues = candidate.get("important_clues")
    current_clues = current.get("important_clues")
    if isinstance(candidate_clues, list) and candidate_clues and (
        not isinstance(current_clues, list) or len(current_clues) < 2
    ):
        merged["important_clues"] = candidate_clues
        changed.append("key_info.important_clues")
    if changed:
        question["key_info"] = merged
    return changed


def merge_choice_explanations(
    question: dict[str, Any],
    candidate: dict[str, dict[str, Any]],
) -> list[str]:
    changed: list[str] = []
    if not candidate:
        return changed
    current = question.get("choice_explanations") if isinstance(question.get("choice_explanations"), dict) else {}
    merged = dict(current)
    for key, incoming in candidate.items():
        existing = current.get(key) if isinstance(current.get(key), dict) else {}
        existing_text = existing.get("rationale") or existing.get("explanation") if isinstance(existing, dict) else existing
        incoming_text = incoming.get("rationale") or incoming.get("explanation")
        if not should_replace(existing_text, incoming_text):
            continue
        if isinstance(existing, dict):
            next_item = {**existing, **incoming}
            # Preserve evidence/media/reference metadata attached to prior reviews.
            for preserved_key in (
                "educational_media",
                "evidence",
                "references",
                "reference_notes",
                "rag_references",
                "harrison_refs",
                "source_refs",
                "learning_points",
            ):
                if preserved_key in existing and preserved_key not in incoming:
                    next_item[preserved_key] = existing[preserved_key]
        else:
            next_item = dict(incoming)
        merged[key] = next_item
        changed.append(f"choice_explanations.{key}")
    if changed:
        question["choice_explanations"] = merged
    return changed


def apply_explanation(
    question: dict[str, Any],
    explanation: ApkgExplanation,
    imported_at: str,
    apkg_name: str,
) -> list[str]:
    changed: list[str] = []
    changed.extend(merge_key_info(question, explanation.key_info))

    if should_replace(question.get("answer_rationale") or question.get("explanation"), explanation.answer_rationale):
        question["answer_rationale"] = explanation.answer_rationale
        if should_replace(question.get("explanation"), explanation.answer_rationale):
            question["explanation"] = explanation.answer_rationale
        changed.append("answer_rationale")

    changed.extend(merge_choice_explanations(question, explanation.choice_explanations))

    current_points = question.get("key_learning_points")
    if explanation.key_learning_points and (
        not isinstance(current_points, list)
        or len(current_points) < 2
        or any(is_weak_text(point) for point in current_points)
    ):
        question["key_learning_points"] = explanation.key_learning_points
        changed.append("key_learning_points")

    if changed:
        imports = question.setdefault("reference_imports", [])
        if isinstance(imports, list):
            imports.append(
                {
                    "source": "paccine_pma_apkg_reference",
                    "apkg_file": apkg_name,
                    "note_id": explanation.note_id,
                    "deck_name": explanation.deck_name,
                    "source_meta": explanation.source_meta,
                    "imported_at": imported_at,
                    "updated_fields": changed,
                }
            )
    return changed


def import_to_targets(
    *,
    apkg_path: Path,
    target_dir: Path,
    dry_run: bool,
    no_backup: bool,
) -> dict[str, Any]:
    explanations = load_apkg_explanations(apkg_path)
    imported_at = datetime.now().isoformat(timespec="seconds")
    summary: dict[str, Any] = {
        "source": "paccine_pma_apkg_reference",
        "apkg_file": str(apkg_path),
        "imported_at": imported_at,
        "apkg_note_count": len(explanations),
        "dry_run": dry_run,
        "files": [],
        "total_questions_changed": 0,
        "total_fields_changed": 0,
        "unmatched_apkg_notes": [],
    }

    matched_keys: set[tuple[str, int]] = set()
    for target in sorted(target_dir.glob("PMA_*.json")):
        data = load_json(target)
        source_exam = str(data.get("exam", {}).get("source_exam") or target.stem)
        questions = data.get("questions") if isinstance(data.get("questions"), list) else []
        file_summary = {
            "file": str(target),
            "source_exam": source_exam,
            "question_count": len(questions),
            "questions_changed": 0,
            "fields_changed": 0,
            "changed_question_numbers": [],
            "backup_file": None,
        }
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        for question in questions:
            if not isinstance(question, dict):
                continue
            try:
                number = int(question.get("question_number"))
            except (TypeError, ValueError):
                continue
            explanation = explanations.get((source_exam, number))
            if not explanation:
                continue
            matched_keys.add((source_exam, number))
            changed = apply_explanation(question, explanation, imported_at, apkg_path.name)
            if changed:
                file_summary["questions_changed"] += 1
                file_summary["fields_changed"] += len(changed)
                file_summary["changed_question_numbers"].append(
                    {"question_number": number, "updated_fields": changed}
                )

        if file_summary["questions_changed"]:
            data["apkg_explanation_import_summary"] = {
                "source": "paccine_pma_apkg_reference",
                "apkg_file": apkg_path.name,
                "imported_at": imported_at,
                "questions_changed": file_summary["questions_changed"],
                "fields_changed": file_summary["fields_changed"],
                "mode": "conservative_fill_weak_fields",
            }
        after = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if before != after and not dry_run:
            if not no_backup:
                backup = target.with_name(f"{target.name}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                shutil.copy2(target, backup)
                file_summary["backup_file"] = str(backup)
            dump_json(target, data)
        summary["files"].append(file_summary)
        summary["total_questions_changed"] += file_summary["questions_changed"]
        summary["total_fields_changed"] += file_summary["fields_changed"]

    summary["unmatched_apkg_notes"] = [
        {"source_exam": key[0], "question_number": key[1]}
        for key in sorted(set(explanations) - matched_keys)
    ]
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import PMA explanations from a P:accine APKG deck.")
    parser.add_argument("--apkg", required=True, type=Path)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    summary = import_to_targets(
        apkg_path=args.apkg,
        target_dir=args.target_dir,
        dry_run=args.dry_run,
        no_backup=args.no_backup,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
