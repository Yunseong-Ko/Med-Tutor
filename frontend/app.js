const form = document.querySelector("#generateForm");
const lectureFile = document.querySelector("#lectureFile");
const lectureLabel = document.querySelector("#lectureLabel");
const styleFiles = document.querySelector("#styleFiles");
const styleLabel = document.querySelector("#styleLabel");
const evidenceFiles = document.querySelector("#evidenceFiles");
const evidenceLabel = document.querySelector("#evidenceLabel");
const imageFiles = document.querySelector("#imageFiles");
const imageLabel = document.querySelector("#imageLabel");
const healthStatus = document.querySelector("#healthStatus");
const runStatus = document.querySelector("#runStatus");
const results = document.querySelector("#results");
const generateButton = document.querySelector("#generateButton");
const providerSelect = document.querySelector("#providerSelect");
const modelSelect = document.querySelector("#modelSelect");
const metricQuestions = document.querySelector("#metricQuestions");
const metricReview = document.querySelector("#metricReview");
const metricMedia = document.querySelector("#metricMedia");
const navReviewBadge = document.querySelector("#navReviewBadge");
const progressMessage = document.querySelector("#progressMessage");
const progressPanel = document.querySelector("#generationProgress");
const progressLabel = document.querySelector("#progressLabel");
const progressPercent = document.querySelector("#progressPercent");
const progressBar = document.querySelector("#progressBar");
const includeImagesToggle = document.querySelector("#includeImagesToggle");
const imagePolicySelect = document.querySelector("#imagePolicySelect");
const imagePolicyField = document.querySelector("#imagePolicyField");
const questionTypeSelect = document.querySelector('select[name="question_type"]');
const selectedMediaIdsInput = document.querySelector("#selectedMediaIds");
const mediaForm = document.querySelector("#mediaForm");
const mediaFile = document.querySelector("#mediaFile");
const mediaFileLabel = document.querySelector("#mediaFileLabel");
const mediaBank = document.querySelector("#mediaBank");
const mediaUploadButton = document.querySelector("#mediaUploadButton");
const mediaSearch = document.querySelector("#mediaSearch");
const selectedMediaCount = document.querySelector("#selectedMediaCount");
const mediaTypeFilters = Array.from(document.querySelectorAll("[data-media-type-filter]"));
const archiveList = document.querySelector("#archiveList");
const imageLightbox = document.querySelector("#imageLightbox");
const lightboxImage = document.querySelector("#lightboxImage");
const lightboxCaption = document.querySelector("#lightboxCaption");
const lightboxClose = document.querySelector("#lightboxClose");
const appTitle = document.querySelector("#appTitle");
const appSubtitle = document.querySelector("#appSubtitle");
const sidebarNoteTitle = document.querySelector("#sidebarNoteTitle");
const sidebarNoteCopy = document.querySelector("#sidebarNoteCopy");
const roleButtons = Array.from(document.querySelectorAll("[data-role-toggle]"));
const navGroups = Array.from(document.querySelectorAll("[data-nav-group]"));
const pageLinks = Array.from(document.querySelectorAll("[data-page-link]"));
const pageViews = Array.from(document.querySelectorAll("[data-page]"));
const facultyCategoryGrid = document.querySelector("#facultyCategoryGrid");
const studentCategoryGrid = document.querySelector("#studentCategoryGrid");
const medlegalCaseList = document.querySelector("#medlegalCaseList");
const medlegalCaseDetail = document.querySelector("#medlegalCaseDetail");
const medlegalNoteForm = document.querySelector("#medlegalNoteForm");
const medlegalNoteText = document.querySelector("#medlegalNoteText");
const medlegalFeedback = document.querySelector("#medlegalFeedback");
const medlegalSubmitButton = document.querySelector("#medlegalSubmitButton");
const courseExamForm = document.querySelector("#courseExamForm");
const courseExamFile = document.querySelector("#courseExamFile");
const courseExamFileLabel = document.querySelector("#courseExamFileLabel");
const answerKeyFile = document.querySelector("#answerKeyFile");
const answerKeyFileLabel = document.querySelector("#answerKeyFileLabel");
const courseExamButton = document.querySelector("#courseExamButton");
const courseExamImportResult = document.querySelector("#courseExamImportResult");
const studentExamSelect = document.querySelector("#studentExamSelect");
const studentPracticeMode = document.querySelector("#studentPracticeMode");
const startStudentPracticeButton = document.querySelector("#startStudentPractice");
const studentPracticeStatus = document.querySelector("#studentPracticeStatus");
const studentPracticeStage = document.querySelector("#studentPracticeStage");
const studentPracticePage = document.querySelector("#student-practice");

let modelCatalog = null;
let progressTimer = null;
let imageAutoEnabled = false;
let mediaAssets = [];
let selectedMediaIds = new Set();
let currentQuestionSet = null;
let currentRole = "faculty";
let latestReviewLoadPromise = null;
let medlegalCases = [];
let currentMedlegalCase = null;
let courseExamPracticeList = [];
let currentPracticeExam = null;
let currentPracticeIndex = 0;
let currentPracticeAnswers = {};

try {
  const restoredMediaIds = JSON.parse(window.sessionStorage?.getItem("axioma.selectedMediaIds") || "[]");
  if (Array.isArray(restoredMediaIds)) {
    selectedMediaIds = new Set(restoredMediaIds.filter(Boolean));
  }
} catch (error) {
  selectedMediaIds = new Set();
}

const pageMeta = {
  "faculty-dashboard": ["교수 홈", "자료 기반 문항 제작"],
  "faculty-studio": ["문항 생성", "강의자료·기출·제시자료 기반 초안 생성"],
  "faculty-review": ["문항 검토", "승인 전 문항 확인"],
  "faculty-archive": ["아카이브/내보내기", "승인 세트 보관과 export"],
  "faculty-report": ["수업 리포트", "신경 및 특수감각기학 통합 성취도 분석"],
  "faculty-ops": ["운영 보드", "팀 작업 배분과 주차별 산출물 관리"],
  "faculty-medlegal": ["EMR/CPX 훈련", "의료법·설명의무·진료기록 교육"],
  "student-dashboard": ["학습 홈", "문제·개념·복습"],
  "student-library": ["나의 서재", "분과별 강의 노트와 문항 모음"],
  "student-practice": ["문제 풀기", "승인 문항 기반 학습/시험 모드"],
  "student-concepts": ["개념 노트", "Obsidian식 문항·강의록·레퍼런스 연결"],
  "student-review": ["복습 카드", "오답과 핵심 개념 플래시카드"],
};

const departmentCategories = [
  { key: "infectious_diseases", title: "감염학", icon: "감", tone: "green", desc: "감염질환, 항생제, 감염관리" },
  { key: "musculoskeletal", title: "근골격학", icon: "근", tone: "blue", desc: "관절, 근육, 외상, 류마티스" },
  { key: "endocrinology", title: "내분비학", icon: "내", tone: "amber", desc: "당뇨, 갑상샘, 부신, 대사" },
  { key: "immunology_dermatology", title: "면역및피부질환", icon: "면", tone: "teal", desc: "면역, 알레르기, 피부질환" },
  { key: "reproductive_medicine", title: "생식계의학", icon: "생", tone: "rose", desc: "산부인과, 생식, 임신과 분만" },
  { key: "growth_development_aging", title: "성장발달노화", icon: "성", tone: "amber", desc: "소아 성장, 발달, 노화" },
  { key: "gastroenterology_nutrition", title: "소화기및영양학", icon: "소", tone: "amber", desc: "위장관, 간담췌, 영양" },
  { key: "cardiology", title: "순환기학", icon: "순", tone: "blue", desc: "심전도, 심부전, 허혈성 심질환" },
  { key: "neuro_special_senses", title: "신경및특수감각기학", icon: "신", tone: "teal", desc: "신경계, 감각기, 뇌영상" },
  { key: "renal_urology", title: "신장비뇨기학", icon: "뇨", tone: "blue", desc: "신장, 전해질, 비뇨기" },
  { key: "human_society_medicine_1", title: "인간·사회·의료(I)", icon: "사", tone: "green", desc: "의료사회, 윤리, 예방의학 기초" },
  { key: "human_society_medicine_2", title: "인간·사회·의료(II)", icon: "의", tone: "green", desc: "법규, 직업환경, 의료관리" },
  { key: "psychiatry", title: "정신의학", icon: "정", tone: "teal", desc: "정신질환, 면담, 약물치료" },
  { key: "disease_pharmacology", title: "질병의이해와약물요법", icon: "약", tone: "red", desc: "병태생리, 약리, 치료 원칙" },
  { key: "hematology_oncology", title: "혈액및종양학", icon: "혈", tone: "red", desc: "빈혈, 혈액종양, 고형암" },
  { key: "pulmonology", title: "호흡기학", icon: "호", tone: "teal", desc: "폐렴, 천식/COPD, 흉부영상" },
];

function bindChange(element, handler) {
  if (element) {
    element.addEventListener("change", handler);
  }
}

function setStatus(text, variant = "") {
  if (!runStatus) return;
  runStatus.textContent = text;
  runStatus.classList.toggle("muted", variant === "muted");
}

function setProgressMessage(text) {
  if (progressMessage) {
    progressMessage.textContent = text;
  }
}

function setReviewCount(count) {
  const safeCount = Number(count || 0);
  if (metricReview) metricReview.textContent = safeCount;
  if (navReviewBadge) {
    navReviewBadge.textContent = safeCount;
    navReviewBadge.hidden = safeCount <= 0;
  }
}

