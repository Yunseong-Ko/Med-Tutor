# Axioma Qbank 벤치마크 및 기능 기획안

## 1. 조사 목적
- 현재 Axioma Qbank에서 추가하면 체감 가치가 큰 기능을 찾는다.
- 단순히 기능 수를 늘리는 것이 아니라, `학생이 왜 돈을 내고 계속 쓰는지`를 기준으로 우선순위를 잡는다.

## 2. 벤치마크 서비스와 관찰 포인트

### UWorld
- 강점:
  - 정교한 해설
  - 시험 같은 풀이 경험
  - 오답 복기 흐름
  - 성과 추적
- 시사점:
  - Axioma도 "문항 생성기"를 넘어서 `해설 품질 + 리뷰 UX`가 핵심 경쟁력이 되어야 한다.

공식 링크:
- https://medical.uworld.com/

### AMBOSS
- 강점:
  - Qbank와 학습 라이브러리의 강한 결합
  - 학습 모드와 시험 모드 분리
  - 세밀한 필터링과 커스텀 세션
  - 모바일 친화성
- 시사점:
  - Axioma는 생성 문항을 `분과/단원/상태/오답 여부`로 강하게 필터링하는 방향이 맞다.

공식 링크:
- https://www.amboss.com/
- https://support.amboss.com/

### TrueLearn
- 강점:
  - 개인 성과 분석
  - cohort 비교
  - 약점 중심 재학습
- 시사점:
  - Axioma도 단순 정답률이 아니라 `내가 어느 단원에서 약한지`를 더 구체적으로 보여줄 필요가 있다.

공식 링크:
- https://truelearn.com/

### Lecturio
- 강점:
  - Qbank와 강의/개념 설명을 함께 묶음
  - AI 기반 학습 보조
- 시사점:
  - Axioma는 향후 `AI 해설`, `힌트`, `개념 연결`을 강화할 가치가 있다.

공식 링크:
- https://www.lecturio.com/

### BoardVitals
- 강점:
  - 시험 환경 중심
  - 커스텀 퀴즈
  - 세부 성과 분석
- 시사점:
  - Axioma도 `실전 모드`, `랜덤화`, `시간 제한`, `블록 시험` 기능이 더 중요해진다.

공식 링크:
- https://www.boardvitals.com/

### Osmosis Quiz Builder
- 강점:
  - active recall 강조
  - 지식 공백 우선 복습
- 시사점:
  - Axioma는 생성 이후 `무엇을 다시 풀게 할지` 추천하는 기능이 중요하다.

공식 링크:
- https://www.osmosis.org/

## 3. 공통 패턴
조사한 서비스들이 공통으로 잘하는 것은 아래 5가지다.

1. 단순 문제 제공이 아니라 `학습 흐름 전체`를 설계한다.
2. 해설과 리뷰 경험이 강하다.
3. 필터링이 세밀하다.
4. 약점 복습을 자동으로 추천한다.
5. 시험과 학습 모드를 명확히 분리한다.

## 4. Axioma에 가장 잘 맞는 추가 기능 아이디어

### P0. 지금 제품에 바로 붙일 가치가 큰 기능
#### 1) Saved Session Templates
- 예:
  - `의총 09단원 10문제`
  - `산부인과 기말대비 30문제`
  - `오답만 다시 풀기`
- 이유:
  - 반복 학습 시 세션 재구성 비용을 줄여준다.

#### 2) Question Status Filters
- 상태:
  - 미풀이
  - 오답
  - 북마크
  - 복습 예정
  - 최근 생성
- 이유:
  - Axioma의 생성 문항이 쌓일수록 정리 비용이 커지기 때문

#### 3) Review-First UX
- 시험 종료 후 바로:
  - 맞은 이유
  - 틀린 이유
  - 다시 보기
  - 북마크
  - 메모
  로 이어지는 구조 강화

#### 4) Quality Feedback on Generated Questions
- 버튼:
  - 좋음
  - 애매함
  - 틀림
  - 너무 쉬움
  - 너무 어려움
- 이유:
  - 생성 품질 학습 데이터 확보
  - 장기적으로 자동 품질 필터 정교화 가능

### P1. 중기적으로 강한 차별점이 되는 기능
#### 1) Style Profiles
- 강의/교수/과목별 스타일 프로파일 저장
- 예:
  - 용어 표기
  - 증례 길이
  - 문제 유형 분포
  - 자주 나오는 포맷
- 이유:
  - Axioma의 핵심 USP와 가장 직접 연결됨

#### 2) Hint Mode
- 정답 공개 전:
  - "검사 소견을 먼저 보세요"
  - "감별진단 2개를 비교해 보세요"
  같은 힌트 제공
- 이유:
  - UWorld/AMBOSS류와 달리 Axioma는 AI 힌트에 강점을 만들 수 있음

#### 3) Image/Table Focused Sessions
- 이미지 포함 문항만
- 표 해석형 문항만
- case-only / mechanism-only
- 이유:
  - 학교 시험에서 실제로 매우 유용한 세션 유형

#### 4) Explain-and-Flashcard Loop
- 틀린 문제를 바로 cloze/단답 카드로 변환
- 이유:
  - 생성 -> 풀이 -> 복습의 연결이 매우 강해짐

### P2. 기관/교육실 판매를 염두에 둔 기능
#### 1) Assignment Mode
- 교수/조교가 특정 세션을 만들어 배포
- 학생별 완료 현황과 오답 경향 확인

#### 2) Cohort Analytics
- 전체 학생 중 취약 단원 파악
- 수업 보강 포인트 도출

#### 3) Shared Reviewed Bank
- 교수 검수 완료 문항만 별도 라이브러리화

## 5. Axioma의 차별화 포인트 재정리
다른 Qbank는 이미 완성된 문제를 잘 푸는 플랫폼이다.  
Axioma는 `내가 가진 강의자료/기출을 기반으로 내 시험에 맞는 문제를 직접 생성하고, 그걸 다시 시험/복습 흐름으로 연결하는 플랫폼`이라는 점이 가장 다르다.

즉, Axioma가 이겨야 하는 포인트는 아래다.
- 생성 속도
- 내신/강의 맞춤성
- 스타일 적합도
- 생성 후 복습 루프 자동화

## 6. 추천 기능 우선순위
1. Saved Session Templates
2. Question Status Filters
3. Review-First UX
4. Quality Feedback on Generated Questions
5. Style Profiles
6. Hint Mode
7. Image/Table Focused Sessions
8. Explain-and-Flashcard Loop
9. Assignment Mode
10. Cohort Analytics

## 7. 결론
벤치마크 결과, Axioma가 추가해야 할 것은 새로운 화려한 기능보다 `생성된 문항을 더 잘 정리하고, 더 빨리 다시 풀게 만들고, 더 깊게 복습하게 만드는 기능`이다.  
즉, 다음 단계의 핵심은 `Qbank처럼 보이게 만드는 것`이 아니라 `생성형 Qbank의 반복 학습 경험을 완성하는 것`이다.

## 8. 참고 링크
- UWorld: https://medical.uworld.com/
- AMBOSS: https://www.amboss.com/
- AMBOSS Support: https://support.amboss.com/
- TrueLearn: https://truelearn.com/
- Lecturio: https://www.lecturio.com/
- BoardVitals: https://www.boardvitals.com/
- Osmosis: https://www.osmosis.org/
