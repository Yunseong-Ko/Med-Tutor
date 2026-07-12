# P0 티켓 — 피드백·계층화 (2026-07-13)

근거: `docs/Feedback_Stratification_Layering_Research_20260711.md` §13 (v2 검증 리서치) · Codex 브리프 §15.
원칙: **새 콘텐츠 저작 없음. 이미 로깅 중인 데이터(attempts.jsonl)·라벨·온톨로지의 재단.** 모든 지표는 참조프레임 + 원탭 액션 동반(대시보드 단독은 성적 무효, Borrella 2025).

공통 가드레일(전 티켓 적용):
- 학생 화면에 raw percentile·리더보드·"하위권" 노출 금지(Kluger & DeNisi).
- 표본 게이트: 문항 attempts <5 "자료 부족" / 5–19 descriptive / ≥20 지표. IRT는 Rasch까지만.
- 원문 stem 외부전송 금지, `data_private/` 경계 유지.

관련 코드(현행): `api_server.py`(normalize_attempt_payload, build_distractor_analysis, `/api/practice/analytics/*`), `frontend/app.js`(practice reader·student-review·faculty pages), `data_private/course_exams/analytics/attempts.jsonl`, `qbank_relabeled.json`, `distractor_bridges.json`.

---

## PA-01 · 오답선지 분포 학생 노출 + "너만 틀림" 플래그
- **가치**: UWorld 패리티, 신규데이터 0. 오답 refute로 거짓지식 차단(Butler & Roediger 2008), 오답 정상화로 낙인 완화.
- **범위**: 기존 faculty-only distractor 집계를 학생 해설화면에 선지별 가로막대(정답 초록/최다오답 회색)로. "동기 다수 정답인데 너만 틀림" 문항을 완료리포트 최우선 리뷰로 태깅.
- **수용기준**
  - [ ] 제출 후 해설화면에 선지별 응답% 막대 표시(응답 ≥5일 때만; 미만은 "자료 부족").
  - [ ] `is_correct=false` & 코호트 정답률 ≥60% 문항 = "우선 복습" 배지.
  - [ ] 원탭 "이 유형 다시 풀기" → 세트빌더로.
- **파일**: `api_server.py`(distractor 집계를 student endpoint로 노출), `frontend/app.js`(reader 해설 블록), `styles.css`.
- **의존성**: 없음. **스레드**: 1(리더). **난이도**: quick.

## PA-02 · 문항-모드 풀 (오답만 / 안 푼 / 북마크)
- **가치**: 세트빌더/시험모드/혼합모의고사의 토대. 오답풀 = 근거 있는 remediation 풀.
- **범위**: 학생별 attempts에서 `question_id × is_correct` 집계 → 세트빌더 풀 필터(오답만/미풀이/북마크). 문항 UI에 'marked' 토글.
- **수용기준**
  - [ ] 세트빌더에 풀 3종(오답/미풀이/북마크) 필터, 범위<개수 충돌 시 "가능한 N개로 축소" 안내.
  - [ ] 북마크 토글이 attempts/별도 store에 지속.
  - [ ] 오답풀은 "가장 오래된 오답 먼저" 정렬 옵션.
- **파일**: `api_server.py`(pool 계산), `frontend/app.js`(세트빌더). **의존성**: 없음. **스레드**: 1. **난이도**: quick.

## PA-03 · 3축 NBME 프로파일 + SE 게이트 + blueprint weight
- **가치**: "2/4 틀림=약점" 오탐 방지. 히트맵을 "약점"→"약점×배점"으로.
- **범위**: 한 응답셋을 `major_category × assessment_domain × disease/finding` 3축 재단. 각 축 Lower/Same/Higher는 **코호트델타 > 라벨 SE** 일 때만 "약함" 발화. 각 셀에 280 실기출 라벨분포 기반 blueprint weight 병기.
- **수용기준**
  - [ ] 라벨당 응답 <SE 문턱이면 "자료 부족"으로 suppress(약함 미발화).
  - [ ] 축별 정렬 = 약점 × exam-frequency.
  - [ ] disease축 미커버(~52%) 문항은 assessment_domain 축으로 fallback 표기.
- **파일**: `api_server.py`(analytics/student 확장), `frontend/app.js`(리포트), `qbank_relabeled.json`(라벨), blueprint = 280문항 분포 계산 스크립트.
- **의존성**: 커버리지 수치 확정(§13.1). **스레드**: 2(축 정의와 공유). **난이도**: medium.

## PA-04 · 경험적 p-value 5티어 난이도
- **가치**: 주관 난이도 대체(AMBOSS hammer 근거판). 혼합난이도 세트가 거짓 약점으로 읽히는 문제 교정.
- **범위**: attempts `is_correct` 롤링 집계 → 문항 p-value → 5분위 티어. 세트빌더 필터 + 벡터축(스레드2). point-biserial로 저변별 문항 은퇴후보 플래그.
- **수용기준**
  - [ ] 응답 ≥20 문항만 티어 확정, 미만은 "임시" 표기.
  - [ ] `answered_at`로 기수 누적(one-shot 아님).
  - [ ] 2PL/3PL 파라미터 미사용.
