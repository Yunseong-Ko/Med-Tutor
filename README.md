# MedTutor

의대생이 강의자료와 기출문제를 빠르게 문제은행으로 전환하고 학습·시험·복습을 한 흐름에서 진행할 수 있는 앱입니다.

## Overview
MedTutor는 로컬 문서(PDF, DOCX, PPTX, HWP 등)를 기반으로 문제를 생성·관리하는 Streamlit 앱입니다.
기존 워크플로우에서 시간이 많이 들던 "문항 정리 → 시험 구성 → 복습 관리"를 하나의 화면에서 처리하도록 설계했습니다.
비개발자는 Python 설치 없이 데스크톱 실행 파일로 사용할 수 있고,
운영자는 웹으로 배포해 링크 기반으로 제공할 수도 있습니다.

## Why This Exists
- 의대 학습은 자료량이 많아 문항화/복습 준비 시간이 과도하게 소모됩니다.
- 기존 도구는 생성, 시험, 복습이 분리되어 있어 파일 이동과 재정리가 반복됩니다.
- 이 프로젝트는 문서 입력부터 시험/복습까지의 작업 시간을 줄이는 MVP를 검증하기 위해 만들었습니다.

## Core Features
- 문서 업로드 기반 문항 생성(객관식, 빈칸, 단답/서술형 일부 지원)
- 학습 모드/시험 모드, 분과·단원 필터 기반 문제 풀이
- 시험 기록 저장 및 리뷰(정답/해설 확인)
- FSRS(설치 시) 또는 기본 복습 스케줄 폴백
- 선택한 분과/단원 문항을 문제집 형식(DOCX)으로 내보내기
- 로컬 JSON/JSONL 저장(`questions.json`, `exam_history.json`, `audit_log.jsonl`)

## How To Use

### Desktop Version
1. [Latest Release](https://github.com/Yunseong-Ko/Med-Tutor/releases/latest)로 이동합니다.
2. `Assets`에서 운영체제에 맞는 파일을 받습니다(`MedTutor-macos.zip` 또는 `MedTutor-windows.zip`).
3. 압축을 해제합니다.
4. 실행합니다(macOS: `MedTutor.app` 우클릭 → `열기`, Windows: `MedTutor.exe` 더블클릭).
5. 브라우저에서 `http://localhost:8501`이 열리면 정상입니다.

Python 설치 필요 여부:
- Desktop 배포본은 Python 설치가 필요 없습니다(런타임 번들 포함).

Assets가 안 보이거나 다운로드가 안 될 때:
- 해당 릴리즈 빌드가 완료되지 않았을 수 있습니다.
- [Actions](https://github.com/Yunseong-Ko/Med-Tutor/actions)에서 `Build Standalone Apps` 성공 여부를 먼저 확인하세요.
- `Source code (zip)`은 실행 파일이 아니므로 받지 않습니다.
- macOS 실행 권한 오류가 나면 `chmod +x "/경로/MedTutor.app/Contents/MacOS/MedTutor"`를 실행합니다.
- 실행 실패 로그는 `launcher_error.log` 파일에서 확인합니다.

### Web Version
1. 운영자가 제공한 배포 URL(예: Streamlit Cloud/Render 링크)로 접속합니다.
2. 업로드할 파일을 선택하고 문제를 생성합니다.
3. 학습 모드 또는 시험 모드로 바로 풀이를 시작합니다.
4. 필요 시 API 키를 입력합니다(운영 정책에 따라 서버 측 설정 가능).

## Current Status
- 상태: MVP (실사용 테스트 단계)
- 강점: 로컬 실행, 빠른 문항화/시험화, 기본 복습 흐름
- 한계: 문서 품질/레이아웃에 따라 파싱 품질 편차가 있으며 일부 문항은 수동 편집이 필요합니다

## Technical Overview (For Developers)
- Stack: Python, Streamlit, JSON/JSONL, optional FSRS, optional Gemini/OpenAI API
- Local run:
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
- Dependency: `requirements.txt` 기준
- Env/Secrets: API 키는 사이드바 입력 또는 환경변수로 관리
- 데이터 경로: `MEDTUTOR_DATA_DIR`를 설정하면 저장 파일 위치를 고정할 수 있음
- 주요 로컬 데이터 파일: `questions.json`, `exam_history.json`, `user_settings.json`, `audit_log.jsonl`

## Deployment
- Python 없이 실행하는 배포 방법: GitHub Actions standalone 빌드(`.app`/`.exe`)를 릴리즈에 올려 배포
- Desktop 패키징: `.github/workflows/build-standalone.yml`로 macOS/Windows standalone 빌드
- 로컬 배포: Release Assets(`MedTutor-macos.zip`, `MedTutor-windows.zip`) 전달
- 웹 배포(무료 데모 권장): Streamlit Community Cloud
- Streamlit Cloud 배포 순서:
1. 저장소를 GitHub에 푸시하고 Public 또는 접근 가능한 상태로 둡니다.
2. [Streamlit Community Cloud](https://share.streamlit.io/)에서 `New app` 선택
3. Repository: `Yunseong-Ko/Med-Tutor`, Branch: `main`, Main file path: `app.py`
4. Secrets에 필요한 키를 등록합니다(`OPENAI_API_KEY`, `GEMINI_API_KEY`)
5. Deploy 후 제공된 URL로 접속합니다.
- 단일 사용자/단일 인스턴스: 로컬 JSON/SQLite로 충분
- 다중 사용자 확장: 서버 DB(Postgres 등)와 인증 계층 필요

## Roadmap
- [ ] 문항 추출 정확도 개선(문서 레이아웃별 파서 안정화)
- [ ] 이미지 문항 매칭 개선(수동 보정 UX 포함)
- [ ] 웹 배포 템플릿 고정화(Secrets, DB 경로, 로그 정책)
- [ ] 초기 사용자 온보딩(튜토리얼/샘플 데이터)

## Limitations
- HWP/PDF 품질 및 표 구조에 따라 변환 결과가 달라질 수 있습니다.
- 이미지-문항 자동 매칭은 완전 자동화가 어렵고 확인 단계가 필요합니다.
- Desktop 번들은 용량이 큽니다(파이썬 런타임 포함).
- 로컬 저장소 기반이므로 다중 사용자 동시 편집에는 적합하지 않습니다.

## Disclaimer (If Relevant)
- 본 도구는 학습 보조용이며 의료 판단/진단 도구가 아닙니다.
- 업로드한 데이터 처리 책임은 사용자/운영자에게 있습니다.
- 외부 AI API 사용 시 각 제공사의 약관, 과금, 개인정보 정책을 확인해야 합니다.
