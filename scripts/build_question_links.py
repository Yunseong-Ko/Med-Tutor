#!/usr/bin/env python3
"""③ 문항간 Ontology 연결 그래프 (데이터층).

각 문항(disease_concept_id 부착됨)에 대해 연관 문항을 계산:
  - same_concept: 같은 disease_concept_id를 다루는 다른 문항 (반복 학습·비교)
  - differential: 이 문항 개념의 감별질환(ontology_grounding.differentials)을 다루는 문항
    (오답 시 감별 개념으로 복습 유도 — '리뷰 확인 목적')
  - same_domain: 같은 assessment_domain(평가요소) 문항 (동일 평가축 반복)

출력: data_private/ontology/question_links.json
  { "questions": { "<qid>": {concept, label, assessment_domain,
      same_concept:[qid..], differential:[{qid, via_concept}..], same_domain:[qid..] } },
    "concept_index": { "<cid>": [qid..] }, "meta": {...} }
결정론·환각 0. 앱 복습/추천의 데이터 소스.
"""

import json
import glob
import collections
from pathlib import Path

OUT = Path("data_private/ontology/question_links.json")


def load_questions():
    """ontology_grounding 부착된 문항 전부 수집. qid = source_exam#question_number."""
    items = {}
    for p in sorted(glob.glob("data_private/course_exams/extracted/*.json")):
        if ".bak" in p:
            continue
        try:
            d = json.load(open(p))
        except Exception:
            continue
        stem = Path(p).stem
        for q in d.get("questions", []):
            g = q.get("ontology_grounding")
            if not g or not g.get("disease_concept_id"):
                continue
            qid = q.get("question_id") or f"{stem}#{q.get('question_number')}"
            lab = q.get("labels") or {}
            items[qid] = {
                "qid": qid, "source": stem, "qn": q.get("question_number"),
                "concept": g["disease_concept_id"], "label": g.get("label"),
                "differentials": g.get("differentials") or [],
                "assessment_domain": lab.get("assessment_domain"),
            }
    return items


def main():
    items = load_questions()
    by_concept = collections.defaultdict(list)
    by_domain = collections.defaultdict(list)
    for qid, it in items.items():
        by_concept[it["concept"]].append(qid)
        if it["assessment_domain"]:
            by_domain[it["assessment_domain"]].append(qid)

    questions = {}
    edge_count = 0
    for qid, it in items.items():
        same = [x for x in by_concept[it["concept"]] if x != qid]
        diff = []
        for dcid in it["differentials"]:
            for x in by_concept.get(dcid, []):
                diff.append({"qid": x, "via_concept": dcid})
        dom = [x for x in by_domain.get(it["assessment_domain"], []) if x != qid] if it["assessment_domain"] else []
        questions[qid] = {
            "concept": it["concept"], "label": it["label"],
            "assessment_domain": it["assessment_domain"], "source": it["source"], "qn": it["qn"],
            "same_concept": same[:20],
            "differential": diff[:20],
            "same_domain": dom[:20],
        }
        edge_count += len(same) + len(diff)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "meta": {"questions": len(items), "concepts": len(by_concept),
                 "same_concept_edges": sum(len(q["same_concept"]) for q in questions.values()),
                 "differential_edges": sum(len(q["differential"]) for q in questions.values()),
                 "source": "ontology_question_links_v1", "needs_review": True},
        "concept_index": {k: v for k, v in by_concept.items()},
        "questions": questions,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문항 {len(items)} · 개념 {len(by_concept)} · same_concept엣지 {sum(len(q['same_concept']) for q in questions.values())} · 감별엣지 {sum(len(q['differential']) for q in questions.values())}")
    top = sorted(by_concept.items(), key=lambda kv: -len(kv[1]))[:8]
    print("문항 많은 개념:", [(k, len(v)) for k, v in top])
    print("저장:", OUT)


if __name__ == "__main__":
    raise SystemExit(main())
