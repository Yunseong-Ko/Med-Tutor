# MedTutor

의대생 학습 자료를 문제은행으로 변환하고, 시험/학습/복습 흐름으로 관리하는 Streamlit 앱입니다.

## 현재 구현 상태 (2026-02-19)

- 홈
- 학습 통계(정답률, 활동 히트맵), 분과/단원 요약, 시험 기록 조회, 빠른 세션 시작
- 문제 생성
- PDF/DOCX/PPTX/HWP 업로드, 객관식/빈칸 생성, 스타일 파일(기출 스타일) 참고 생성, 결과 미리보기/저장
- 기출문제 변환
- 파일 변환 후 문항 미리보기, 수동 편집, 저장 전 점검
- 실전 시험
- 시험모드/학습모드, 분과-단원 계층 선택, 문항 네비게이션, 채점/리뷰, 메모
- 학습모드에서 정답 확인 후 해설 표시, 필요 시 AI 해설 생성
- 복습 주기
- `fsrs` 설치 시 FSRS 사용, 미설치 시 기본 SRS 폴백
- 문항 관리
- 객관식 개별 삭제, 세트 삭제, 분과별 삭제, 문항 개별 수정
- 안정성
- 생성 실패 복구 패널, 표 렌더링 폴백(`safe_dataframe`), 프로필 불러오기 방어 로직

## 비개발자용 실행 (권장)

아래 2가지 중 하나를 선택해 실행하면 됩니다.

### A) 운영자가 배포한 실행파일로 실행 (Python 설치 불필요)

이 방식이 가장 쉽습니다.

공통 다운로드 링크:

- [Latest Release](https://github.com/Yunseong-Ko/Med-Tutor/releases/latest)

다운로드 전에 꼭 확인:

1. `Assets`에서 `MedTutor-macos.zip` 또는 `MedTutor-windows.zip`을 받습니다.
2. `Source code (zip)`은 앱 실행 파일이 아니라 소스코드이므로 비개발자는 받지 않습니다.
3. ZIP을 받은 뒤에는 압축을 먼저 해제합니다.

#### macOS 실행 절차

1. [Latest Release](https://github.com/Yunseong-Ko/Med-Tutor/releases/latest) 페이지 진입
2. `Assets` 목록에서 `MedTutor-macos.zip` 클릭
3. `다운로드` 폴더에서 ZIP 더블클릭하여 압축 해제
4. 압축 해제 후 `MedTutor.app` 확인
5. `MedTutor.app` 우클릭 `열기` 선택
6. 보안 경고가 한 번 더 나오면 `열기`를 다시 선택
7. 브라우저에서 `http://localhost:8501` 열리면 정상 실행

macOS에서 앱이 열리지 않을 때(구버전 배포본 대응):

1. 터미널 실행
2. 아래 명령 실행

```bash
chmod +x "/경로/MedTutor.app/Contents/MacOS/MedTutor"
```

3. 다시 `MedTutor.app` 우클릭 `열기`

#### Windows 실행 절차

1. [Latest Release](https://github.com/Yunseong-Ko/Med-Tutor/releases/latest) 페이지 진입
2. `Assets` 목록에서 `MedTutor-windows.zip` 클릭
3. `다운로드` 폴더에서 ZIP 우클릭 `모두 압축 풀기`
4. 생성된 `MedTutor-windows` 폴더 열기
5. `MedTutor.exe` 더블클릭
6. SmartScreen 경고가 나오면 `추가 정보 > 실행`
7. 브라우저에서 `http://localhost:8501` 열리면 정상 실행

### B) 저장소 폴더에서 실행 스크립트로 실행 (Python 설치 필요)

운영자 배포본이 없을 때 사용하는 방법입니다. VSCode는 필요 없습니다.

1. 저장소 ZIP을 내려받아 압축 해제합니다.
2. 프로젝트 폴더를 엽니다.
3. 실행 스크립트를 더블클릭합니다.
- macOS: `start_medtutor.command`
- Windows: `start_medtutor.bat`
4. 첫 실행은 자동 설치가 진행되어 2-10분 정도 걸릴 수 있습니다.
5. 브라우저에서 `http://localhost:8501`이 열리면 실행 완료입니다.

스크립트가 첫 실행 때 자동으로 수행하는 작업:

1. `.venv` 가상환경 생성
2. `pip` 업데이트
3. `requirements.txt` 설치
4. `streamlit run app.py` 실행

참고: `.venv/.medtutor_installed` 파일이 생성되면 다음 실행부터 설치 과정을 건너뜁니다.

### 실행 후 앱에서 해야 할 일

1. 왼쪽 사이드바에서 사용할 모델을 선택합니다.
2. API 키를 입력합니다.
- Gemini: [Google AI Studio](https://aistudio.google.com/app/apikey)
- OpenAI: [OpenAI API keys](https://platform.openai.com/api-keys)
3. `문제 생성` 또는 `기출문제 변환` 탭에서 파일 업로드를 시작합니다.

### 종료 방법

1. 앱을 띄운 터미널/명령 프롬프트 창으로 이동합니다.
2. `Ctrl + C`를 눌러 종료합니다.
3. 창을 닫습니다.

### 자주 발생하는 실행 문제

1. 더블클릭해도 바로 꺼짐
- B 방식(스크립트 실행)에서는 Python 3 미설치일 수 있습니다.
2. 권한/보안 경고로 실행 차단
- macOS 우클릭 `열기`, Windows `추가 정보 > 실행`으로 1회 허용합니다.
3. 브라우저가 자동으로 안 열림
- 주소창에 `http://localhost:8501`을 직접 입력합니다.
4. `8501` 포트가 이미 사용 중이라고 나옴
- 기존 실행 창을 닫고 다시 실행하거나, 기존 Streamlit 프로세스를 종료합니다.

## Python 없이 실행하는 배포 방법 (운영자용)

최종 사용자가 Python 3를 설치하지 않도록 하려면, 실행 파일을 먼저 빌드해서 배포하면 됩니다.

### 1) GitHub Actions로 자동 빌드

이 저장소에는 독립 실행파일 빌드 워크플로우가 포함되어 있습니다.

- 경로: `.github/workflows/build-standalone.yml`
- 트리거:
1. `workflow_dispatch` (수동 실행)
2. `v*` 태그 푸시 (예: `v0.1.0`)
- 결과물:
1. `MedTutor-macos.zip` (`MedTutor.app` 포함)
2. `MedTutor-windows.zip` (`MedTutor.exe` 포함 폴더)

### 2) 사용자에게 배포

1. `v*` 태그 푸시 시 Actions가 빌드 후 Release 자산까지 자동 업로드합니다.
2. 사용자는 [Latest Release](https://github.com/Yunseong-Ko/Med-Tutor/releases/latest)에서 아래 파일을 받습니다.
- macOS: `MedTutor-macos.zip`
- Windows: `MedTutor-windows.zip`
3. 압축 해제 후 앱 파일을 실행합니다.

### 3) 참고

- macOS 사용자는 Gatekeeper 경고가 나오면 우클릭 `열기`로 실행합니다.
- Windows 사용자는 SmartScreen 경고 시 `추가 정보 > 실행`으로 진행합니다.
- 2026-02-19 기준 macOS 구버전 배포본에서 실행 권한 누락 이슈를 확인했고, 워크플로우에서 `chmod +x`를 추가해 수정했습니다.

## 수동 실행

```bash
cd /path/to/Med-Tutor
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

## API 키 설정

앱 좌측 사이드바에 모델 키를 입력합니다.

- Gemini: [Google AI Studio](https://aistudio.google.com/app/apikey)
- OpenAI: [OpenAI API keys](https://platform.openai.com/api-keys)

## 데이터 저장 위치

기본 실행 경로(개발 실행 시 프로젝트 폴더) 기준으로 아래 파일을 사용합니다.

- `questions.json`: 문제은행
- `exam_history.json`: 시험 기록
- `user_settings.json`: 사용자 설정
- `audit_log.jsonl`: 감사 로그(append-only)

## 테스트

```bash
python -m unittest discover -s tests -q
```

## 패키징 (옵션)

```bash
source .venv/bin/activate
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name MedTutor launcher.py --add-data "app.py:."
```

## 현재 제한사항

- HWP/PDF 원본 품질에 따라 문항 추출 품질이 달라질 수 있습니다.
- 이미지-문항 자동 매칭은 문서 레이아웃에 따라 오차가 발생할 수 있어 수동 확인이 필요합니다.
- OCR/AI 변환은 문서마다 후편집이 필요할 수 있습니다.
