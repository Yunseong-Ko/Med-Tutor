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

VSCode, 가상환경 명령어 없이 실행할 수 있습니다.

- macOS: `start_medtutor.command` 더블클릭
- Windows: `start_medtutor.bat` 더블클릭

최초 1회에 자동으로 수행됩니다.

- `.venv` 가상환경 생성
- `requirements.txt` 의존성 설치
- `streamlit run app.py` 실행

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