function setProgress(percent, label, activeStep) {
  const safePercent = Math.max(0, Math.min(100, Math.round(percent)));
  const stepOrder = ["upload", "extract", "generate", "review"];
  const activeIndex = stepOrder.indexOf(activeStep);
  if (progressPanel) progressPanel.hidden = false;
  if (progressLabel) progressLabel.textContent = label;
  if (progressPercent) progressPercent.textContent = `${safePercent}%`;
  if (progressBar) progressBar.style.width = `${safePercent}%`;

  document.querySelectorAll("[data-progress-step]").forEach((step) => {
    const stepIndex = stepOrder.indexOf(step.dataset.progressStep);
    const isActive = step.dataset.progressStep === activeStep;
    step.classList.toggle("active", isActive);
    step.classList.toggle("complete", stepIndex >= 0 && activeIndex >= 0 && stepIndex < activeIndex);
  });
}

function finishProgress(status = "complete") {
  if (status === "error") {
    setProgress(100, "오류 확인 필요", "review");
    progressPanel?.classList.add("has-error");
    return;
  }
  progressPanel?.classList.remove("has-error");
  setProgress(100, "생성 완료", "review");
}

function formatElapsed(seconds) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes ? `${minutes}분 ${rest}초` : `${rest}초`;
}

function startProgressTimer(formData) {
  clearProgressTimer();
  const startedAt = Date.now();
  const provider = formData.get("provider") || "auto";
  const count = Number(formData.get("num_questions") || 0);
  const providerLabel = provider === "prompt-only" ? "프롬프트 준비" : "문항 생성";
  progressPanel?.classList.remove("has-error");
  setProgress(8, "파일 업로드 준비", "upload");

  const update = () => {
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    setStatus(`${providerLabel} 중 · ${formatElapsed(elapsed)}`);
    const estimateSeconds = provider === "prompt-only" ? 20 : Math.max(120, Math.min(420, 70 + count * 55));
    const estimatedPercent = Math.min(92, 10 + (elapsed / estimateSeconds) * 82);

    if (elapsed < 8) {
      setProgress(estimatedPercent, "파일 업로드 및 저장", "upload");
    } else if (elapsed < 28) {
      setProgress(estimatedPercent, "강의록 텍스트·이미지 후보 분석", "extract");
    } else {
      setProgress(estimatedPercent, "AI 문항·해설 생성", "generate");
    }

    if (elapsed >= 210) {
      setProgressMessage("아직 생성 중입니다. 큰 강의록이나 5문항 이상은 시간이 오래 걸릴 수 있어요. 실패하면 2~3문항으로 줄여 다시 시도하면 안정적입니다.");
    } else if (elapsed >= 120) {
      setProgressMessage("Claude Code가 문항과 해설, 참고문헌을 구성하는 중입니다. 현재 단계는 오래 걸려도 정상일 수 있습니다.");
    } else if (elapsed >= 45) {
      setProgressMessage(`강의자료를 바탕으로 ${count || "선택한 개수"}문항 초안을 만드는 중입니다. 보통 2문항 기준 1~3분 정도 걸립니다.`);
    } else if (elapsed >= 15) {
      setProgressMessage("업로드는 완료됐고, 강의록 텍스트와 이미지 후보를 정리한 뒤 모델에 넘기는 중입니다.");
    } else {
      setProgressMessage("파일을 읽고 문항 생성 요청을 준비하고 있습니다.");
    }
  };

  update();
  progressTimer = window.setInterval(update, 1000);
}

function clearProgressTimer() {
  if (progressTimer) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
}

function roleForPage(pageId) {
  return String(pageId || "").startsWith("student") ? "student" : "faculty";
}

function setActiveNav(pageId) {
  pageLinks.forEach((link) => {
    link.classList.toggle("active", link.dataset.pageLink === pageId);
  });
}

function setRole(role) {
  currentRole = role === "student" ? "student" : "faculty";
  document.body.dataset.role = currentRole;
  roleButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.roleToggle === currentRole);
  });
  navGroups.forEach((group) => {
    group.hidden = group.dataset.navGroup !== currentRole;
  });
  if (sidebarNoteTitle && sidebarNoteCopy) {
    if (currentRole === "student") {
      sidebarNoteTitle.textContent = "학습 원칙";
      sidebarNoteCopy.textContent = "승인 자료와 문항을 기반으로 개념, 문제, 복습 카드를 연결합니다.";
    } else {
      sidebarNoteTitle.textContent = "검토 원칙";
      sidebarNoteCopy.textContent = "AI 생성 문항은 확인 후 학생에게 배포됩니다.";
    }
  }
}

function showPage(pageId, options = {}) {
  const safePage = pageMeta[pageId] ? pageId : "faculty-dashboard";
  const nextRole = roleForPage(safePage);
  setRole(nextRole);
  pageViews.forEach((view) => {
    view.classList.toggle("active", view.dataset.page === safePage);
  });
  setActiveNav(safePage);
  if (appTitle) appTitle.textContent = pageMeta[safePage][0];
  if (appSubtitle) appSubtitle.textContent = pageMeta[safePage][1];
  if (generateButton) {
    generateButton.hidden = safePage !== "faculty-studio";
  }
  if (safePage === "faculty-medlegal" && !medlegalCases.length) {
    loadMedlegalCases();
  }
  if (safePage === "student-practice" && !courseExamPracticeList.length) {
    loadStudentCourseExams();
  }
  if (options.updateHash !== false && window.location.hash !== `#${safePage}`) {
    window.history.pushState(null, "", `#${safePage}`);
  }
  if (options.scrollTop !== false) {
    window.scrollTo({ top: 0, behavior: "auto" });
  }
}

function updateImagePolicyState() {
  if (!includeImagesToggle || !imagePolicySelect || !imagePolicyField) return;
  const enabled = includeImagesToggle.checked;
  imagePolicySelect.disabled = !enabled;
  imagePolicyField.classList.toggle("is-disabled", !enabled);
  imagePolicySelect.value = enabled ? (imagePolicySelect.value === "none" ? "clinical_visuals" : imagePolicySelect.value) : "none";
  updateSelectedMediaInput();
}

function syncImagePolicyWithQuestionType() {
  if (!questionTypeSelect || !includeImagesToggle || !imagePolicySelect) return;
  if (questionTypeSelect.value === "image_based" && !includeImagesToggle.checked) {
    imageAutoEnabled = true;
    includeImagesToggle.checked = true;
    imagePolicySelect.value = "clinical_visuals";
    updateImagePolicyState();
  } else if (questionTypeSelect.value !== "image_based" && imageAutoEnabled) {
    imageAutoEnabled = false;
    includeImagesToggle.checked = false;
    updateImagePolicyState();
  }
}

function handleImageToggleChange() {
  imageAutoEnabled = false;
  updateImagePolicyState();
}

function fileSummary(input, fallback) {
  const files = Array.from(input.files || []);
  if (!files.length) return fallback;
  if (files.length === 1) return files[0].name;
  return `${files[0].name} 외 ${files.length - 1}개`;
}

function renderCourseExamImportResult(payload) {
  if (!courseExamImportResult) return;
  const summary = payload?.summary || {};
  const warnings = summary.extraction_warnings || [];
  const answerKey = payload?.answer_key || {};
  courseExamImportResult.hidden = false;
  courseExamImportResult.innerHTML = `
    <strong>${escapeHtml(summary.source_file || "시험지")} 구조화 완료</strong>
    <dl>
      <div><dt>문항</dt><dd>${escapeHtml(summary.question_count || 0)}</dd></div>
      <div><dt>예상</dt><dd>${escapeHtml(summary.expected_objective_count || "-")}</dd></div>
      <div><dt>정답</dt><dd>${escapeHtml(summary.with_answer_count || 0)}</dd></div>
      <div><dt>제시자료</dt><dd>${escapeHtml(summary.with_stimulus_count || 0)}</dd></div>
      <div><dt>해설</dt><dd>${escapeHtml(summary.with_explanation_count || 0)}</dd></div>
      <div><dt>이미지</dt><dd>${escapeHtml(summary.media_asset_count || 0)}</dd></div>
    </dl>
    <p>
      검수 필요 ${escapeHtml(summary.needs_review_count || 0)}개
      · 이미지 연결 문항 ${escapeHtml(summary.media_linked_question_count || 0)}개
      ${answerKey.matched_count !== undefined ? `· 정답지 매핑 ${escapeHtml(answerKey.matched_count)}개` : ""}
    </p>
    ${warnings.length ? `<p class="inline-error">경고: ${escapeHtml(warnings.join(", "))}</p>` : ""}
    ${answerKey.missing_question_numbers?.length ? `<p class="inline-error">정답 누락 문항: ${escapeHtml(answerKey.missing_question_numbers.join(", "))}</p>` : ""}
    ${payload.preview_url ? `<a class="secondary-button" href="${escapeHtml(payload.preview_url)}" target="_blank" rel="noreferrer">검수 미리보기 열기</a>` : ""}
  `;
}

