# set-builder-spec — v6 델타 (검증 리서치 반영)

> **성격** 이 문서는 `docs/design/set-builder-spec.md`(소스오브트루스, 현재 `peaceful-euler-bc41a7` 워크트리, v5)에 **병합 대상 델타**다. 워크트리 경계상 여기(메인)에 companion으로 두고, 스펙 소유 세션이 §4·§5.4·§5.5·§5.6·§7·§8을 아래대로 갱신해 v6로 흡수한다.
> **근거** `docs/Feedback_Stratification_Layering_Research_20260711.md` §13 (14축 웹+PubMed 검증 리서치) · 티켓 `docs/P0_Feedback_Stratification_Tickets_20260713.md` (PA-01~08).
> **작성** 2026-07-13.

---

## 0. 전제 — 재논의 안 하는 것 (v5 유지)

D1~D7 전부 lock. 특히 아래는 리서치와 **일치**하므로 그대로 둔다:
- **D1** 이어풀기=원탭 빌더 skip (연습의 즉시성 보존).
- **D3** D-14 넛지만, 자동 모드전환 없음 (강제 전환 금지 — 리서치도 동일).
- percentile·리더보드 학생 비노출 (Kluger & DeNisi: self/normative 피드백은 >1/3에서 수행 저하; 소규모·상호인지 코호트에서 특히 위험).
- 손맛(D7): 선지 소거·하이라이트·time = "어디서 헷갈렸나" 신호 수집기 (아래 fast_wrong·오개념 라우팅의 입력).

리서치가 더하는 건 **새 상태가 아니라 기존 표면 5곳에 얹는 근거기반 계측·피드백**이다.

---

## 1. 상태머신 (§4 개정) — `review` 1급 승격

```
round(learn|exam) → (paused) → report(완료) → review → {오답 다시풀기 | SRS | 새 세트}
```
- **learn**: 정답 확인 → reveal이 곧 review(현행 유지).
- **exam**: §7의 "시험모드 채점 후 리뷰"를 **review 상태로 확정**. report(결과요약) → 문항별 review(리더 리뷰모드, 해설스택 전부공개, 팔레트+필터).
- **review = 오답 소비 지점 + SRS 등록 지점.** 확신오답·fast_wrong·오개념 브리지가 여기서 복습 큐로 흘러간다. (PA-08)

→ §7 열린항목 "시험모드 채점 후 리뷰" 해소.

---

## 2. 빌더 (§5.4 개정) — 경험적 난이도 필터 + 기본값

- **난이도 티어 필터 추가**(PA-04): 고급설정 "문항상태"와 나란히 **경험적 p-value 5분위 티어**(attempts 롤링 집계). 주관 난이도칩 대체. 응답 ≥20 문항만 티어 확정, 미만 "임시". 이 축은 **스레드2 벡터축과 공유** → §6 접합면에 4번째로 추가.
- **기본 문항수 = 적응형**(살아있던 v5 미명세 항목): "범위 내 미풀이 전체(상한 20)". 고정 20 아님 — 우리 계통은 4~14문항짜리가 흔해(혈액4·감염3) 고정값이면 범위<개수 충돌이 기본이 됨.
- **범위<개수 충돌 카피 명문화**: §5.4에 풀 카운트는 이미 표시 → "가능한 N개로 축소합니다" 안내만 추가.
- point-biserial 저변별 문항 = 교수측 은퇴후보 플래그(학생 비노출).

---

## 3. 리더 reveal (§5.5 개정) — 3개 추가

현행 reveal(선지별 해설 아코디언 + 탭)에 얹는다. **시험모드는 (a)(b)(c) 전부 채점 후 review에서만.**

- **(a) 오답선지 분포 막대** (PA-01): 선지별 해설 위 코호트 분포 "동기 68% 정답 · 22% 이 선지"(응답 ≥5, 미만 "자료 부족"). 기존 faculty-only 오답선지분석을 student로 승격. "동기 다수 정답인데 나만 틀림" 문항 = 완료리포트 우선복습 배지.
- **(b) 오개념 라우팅** (PA-07): 고른 오답이 `distractor_bridges.json` 브리지면 그 선지 해설을 *명명된 혼동*으로 전면화(예: "schistocyte로 TTP↔HUS 혼동, 감별점은 X"). 브리지는 **소견에 정의** → 개념 미커버(~52%) 문항에서도 작동(fallback). misconception 라벨은 게이트(정답검증·해설존재·item_quality OK·표본충분) 통과 시만, 아니면 "검토 필요 오답 패턴".
- **(c) 근거 blocking 게이트** (PA-12): 개념노트 탭 근거는 **verified만** 노출(evidence_jump에 RAGAS/ALCE식 NLI entailment 체크 — 각 해설문장이 인용 Harrison 구절에 함의). 미검증은 링크 없이 "근거 확인 필요", 미커버 계산/기전/술기는 **명시적 abstention**. 근거: Li & Aral 2025 — citation은 틀려도 신뢰를 올리므로 검증은 표시선택이 아니라 **차단**이어야 함.

