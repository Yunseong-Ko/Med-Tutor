# CPX Station Lab

CPX/OSCE 시험 대비용 독립형 웹앱입니다. 현재 폴더의 `index.html`을 브라우저로 열면 바로 사용할 수 있습니다.

## 들어간 기능

- 사용자 요청 주제 18개 케이스 수록
- OSCE 술기 4개 추가: ABGA, 수혈, 혈액배양 채혈, 베타딘 상처관리
- 12분 스테이션 타이머와 단계별 흐름 안내
- 좌측 케이스 목록 책갈피형 접기/펼치기: 좁은 화면이나 집중 학습 시 본문 공간 확장
- 케이스 이동 시 현재 탭과 좌측 목록 위치 유지
- 상단 `시험범위` 버튼: 2026년 3학년 1학기 실기시험 운영 요약, 6문항 구성, 준비물, PPI 주의사항
- 상단 `기출소재` 버튼: `본3 부경 (2).xlsx`의 61개 기출 주제 전체 보관, 확장용 랜덤 환자 케이스 제공
- 케이스별 `공부대본` 탭: 첫 문장, 문진 순서, 진찰/검사 선언, 설명/계획, 마무리 문장
- 케이스별 `진단노트` 탭: 정의, 진단 기준/핵심 단서, 확인 검사, 감별 함정
- 케이스별 `진찰가이드` 탭: 복부, DRE, 골반진찰, 무릎, 신경학적 진찰, 소아 발달 관찰, OSCE 술기 순서
- 진찰/술기별 공개 영상·사진 자료 링크: Murphy sign, DRE, ABGA, 수혈, 혈액배양, 상처관리 등
- 케이스별 문진, 진찰/검사, 설명, 마무리 체크리스트
- 필수 항목 누락 표시와 영역별 점수
- 환자 역할 답변 카드
- 케이스별 누락 항목과 공부 흐름을 읽어 답하는 `실전 코치` 대화 패널
- `AI실전` 탭: AI 표준화환자와 1:1 실전 문진 연습, 종료 후 체크리스트 기준 채점과 다음 회독용 5문장 제공
- 케이스별 메모 자동 저장
- 진행도 JSON 내보내기와 인쇄용 체크리스트

## AI 표준화환자 실전모드

- 중앙 `AI실전` 탭 또는 실전 코치의 `AI 환자 시작` 버튼으로 시작합니다.
- AI는 환자 역할만 하며, 물어본 것에만 답하고 진단명/검사계획을 먼저 말하지 않습니다.
- `마무리했습니다` 입력 또는 `채점하기` 버튼으로 면담을 끝내면 잘한 점, 필수 누락, 시험장에서 빠지면 위험한 말, 다음 회독용 5문장, 치료계획 말하기 방식을 돌려줍니다.
- 막히면 `첫 문장` / `치료계획` / `누락 확인` / `마무리` 힌트 버튼을 쓸 수 있고, `힌트 없이` 모드로 끌 수 있습니다.
- 구조: 프론트는 `ai-patient.js`의 `window.CpxAI` 경계만 호출하고, 실제 LLM은 Cloudflare Pages Function(`functions/api/cpx-chat.js`)이 서버 환경변수 `ANTHROPIC_API_KEY`로 Claude API를 호출합니다. 환자 역할은 `claude-haiku-4-5`(빠르고 저렴), 채점은 `claude-sonnet-5`(JSON 스키마 강제 채점)를 사용하며 `ANTHROPIC_PATIENT_MODEL` / `ANTHROPIC_GRADER_MODEL` 환경변수로 바꿀 수 있습니다. API 키가 없거나 서버가 응답하지 않으면 케이스 데이터 기반 로컬 mock 환자/간이 채점으로 자동 전환됩니다(화면에 `로컬 연습 모드` 배지 표시).
- 대화 기록과 채점 결과는 localStorage에 저장되며 `내보내기` JSON에 포함됩니다.

### 배포 (Cloudflare Pages)

1. 정적 파일을 `dist/`에 동기화한 뒤 프로젝트 루트에서 `npx wrangler pages deploy` 실행 (`wrangler.toml`이 `dist`와 루트 `functions/`를 함께 배포).
2. Cloudflare Pages 대시보드 > Settings > Environment variables 에 `ANTHROPIC_API_KEY`(Secret)를 설정하거나, 터미널에서 `npx wrangler pages secret put ANTHROPIC_API_KEY --project-name med-tutor-cpx-osce` 실행.
3. 키 설정 전에는 자동으로 mock 모드로 동작하므로 배포 순서는 자유롭습니다.
4. 로컬에서 Function까지 테스트하려면 루트에 `.dev.vars`(`ANTHROPIC_API_KEY=sk-ant-...`)를 만들고 `npx wrangler pages dev dist`.

## 학습 문서

- [CPX/OSCE 실전 가이드라인 및 예시 대본](guides/cpx_osce_guidelines_and_scripts.md)
- [2026 실기시험 범위/운영 요약](guides/2026_practical_exam_scope_summary.md)
- [본3 부경 기출 정리 전체 보관함](guides/past_exam_archive_summary.md)

## 자료 사용 원칙

- 사용자가 제공한 CPX/OSCE PDF는 12분 시험 흐름과 공통 구조 참고용으로 사용했습니다.
- 사용자가 제공한 2026년 실기시험 세부계획서 HWP는 시험 운영 구조와 준비물 참고용으로 사용했고, 응시번호/이름/개인별 위치 표는 반영하지 않았습니다.
- 사용자가 제공한 `본3 부경 (2).xlsx`는 이번 22개 집중 케이스와 분리해 사이트 확장용 기출소재 보관함으로 반영했습니다.
- 학생 대본 파일은 말하는 순서와 실전 표현감을 보는 참고용으로만 사용했습니다.
- 의학 지식은 질병관리청, CDC, NICE, KDIGO, ACG, WHO 등 공식 지침과 공신력 있는 자료를 우선해 재구성했습니다.
- 신체진찰 순서는 Stanford Medicine 25, Geeky Medics, SimpleOSCE 등 공개 임상교육 자료를 참고하되 앱용 문장으로 새로 요약했습니다.
- 영상과 사진 자료는 앱 안에 복제하지 않고 Stanford Medicine 25, CDC, NHS/NHSBT, Oxford Medical Education, Geeky Medics, AMBOSS YouTube 등 외부 공개 링크로만 연결했습니다.
- AMBOSS, UpToDate, 알렌의서재는 개념 교차확인과 시험식 표현 흐름 참고용으로만 사용했고 원문을 옮기지 않았습니다.
- 원문 케이스, 표, 대본, 유료 콘텐츠를 그대로 복제하지 않고 앱용 문장으로 새로 작성했습니다.

## 주의

이 앱은 시험 연습용 학습 도구입니다. 실제 진료, 처방, 예방접종 일정, 학교별 CPX 채점 기준은 최신 지침과 소속 기관 자료를 확인하세요.