function joinList(values) {
  return (values || []).filter(Boolean).join(", ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeCssValue(value) {
  if (window.CSS?.escape) {
    return CSS.escape(String(value ?? ""));
  }
  return String(value ?? "").replaceAll('"', '\\"');
}

function examTitle(summary) {
  return [
    summary.course_name || "미분류 시험",
    summary.round_label,
    summary.question_count ? `${summary.question_count}문항` : "",
  ].filter(Boolean).join(" · ");
}

function renderStudentExamOptions() {
  if (!studentExamSelect) return;
  const playableExams = courseExamPracticeList.filter((item) => Number(item.practice_ready_count || 0) > 0);
  if (!playableExams.length) {
    studentExamSelect.innerHTML = '<option value="">구조화된 문항 세트가 없습니다</option>';
    studentExamSelect.disabled = true;
    if (studentPracticeStatus) {
      studentPracticeStatus.textContent = "교수 화면에서 HWP/PDF 시험지를 먼저 구조화하면 여기에 표시됩니다.";
    }
    return;
  }
  studentExamSelect.disabled = false;
  studentExamSelect.innerHTML = playableExams
    .map((item) => {
      const ready = item.practice_ready_count || 0;
      const label = `${examTitle(item)} · 풀이 가능 ${ready}문항`;
      return `<option value="${escapeHtml(item.exam_id)}">${escapeHtml(label)}</option>`;
    })
    .join("");
  if (!studentExamSelect.value && playableExams[0]?.exam_id) {
    studentExamSelect.value = playableExams[0].exam_id;
  }
  if (studentPracticeStatus) {
    studentPracticeStatus.textContent = `${playableExams.length}개 풀이 가능 세트를 불러왔습니다. 세트를 선택해 문제 풀이를 시작할 수 있습니다.`;
  }
}

async function loadStudentCourseExams() {
  if (!studentExamSelect && !studentPracticeStage) return;
  try {
    const response = await fetch("/api/course-exams?limit=50");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "구조화 문항 목록 로드 실패");
    }
    courseExamPracticeList = payload.exams || [];
    renderStudentExamOptions();
  } catch (error) {
    if (studentPracticeStatus) {
      studentPracticeStatus.textContent = `구조화 문항 목록을 불러오지 못했습니다: ${error.message}`;
    }
  }
}

function practiceChoiceEntries(question) {
  return Object.entries(question?.choices || {})
    .sort(([left], [right]) => Number(left) - Number(right));
}