---

## 4. 리포트 (§5.6 개정) — 측정오차·배점

- **점수 = Wilson/SEM 구간**(PA-05): bare "78%" 폐기. 세션 문항 수십 개 → 측정오차 큼(NBME는 점추정 안 보여줌).
- **취약단원 = 3축 SE 게이트**(PA-03): `major_category × assessment_domain × disease/finding`. "약함"은 **코호트델타 > 그 라벨 SE** 일 때만 발화(라벨당 문항 적어 오탐 방지, 미만은 "자료 부족" suppress).
- **blueprint weight 병기**: 280 실기출 라벨분포 → "약점 × 배점"으로 정렬(약점을 배점가중으로 읽음).
- 위험/D-14 경고는 구간이 컷(예: 작년 과정시험 컷) 넘을 때만, 사적으로(끈끈한 at-risk 배지 금지).

---

## 5. 데이터모델 (§8 개정) — fast_wrong·confident-error

```
attempt { ...기존..., time_percentile }   // time_spent_sec의 문항별 코호트 percentile
```
- **fast_wrong = per-item 정규화**(PA-06): `time_spent_sec`를 `q_id`별 코호트 percentile로 변환 후 하위(빠름)+오답. **절대초 임계 금지**(고수를 덤벙으로 오분류, Desender 2022).
- **confident-error → SRS 강제 트리거**: fast_wrong(또는 P1 confidence 탭='확신'+오답)은 (a) 즉시 full 해설 "확신했는데 틀림" 프레임 + (b) **1주 내 같은 q_id 강제 재출제**(Butler 2011: 확신오답은 1주 내 relapse). 범용 Leitner가 아닌 원칙적 트리거.
- §8 SRS 규칙 확장: 기존 `is_correct=false → 복습` 위에 위 우선순위를 얹는다.

---

## 6. §7 열린 것 — 갱신

| 항목 | v6 상태 |
|---|---|
| 시험모드 채점 후 리뷰 | ✅ review 상태로 설계됨 (§1 위) |
| 개념망·맞춤추천 상세 | ⬜ 유지 — 스레드2 산출물 대기 |
| CPX/OSCE 루프 | ⬜ 유지 |
| 난이도 티어 데이터 소스 | ⬜ 신규 — attempts p-value 롤링 (PA-04) |

---

## 7. PA 티켓 ↔ 스펙 섹션 매핑

| PA | 내용 | 스펙 섹션 | 난이도 |
|---|---|---|---|
| PA-01 | 오답선지 분포 학생노출 | §5.5 (a) | quick |
| PA-02 | 문항-모드 풀(오답/미풀이/북마크) | §5.4 (이미 고급설정에 있음, 풀 계산 확인) | quick |
| PA-03 | 3축 SE 게이트 + blueprint | §5.6 | medium |
| PA-04 | 경험적 p-value 5티어 | §5.4 + 스레드2 축 | quick |
| PA-05 | 세션점수 Wilson 구간 | §5.6 | quick |
| PA-06 | fast_wrong 큐 + confident-error SRS | §8 | medium |
| PA-07 | 오개념 라우팅 | §5.5 (b) | medium |
| PA-08 | 시험/학습 모드 + review | §1(상태머신)·§5.5 | medium |

---

## 8. 가드레일 (전 델타 공통)

- percentile·리더보드 학생 비노출 유지·강화.
- 표본 게이트: 문항 attempts <5 "자료 부족" / 5–19 descriptive / ≥20 지표. IRT는 Rasch까지만(2PL/3PL 금지, 소규모 N).
- 포지셔닝: 문제은행 숙달 = T1(시험지식) 성과. 임상역량 전이 약속 금지.
- 원문 stem 외부전송 금지, `data_private/` 경계.

---

## 9. 변경 이력 (스펙 §9에 추가 제안)

| 날짜 | 버전 | 변경 |
|---|---|---|
| 2026-07-13 | v6(델타) | 14축 검증 리서치 반영. review 1급 승격(§4), 경험적 난이도 티어+적응형 기본 문항수(§5.4), 리더 reveal 3추가—오답분포·오개념 라우팅·근거 blocking(§5.5), 리포트 Wilson구간+3축 SE게이트+blueprint(§5.6), fast_wrong per-item 정규화+confident-error SRS(§8). D1~D7 유지. |
