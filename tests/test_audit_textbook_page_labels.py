"""과별 교과서 쪽 라벨 감사 스크립트 — 합성 픽스처, 리포트에 본문이 없음을 확인."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_textbook_page_labels", ROOT / "scripts" / "audit_textbook_page_labels.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)  # type: ignore[union-attr]


def test_audit_counts_and_report_has_no_text(tmp_path):
    book = tmp_path / "tb" / "b1"
    book.mkdir(parents=True)
    rows = [
        {"pdf_page": 1, "printed_label": "Cover", "chapter": None, "text": "SECRET-BODY"},
        {"pdf_page": 2, "printed_label": "10", "chapter": 1, "text": "SECRET-BODY"},
        {"pdf_page": 3, "printed_label": "11", "chapter": 1, "text": "SECRET-BODY"},
        {"pdf_page": 4, "printed_label": "9", "chapter": 1, "text": "SECRET-BODY"},
        {"pdf_page": 5, "printed_label": "9", "chapter": None, "text": ""},
        {"pdf_page": 6, "printed_label": None, "chapter": 2, "text": "SECRET-BODY"},
    ]
    (book / "pages.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "report.json"
    assert audit.main(["--textbooks-dir", str(tmp_path / "tb"), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "SECRET-BODY" not in text and "Cover" not in text
    row = json.loads(text)["books"]["b1"]
    assert (row["pages"], row["pages_with_printed_label"], row["pages_with_numeric_label"], row["pages_with_chapter"]) == (6, 5, 4, 4)
    assert row["label_monotonic_violations"] == 1 and row["label_repeat_count"] == 1


def test_quality_json_flags_garbled_and_chapterless_books(tmp_path):
    root = tmp_path / "tb"
    clean = "Normal clinical prose, with numbers 12.5 mg/dL (ok). " * 8
    garbled = ("Ab\u00a4\u00a6\u0192\u2021 \ue000\ue001\ufffd Cd " * 20)
    for book_id, text, chapter in (("clean", clean, 1), ("noisy", garbled, 1), ("nochap", clean, None)):
        d = root / book_id
        d.mkdir(parents=True)
        rows = [{"pdf_page": i, "printed_label": None, "chapter": chapter, "text": text} for i in range(1, 6)]
        rows.append({"pdf_page": 6, "printed_label": None, "chapter": None, "text": "tiny"})   # 짧은 쪽은 측정 제외
        (d / "pages.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert audit.main(["--textbooks-dir", str(root), "--out", str(tmp_path / "r.json")]) == 0
    q = {b: json.loads((root / b / "quality.json").read_text(encoding="utf-8")) for b in ("clean", "noisy", "nochap")}
    assert q["clean"]["usable_for_evidence"] is True and q["clean"]["reasons"] == [] and q["clean"]["pages_measured"] == 5
    assert q["noisy"]["usable_for_evidence"] is False and q["noisy"]["garbled_ratio_median"] >= audit.GARBLED_MEDIAN_MAX
    assert q["nochap"]["usable_for_evidence"] is False and q["nochap"]["reasons"] == ["no_chapter_assignment"]
    assert "Normal clinical" not in (root / "clean" / "quality.json").read_text(encoding="utf-8")


def test_garbled_ratio_definition():
    assert audit.garbled_ratio("") == 0.0
    assert audit.garbled_ratio("Ab 1,2 (x) \u03b1 \u03b2") == 0.0          # 글자·숫자·공백·흔한 구두점·그리스 문자
    assert audit.garbled_ratio("ab\ue000\ue001") == 0.5