function renderPracticeQuestionStrip(questions) {
  if (!questions.length) return "";
  const windowSize = 18;
  const start = Math.max(0, Math.min(currentPracticeIndex - 8, questions.length - windowSize));
  const visibleQuestions = questions.slice(start, start + windowSize);
  return `
    <div class="practice-question-strip" aria-label="문항 빠른 이동">
      ${visibleQuestions.map((item, offset) => {
        const index = start + offset;
        const key = item.question_id || String(item.question_number || index);
        const answered = currentPracticeAnswers[key];
        const active = index === currentPracticeIndex;
        return `
          <button
            type="button"
            class="${active ? "active" : ""} ${answered ? "answered" : ""}"
            data-practice-jump="${escapeHtml(index)}"
            aria-label="${escapeHtml(index + 1)}번 문항으로 이동"
          >
            ${escapeHtml(index + 1)}
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function renderPracticeMedia(mediaRefs) {
  const media = (mediaRefs || []).filter((item) => item.url);
  if (!media.length) return "";
  return `
    <div class="practice-media-grid">
      ${media.map((item) => `
        <figure class="practice-media-card">
          <img
            src="${escapeHtml(item.url)}"
            alt="${escapeHtml(item.caption || item.media_id || "문항 제시자료")}"
            data-lightbox-src="${escapeHtml(item.url)}"
            data-lightbox-caption="${escapeHtml(item.caption || item.media_id || "문항 제시자료")}"
          />
          <figcaption>${escapeHtml(item.modality || item.filename || "제시자료")} · match ${escapeHtml(item.match_confidence ?? "-")}</figcaption>
        </figure>
      `).join("")}
    </div>
  `;
}

function renderStudentPracticeQuestion() {
  if (!studentPracticeStage) return;
  studentPracticeStage.className = "practice-layout uworld-layout";
  const questions = currentPracticeExam?.questions || [];
  const question = questions[currentPracticeIndex];
  if (!question) {
    studentPracticeStage.innerHTML = `
      <article class="practice-question empty-practice">
        <p>선택한 세트에서 풀이 가능한 문항을 찾지 못했습니다.</p>
      </article>
      <aside class="practice-helper">
        <h3>확인 필요</h3>
        <p>문항 지문이나 선지 추출이 누락된 경우 교수 검토 화면에서 구조를 먼저 확인해야 합니다.</p>
      </aside>
    `;
    return;
  }

  const questionKey = question.question_id || String(question.question_number || currentPracticeIndex);
  const selectedAnswer = currentPracticeAnswers[questionKey];
  const answer = String(question.answer || "");
  const revealAnswer = Boolean(selectedAnswer) && (studentPracticeMode?.value || "study") === "study";
  const correctCount = questions.filter((item, index) => {
    const key = item.question_id || String(item.question_number || index);
    return currentPracticeAnswers[key] && String(item.answer || "") === currentPracticeAnswers[key];
  }).length;
  const answeredCount = Object.keys(currentPracticeAnswers).length;
  const progressPercent = questions.length ? Math.round(((currentPracticeIndex + 1) / questions.length) * 100) : 0;
  const choices = practiceChoiceEntries(question)
    .map(([key, text]) => {
      const normalizedKey = String(key);
      const isSelected = selectedAnswer === normalizedKey;
      const isCorrect = revealAnswer && answer === normalizedKey;
      const isWrong = revealAnswer && isSelected && answer && answer !== normalizedKey;
      const className = [
        isSelected ? "selected" : "",
        isCorrect ? "correct" : "",
        isWrong ? "incorrect" : "",
      ].filter(Boolean).join(" ");
      return `
        <button type="button" class="${className}" data-practice-choice="${escapeHtml(normalizedKey)}">
          <span>${escapeHtml(normalizedKey)}</span>
          ${escapeHtml(text)}
        </button>
      `;
    })
    .join("");

  const labels = question.labels || {};
  const conceptTags = Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
  const helperStatus = selectedAnswer
    ? revealAnswer
      ? answer === selectedAnswer ? "정답입니다." : `오답입니다. 정답은 ${answer || "미확인"}번입니다.`
      : "선택이 저장됐습니다. 시험 모드에서는 마지막에 해설을 확인합니다."
    : "선지를 선택하면 학습 모드에서는 정답과 해설이 바로 표시됩니다.";
  const answerPanel = selectedAnswer
    ? `
      <section class="uworld-explanation-card ${revealAnswer && answer === selectedAnswer ? "correct" : revealAnswer ? "incorrect" : ""}">
        <span>${revealAnswer ? answer === selectedAnswer ? "Correct" : "Incorrect" : "Selected"}</span>
        <strong>${revealAnswer ? `정답 ${escapeHtml(answer || "미확인")}번` : `${escapeHtml(selectedAnswer)}번 선택됨`}</strong>
        ${revealAnswer
          ? question.explanation
            ? `<p>${escapeHtml(question.explanation)}</p>`
            : "<p>저장된 해설이 없습니다. 교수 검토 단계에서 해설 보강이 필요합니다.</p>"
          : "<p>시험 모드에서는 세션 종료 후 해설을 확인하도록 설계할 수 있습니다.</p>"
        }
      </section>
    `
    : `
      <section class="uworld-explanation-card pending">
        <span>Tutor Panel</span>
        <strong>선지를 선택하면 해설이 열립니다.</strong>
        <p>오른쪽 패널은 UWorld식 학습 모드처럼 정답, 해설, 관련 개념, 복습 버튼을 모아두는 영역입니다.</p>
      </section>
    `;

  studentPracticeStage.innerHTML = `
    <section class="uworld-practice-shell">
      <header class="uworld-testbar">
        <div>
          <span>Block 1</span>
          <strong>Q${escapeHtml(question.question_number || currentPracticeIndex + 1)} · ${escapeHtml(labels.question_type || "course exam")}</strong>
        </div>
        <div class="uworld-progress">
          <span>${escapeHtml(currentPracticeIndex + 1)} / ${escapeHtml(questions.length)}</span>
          <div aria-hidden="true"><b style="width: ${escapeHtml(progressPercent)}%"></b></div>
        </div>
        <div class="uworld-session-stats">
          <span>${escapeHtml(studentPracticeMode?.value === "exam" ? "Exam Mode" : "Tutor Mode")}</span>
          <strong>${escapeHtml(answeredCount)} answered</strong>
          <button type="button" data-practice-reset>세트 변경</button>
        </div>
      </header>

      ${renderPracticeQuestionStrip(questions)}

      <div class="uworld-workspace">
        <article class="practice-question uworld-question-panel">
          <div class="uworld-question-head">
            <span>Question</span>
            <strong>${escapeHtml(currentPracticeIndex + 1)} of ${escapeHtml(questions.length)}</strong>
          </div>
          <p class="uworld-stem">${escapeHtml(question.stem || "문항 지문 미추출")}</p>
          ${question.stimulus ? `<blockquote class="practice-stimulus">${escapeHtml(question.stimulus)}</blockquote>` : ""}
          ${renderPracticeMedia(question.media_refs || [])}
          <div class="practice-choices interactive uworld-choice-list">${choices}</div>
          <div class="practice-nav-actions uworld-bottom-actions">
            <button type="button" class="secondary-button" data-practice-nav="prev" ${currentPracticeIndex <= 0 ? "disabled" : ""}>이전</button>
            <button type="button" data-practice-nav="next" ${currentPracticeIndex >= questions.length - 1 ? "disabled" : ""}>다음</button>
          </div>
        </article>

        <aside class="practice-helper uworld-side-panel">
          <h3>해설 · 복습</h3>
          <div class="practice-helper-status">${escapeHtml(helperStatus)}</div>
          ${answerPanel}
          <dl class="practice-mini-metrics">
            <div><dt>풀이</dt><dd>${escapeHtml(answeredCount)}문항</dd></div>
            <div><dt>정답</dt><dd>${escapeHtml(correctCount)}문항</dd></div>
            <div><dt>태그</dt><dd>${escapeHtml(conceptTags.slice(0, 3).join(", ") || labels.cognitive_level || "라벨 필요")}</dd></div>
          </dl>
          <div class="uworld-side-actions">
            <button type="button" class="secondary-button" data-page-link="student-concepts">관련 개념</button>
            <button type="button" class="secondary-button" data-page-link="student-review">Anki 카드</button>
          </div>
        </aside>
      </div>
    </section>
  `;
}

async function startStudentPractice() {
  const examId = studentExamSelect?.value;
  if (!examId) return;
  if (startStudentPracticeButton) startStudentPracticeButton.disabled = true;
  if (studentPracticeStatus) {
    studentPracticeStatus.textContent = "선택한 문항 세트를 불러오는 중입니다.";
  }
  try {
    const response = await fetch(`/api/course-exams/extracted/${encodeURIComponent(examId)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "문항 세트 로드 실패");
    }
    currentPracticeExam = payload;
    currentPracticeIndex = 0;
    currentPracticeAnswers = {};
    studentPracticePage?.classList.add("practice-active");
    if (studentPracticeStatus) {
      const summary = payload.summary || {};
      studentPracticeStatus.textContent = `${examTitle(summary)} 세트를 열었습니다. ${payload.questions?.length || 0}문항을 풀 수 있습니다.`;
    }
    renderStudentPracticeQuestion();
  } catch (error) {
    if (studentPracticeStatus) {
      studentPracticeStatus.textContent = `문항 세트 로드 실패: ${error.message}`;
    }
  } finally {
    if (startStudentPracticeButton) startStudentPracticeButton.disabled = false;
  }
}

function mediaMaterialText(asset) {
  return [
    asset.original_name,
    asset.asset_type,
    asset.modality,
    asset.unit,
    asset.diagnosis,
    asset.caption,
    asset.faculty_note,
    ...(Array.isArray(asset.key_findings) ? asset.key_findings : []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function mediaMaterialKeys(asset) {
  const text = mediaMaterialText(asset);
  const keys = new Set();
  if (/x-?ray|cxr|radiograph|엑스레이|흉부\s*x/i.test(text)) keys.add("xray");
  if (/\bct\b|computed tomography|컴퓨터단층|전산화단층/i.test(text)) keys.add("ct");
  if (/\bmri\b|magnetic resonance|자기공명/i.test(text)) keys.add("mri");
  if (/\bus\b|ultrasound|sono|초음파/i.test(text)) keys.add("us");
  if (/\bpbs\b|peripheral blood smear|blood smear|말초혈액|도말/i.test(text)) keys.add("pbs");
  if (/pathology|histology|biopsy|병리|조직|슬라이드/i.test(text)) keys.add("pathology");
  if (/patient photo|clinical_photo|clinical photo|환자|진찰|피부|소견사진/i.test(text)) keys.add("patient_photo");
  if (/\becg\b|\beekg\b|\beeg\b|electrocardiogram|심전도|뇌파/i.test(text)) keys.add("ecg_eeg");
  return keys;
}

function selectedMediaTypeKeys() {
  return new Set(mediaTypeFilters.filter((input) => input.checked).map((input) => input.value));
}

function renderMediaAssets(assets) {
  if (!mediaBank) return;
  if (!assets.length) {
    mediaBank.className = "media-bank-empty";
    mediaBank.textContent = "저장된 제시자료가 없습니다.";
    return;
  }
  const query = (mediaSearch?.value || "").trim().toLowerCase();
  const materialFilters = selectedMediaTypeKeys();
  const visibleAssets = assets.filter((asset) => {
    const haystack = mediaMaterialText(asset);
    if (query && !haystack.includes(query)) return false;
    if (!materialFilters.size) return true;
    const keys = mediaMaterialKeys(asset);
    return Array.from(materialFilters).some((key) => keys.has(key));
  });
  if (!visibleAssets.length) {
    mediaBank.className = "media-bank-empty";
    mediaBank.textContent = "검색 결과가 없습니다.";
    return;
  }
  mediaBank.className = "media-grid";
  mediaBank.innerHTML = visibleAssets
    .map((asset) => {
      const checked = selectedMediaIds.has(asset.asset_id) ? "checked" : "";
      const findings = joinList(asset.key_findings);
      return `
        <article class="media-card" data-media-asset-id="${escapeHtml(asset.asset_id)}">
          <label class="media-select">
            <input type="checkbox" value="${escapeHtml(asset.asset_id)}" ${checked} />
            <span>이번 문항에 사용</span>
          </label>
          <img src="${escapeHtml(asset.url)}" alt="${escapeHtml(asset.caption || asset.original_name || "media asset")}" />
          <div class="media-card-body">
            <strong>${escapeHtml(asset.modality || asset.asset_type || "Media")}</strong>
            <p>${escapeHtml(asset.caption || asset.original_name || "")}</p>
            ${asset.diagnosis ? `<small>진단/주제: ${escapeHtml(asset.diagnosis)}</small>` : ""}
            ${findings ? `<small>핵심 소견: ${escapeHtml(findings)}</small>` : ""}
            <div class="media-tags">
              <span class="${asset.deidentified ? "approved" : "review"}">${asset.deidentified ? "비식별화" : "비식별 확인 필요"}</span>
              <span class="${asset.approved_for_question_use ? "approved" : "review"}">${asset.approved_for_question_use ? "사용 승인" : "승인 필요"}</span>
            </div>
            <button type="button" class="delete-media-button" data-delete-media="${escapeHtml(asset.asset_id)}">삭제</button>
          </div>
        </article>
      `;
    })
    .join("");

  mediaBank.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedMediaIds.add(checkbox.value);
        if (includeImagesToggle) includeImagesToggle.checked = true;
        if (imagePolicySelect && imagePolicySelect.value === "none") imagePolicySelect.value = "clinical_visuals";
        if (questionTypeSelect) questionTypeSelect.value = "image_based";
      } else {
        selectedMediaIds.delete(checkbox.value);
      }
      updateSelectedMediaInput();
      updateImagePolicyState();
    });
  });
}

function updateSelectedMediaInput() {
  if (selectedMediaIdsInput) {
    selectedMediaIdsInput.value = Array.from(selectedMediaIds).join(",");
  }
  if (selectedMediaCount) {
    selectedMediaCount.textContent = `${selectedMediaIds.size}개 선택`;
  }
  try {
    window.sessionStorage?.setItem("axioma.selectedMediaIds", JSON.stringify(Array.from(selectedMediaIds)));
  } catch (error) {
    // Selection persistence is a convenience feature; generation still works without it.
  }
}

function renderArchiveSets(sets) {
  if (!archiveList) return;
  if (!sets.length) {
    archiveList.className = "archive-empty";
    archiveList.textContent = "아직 아카이브된 문항 세트가 없습니다.";
    return;
  }
  archiveList.className = "archive-list";
  archiveList.innerHTML = sets
    .map((set) => `
      <article class="archive-row">
        <div>
          <strong>${escapeHtml(set.source_name || set.set_id)}</strong>
          <p>${escapeHtml(set.subject || "-")} · ${escapeHtml(set.unit || "-")} · ${escapeHtml(set.review_status || "draft")}</p>
        </div>
        <dl>
          <div><dt>문항</dt><dd>${escapeHtml(set.question_count || 0)}</dd></div>
          <div><dt>이미지</dt><dd>${escapeHtml(set.image_question_count || 0)}</dd></div>
          <div><dt>확인</dt><dd>${escapeHtml(set.needs_review_count || 0)}</dd></div>
          <div><dt>승인</dt><dd>${escapeHtml(set.approved_count || 0)}</dd></div>
        </dl>
        <div class="archive-actions">
          <button type="button" class="secondary-button" data-open-set="${escapeHtml(set.set_id)}">문항 열기</button>
          <button type="button" class="secondary-button" data-export-anki="${escapeHtml(set.set_id)}">Anki Export</button>
        </div>
      </article>
    `)
    .join("");
}

function renderCategoryGrid(container, mode) {
  if (!container) return;
  container.innerHTML = departmentCategories
    .map((category) => `
      <button
        type="button"
        class="category-card tone-${escapeHtml(category.tone)}"
        data-category-key="${escapeHtml(category.key)}"
        data-category-title="${escapeHtml(category.title)}"
        data-category-mode="${escapeHtml(mode)}"
      >
        <span class="category-icon">${escapeHtml(category.icon)}</span>
        <strong>${escapeHtml(category.title)}</strong>
        <small>${escapeHtml(category.desc)}</small>
      </button>
    `)
    .join("");
}

function selectCategory(categoryTitle, mode) {
  const subjectInput = form?.querySelector('input[name="subject"]');
  const unitInput = form?.querySelector('input[name="unit"]');
  if (subjectInput) subjectInput.value = categoryTitle;
  if (unitInput && !unitInput.value.trim()) unitInput.value = "미분류";
  if (mode === "student") {
    showPage("student-concepts");
  } else {
    showPage("faculty-studio");
  }
}

function renderMedlegalCases() {
  if (!medlegalCaseList) return;
  if (!medlegalCases.length) {
    medlegalCaseList.className = "medlegal-case-list empty";
    medlegalCaseList.textContent = "아직 등록된 훈련 케이스가 없습니다.";
    return;
  }
  medlegalCaseList.className = "medlegal-case-list";
  medlegalCaseList.innerHTML = medlegalCases
    .map((item) => {
      const active = currentMedlegalCase?.case_id === item.case_id ? "active" : "";
      return `
        <button type="button" class="medlegal-case-button ${active}" data-medlegal-case="${escapeHtml(item.case_id)}">
          <span>${escapeHtml(item.care_setting || "진료")}</span>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${escapeHtml((item.risk_tags || []).join(" · "))}</small>
        </button>
      `;
    })
    .join("");
}

function renderMedlegalCaseDetail(caseData) {
  if (!medlegalCaseDetail) return;
  if (!caseData) {
    medlegalCaseDetail.className = "medlegal-case-detail empty";
    medlegalCaseDetail.textContent = "케이스를 선택하면 시나리오와 작성 과제가 표시됩니다.";
    return;
  }
  medlegalCaseDetail.className = "medlegal-case-detail";
  const requiredItems = (caseData.required_elements || [])
    .map((item) => `<li>${escapeHtml(item.label)}</li>`)
    .join("");
  const sources = (caseData.sources || [])
    .map((source) => `
      <a href="${escapeHtml(source.url || "#")}" target="_blank" rel="noreferrer">
        ${escapeHtml(source.title)}
      </a>
    `)
    .join("");
  medlegalCaseDetail.innerHTML = `
    <div class="medlegal-detail-head">
      <div>
        <p class="section-label">${escapeHtml(caseData.track || "medlegal")}</p>
        <h2>${escapeHtml(caseData.title)}</h2>
      </div>
      <span class="badge light">${escapeHtml(caseData.required_note_type || "EMR")}</span>
    </div>
    <p class="medlegal-scenario">${escapeHtml(caseData.scenario || "")}</p>
    <div class="medlegal-task">
      <strong>작성 과제</strong>
      <p>${escapeHtml(caseData.task || "")}</p>
    </div>
    <div class="medlegal-checklist">
      <strong>피드백 기준</strong>
      <ul>${requiredItems}</ul>
    </div>
    <div class="medlegal-sources">
      <strong>교육 근거</strong>
      <div>${sources || "<span>근거 자료 검토 예정</span>"}</div>
    </div>
  `;
}

function renderMedlegalFeedback(payload) {
  if (!medlegalFeedback) return;
  if (!payload?.feedback) {
    medlegalFeedback.className = "medlegal-feedback empty";
    medlegalFeedback.textContent = "작성한 기록을 제출하면 빠진 설명 항목, 위험 표현, 수정 방향이 표시됩니다.";
    return;
  }
  const feedback = payload.feedback;
  const missing = (feedback.missing_items || [])
    .map((item) => `<li><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.feedback || "")}</span></li>`)
    .join("");
  const risky = (feedback.risky_phrases || [])
    .map((item) => `<li><strong>${escapeHtml(item.pattern)}</strong><span>${escapeHtml(item.reason || "")}</span></li>`)
    .join("");
  const dimensions = Object.entries(feedback.dimension_scores || {})
    .map(([key, value]) => `
      <div>
        <span>${escapeHtml(key.replaceAll("_", " "))}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `)
    .join("");
  medlegalFeedback.className = "medlegal-feedback";
  medlegalFeedback.innerHTML = `
    <div class="medlegal-score">
      <span>교육용 기록 점검 점수</span>
      <strong>${escapeHtml(feedback.overall_score)}%</strong>
    </div>
    <div class="medlegal-dimensions">${dimensions}</div>
    <section>
      <h3>보강할 항목</h3>
      ${missing ? `<ul>${missing}</ul>` : "<p>핵심 항목이 대부분 포함되어 있습니다.</p>"}
    </section>
    <section>
      <h3>주의 표현</h3>
      ${risky ? `<ul>${risky}</ul>` : "<p>현재 제출문에서는 주요 위험 표현이 감지되지 않았습니다.</p>"}
    </section>
    <section>
      <h3>수정 방향</h3>
      <p>${escapeHtml(feedback.recommended_revision || "")}</p>
    </section>
    <small>${escapeHtml(feedback.disclaimer || "")}</small>
  `;
}

async function loadMedlegalCases() {
  if (!medlegalCaseList) return;
  try {
    const response = await fetch("/api/medlegal/cases");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "케이스 로드 실패");
    }
    medlegalCases = payload.cases || [];
    renderMedlegalCases();
    if (!currentMedlegalCase && medlegalCases[0]) {
      await loadMedlegalCase(medlegalCases[0].case_id);
    }
  } catch (error) {
    medlegalCaseList.className = "medlegal-case-list empty";
    medlegalCaseList.textContent = `케이스 로드 실패: ${error.message}`;
  }
}

async function loadMedlegalCase(caseId) {
  if (!caseId) return;
  try {
    const response = await fetch(`/api/medlegal/cases/${encodeURIComponent(caseId)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "케이스 상세 로드 실패");
    }
    currentMedlegalCase = payload;
    renderMedlegalCases();
    renderMedlegalCaseDetail(payload);
    renderMedlegalFeedback(null);
    if (medlegalNoteText) {
      medlegalNoteText.value = "";
      medlegalNoteText.focus({ preventScroll: true });
    }
  } catch (error) {
    if (medlegalCaseDetail) {
      medlegalCaseDetail.className = "medlegal-case-detail empty";
      medlegalCaseDetail.textContent = `케이스 상세 로드 실패: ${error.message}`;
    }
  }
}

