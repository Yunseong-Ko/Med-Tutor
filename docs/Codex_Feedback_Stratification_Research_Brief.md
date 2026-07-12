# Codex Brief: Feedback, Stratification, and Progressive Evidence Layering

Date: 2026-07-11  
Audience: Claude/Codex/implementation agent  
Use: 다음 개발 세션에서 바로 읽고 구현 범위를 잡기 위한 자립형 브리프

## 0. One-Line Direction

P:accine은 "AI 문제 생성기"가 아니라, 실제/승인 문항 풀이 기록을 축적해 학생에게는 다음 복습 세트를, 교수에게는 수업 보강 포인트를 보여주는 의학교육 closed-loop 시스템이다.

## 1. Current Repo Facts to Preserve

Do not overwrite these assumptions without re-auditing the files.

- `data_private/embedding/qbank_relabeled.json`
  - 672 items
  - 516/672 have non-empty deterministic `disease_concept_id` mapping; 156 are empty
  - all 672 mappings currently have `needs_review=true`
  - all 672 have `assessment_domain`, `major_category`, `topic`, `subtopic`, `source_exam`, `finding_tags`
  - `question_type`, `faculty`, `concept_tags` are not populated in this file
- `data_private/concept_registry.json`
  - 598 concepts
  - all 598 currently `needs_review=true`
  - 531 have Harrison evidence
  - 538 have edges
  - 510 have clinical axes
- `data_private/curriculum/finding_registry.json`
  - 196 findings
- `data_private/curriculum/distractor_bridges.json`
  - 43 bridges
- `data_private/curriculum/item_evidence_packs.json`
  - 292 packs
- `data_private/course_exams/analytics/attempts.jsonl`
  - 40 attempts
  - 2 users
  - 9 exams
  - 23 correct

Important: the current offline file has 516/672 = 76.8% non-empty deterministic mappings. The former 672/672 count treated empty arrays as mappings. This does not mean the current Practice path is connected or student-approved.

## 2. Product Scope

### Keep

- Student question solving
- Attempt logging
- selected choice, correctness, time, bookmark
- per-choice explanation
- key learning points
- evidence references
- completion report
- weak-area routing
- faculty item/distractor report
- set builder by labels

### Defer

- full graph mastery diagnosis
- hard adaptive learning
- high-stakes ranking
- raw percentile/leaderboards
- automated medical approval
- polished Anki export if it delays the solve loop

## 3. Implementation Principle

Build around one strong loop:

1. Student solves a real or approved synthetic item.
2. App records `selected_choices`, `is_correct`, `time_ms`, `question_id`, `mode`, `timestamp`.
3. App joins question to labels: `major_category`, `assessment_domain`, `disease_concept_id`, `finding_tags`.
4. Student sees post-answer explanation and recommended next set.
5. Faculty sees item-level correct rate and wrong-choice distribution.

## 4. Student Stratification Rules

Do not classify students as good/bad. Classify learning states.

Use these labels:

- `unseen`
- `attempted`
- `fast_wrong`
- `slow_wrong`
- `repeated_wrong`
- `bookmarked`
- `concept_needs_review`
- `evidence_needed`

Do not use:

- low performer
- poor student
- bottom group
- risk student
- cohort rank by default

Suggested gates:

- attempts < 5: show "자료 부족"
- attempts 5-19: show descriptive signal only
- attempts >= 20: show pilot-level item percentage
- concept weakness: at least 5 attempts across at least 3 distinct items
- persistent weakness: repeated across sessions separated by at least 7 days

## 5. Distractor Feedback Rules

Selected distractors can be powerful, but only if interpreted carefully.

Only call something a misconception when:

- answer key is verified
- choice parsing is verified
- choice explanation exists
- item quality is acceptable
- distractor bridge or concept mapping exists
- enough attempts exist

Otherwise call it:

- "선택지 분포"
- "오답 선택 패턴"
- "검토 필요 오답 패턴"

### Faculty Report Query Target

For each item:

- item id
- source exam
- correct rate
- answer key
- most selected wrong choice
- wrong-choice count and percent
- linked concept/finding
- teaching suggestion
- item quality warning
- sample size warning

This is the single most persuasive demo artifact.

## 6. Progressive Disclosure UX

### Before submit

Show:

- stem
- choices
- media/images
- bookmark
- timer

Hide:

- question type
- source exam chip if visually distracting
- disease label
- topic label
- answer rate
- key info
- evidence links
- explanation

### After submit

Show in this order:

