# Axioma Qbank

의대생이 강의자료와 기출문제를 빠르게 문제은행으로 전환하고 학습·시험·복습을 한 흐름에서 진행할 수 있는 앱입니다.

## Overview
Axioma Qbank는 로컬 문서(PDF, DOCX, PPTX, HWP 등)를 기반으로 문제를 생성·관리하는 Streamlit 앱입니다.
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
- Supabase Auth 기반 사용자 로그인 및 사용자별 데이터 분리 저장
- 테마는 기본 적용(라이트 톤)이며, 사이드바 테마 토글은 제거

## How To Use

### Desktop Version
1. [Latest Release](https://github.com/Yunseong-Ko/Med-Tutor/releases/latest)로 이동합니다.
2. `Assets`에서 운영체제에 맞는 파일을 받습니다(`AxiomaQbank-macos.zip` 또는 `AxiomaQbank-windows.zip`).
3. 압축을 해제합니다.
4. 실행합니다(macOS: `AxiomaQbank.app` 우클릭 → `열기`, Windows: `AxiomaQbank.exe` 더블클릭).
5. 브라우저에서 `http://localhost:8501`이 열리면 정상입니다.

Python 설치 필요 여부:
- Desktop 배포본은 Python 설치가 필요 없습니다(런타임 번들 포함).

Assets가 안 보이거나 다운로드가 안 될 때:
- 해당 릴리즈 빌드가 완료되지 않았을 수 있습니다.
- [Actions](https://github.com/Yunseong-Ko/Med-Tutor/actions)에서 `Build Standalone Apps` 성공 여부를 먼저 확인하세요.
- `Source code (zip)`은 실행 파일이 아니므로 받지 않습니다.
- macOS 실행 권한 오류가 나면 `chmod +x "/경로/AxiomaQbank.app/Contents/MacOS/AxiomaQbank"`를 실행합니다.
- 실행 실패 로그는 `launcher_error.log` 파일에서 확인합니다.

### Web Version
1. 운영자가 제공한 배포 URL(예: Streamlit Cloud/Render 링크)로 접속합니다.
2. 사이드바에서 회원가입/로그인을 진행합니다.
   - Supabase 설정 시: 이메일/비밀번호 로그인
   - Supabase 미설정 시: 로컬 파일 기반 로그인(데모용)
3. 업로드할 파일을 선택하고 문제를 생성합니다.
4. 학습 모드 또는 시험 모드로 바로 풀이를 시작합니다.
5. 필요 시 API 키를 입력합니다(운영 정책에 따라 서버 측 설정 가능).

### Mobile Version (iOS/Android WebView)
1. 이 방식은 웹 UI를 앱 컨테이너(WebView)로 여는 방식입니다. 핵심 화면/기능은 웹과 동일합니다.
2. 기본 목적은 모바일에서 `풀이 중심` 사용입니다. 문항 생성/대용량 업로드는 PC 사용을 권장합니다.
3. 모바일 래퍼는 `?mobile=1`을 전달해 실전 시험 화면을 터치 친화 UI로 표시합니다.
4. 테마는 앱 상단 메뉴에서 `System/Light/Dark`를 바꿀 수 있고, 웹앱에 `?theme=light|dark`로 전달됩니다.
5. Flutter SDK 설치 후 프로젝트 루트에서 아래를 실행합니다.
```bash
./scripts/create_mobile_shell.sh
```
6. Android 실행:
```bash
cd mobile_shell
flutter run -d android
```
7. iOS 실행(macOS + Xcode 필요):
```bash
cd mobile_shell
flutter run -d ios
```

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
- Env/Secrets:
- `OPENAI_API_KEY`, `GEMINI_API_KEY` (선택)
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` (로그인/영구 사용자 데이터 분리용)
- 데이터 경로: `AXIOMA_QBANK_DATA_DIR`(또는 레거시 `MEDTUTOR_DATA_DIR`)를 설정하면 저장 파일 위치를 고정할 수 있음
- 주요 로컬 데이터 파일:
- 글로벌: `questions.json`, `exam_history.json`, `user_settings.json`, `audit_log.jsonl`
- 사용자 분리 저장: `users/<user_id>/questions.json`, `users/<user_id>/exam_history.json`, `users/<user_id>/user_settings.json`, `users/<user_id>/audit_log.jsonl`

## Deployment
- Python 없이 실행하는 배포 방법: GitHub Actions standalone 빌드(`.app`/`.exe`)를 릴리즈에 올려 배포
- Desktop 패키징: `.github/workflows/build-standalone.yml`로 macOS/Windows standalone 빌드
- 로컬 배포: Release Assets(`AxiomaQbank-macos.zip`, `AxiomaQbank-windows.zip`) 전달
- 웹 배포(무료 데모 권장): Streamlit Community Cloud
- 모바일 WebView 배포: `mobile_shell/` Flutter 프로젝트를 빌드해 Android/iOS로 배포
- Streamlit Cloud 배포 순서:
1. 저장소를 GitHub에 푸시하고 Public 또는 접근 가능한 상태로 둡니다.
2. [Streamlit Community Cloud](https://share.streamlit.io/)에서 `New app` 선택
3. Repository: `Yunseong-Ko/Med-Tutor`, Branch: `main`, Main file path: `app.py`
4. Secrets에 필요한 키를 등록합니다(`OPENAI_API_KEY`, `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`)
5. Deploy 후 제공된 URL로 접속합니다.
- Streamlit Cloud 반영 확인 순서(운영자 체크리스트):
1. GitHub `main` 최신 커밋 해시를 확인합니다.
2. Streamlit Cloud 앱의 `Manage app` → `Reboot app`을 실행합니다.
3. `Logs`에서 아래 순서를 확인합니다.
   - `Pulling code changes from Github...`
   - `Processed dependencies!`
   - `Updated app!`
4. URL 접속 후 강제 새로고침(`Ctrl+Shift+R` 또는 `Cmd+Shift+R`)합니다.
5. 앱에서 방금 수정한 화면 요소가 보이는지 확인합니다.
   - 예: 생성/변환 탭의 저작권 확인 체크 UI
6. 반영이 안 되면 아래를 점검합니다.
   - 저장소가 `private`이면 Streamlit Cloud GitHub 연동 권한이 유효한지 확인
   - `fatal: could not read Username for 'https://github.com'`가 로그에 있으면 앱을 GitHub 재연결
   - Secrets 수정 후에는 반드시 `Reboot app` 재실행
- 베타 권장: Supabase Auth Email provider를 활성화하고, 초기 테스트에서는 이메일 확인 요구를 비활성화(선택)하면 가입/로그인이 빠릅니다.
- Supabase 테이블 생성(SQL Editor):
```sql
create table if not exists public.medtutor_user_data (
  user_id uuid primary key references auth.users(id) on delete cascade,
  questions jsonb not null default '{"text":[],"cloze":[]}'::jsonb,
  exam_history jsonb not null default '[]'::jsonb,
  user_settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.medtutor_user_data enable row level security;

create policy if not exists "select own data" on public.medtutor_user_data
for select using (auth.uid() = user_id);

create policy if not exists "insert own data" on public.medtutor_user_data
for insert with check (auth.uid() = user_id);

create policy if not exists "update own data" on public.medtutor_user_data
for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
```
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
- Supabase 미설정 상태에서는 로컬 파일 기반 로그인으로 동작하며 서버 재시작 시 데이터가 유지되지 않을 수 있습니다.
- Streamlit Community Cloud 무료 플랜은 절전/재시작이 발생할 수 있어 베타에서 지연이 생길 수 있습니다.

## Disclaimer (If Relevant)
- 본 도구는 학습 보조용이며 의료 판단/진단 도구가 아닙니다.
- 업로드 자료는 본인이 저작권을 보유했거나 사용 허락을 받은 자료만 사용해야 합니다.
- 서비스 내 변환/생성 기능은 저작권 확인 체크 이후에만 실행되며, 무단 복제·재배포 용도로 사용하면 안 됩니다.
- 업로드한 데이터 처리 및 저작권 준수 책임은 사용자/운영자에게 있습니다.
- 원문 파일은 기본적으로 세션 처리 후 폐기를 전제로 하며, 저장되는 것은 사용자가 저장한 문항 데이터(JSON)입니다.
- 외부 AI API 사용 시 각 제공사의 약관, 과금, 개인정보 정책을 확인해야 합니다.