function renderParagraphs(value) {
  return String(value ?? "")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `<p>${escapeHtml(line)}</p>`)
    .join("");
}

function imagePlaceholderPattern() {
  return /\s*\[(?:첨부|제시)?\s*이미지\s*참조[^\]]*\]\s*/g;
}

function renderQuestionImages(imageRefs) {
  return (imageRefs || [])
    .map((image) => {
      const locator = image.locator_label || (image.page ? `p.${image.page}` : "업로드 이미지");
      const priority = Number(image.visual_priority || 0);
      const confidence = Number(image.match_confidence || 0);
      const focus = priority >= 0.45
        ? "환자/영상 자료 우선"
        : priority >= 0.2
          ? "시각자료 후보"
          : "확인 필요 후보";
      const confidenceClass = confidence >= 0.8 ? "high" : confidence >= 0.5 ? "mid" : "low";
      const confidenceLabel = confidence >= 0.8 ? "매칭 양호" : confidence >= 0.5 ? "확인 권장" : "확인 필요";
      return `
        <figure class="question-image embedded">
          <div class="image-ribbon">문항 제시자료</div>
          <img
            src="${escapeHtml(image.url)}"
            alt="${escapeHtml(image.source_name || "lecture image")} ${escapeHtml(locator)}"
            data-lightbox-src="${escapeHtml(image.url)}"
            data-lightbox-caption="${escapeHtml(`${image.source_name || "강의자료"} · ${locator}`)}"
          />
          <figcaption>
            <span class="confidence-badge ${confidenceClass}">${escapeHtml(confidenceLabel)} ${escapeHtml(image.match_confidence ?? "-")}</span>
            ${escapeHtml(image.source_name || "강의자료")} · ${escapeHtml(locator)}
            · ${escapeHtml(focus)}
          </figcaption>
        </figure>
      `;
    })
    .join("");
}

function renderQuestionStem(item) {
  const rawProblem = String(item.problem ?? "");
  const images = renderQuestionImages(item.image_refs || []);
  const pieces = rawProblem.split(imagePlaceholderPattern()).map((piece) => piece.trim()).filter(Boolean);

  if (images && rawProblem.match(imagePlaceholderPattern())) {
    const before = pieces[0] || "";
    const after = pieces.slice(1).join("\n\n");
    return `
      <div class="question-stem">
        ${renderParagraphs(before)}
        <div class="embedded-visuals">${images}</div>
        ${renderParagraphs(after)}
      </div>
    `;
  }

  const cleanProblem = rawProblem.replace(imagePlaceholderPattern(), " ").trim();
  return `
    <div class="question-stem">
      ${images ? `<div class="embedded-visuals">${images}</div>` : ""}
      ${renderParagraphs(cleanProblem)}
    </div>
  `;
}