1. selected answer result
2. key clues
3. core explanation
4. selected choice explanation
5. correct choice explanation
6. all-choice explanations
7. learning points
8. evidence links
9. Anki card candidates

## 7. Explanation Style

Never write:

- "이 문항은 무엇을 평가한다"
- "교수 검토 필요"
- "정답이기 때문에 맞다"
- "오답이기 때문에 틀리다"

Do write:

- what the choice medically means
- when the choice is used
- why the stem does or does not fit that mechanism
- the key physiology/pathophysiology/diagnostic/treatment principle

Good explanation pattern:

```text
Valsalva maneuver는 흉강내압을 증가시켜 정맥환류를 감소시킨다. 이 환자는 이미 하대정맥 압박으로 정맥환류가 감소한 상태이므로, 이 조작은 증상을 완화하기보다 악화시킬 수 있다.
```

Bad explanation pattern:

```text
Valsalva maneuver는 정답이 아니므로 틀렸다.
```

## 8. Evidence Layer Rules

Evidence links should not be decorative. A citation that looks authoritative but points to a weak or unrelated source is worse than no citation.

Preferred hierarchy:

1. Local approved lecture/internal summary
2. Harrison / Williams / Nelson / standard textbook reference
3. Official guideline: CDC, WHO, NICE, KDIGO, ACG, AABB, etc.
4. Public professional reference: MSD Manual
5. PubMed/review/journal when needed

If evidence is missing:

- show "근거 확인 필요"
- do not hallucinate an exact citation
- keep explanation educational but mark `needs_review=true`

## 9. Set Builder Requirements

Student should be able to build sessions by:

- source exam
- subject/course
- major category
- topic/subtopic
- disease concept
- finding
- assessment domain
- wrong only
- unseen only
- bookmarked only
- fast wrong
- slow wrong

When labels conflict, use this fallback:

1. explicit subject/course override
2. disease concept system
3. finding system
4. topic/subtopic
5. source exam
6. manual review needed

## 10. Analytics Output

### Student Completion Report

Show:

- score
- correct count / total
- average time
- wrong items
- bookmarked items
- fast wrong items
- slow wrong items
- weak concept candidates
- buttons:
  - "틀린 문항 다시 풀기"
  - "북마크 문항 풀기"
  - "취약 개념 세트 만들기"
  - "Anki 후보 보기"

### Faculty Report

Show:

- item correct rate
- most selected wrong choice
- wrong-choice distribution
- low-performing content area
- item quality warning
- sample size warning
- action: "보강 문항 세트 만들기"

## 11. Statistical Caution

The current 40 attempts are not enough for cohort inference. Treat all current analytics as instrumentation and demo.

Use language:

- "시연용 풀이 로그"
- "현재 누적 데이터 기준"
- "응답 수 부족"
- "추가 풀이 후 안정화"

Avoid:

- "이 단원은 학생들이 모른다"
- "교수 수업이 부족하다"
- "학년 전체 취약 영역"

## 12. References for the Agent

Use these as benchmark sources, not as UI copy to reproduce.

- NBME INSIGHTS: https://www.nbme.org/wp-content/uploads/2026/04/INSIGHTS_User_Guide.pdf
- NBME CCSSA report: https://www.nbme.org/sites/default/files/2022-12/CCSSA_Examinee_Performance_Report_2022.pdf
- NBME CAS guide: https://www.nbme.org/sites/default/files/2023-10/NBME_CAS_Program_Guide.pdf
- UWorld features: https://medical.uworld.com/usmle/features/
- AMBOSS difficulty: https://support.amboss.com/hc/en-us/articles/360035679652-Question-difficulty
- AMBOSS Qbank sessions: https://support.amboss.com/hc/en-us/articles/360032477132-Creating-a-Qbank-session
- AMBOSS study/exam mode: https://support.amboss.com/hc/en-us/articles/360036038991-Using-Study-Mode-Exam-Mode
- Anki FSRS: https://docs.ankiweb.net/deck-options.html
- Response-oriented feedback: https://pmc.ncbi.nlm.nih.gov/articles/PMC7550480/
- Feedback intervention risks: https://doi.org/10.1037/0033-2909.119.2.254
- Distractor quality: https://pmc.ncbi.nlm.nih.gov/articles/PMC7372664/
- RAGAS: https://arxiv.org/abs/2309.15217
- ALCE: https://arxiv.org/abs/2305.14627

## 13. Next Implementation Checklist

