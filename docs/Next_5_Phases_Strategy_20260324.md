# Axioma Qbank 다음 5단계 전략 기획서

## 1. 문서 목적
- 현재까지 구현된 `문제 생성 -> 저장 -> 학습/시험 -> 복습` 흐름을 바탕으로, 다음 5단계 제품/기술 우선순위를 정리한다.
- 가장 중요한 목표는 `문제를 뽑는 시간`과 `사이트 체감 속도`를 줄이는 것이다.
- 그 다음으로, 이미 존재하는 강의자료 기반 생성 기능을 `지속 사용하게 만드는 학습 플랫폼`으로 확장한다.

## 2. 현재 상태 요약
Axioma Qbank는 이미 아래 흐름을 지원한다.
- 강의자료/기출 업로드
- Basic / Case / Mix / Auto 기반 문제 생성
- 계정별 저장
- 학습/시험 모드 풀이
- 시험 기록, 오답, 해설, 일부 AI 보조 기능

하지만 실제 사용성 기준으로 가장 큰 병목은 다음이다.
- 생성 대기 시간이 길다
- 페이지 이동 시 무겁다
- 생성된 문제를 장기적으로 정리/반복하는 UX는 아직 약하다

따라서 다음 단계는 "기능을 더 붙이는 것"보다 `속도 -> 반복 사용 -> 개인화 -> 기관화 -> 플랫폼화` 순서로 가는 것이 맞다.

---

## 3. 단계별 전략

### Phase 1. 성능 최적화와 체감 속도 개선
#### 목표
- 사용자가 가장 먼저 불편함을 느끼는 `문항 생성 시간`과 `페이지 렌더 속도`를 줄인다.

#### 왜 지금 먼저 해야 하나
- 현재 베타 단계에서 가장 직접적인 이탈 요인은 기능 부족보다 "기다림"이다.
- 같은 기능이라도 느리면 가치가 급격히 떨어진다.

#### 핵심 작업
- 파일 해시 기반 영속 전처리 캐시
- 홈/시험 페이지 lazy-load
- 질문 집계 결과 캐시
- 생성 작업과 UI 렌더 분리
- 진행 상태 표시 고도화

#### 참고할 레퍼런스
- AMBOSS: Study mode / Exam mode 분리와 custom session 흐름이 명확함  
  https://support.amboss.com/hc/en-us/articles/360036038991-Using-Study-Mode-Exam-Mode  
  https://support.amboss.com/hc/en-us/articles/360032477132-Creating-a-Qbank-session
- BARBRI: 개인 학습 계획이 매일 자동 재조정됨  
  https://www.barbri.com/en/personal-study-plan

#### Axioma에 적용하는 해석
- AMBOSS처럼 "바로 문제를 푸는 상태"로 진입시키고
- BARBRI처럼 기다리는 시간을 사용자가 예측 가능한 상태로 만들어야 한다.

#### 성공 기준
- 동일 자료 재생성 시 대기열 추가가 즉시 끝난다
- 홈/시험 페이지 첫 진입 시간이 체감상 짧아진다
- 10문항 생성 요청 시 사용자가 "기다릴 수 있는 수준"이 아니라 "미리 예측 가능한 수준"이 된다

---

### Phase 2. Qbank 사용성 완성
#### 목표
- 생성된 문제를 다시 쓰기 쉽게 만든다.
- `문제 생성기`에서 `실제로 반복 사용하는 Qbank`로 넘어간다.

#### 핵심 작업
- Saved Session Templates
- Question Status Filters
- Review-First UX
- 틀린 문제 -> 북마크/메모/재풀이 흐름 강화
- 세션 저장 및 빠른 재호출

#### 참고할 레퍼런스
- UWorld: 해설 중심 복기 경험과 성과 분석  
  https://medical.uworld.com/usmle/features/  
  https://medical.uworld.com/our-difference/active-learning/
- Quizlet: Learn / Test 모드와 개인화 홈 피드  
  https://help.quizlet.com/hc/en-us/articles/360030986971-Studying-with-Learn-mode  
  https://quizlet.com/features/study-modes  
  https://help.quizlet.com/hc/en-us/articles/38999971996301-Navigating-your-home-feed-on-mobile-devices
- HackerRank: mock test + detailed performance report 구조  
  https://help.hackerrank.com/articles/9054300007-hackerrank-subscription-plans

#### Axioma에 적용하는 해석
- UWorld처럼 "문항 하나의 해설 가치"를 올리고
- Quizlet처럼 "다음에 무엇을 할지"를 홈에서 제안하고
- HackerRank처럼 "시험 한 번 보고 끝"이 아니라 리포트와 재시도 흐름을 붙여야 한다.

#### 성공 기준
- 사용자가 새 문제를 뽑지 않아도 기존 문제은행만으로 재학습할 수 있다
- 북마크 / 오답 / 미풀이 / 최근 생성 필터가 실사용된다
- 시험 후 리뷰까지의 전환율이 높아진다

---

### Phase 3. 스타일 적합도와 개인화 생성 강화
#### 목표
- "내 시험 스타일에 맞는 문제를 만든다"는 Axioma의 핵심 차별점을 더 분명히 만든다.

#### 핵심 작업
- 교수/과목/강의별 Style Profile
- 용어 표기 규칙 자동 추정 고도화
- Basic / Case / Mix 비율 프로파일화
- 생성 품질 피드백 수집
- AI 해설 / 힌트 / 보정 프롬프트 체계화