function renderQuestionTable(table) {
  if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows) || !table.columns.length || !table.rows.length) {
    return "";
  }
  const headers = table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const rows = table.rows
    .map((row) => {
      const cells = Array.from({ length: table.columns.length }, (_, index) => `<td>${escapeHtml(row?.[index] ?? "")}</td>`).join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `
    <figure class="question-table">
      ${table.title ? `<figcaption>${escapeHtml(table.title)}</figcaption>` : ""}
      <table>
        <thead><tr>${headers}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </figure>
  `;
}

function renderPromptReady(data) {
  if (!results) return;
  results.className = "question-card";
  results.innerHTML = `
    <header>
      <h3>프롬프트 생성 완료</h3>
        <span class="review">생성 대기</span>
    </header>
    <p>모델 호출 없이 검토용 프롬프트와 추출 텍스트를 준비했습니다.</p>
    <ul class="choices">
      <li>프롬프트: ${escapeHtml(data.paths?.prompt)}</li>
      <li>추출 텍스트: ${escapeHtml(data.paths?.extracted_text)}</li>
      <li>출력 패킷: ${escapeHtml(data.paths?.output)}</li>
    </ul>
  `;
}

function renderQuestions(data) {
  if (!results) return;
  const sample = data.sample || [];
  if (!sample.length) {
    renderPromptReady(data);
    return;
  }
  results.className = "";
  results.innerHTML = sample
    .map((item, index) => {
      const choices = (item.options || [])
        .map((choice, choiceIndex) => `<li>${choiceIndex + 1}. ${escapeHtml(choice)}</li>`)
        .join("");
      const references = (item.reference_notes || [])
        .map((ref) => `<li>${escapeHtml(ref.ref_no)}. ${escapeHtml(ref.source)} — ${escapeHtml(ref.basis || "근거 요약 확인 필요")}</li>`)
        .join("");
      return `
        <article class="question-card">
          <header>
            <h3>문항 ${index + 1} · ${escapeHtml(item.question_id || "")}</h3>
            <span class="${item.needs_review ? "review" : "approved"}">
              ${item.needs_review ? "확인 필요" : "초안 양호"}
            </span>
          </header>
          ${renderQuestionStem(item)}
          ${renderQuestionTable(item.data_table)}
          <ul class="choices">${choices}</ul>
          <p><strong>정답:</strong> ${escapeHtml(item.answer)}번</p>
          <p><strong>해설:</strong> ${escapeHtml(item.explanation)}</p>
          <p><strong>근거 수준:</strong> ${escapeHtml(item.evidence_tier || "lecture_only")}</p>
          ${references ? `<ol class="references">${references}</ol>` : ""}
        </article>
      `;
    })
    .join("");
}

function statusLabel(status, needsReview) {
  if (status === "approved") return "승인 완료";
  if (status === "rejected") return "반려";
  if (status === "needs_revision") return "수정 필요";
  return needsReview ? "확인 필요" : "초안";
}

function statusClass(status, needsReview) {
  if (status === "approved") return "approved";
  if (status === "rejected" || needsReview) return "review";
  return "draft";
}

function renderChoiceEditors(item) {
  const options = item.options || [];
  return Array.from({ length: 5 }, (_, index) => {
    const value = options[index] || "";
    return `
      <label>
        ${index + 1}번 선지
        <input data-review-field="choice" data-choice-index="${index}" value="${escapeHtml(value)}" />
      </label>
    `;
  }).join("");
}

function renderAnswerOptions(answer) {
  return Array.from({ length: 5 }, (_, index) => {
    const value = index + 1;
    const selected = Number(answer) === value ? "selected" : "";
    return `<option value="${value}" ${selected}>${value}번</option>`;
  }).join("");
}

function renderReviewQuestionSet(packet) {
  if (!results) return;
  currentQuestionSet = packet;
  const questions = packet.questions || [];
  const summary = packet.summary || {};
  const setQuestionType = summary.question_type || packet.metadata?.question_type || "";
  if (metricQuestions) metricQuestions.textContent = summary.question_count || questions.length || 0;
  setReviewCount(summary.needs_review_count || 0);

  results.className = "review-workbench";
  results.innerHTML = `
    <section class="review-set-head">
      <div>
        <p class="section-label">Loaded Review Set</p>
        <h3>${escapeHtml(summary.source_name || packet.set_id)}</h3>
        <p>${escapeHtml(summary.subject || "-")} · ${escapeHtml(summary.unit || "-")} · ${escapeHtml(summary.provider || "-")} ${escapeHtml(summary.model || "")}</p>
      </div>
      <div class="review-stats">
        <span>문항 ${escapeHtml(summary.question_count || questions.length || 0)}</span>
        <span>확인 ${escapeHtml(summary.needs_review_count || 0)}</span>
        <span>승인 ${escapeHtml(summary.approved_count || 0)}</span>
      </div>
    </section>
    ${questions.map((item, index) => {
      const references = (item.reference_notes || [])
        .map((ref) => `<li>${escapeHtml(ref.ref_no)}. ${escapeHtml(ref.source)} — ${escapeHtml(ref.basis || "근거 요약 확인 필요")}</li>`)
        .join("");
      const reasons = (item.review_reasons || []).join(", ");
      const reviewStatus = item.review_status || "draft";
      const isImageBased = (item.question_type || setQuestionType) === "image_based";
      const missingImage = isImageBased && !(item.image_refs || []).length;
      return `
        <article class="review-editor" data-question-id="${escapeHtml(item.question_id || `question_${index + 1}`)}">
          <header>
            <div>
              <h3>문항 ${index + 1}</h3>
              <p>${escapeHtml(item.question_id || "")}</p>
            </div>
            <span class="${statusClass(reviewStatus, item.needs_review)}">${statusLabel(reviewStatus, item.needs_review)}</span>
          </header>

          ${missingImage ? `<p class="warning-banner">이미지/자료해석형 문항인데 연결된 제시자료가 없습니다. 문항 생성 화면의 제시자료 영역에서 이미지를 선택하거나 문항 유형을 조정해주세요.</p>` : ""}
          ${renderQuestionImages(item.image_refs || [])}
          ${renderQuestionTable(item.data_table)}

          <label>
            문제 본문
            <textarea data-review-field="problem" rows="6">${escapeHtml(item.problem || "")}</textarea>
          </label>

          <div class="field-grid five review-choices">
            ${renderChoiceEditors(item)}
          </div>

          <div class="field-grid two">
            <label>
              정답
              <select data-review-field="answer">${renderAnswerOptions(item.answer)}</select>
            </label>
            <label>
              검토 상태
              <select data-review-field="review_status">
                <option value="draft" ${reviewStatus === "draft" ? "selected" : ""}>초안</option>
                <option value="needs_revision" ${reviewStatus === "needs_revision" ? "selected" : ""}>수정 필요</option>
                <option value="approved" ${reviewStatus === "approved" ? "selected" : ""}>승인</option>
                <option value="rejected" ${reviewStatus === "rejected" ? "selected" : ""}>반려</option>
              </select>
            </label>
          </div>

          <label>
            해설
            <textarea data-review-field="explanation" rows="7">${escapeHtml(item.explanation || "")}</textarea>
          </label>

          <label>
            검토 메모/사유
            <input data-review-field="review_reasons" value="${escapeHtml(reasons)}" placeholder="예: reference_needed, image_confirm_needed" />
          </label>

          ${references ? `<ol class="references">${references}</ol>` : ""}

          <div class="review-actions">
            <button type="button" class="secondary-button" data-review-action="save">수정 저장</button>
            <button type="button" data-review-action="approve">승인</button>
            <button type="button" class="danger-button" data-review-action="reject">반려</button>
          </div>
        </article>
      `;
    }).join("")}
  `;
}

function collectReviewUpdates(card) {
  const choices = Array.from(card.querySelectorAll('[data-review-field="choice"]'))
    .sort((a, b) => Number(a.dataset.choiceIndex) - Number(b.dataset.choiceIndex))
    .map((input) => input.value.trim());
  const reviewStatus = card.querySelector('[data-review-field="review_status"]')?.value || "draft";
  return {
    problem: card.querySelector('[data-review-field="problem"]')?.value.trim() || "",
    options: choices,
    answer: Number(card.querySelector('[data-review-field="answer"]')?.value || 1),
    explanation: card.querySelector('[data-review-field="explanation"]')?.value.trim() || "",
    review_status: reviewStatus,
    needs_review: reviewStatus === "needs_revision" || reviewStatus === "rejected",
    review_reasons: card.querySelector('[data-review-field="review_reasons"]')?.value || "",
  };
}

async function loadQuestionSet(setId) {
  return loadQuestionSetWithOptions(setId, { scroll: true });
}

async function loadQuestionSetWithOptions(setId, options = {}) {
  if (!setId) return;
  showPage("faculty-review", { updateHash: true, scrollTop: false });
  if (results) {
    results.className = "results-empty";
    results.textContent = "저장된 문항 세트를 불러오는 중입니다.";
  }
  const response = await fetch(`/api/question-sets/${encodeURIComponent(setId)}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "문항 세트 로드 실패");
  }
  renderReviewQuestionSet(payload);
  setStatus("문항 검토 로드 완료", "muted");
  if (options.scroll !== false && results?.scrollIntoView) {
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function loadLatestQuestionSetForReview() {
  if (!results || currentQuestionSet) return;
  if (latestReviewLoadPromise) return latestReviewLoadPromise;
  results.className = "results-empty";
  results.textContent = "최근 생성된 문항 세트를 불러오는 중입니다.";
  latestReviewLoadPromise = (async () => {
    const response = await fetch("/api/question-sets?limit=1");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "최근 문항 세트 로드 실패");
    }
    const latestSet = (payload.sets || [])[0];
    if (!latestSet?.set_id) {
      results.className = "results-empty";
      results.textContent = "아직 생성된 문항이 없습니다. 강의자료를 업로드하고 문항 초안을 생성해보세요.";
      return;
    }
    await loadQuestionSetWithOptions(latestSet.set_id, { scroll: false });
  })()
    .catch((error) => {
      results.className = "results-empty";
      results.textContent = `최근 문항 세트 로드 실패: ${error.message}`;
    })
    .finally(() => {
      latestReviewLoadPromise = null;
    });
  return latestReviewLoadPromise;
}

async function submitReviewAction(card, action) {
  const setId = currentQuestionSet?.set_id;
  const questionId = card?.dataset?.questionId;
  if (!setId || !questionId) return;
  const updates = collectReviewUpdates(card);
  const cardTop = card.getBoundingClientRect().top;
  const endpoint = action === "save"
    ? `/api/question-sets/${encodeURIComponent(setId)}/questions/${encodeURIComponent(questionId)}`
    : `/api/question-sets/${encodeURIComponent(setId)}/questions/${encodeURIComponent(questionId)}/${action}`;
  const method = action === "save" ? "PATCH" : "POST";
  const button = card.querySelector(`[data-review-action="${action}"]`);
  if (button) button.disabled = true;
  setStatus(action === "approve" ? "승인 저장 중" : action === "reject" ? "반려 저장 중" : "수정 저장 중");
  try {
    const response = await fetch(endpoint, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        updates,
        actor_id: "local_faculty",
        comment: action === "approve" ? "문항 승인" : action === "reject" ? "문항 반려" : "문항 수정",
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "문항 저장 실패");
    }
    await loadQuestionSetWithOptions(setId, { scroll: false });
    const refreshedCard = results?.querySelector(`[data-question-id="${escapeCssValue(questionId)}"]`);
    if (refreshedCard) {
      window.scrollTo({
        top: window.scrollY + refreshedCard.getBoundingClientRect().top - cardTop,
        behavior: "auto",
      });
    }
    await loadArchiveSets();
    setStatus(action === "approve" ? "승인 완료" : action === "reject" ? "반려 완료" : "수정 저장 완료", "muted");
  } catch (error) {
    setStatus("문항 저장 오류");
    card.insertAdjacentHTML(
      "beforeend",
      `<p class="inline-error">문항 저장 실패: ${escapeHtml(error.message)}</p>`
    );
  } finally {
    if (button) button.disabled = false;
  }
}

async function checkHealth() {
  if (!healthStatus) return;
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("bad health");
    healthStatus.textContent = "API 연결됨";
  } catch (error) {
    healthStatus.textContent = "API 연결 실패";
    healthStatus.classList.add("muted");
  }
}

function renderProviderOptions(catalog) {
  if (!providerSelect || !modelSelect) return;
  modelCatalog = catalog;
  providerSelect.innerHTML = "";
  for (const provider of catalog.providers || []) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.available ? provider.label : `${provider.label} (미연결)`;
    providerSelect.appendChild(option);
  }
  providerSelect.value = "auto";
  renderModelOptions();
}

function renderModelOptions() {
  if (!modelCatalog || !providerSelect || !modelSelect) return;
  const selectedProvider = providerSelect.value;
  const provider = (modelCatalog.providers || []).find((item) => item.id === selectedProvider);
  const models = provider?.models || [{ id: "auto", label: "자동", note: "" }];
  modelSelect.innerHTML = "";
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.note ? `${model.label} · ${model.note}` : model.label;
    modelSelect.appendChild(option);
  }
}

async function loadModels() {
  if (!modelSelect) return;
  try {
    const response = await fetch("/api/models");
    if (!response.ok) throw new Error("model catalog failed");
    renderProviderOptions(await response.json());
  } catch (error) {
    modelSelect.innerHTML = '<option value="auto">자동</option>';
  }
}

async function loadMediaAssets() {
  try {
    const response = await fetch("/api/media");
    if (!response.ok) throw new Error("media load failed");
    const payload = await response.json();
    mediaAssets = payload.assets || [];
    if (metricMedia) metricMedia.textContent = mediaAssets.length;
    renderMediaAssets(mediaAssets);
  } catch (error) {
    if (mediaBank) {
      mediaBank.className = "media-bank-empty";
      mediaBank.textContent = "제시자료를 불러오지 못했습니다.";
    }
  }
}

async function loadArchiveSets() {
  try {
    const response = await fetch("/api/question-sets?limit=8");
    if (!response.ok) throw new Error("archive load failed");
    const payload = await response.json();
    renderArchiveSets(payload.sets || []);
  } catch (error) {
    if (archiveList) {
      archiveList.className = "archive-empty";
      archiveList.textContent = "아카이브를 불러오지 못했습니다.";
    }
  }
}

bindChange(lectureFile, () => {
  if (lectureLabel) {
    lectureLabel.textContent = fileSummary(lectureFile, "PDF, PPTX, DOCX, HWP, TXT");
  }
});

bindChange(styleFiles, () => {
  if (styleLabel) {
    styleLabel.textContent = fileSummary(styleFiles, "선택 안 함");
  }
});

bindChange(evidenceFiles, () => {
  if (evidenceLabel) {
    evidenceLabel.textContent = fileSummary(evidenceFiles, "선택 안 함");
  }
});

bindChange(imageFiles, () => {
  if (imageLabel) {
    imageLabel.textContent = fileSummary(imageFiles, "선택 안 함");
  }
});

bindChange(mediaFile, () => {
  if (mediaFileLabel) {
    mediaFileLabel.textContent = fileSummary(mediaFile, "선택 안 함");
  }
});

bindChange(courseExamFile, () => {
  if (courseExamFileLabel) {
    courseExamFileLabel.textContent = fileSummary(courseExamFile, "HWP 또는 PDF 선택");
  }
});

bindChange(answerKeyFile, () => {
  if (answerKeyFileLabel) {
    answerKeyFileLabel.textContent = fileSummary(answerKeyFile, "선택 안 함");
  }
});

mediaSearch?.addEventListener("input", () => {
  renderMediaAssets(mediaAssets);
});

mediaTypeFilters.forEach((input) => {
  input.addEventListener("change", () => {
    renderMediaAssets(mediaAssets);
  });
});

bindChange(providerSelect, renderModelOptions);
bindChange(includeImagesToggle, handleImageToggleChange);
bindChange(questionTypeSelect, syncImagePolicyWithQuestionType);

pageLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(link.dataset.pageLink);
    if (link.dataset.pageLink === "faculty-review") {
      loadLatestQuestionSetForReview();
    }
  });
});

roleButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const role = button.dataset.roleToggle;
    showPage(role === "student" ? "student-dashboard" : "faculty-dashboard");
  });
});

document.addEventListener("click", (event) => {
  const categoryCard = event.target.closest("[data-category-title]");
  if (!categoryCard) return;
  selectCategory(categoryCard.dataset.categoryTitle, categoryCard.dataset.categoryMode);
});

if (medlegalCaseList) {
  medlegalCaseList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-medlegal-case]");
    if (!button) return;
    loadMedlegalCase(button.dataset.medlegalCase);
  });
}

if (medlegalNoteForm) {
  medlegalNoteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!currentMedlegalCase) {
      renderMedlegalFeedback({
        feedback: {
          overall_score: 0,
          dimension_scores: {},
          missing_items: [],
          risky_phrases: [],
          recommended_revision: "먼저 훈련 케이스를 선택해주세요.",
          disclaimer: "Educational feedback only.",
        },
      });
      return;
    }
    if (medlegalSubmitButton) medlegalSubmitButton.disabled = true;
    if (medlegalFeedback) {
      medlegalFeedback.className = "medlegal-feedback empty";
      medlegalFeedback.textContent = "기록을 점검하는 중입니다.";
    }
    try {
      const response = await fetch(`/api/medlegal/cases/${encodeURIComponent(currentMedlegalCase.case_id)}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          learner_role: "clerkship_student",
          note_type: currentMedlegalCase.required_note_type,
          note_text: medlegalNoteText?.value || "",
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "기록 피드백 생성 실패");
      }
      renderMedlegalFeedback(payload);
    } catch (error) {
      if (medlegalFeedback) {
        medlegalFeedback.className = "medlegal-feedback empty";
        medlegalFeedback.textContent = `피드백 실패: ${error.message}`;
      }
    } finally {
      if (medlegalSubmitButton) medlegalSubmitButton.disabled = false;
    }
  });
}

