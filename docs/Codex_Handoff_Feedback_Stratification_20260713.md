# Codex 핸드오프 — 피드백·계층화·자료계층화 (2026-07-13)

> **이 문서 하나만 먼저 읽어라.** 나머지는 여기서 가리키는 순서대로 연다.
> **브랜치** `codex/pma-question-pipeline` · 관련 커밋 `83100c8`, `d6d1975` (push 안 됨).
> **역할** 이 세션(기획/리서치)이 정리한 결과를 **구현**한다. 프라이버시·근거 경계 준수(§4).
> **성격** 신규 콘텐츠 저작 없음 = 이미 로깅 중인 데이터(attempts)·라벨·온톨로지의 **재단·라우팅·스케줄링**.

---

## 0. 한 줄 방향

학생이 실제/승인 문항을 풀면, P:accine이 정오답뿐 아니라 **고른 오답·풀이시간·문항라벨·온톨로지 근거**를 연결해 — 학생에겐 다음 복습 세트를, 교수에겐 수업 보강점을, **순위 없이·측정오차 정직하게·근거 검증된 채로** 보여준다.

---

## 1. 먼저 읽을 파일 (순서대로)

### 1-A. 이 세션 산출 (committed, 근거·명세)
| 파일 | 무엇 |
|---|---|
| `docs/P0_Feedback_Stratification_Tickets_20260713.md` | **★ 구현 대상 = PA-01~08.** 각 수용기준·파일 터치포인트·의존성·실행순서. 여기부터. |
| `docs/design/set-builder-spec-v6-research-delta.md` | 스레드1(세트빌더/리더/리포트) v6 델타. 화면별 변경 = §1~5. PA↔섹션 매핑 §7. |
| `docs/Feedback_Stratification_Layering_Research_20260711.md` | 근거 원문. **§13 = 2026-07-13 검증 델타**(효과크기·수치·인용가능/금지 목록). |
| `docs/Codex_Feedback_Stratification_Research_Brief.md` | 구현 규칙 브리프. **§15~16 = v2 sharpen 규칙 + 체크리스트**. |

### 1-B. 데이터 자산 (data_private/, gitignored, 실존)
| 파일 | 스키마/용도 |
|---|---|
| `data_private/embedding/qbank_relabeled.json` | 문항→개념 조인. item당 `disease_concept_id[]`(결정론 정확일치)·`finding_tags[]`·`assessment_domain`·라벨. |
| `data_private/embedding/coverage_report.md` | ★ 커버리지 = **321/672(47.8%, ≥1 concept)**. §5 선결 참조. |
| `data_private/course_exams/analytics/attempts.jsonl` | 풀이로그: `question_id·is_correct·time_ms·selected_choices·choice_texts·answer_keys·labels·answered_at·session_id`. (현재 소량 = 계측/시연) |
| `data_private/concept_registry.json` | 573 개념. `edges`(differential_of/presents_with/treated_with/is_a…)·`evidence.harrison{chapter,page,part,accessmedicine}`·`taxonomy.top_category`·`cognitive_model`. |
| `data_private/curriculum/distractor_bridges.json` | 43 브리지(공유소견→공출현 질환세트). 오답→오개념 라우팅 근거. |
| `data_private/curriculum/finding_registry.json` | 196 HPO 소견. 개념 미커버 fallback. |
| `data_private/curriculum/item_evidence_packs.json` | 질환별 근거팩 + provenance된 distractor_pool. |

### 1-C. 현행 코드 터치포인트
| 위치 | 무엇 |
|---|---|
| `api_server.py` | `normalize_attempt_payload`(attempt 스키마), `build_distractor_analysis`(오답집중, 현재 faculty), `/api/practice/analytics/*`. |
| `frontend/app.js` | practice 리더(`commitPracticeAnswer`·reveal·탭), student-review(히트맵·문항이력), faculty-evidence 페이지. (practice 함수 다수 이미 존재) |
| `scripts/evidence_jump_poc.py` | 근거해설+Harrison 페이지+AccessMedicine, 가드레일(인용≤600자). PA-12 NLI 게이트 부착 지점. |
| `scripts/item_quality_check.py` | 결함 스캐너(longest_is_key 등). 뱅크 진입 하드게이트. |
| `src/services/rag_library.py` | `search_rag_evidence`(committed). |

---

## 2. 구현 대상 — P0 8개 (상세 = 티켓 문서)

우선순위·의존성은 `P0_..._Tickets` 참조. 요약:

