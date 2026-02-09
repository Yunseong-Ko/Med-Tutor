# 🧬 Med-Tutor: 의대생 AI 튜터

방대한 의학 강의 자료를 AI가 자동으로 **시험 문제**와 **암기 카드(Anki)**로 변환해주는 도구입니다.

## 📋 핵심 기능

### 1️⃣ 멀티 포맷 지원
- **PDF** (`PyMuPDF`)
- **Word 문서** (`.docx`) - `python-docx`
- **PowerPoint** (`.pptx`) - `python-pptx`

### 2️⃣ 이중 생성 모드

| 모드 | 용도 | 출력 형식 |
|------|------|---------|
| **📝 객관식 문제** | 실전 시험 대비 | 5지선다 + 해설 |
| **🧩 빈칸 뚫기** | Anki 암기 카드 | Cloze 형식 |

---

## 🚀 설치 및 실행

### 1단계: 환경 설정

```bash
# 프로젝트 디렉토리 이동
cd ~/Documents/AI\ Projects/Med-Tutor

# 가상환경 생성 (처음 한 번만)
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate  # macOS/Linux
# 또는
venv\Scripts\activate  # Windows
```

### 2단계: 의존성 설치

```bash
pip install -r requirements.txt
```

### 3단계: Gemini API 키 획득

1. [Google AI Studio](https://aistudio.google.com/app/apikey)에서 **API 키 생성**
2. 키를 안전한 곳에 저장

### 4단계: 앱 실행

```bash
streamlit run app.py
```

자동으로 브라우저에서 `http://localhost:8501` 로 열립니다.

---

## 📖 사용 방법

### 단계별 가이드

1. **API 키 입력**
   - 왼쪽 사이드바의 입력 필드에 Gemini API 키를 붙여넣기

2. **모드 선택**
   - "📝 객관식 문제" 또는 "🧩 빈칸 뚫기" 선택

3. **파일 업로드**
   - PDF, Word, PowerPoint 파일을 드래그 앤 드롭
   - 또는 클릭하여 선택

4. **분석 시작**
   - "🚀 AI 분석 시작" 버튼 클릭
   - 처리 진행 상태 확인 (보통 30초~2분)

5. **결과 다운로드**
   - 생성된 텍스트 미리보기
   - "📥 텍스트 파일로 다운로드" 클릭

### Anki에 임포트하기

생성된 파일을 Anki에 임포트:
1. Anki 앱 열기
2. `File > Import`
3. 다운로드한 `.txt` 파일 선택
4. 임포트 설정 확인 후 완료

---

## 🛠 기술 스택

- **UI**: Streamlit
- **AI Model**: Google Gemini 1.5 Flash
- **데이터 처리**:
  - PDF: PyMuPDF (`fitz`)
  - Word: python-docx
  - PowerPoint: python-pptx

---

## 💡 프롬프트 커스터마이징

`app.py`의 `PROMPT_MCQ`와 `PROMPT_CLOZE`를 수정하여:
- 생성되는 문제의 난이도 조절
- 형식 변경
- 언어 변경 등을 할 수 있습니다.

---

## ⚠️ 주의사항

- **API 할당량**: 무료 계정의 경우 하루 최대 60요청 제한
- **문서 크기**: 30,000 글자까지만 AI 분석 가능 (초과분은 자동 자름)
- **텍스트 레이어**: 스캔된 이미지 PDF는 OCR 미지원

---

## 📊 향후 계획 (Roadmap)

- **Phase 2**: 직접 `.apkg` (Anki 패키지) 생성
- **Phase 3**: OCR로 이미지 기반 자료 지원
- **Phase 4**: 음성 파일 STT 변환

---

## 📧 문제 보고

버그나 기능 건의는 이 저장소의 Issues에 등록해주세요.

---

## 📄 라이선스

MIT License

---

**제작자**: Yunseong Ko (Noah)
**마지막 업데이트**: 2026년 2월 8일