window.addEventListener("hashchange", () => {
  const pageId = window.location.hash.replace("#", "");
  if (pageId) {
    showPage(pageId, { updateHash: false });
    if (pageId === "faculty-review") {
      loadLatestQuestionSetForReview();
    }
  }
});

if (mediaForm) {
  mediaForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!mediaFile?.files?.length) {
      if (mediaBank) {
        mediaBank.className = "media-bank-empty";
        mediaBank.textContent = "먼저 이미지 파일을 선택해주세요.";
      }
      return;
    }
    if (mediaUploadButton) mediaUploadButton.disabled = true;
    try {
      const payload = new FormData(mediaForm);
      const response = await fetch("/api/media", {
        method: "POST",
        body: payload,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "제시자료 저장 실패");
      }
      selectedMediaIds.add(data.asset.asset_id);
      mediaForm.reset();
      if (mediaFileLabel) mediaFileLabel.textContent = "선택 안 함";
      await loadMediaAssets();
      updateSelectedMediaInput();
      if (includeImagesToggle) includeImagesToggle.checked = true;
      if (imagePolicySelect) imagePolicySelect.value = "clinical_visuals";
      if (questionTypeSelect) questionTypeSelect.value = "image_based";
      updateImagePolicyState();
    } catch (error) {
      if (mediaBank) {
        mediaBank.className = "media-bank-empty";
        mediaBank.textContent = `제시자료 저장 실패: ${error.message}`;
      }
    } finally {
      if (mediaUploadButton) mediaUploadButton.disabled = false;
    }
  });
}

if (mediaBank) {
  mediaBank.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-media]");
    if (!button) return;
    const assetId = button.dataset.deleteMedia;
    if (!assetId) return;
    const ok = window.confirm("이 제시자료를 삭제할까요? 로컬 보관함과 현재 선택 목록에서 제거됩니다.");
    if (!ok) return;
    button.disabled = true;
    try {
      const response = await fetch(`/api/media/${encodeURIComponent(assetId)}`, {
        method: "DELETE",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "제시자료 삭제 실패");
      }
      selectedMediaIds.delete(assetId);
      updateSelectedMediaInput();
      await loadMediaAssets();
    } catch (error) {
      if (mediaBank) {
        mediaBank.insertAdjacentHTML(
          "afterbegin",
          `<p class="inline-error">제시자료 삭제 실패: ${escapeHtml(error.message)}</p>`
        );
      }
    } finally {
      button.disabled = false;
    }
  });
}