- [ ] Confirm `qbank_relabeled.json` is the coverage source of truth.
- [ ] Hide labels/evidence before answer submit.
- [ ] Add set builder filters for wrong/unseen/bookmark/weak/fast-wrong/slow-wrong.
- [ ] Add completion report CTA buttons.
- [ ] Add faculty distractor distribution report with sample-size warnings.
- [ ] Add item-quality gate to analytics interpretation.
- [ ] Add evidence-status badge: verified / partial / needs review.
- [ ] Ensure no private stems are copied into public docs.
- [ ] Ensure no raw rankings are shown to students.

## 14. North Star Demo

Demo one item where several students choose the same wrong answer:

1. show the item
2. solve it
3. reveal explanation
4. show wrong-choice distribution
5. show the misconception label
6. click "보강 세트 만들기"

This proves why P:accine is not just another LLM wrapper.

---

## 15. v2 델타 (2026-07-13) — 검증 리서치 반영

§1~14 유지. 아래는 2026-07-13 14축 멀티에이전트 검증 리서치(37인용)로 sharpen된 구현 규칙. 전체 근거 = `docs/Feedback_Stratification_Layering_Research_20260711.md` §13, 티켓 = `docs/P0_Feedback_Stratification_Tickets_20260713.md`.

- **커버리지 재확인**: `coverage_report.md` 현재 **321/672=47.8%**(≥1 concept). §1의 516/672=76.8%와 불일치 → `build_concept_registry.py` 재실행 후 단일화. 설계는 47.8% 상한 가정 + finding/assessment_domain fallback 유지.
- **`fast_wrong` 정의 = per-item 정규화**: time_ms를 `question_id`별 코호트 percentile로 변환한 뒤 하위(빠름)+오답. **절대초 임계 금지**(고수 오분류, Desender 2022).
- **confident-error → SRS 강제 트리거**: fast_wrong(또는 P1 confidence='확신'+오답)은 (a) 즉시 full 해설 "확신했는데 틀림" 프레임 + (b) 1주 내 같은 `question_id` 재출제 강제. 범용 Leitner 아님(Butler 2011: 확신오답은 1주 내 relapse).
- **난이도 = 경험적 p-value 5티어**: 주관 난이도 대체, attempts `is_correct` 롤링 집계. 세트빌더 필터 + 벡터축. + point-biserial로 저변별 문항 은퇴후보.
- **3축 프로파일 SE 게이트**: (`major_category` × `assessment_domain` × disease/finding) 각 축 "약함"은 **코호트델타 > 라벨 SE** 일 때만. blueprint weight(280 실기출 라벨분포) 곁들여 "약점×배점" 우선순위.
- **세션점수 = Wilson/SEM 구간**: bare % 금지. 위험/D-14 경고는 구간이 컷 넘을 때만(NBME는 점추정 안 보여줌).
- **오답선지 분포 학생노출**: faculty-only distractor 분석을 학생 해설화면 막대로 승격 + "동기 다수 정답인데 너만 틀림" 최우선 리뷰(Butler & Roediger 2008: 오답 refute 필수).
- **evidence 검증 = blocking**: `evidence_jump_poc.py`에 NLI(RAGAS/ALCE) 체크, verified 아니면 **링크 없이** 배포(회색링크 금지). 미근거 ~52%는 abstention(Li & Aral 2025: citation은 틀려도 신뢰↑).
- **시험모드 vs 학습모드 = 피드백 게이팅 플래그**(timing 무관, Ryan 2023): 기존 440풀 위 플래그만.
- **`item_quality_check.py` = 뱅크 진입 하드게이트**: 결함문항(특히 longest-choice=key 편향) selected_choices는 오개념 신호로 못 씀.
- **포지셔닝**: 문제은행 숙달 = T1(시험지식) 성과. 임상역량 전이 약속 금지(Cook 2011).

## 16. Next Implementation Checklist v2 (§13에 추가)
- [ ] `fast_wrong`를 per-`question_id` percentile로 계산(절대초 아님)
- [ ] confident-error SRS 강제 재출제 트리거(1주 내)
- [ ] 경험적 p-value 5티어 난이도 + point-biserial 은퇴후보
- [ ] 3축 SE 게이트 + blueprint weight 우선순위
- [ ] 세션점수 Wilson 구간화, 위험경고=구간-컷 오버랩
- [ ] `evidence_jump` NLI blocking 게이트 + 미근거 abstention
- [ ] 학생용 오답선지 분포 막대(faculty→student 승격)
