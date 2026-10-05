#!/usr/bin/env python3
"""draft → DEMO release 승격 (시연용). 실제 교수 승인 아님.

release_eligible=true(정답충돌 아님) draft만 releases로 승격하되,
demo_release=true / needs_real_faculty_review=true / reviewer_id='demo'로 명시한다.
원본 qbank.json checksum을 built_against_sha256에 기록해 이후 원본이 바뀌면
overlay가 fail-closed로 무시되게 한다.

용법: python3 scripts/promote_qbank_drafts_demo.py [--iso 2026-07-23T00:00:00Z]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QBANK = ROOT / "data_private" / "student" / "qbank.json"
DRAFT = ROOT / "data_private" / "student" / "qbank_enrichment.draft.json"
RELEASES = ROOT / "data_private" / "student" / "qbank_enrichment.releases.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default="2026-07-23T00:00:00Z", help="reviewed_at 타임스탬프")
    args = ap.parse_args()

    sha = hashlib.sha256(QBANK.read_bytes()).hexdigest()
    drafts = json.loads(DRAFT.read_text(encoding="utf-8")).get("drafts", {})
    releases_payload = json.loads(RELEASES.read_text(encoding="utf-8")) if RELEASES.exists() else {}
    releases_payload.setdefault("schema_version", "paccine.qbank_enrichment.releases.v1")
    releases_payload["built_against_sha256"] = sha
    releases_payload["notice"] = "교수 승인 release만. approved=true인 항목만 학생 노출. demo_release는 시연용이며 실제 검수 필요."
    releases = releases_payload.setdefault("releases", {})

    promoted = 0
    for qid, d in drafts.items():
        if not d.get("release_eligible"):
            continue
        releases[qid] = {
            # 시연 데이터는 실제 교수 승인 release가 아니다. 학생 loader는
            # approved+medical_approval이 모두 true인 실제 검수 건만 허용한다.
            "approved": False,
            "medical_approval": False,
            "demo_release": True,
            "needs_real_faculty_review": True,
            "review_status": "demo_only_needs_real_faculty_review",
            "reviewer_id": "demo:learning-loop-demo",
            "reviewed_at": args.iso,
            "explanation": d.get("explanation"),
            "choice_explanations": d.get("choice_explanations") or [],
            "points": d.get("points") or [],
            "source": d.get("source"),
            "provenance": d.get("provenance"),
        }
        promoted += 1

    RELEASES.write_text(json.dumps(releases_payload, ensure_ascii=False, indent=1), encoding="utf-8")
    held = sum(1 for d in drafts.values() if not d.get("release_eligible"))
    print(f"demo release 승격: {promoted}개 (정답충돌 보류 {held}개 제외) → {RELEASES.name}")
    print(f"built_against_sha256={sha[:16]} · reviewed_at={args.iso}")
    print("⚠ demo_release=true / needs_real_faculty_review=true — 실제 교수 검수로 대체 필요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