if (archiveList) {
  archiveList.addEventListener("click", async (event) => {
    const exportButton = event.target.closest("[data-export-anki]");
    if (exportButton) {
      exportButton.disabled = true;
      const originalText = exportButton.textContent;
      exportButton.textContent = "생성 중";
      try {
        const response = await fetch(
          `/api/question-sets/${encodeURIComponent(exportButton.dataset.exportAnki)}/export/anki`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ include_unapproved: false }),
          }
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Anki export 생성 실패");
        }
        window.location.href = payload.download_url;
      } catch (error) {
        archiveList.insertAdjacentHTML(
          "afterbegin",
          `<p class="inline-error">Anki export 실패: ${escapeHtml(error.message)}</p>`
        );
      } finally {
        exportButton.disabled = false;
        exportButton.textContent = originalText;
      }
      return;
    }

    const button = event.target.closest("[data-open-set]");
    if (!button) return;
    button.disabled = true;
    try {
      await loadQuestionSet(button.dataset.openSet);
    } catch (error) {
      if (results) {
        results.className = "results-empty";
        results.textContent = `문항 세트 로드 실패: ${error.message}`;
      }
    } finally {
      button.disabled = false;
    }
  });
}

if (results) {
  results.addEventListener("click", async (event) => {
    const image = event.target.closest("[data-lightbox-src]");
    if (image && imageLightbox && lightboxImage) {
      lightboxImage.src = image.dataset.lightboxSrc;
      lightboxImage.alt = image.alt || "확대 이미지";
      if (lightboxCaption) lightboxCaption.textContent = image.dataset.lightboxCaption || "";
      imageLightbox.showModal();
      return;
    }
    const button = event.target.closest("[data-review-action]");
    if (!button) return;
    const card = button.closest("[data-question-id]");
    await submitReviewAction(card, button.dataset.reviewAction);
  });
}

startStudentPracticeButton?.addEventListener("click", startStudentPractice);

studentPracticeStage?.addEventListener("click", (event) => {
  const image = event.target.closest("[data-lightbox-src]");
  if (image && imageLightbox && lightboxImage) {
    lightboxImage.src = image.dataset.lightboxSrc;
    lightboxImage.alt = image.alt || "확대 이미지";
    if (lightboxCaption) lightboxCaption.textContent = image.dataset.lightboxCaption || "";
    imageLightbox.showModal();
    return;
  }

  const choiceButton = event.target.closest("[data-practice-choice]");
  if (choiceButton) {
    const question = currentPracticeExam?.questions?.[currentPracticeIndex];
    if (!question) return;
    const questionKey = question.question_id || String(question.question_number || currentPracticeIndex);
    currentPracticeAnswers[questionKey] = choiceButton.dataset.practiceChoice;
    renderStudentPracticeQuestion();
    return;
  }

  const resetButton = event.target.closest("[data-practice-reset]");
  if (resetButton) {
    currentPracticeExam = null;
    currentPracticeIndex = 0;
    currentPracticeAnswers = {};
    studentPracticePage?.classList.remove("practice-active");
    studentPracticeStage.className = "practice-layout";
    studentPracticeStage.innerHTML = `
      <article class="practice-question empty-practice">
        <p>기출/과정시험 세트를 선택하면 UWorld식 문제풀이 화면으로 열립니다.</p>
      </article>
      <aside class="practice-helper">
        <h3>학습 모드 도구</h3>
        <button type="button" class="secondary-button" data-page-link="student-concepts">관련 개념 열기</button>
        <button type="button" class="secondary-button" data-page-link="student-review">Anki 카드 만들기</button>
        <p>세트 선택 후 문제를 풀면 정답/해설, 관련 개념, 복습 카드가 같은 흐름으로 이어집니다.</p>
      </aside>
    `;
    if (studentPracticeStatus) {
      studentPracticeStatus.textContent = `${studentExamSelect?.options?.length || 0}개 풀이 가능 세트를 불러왔습니다. 세트를 선택해 문제 풀이를 시작할 수 있습니다.`;
    }
    return;
  }

  const navButton = event.target.closest("[data-practice-nav]");
  if (navButton) {
    if (navButton.dataset.practiceNav === "prev") {
      currentPracticeIndex = Math.max(0, currentPracticeIndex - 1);
    } else {
      const lastIndex = Math.max(0, (currentPracticeExam?.questions || []).length - 1);
      currentPracticeIndex = Math.min(lastIndex, currentPracticeIndex + 1);
    }
    renderStudentPracticeQuestion();
    return;
  }

  const jumpButton = event.target.closest("[data-practice-jump]");
  if (!jumpButton) return;
  const jumpIndex = Number(jumpButton.dataset.practiceJump);
  const lastIndex = Math.max(0, (currentPracticeExam?.questions || []).length - 1);
  if (Number.isFinite(jumpIndex)) {
    currentPracticeIndex = Math.max(0, Math.min(lastIndex, jumpIndex));
    renderStudentPracticeQuestion();
  }
});

lightboxClose?.addEventListener("click", () => {
  imageLightbox?.close();
});

imageLightbox?.addEventListener("click", (event) => {
  if (event.target === imageLightbox) {
    imageLightbox.close();
  }
});

if (courseExamForm) {
  courseExamForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!courseExamFile?.files?.length) {
      if (courseExamImportResult) {
        courseExamImportResult.hidden = false;
        courseExamImportResult.innerHTML = '<p class="inline-error">먼저 HWP/PDF 시험지를 선택해주세요.</p>';
      }
      return;
    }

    if (courseExamButton) courseExamButton.disabled = true;
    setStatus("시험지 구조화 중");
    if (courseExamImportResult) {
      courseExamImportResult.hidden = false;
      courseExamImportResult.textContent = "시험지를 문항 단위로 나누고 정답지/제시자료 후보를 연결하는 중입니다.";
    }

    try {
      const payload = new FormData(courseExamForm);
      const response = await fetch("/api/course-exams/import", {
        method: "POST",
        body: payload,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "시험지 구조화 실패");
      }
      renderCourseExamImportResult(data);
      await loadStudentCourseExams();
      setStatus("시험지 구조화 완료", "muted");
    } catch (error) {
      setStatus("시험지 구조화 오류");
      if (courseExamImportResult) {
        courseExamImportResult.hidden = false;
        courseExamImportResult.innerHTML = `<p class="inline-error">시험지 구조화 실패: ${escapeHtml(error.message)}</p>`;
      }
    } finally {
      if (courseExamButton) courseExamButton.disabled = false;
    }
  });
}

if (form) {
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (generateButton) {
    generateButton.disabled = true;
  }
  setStatus("업로드 중");
  if (results) {
    results.className = "results-empty";
    results.textContent = "파일을 서버로 보내고 있습니다. 큰 PDF/HWP나 Claude Code 생성은 몇 분 걸릴 수 있습니다.";
  }

  try {
    const payload = new FormData(form);
    if (!payload.get("lecture_file") || !payload.get("lecture_file").name) {
      throw new Error("강의자료 파일을 먼저 선택해주세요.");
    }
    if (!includeImagesToggle?.checked) {
      payload.set("image_policy", "none");
    }
    payload.set("selected_media_ids", Array.from(selectedMediaIds).join(","));
    startProgressTimer(payload);
    if (results?.scrollIntoView) {
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    const response = await fetch("/api/generate", {
      method: "POST",
      body: payload,
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : { detail: await response.text() };
    if (!response.ok) {
      throw new Error(data.detail || "생성 실패");
    }

    setStatus(data.status === "generated" ? "생성 완료" : "프롬프트 준비");
    finishProgress();
    setProgressMessage(
      data.status === "generated"
        ? "문항 초안 생성이 완료됐습니다. 이제 문항 검토 화면에서 문제, 해설, 참고문헌을 확인하면 됩니다."
        : "API/Claude 생성 대신 프롬프트 패킷이 준비됐습니다. 실제 문항 생성을 원하면 제공자를 Claude Code 계정 또는 API로 선택해주세요."
    );
    if (metricQuestions) metricQuestions.textContent = data.question_count || 0;
    setReviewCount((data.sample || []).filter((item) => item.needs_review).length);
    if (metricMedia) metricMedia.textContent = mediaAssets.length;

    if (data.status === "prompt_ready") {
      showPage("faculty-review", { scrollTop: false });
      renderPromptReady(data);
    } else if (data.set_id) {
      await loadQuestionSet(data.set_id);
    } else {
      showPage("faculty-review", { scrollTop: false });
      renderQuestions(data);
    }
    await loadArchiveSets();
  } catch (error) {
    setStatus("오류");
    finishProgress("error");
    setProgressMessage("생성 중 문제가 발생했습니다. 아래 오류 문구를 확인하고, 우선 생성 개수를 2~3개로 줄여 다시 시도해보세요.");
    if (results) {
      results.className = "results-empty";
      results.textContent = `처리 실패: ${error.message}`;
    }
  } finally {
    clearProgressTimer();
    if (generateButton) {
      generateButton.disabled = false;
    }
  }
});
}

checkHealth();
renderCategoryGrid(facultyCategoryGrid, "faculty");
renderCategoryGrid(studentCategoryGrid, "student");
loadModels();
loadMediaAssets();
loadArchiveSets();
loadStudentCourseExams();
updateImagePolicyState();
showPage(window.location.hash.replace("#", "") || "faculty-dashboard", {
  updateHash: false,
  scrollTop: true,
});
if (window.location.hash === "#faculty-review") {
  loadLatestQuestionSetForReview();
}

if (window.location.hash) {
  const restoreTop = () => window.scrollTo({ top: 0, behavior: "auto" });
  window.requestAnimationFrame(restoreTop);
  window.setTimeout(restoreTop, 120);
  window.setTimeout(restoreTop, 480);
}