- **파일**: `api_server.py` 또는 배치 스크립트(문항별 p-value), `frontend/app.js`(필터). **의존성**: 없음. **스레드**: 1·2. **난이도**: quick.

## PA-05 · 세션점수 Wilson/SEM 구간화
- **가치**: 소표본 세션점수의 측정오차 정직 표기. 위험경고 오탐 방지.
- **범위**: "오늘 78%" 점추정 대신 Wilson 구간. 위험/D-14 경고는 구간이 컷(예: 작년 과정시험 컷) 넘을 때만.
- **수용기준**
  - [ ] 완료리포트 점수 = 구간 표기.
  - [ ] 위험 배너는 구간-컷 오버랩 조건에서만, 사적으로(끈끈한 배지 금지).
- **파일**: `api_server.py`(세션 집계), `frontend/app.js`(완료리포트). **의존성**: 없음. **스레드**: 1. **난이도**: quick.

## PA-06 · 속도×정오답 2x2 = 큐 오더링(차트 아님)
- **가치**: 확신오답(fast-wrong)은 최고수익이나 1주 내 relapse(Butler 2011) → 원칙적 SRS 트리거.
- **범위**: `time_ms`를 `question_id`별 코호트 percentile로 정규화 → 4분면. fast-wrong 셀 = 즉시 full 해설 "확신했는데 틀림" 프레임 + SRS 최우선 재출제 후보. **패시브 인포그래픽 아니라 액션 커플링**(Perry/Rainsford: 표시만으로 재보정 안 됨).
- **수용기준**
  - [ ] fast-wrong = time_ms 하위 percentile & 오답(절대초 임계 금지).
  - [ ] 해당 셀 문항이 복습 큐 상단에 자동 진입.
  - [ ] 사적 진단(공개 순위 아님).
- **파일**: `api_server.py`(normalize + 셀 분류), `frontend/app.js`. **의존성**: PA-09(SRS) 있으면 강화. **스레드**: 1·2. **난이도**: medium.

## PA-07 · distractor → 오개념 라우팅
- **가치**: faculty-only 지표를 학생 선수개념 remediation으로. **개념 미연결 ~52% 문항에서도 작동**(브리지는 소견에 정의).
- **범위**: `selected_choices`를 `distractor_bridges.json`/`item_evidence_packs` provenance에 조인. 공유소견 브리지 선지(예: schistocyte→TTP↔HUS) 선택 시 그 선지 해설을 *명명된 혼동*으로 전면화 + 자동 재출제 플래그.
- **수용기준**
  - [ ] 선택 선지가 브리지에 매칭되면 "명명된 혼동" 카드 노출.
  - [ ] misconception 라벨은 게이트 통과 시만(정답검증·해설존재·item_quality OK·표본충분), 아니면 "검토 필요 오답 패턴".
  - [ ] 개념 미커버 문항은 finding-level로 fallback.
- **파일**: `frontend/app.js`(해설), `api_server.py`, `distractor_bridges.json`, `finding_registry.json`. **의존성**: PA-01. **스레드**: 1. **난이도**: medium.

## PA-08 · 시험모드 vs 학습모드 (피드백 게이팅 플래그)
- **가치**: 시험 직전 유스케이스 핵심. timing 무관(Ryan 2023)이라 배칭에 리텐션 손해 없음. 순수 UI 게이팅(신규 저작 0).
- **범위**: 기존 440풀 위 플래그. 시험모드=해설/KLP/힌트 숨김 + 타이머 + 블록끝 일괄공개 → 기존 학습리포트. 학습모드=KLP+선지별해설 즉시.
- **수용기준**
  - [ ] 두 모드가 동일 풀·동일 해설스택 위에서 노출 타이밍만 다름.
  - [ ] 시험모드 종료 시 완료리포트(PA-05 구간)로 연결.
- **파일**: `frontend/app.js`(reader 상태머신: active(learn|exam)→review), `styles.css`. **의존성**: PA-02. **스레드**: 1(상태머신). **난이도**: medium.

---

## 실행 순서 제안
1. **quick 먼저**: PA-01 · PA-02 · PA-04 · PA-05 (신규데이터 0, 즉시 체감).
2. **medium**: PA-08(모드) → PA-03(3축 프로파일) → PA-07(오개념) → PA-06(2x2 큐).
3. PA-03·PA-04·PA-06은 **스레드2(벡터화 축)** 와 필드 공유 → 벡터축 확정과 함께 진행하면 중복 없음.
4. **선결**: §13.1 커버리지 수치 확정(`build_concept_registry.py` 재실행) — PA-03/PA-07의 fallback 경계에 필요.

> P1(후속): 네이티브 SRS(FSRS, concept 단위 fitting) · confidence tap · per-concept mastery 게이트(응급/약물 conjunctive) · evidence_jump NLI blocking · 선수개념 그래프 전파 · 개념맵 구성 remediation · 비기능 distractor 자동플래그.