**quick(신규데이터 0):**
- **PA-01** 오답선지 분포 학생노출 + "동기 다수 정답인데 나만 틀림" 우선복습 (faculty→student 승격).
- **PA-02** 문항-모드 풀(오답만/미풀이/북마크) 세트빌더 필터.
- **PA-04** 경험적 p-value 5티어 난이도(주관 난이도 대체) → 빌더 필터 + 스레드2 축.
- **PA-05** 세션점수 Wilson/SEM 구간(bare % 폐기), 위험경고=구간-컷 오버랩.

**medium:**
- **PA-08** 시험모드 vs 학습모드 플래그 + `review` 상태(채점 후 전체공개 리뷰=SRS 등록점).
- **PA-03** 3축(계통×평가영역×질환/소견) SE 게이트 + blueprint weight.
- **PA-07** 오답→오개념 라우팅(selected_choices × distractor_bridges).
- **PA-06** 속도×정오답 2x2 = 큐 오더링(per-item 정규화), fast_wrong→즉시해설+SRS.

---

## 3. 반드시 지킬 구현 규칙 (검증 리서치)

- **fast_wrong = per-`question_id` percentile 정규화**. 절대초 임계 금지(고수 오분류, Desender 2022).
- **confident-error → 1주 내 같은 q_id 강제 SRS 재출제**(Butler 2011). 범용 Leitner 아님.
- **3축 "약함" = 코호트델타 > 라벨 SE** 일 때만. 표본 게이트: <5 "자료 부족" / 5–19 descriptive / ≥20 지표.
- **evidence 검증 = blocking**: `evidence_jump`에 NLI(RAGAS/ALCE) 체크, verified 아니면 링크 없이 배포(회색링크 금지), 미커버 abstention. (Li & Aral 2025: citation은 틀려도 신뢰↑)
- **오답선지 refute 필수**(Butler & Roediger 2008): 고른 오답이 왜 틀렸는지 개념으로.
- **item_quality_check.py = 뱅크 진입 하드게이트**: 결함문항(longest-choice=key 편향) selected_choices는 오개념 신호로 못 씀.
- **timing 무관**(Ryan 2023): 시험모드 피드백 배칭에 리텐션 손해 없음 → 타이밍 최적화에 공수 쓰지 말 것.
- **IRT는 Rasch/1PL까지만**(소규모 N, 2PL/3PL 금지).

---

## 4. 프라이버시·경계 (절대)

- 원문 문항 stem을 외부 서비스/프롬프트에 **전송 금지**. 개념명만 허용(`attach_evidence_ncbi` 규칙).
- 산출/문서엔 스키마·필드·카운트만, 원문 복붙 금지.
- `data_private/` 는 gitignored 입력전용. 학생은 generated-only + verified 근거만 본다.
- 학생 화면에 raw percentile·리더보드·"하위권/위험" 표현 **금지**(소규모·상호인지 코호트에 해로움).

---

## 5. ★ 선결 조건 (블로킹)

**커버리지 수치 불일치 재조정**: 이전 문서 76.8%(516/672) vs 현재 `coverage_report.md` 47.8%(321/672). PA-03/PA-07의 fallback 경계에 직결. → **`scripts/build_concept_registry.py` 재실행 후 단일 수치 확정**(그 전엔 47.8% 상한 가정). 재실행 시 `apply_topic_recovery.py`를 build 직후 실행하는 순서 주의(build가 커버리지를 영어조인으로 리셋).

---

## 6. 스레드1 스펙 소유권 주의

세트빌더/리더 소스오브트루스 = `docs/design/set-builder-spec.md` (현재 **`peaceful-euler-bc41a7` 워크트리**, v5). 이 세션의 v6 델타는 `docs/design/set-builder-spec-v6-research-delta.md`(메인)에 companion으로 둠. **UI 변경 구현 전, 그 워크트리 스펙과 대조**하거나 델타를 v6로 병합한 뒤 진행(중복/충돌 방지).

---

## 7. Definition of Done (P0)

- [ ] 커버리지 수치 재확정(§5) 후 착수.
- [ ] PA-01·02·04·05(quick) 먼저, 각 수용기준 통과.
- [ ] PA-08→03→07→06 순.
- [ ] 학생 화면 percentile/리더보드 0건, 표본 게이트 동작.
- [ ] evidence 미검증 시 링크 미표시(abstention) 확인.
- [ ] item_quality 하드게이트 통과 문항만 오개념 신호 사용.
- [ ] 원문 stem 외부전송·문서 복붙 0건.
- [ ] 스레드1 UI는 v6 델타/워크트리 스펙과 정합.