#### 참고할 레퍼런스
- AMBOSS: 토픽, 상태, 난이도 기준의 세밀한 Qbank 필터  
  https://support.amboss.com/hc/en-us/articles/360034825692-Platform-overview
- BARBRI: 사용자의 진행/시간에 따라 학습 계획을 다시 맞춤  
  https://www.barbri.com/en/personal-study-plan
- Anki: FSRS 기반 복습 개인화  
  https://docs.ankiweb.net/deck-options

#### Axioma에 적용하는 해석
- AMBOSS는 문제를 고르는 쪽에서 개인화를 하고,
- Anki는 복습 스케줄에서 개인화를 한다.
- Axioma는 그 중간인 `문제 생성 자체`를 개인화해야 한다.

#### 성공 기준
- 같은 강의자료라도 스타일 파일 유무/과목 특성에 따라 결과가 눈에 띄게 달라진다
- 사용자가 "이건 우리 학교 시험 느낌 난다"라고 체감한다
- 품질 피드백이 다음 생성 품질 개선에 연결된다

---

### Phase 4. 기관/교육실용 기능 확장
#### 목표
- 개인 학습 도구를 넘어 교수/교육실이 관리 가능한 도구로 확장한다.

#### 핵심 작업
- Assignment Mode
- cohort analytics
- 교수 검수 완료 문제은행
- 분반/수업별 배포
- 운영자 리포트

#### 참고할 레퍼런스
- AMBOSS Teaching / Educator 기능  
  https://support.amboss.com/hc/en-us/articles/360034825692-Platform-overview
- Quizlet Classes / Learn & Test access 구조  
  https://help.quizlet.com/hc/en-au/articles/34270983035149-Free-student-access-to-Learn-and-Test-modes
- BARBRI: 학습 코치, 진행관리, 개인 일정 지원  
  https://www.barbri.com/sqe/sqe1-prep

#### Axioma에 적용하는 해석
- 교육실 입장에서는 "AI가 문제를 만든다"보다
  - 학생들이 실제로 풀었는지
  - 어느 단원이 약한지
  - 어떤 자료가 반복 활용되는지
  가 더 중요하다.

#### 성공 기준
- 교수/조교가 세션을 만들고 학생들에게 배포할 수 있다
- 수업 단위 성과 분석이 가능하다
- 기관 계약 시 설명 가능한 관리 지표가 생긴다

---

### Phase 5. 플랫폼화와 멀티채널 확장
#### 목표
- Axioma를 단일 웹앱이 아니라, 장기적으로 확장 가능한 학습 플랫폼으로 만든다.

#### 핵심 작업
- 백그라운드 워커 구조
- 생성 파이프라인 지속 저장
- 모바일 우선 풀이 UX 강화
- API/외부 연동 구조 정리
- 향후 LMS/학교 계정 연동 가능성 열어두기

#### 참고할 레퍼런스
- HackerRank: role-specific prep, mock test, AI tutor 분리 구조  
  https://help.hackerrank.com/articles/1723224478-introduction-to-prep-kits  
  https://help.hackerrank.com/articles/9054300007-hackerrank-subscription-plans
- Anki: 확장 가능한 add-on 생태계  
  https://docs.ankiweb.net/addons.html
- Quizlet 모바일 홈 피드: 추천 중심 진입 UX  
  https://help.quizlet.com/hc/en-us/articles/38999971996301-Navigating-your-home-feed-on-mobile-devices

#### Axioma에 적용하는 해석
- 앞으로는 웹에서만 잘 되는 것이 아니라
  - 생성은 백엔드/워커가 하고
  - 사용자는 웹/모바일에서 문제를 푸는 구조가 되어야 한다.

#### 성공 기준
- 생성 중에도 서비스 전체가 버벅이지 않는다
- 모바일에서 풀이 중심 경험이 자연스럽다
- 향후 학교/기관 시스템과 연결 가능한 구조가 된다

---

## 4. 우선순위 결론
현재 기준으로 가장 중요한 순서는 아래다.

1. 성능 최적화
2. Qbank 사용성 완성
3. 스타일 적합도/개인화 강화
4. 기관용 기능
5. 플랫폼화

이 순서가 중요한 이유는,
- 느리면 사용자가 떠나고
- 반복 사용성이 없으면 재방문이 줄고
- 개인화가 약하면 차별점이 흐려지고
- 기관 기능은 그 위에서만 가치가 생기기 때문이다.

---

## 5. 실제 실행 제안
가장 현실적인 다음 행동은 아래다.

### 바로 구현할 것
- 영속 전처리 캐시
- 홈/시험 lazy-load
- Saved Session Templates
- 문제 상태 필터

### 바로 기획만 할 것
- Style Profile schema
- Assignment / educator flow
- worker architecture

---

## 6. 최종 요약
Axioma Qbank의 다음 단계는 "더 많은 AI 기능"이 아니라,  
`더 빨리 생성하고`, `더 자주 다시 풀게 만들고`, `더 내 시험에 맞게 조정하고`, `나중에는 기관 운영까지 가능하게 만드는 것`이다.

즉, 제품 전략의 중심은 다음 한 줄로 정리된다.

**강의자료 기반 생성형 Qbank를, 실제 반복 학습과 운영이 가능한 학습 플랫폼으로 전환한다.**
