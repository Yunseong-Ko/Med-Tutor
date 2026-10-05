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
const imageConfigBlock = document.querySelector("#imageConfigBlock");
const questionTypeSelect = document.querySelector('select[name="question_type"]');
const targetAxisTypeSelect = document.querySelector("#targetAxisTypeSelect");
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
const ankiCardDialog = document.querySelector("#ankiCardDialog");
const ankiCardDialogBody = document.querySelector("#ankiCardDialogBody");
const ankiCardDialogClose = document.querySelector("#ankiCardDialogClose");
const appTitle = document.querySelector("#appTitle");
const appSubtitle = document.querySelector("#appSubtitle");
const workspaceRail = document.querySelector("#workspaceRail");
const workspaceRailToggle = document.querySelector("#workspaceRailToggle");
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
const studentPracticeShuffle = document.querySelector("#studentPracticeShuffle");
const studentPracticeCount = document.querySelector("#studentPracticeCount");
const startStudentPracticeButton = document.querySelector("#startStudentPractice");
const studentPracticeStatus = document.querySelector("#studentPracticeStatus");
const studentPracticeStage = document.querySelector("#studentPracticeStage");
const studentPracticePage = document.querySelector("#student-practice");
const studentCourseBuilder = document.querySelector("#studentCourseBuilder");
const studentReviewAnalytics = document.querySelector("#studentReviewAnalytics");
const facultyReportAnalytics = document.querySelector("#facultyReportAnalytics");
const cpxOsceModule = document.querySelector("#cpxOsceModule");

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
let currentPracticePendingAnswers = {};
let currentPracticeAnswerEvents = {};
let currentPracticeTimeByQuestion = {};
let currentPracticeViewed = new Set();
let currentPracticeBookmarks = new Set();
let currentPracticeFlags = {};
let currentPracticeExpandedChoices = {};
let currentPracticeTab = "key";
let currentPracticeSidebarCollapsed = false;
let currentPracticeSessionId = null;
let currentPracticeSessionStartedAt = null;
let currentPracticeActiveQuestionKey = null;
let currentPracticeQuestionStartedAt = null;
let currentPracticeTimerPaused = false;
let practiceRagEvidenceCache = {};
let practiceRagAnkiCache = {};
let practiceChoiceExplanationCache = {};
let courseExamDetailCache = {};
let studentLibraryIndex = null;
let studentLibraryMajorLookup = {};
let studentLibraryTopicLookup = {};
let selectedLibraryTopicIds = new Set();
let studentCategoryQuestionCounts = {};
let selectedLibraryCourseKey = "hematology_oncology";
let studentLibraryRenderSeq = 0;
let practiceTimerInterval = null;
let practiceAnkiStyleText = true;
let practiceSelectedAnkiCardIds = new Set();
let practiceAnkiDialogCards = [];
const CPX_OSCE_STORAGE_KEY = "paccine.cpxosce.state.v1";
const CPX_OSCE_TABS = new Set(["study", "diagnosis", "checklist", "patient", "summary", "coach"]);
let cpxOsceState = {
  selectedCaseId: "",
  query: "",
  category: "전체",
  activeTab: "study",
  checklistSectionId: "history",
  checked: {},
  notes: {},
  coachMessages: {},
  coachDraft: "",
  timerRemaining: 12 * 60,
  timerRunning: false,
  timerCaseId: "",
};
let cpxOsceTimerInterval = null;

try {
  const restoredMediaIds = JSON.parse(window.sessionStorage?.getItem("axioma.selectedMediaIds") || "[]");
  if (Array.isArray(restoredMediaIds)) {
    selectedMediaIds = new Set(restoredMediaIds.filter(Boolean));
  }
} catch (error) {
  selectedMediaIds = new Set();
}

const pageMeta = {
  "faculty-dashboard": ["교수 홈", "강의록 및 시험 기출 통합 아카이브"],
  "faculty-studio": ["문항 생성", "문항 파싱 및 JSON 변환"],
  "faculty-review": ["문항 검토", "승인 전 문항 확인"],
  "faculty-evidence": ["근거 검토", "자동 부착된 논문 근거 승인·반려"],
  "faculty-archive": ["아카이브/내보내기", "승인 세트 보관과 export"],
  "faculty-report": ["시험 피드백", "학생 피드백·오답 분석·취약 영역 정리"],
  "faculty-ops": ["운영 보드", "팀 작업 배분과 주차별 산출물 관리"],
  "faculty-medlegal": ["EMR/CPX 훈련", "의료법·설명의무·진료기록 교육"],
  "student-dashboard": ["학습 홈", "문항 세트와 풀이 기록"],
  "student-library": ["나의 서재", "시험지·파트별 문항 선택"],
  "student-practice": ["문제 풀기", "승인 문항 기반 학습/시험 모드"],
  "student-cpx-osce": ["CPX/OSCE", "실전 스테이션과 술기 체크리스트"],
  "student-concepts": ["개념 노트", "Obsidian식 문항·강의록·레퍼런스 연결"],
  "student-review": ["학습 리포트", "풀이 기록과 취약 영역"],
};

const departmentCategories = [
  { key: "infectious_diseases", title: "감염학", icon: "감", tone: "green", desc: "감염질환, 항생제, 감염관리" },
  { key: "musculoskeletal", title: "근골격학", icon: "근", tone: "blue", desc: "관절, 근육, 외상, 류마티스" },
  { key: "endocrinology", title: "내분비학", icon: "내", tone: "amber", desc: "당뇨, 갑상샘, 부신, 대사" },
  { key: "immunology_dermatology", title: "면역및피부질환", icon: "면", tone: "teal", desc: "면역, 알레르기, 피부질환" },
  { key: "reproductive_medicine", title: "생식계의학", icon: "생", tone: "rose", desc: "산부인과, 생식, 임신과 분만" },
  { key: "growth_development_aging", title: "성장발달노화", icon: "성", tone: "amber", desc: "소아 성장, 발달, 노화" },
  { key: "clinical_intro", title: "임상의학입문", icon: "입", tone: "blue", desc: "기본진료, 급성 복증, 탈장" },
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

const WORKSPACE_RAIL_STORAGE_KEY = "paccine.workspaceRailCollapsed";

function applyWorkspaceRailState(collapsed, options = {}) {
  const { persist = true } = options;
  const isCompactViewport = window.matchMedia("(max-width: 820px)").matches;
  const shouldCollapse = Boolean(collapsed) && !isCompactViewport;
  document.body.classList.toggle("rail-collapsed", shouldCollapse);
  workspaceRailToggle?.setAttribute("aria-expanded", String(!shouldCollapse));
  workspaceRailToggle?.setAttribute("aria-label", shouldCollapse ? "내비게이션 펼치기" : "내비게이션 접기");
  const toggleGlyph = workspaceRailToggle?.querySelector("span");
  if (toggleGlyph) toggleGlyph.textContent = shouldCollapse ? "›" : "‹";
  if (persist) {
    try {
      window.localStorage?.setItem(WORKSPACE_RAIL_STORAGE_KEY, shouldCollapse ? "1" : "0");
    } catch (error) {
      // Storage is optional; navigation still works when it is unavailable.
    }
  }
}

function initWorkspaceRail() {
  if (!workspaceRail || !workspaceRailToggle) return;
  let storedCollapsed = false;
  try {
    storedCollapsed = window.localStorage?.getItem(WORKSPACE_RAIL_STORAGE_KEY) === "1";
  } catch (error) {
    storedCollapsed = false;
  }
  applyWorkspaceRailState(storedCollapsed, { persist: false });
  workspaceRailToggle.addEventListener("click", () => {
    applyWorkspaceRailState(!document.body.classList.contains("rail-collapsed"));
  });
  window.addEventListener("resize", () => {
    let preferredCollapsed = false;
    try {
      preferredCollapsed = window.localStorage?.getItem(WORKSPACE_RAIL_STORAGE_KEY) === "1";
    } catch (error) {
      preferredCollapsed = false;
    }
    applyWorkspaceRailState(preferredCollapsed, { persist: false });
  });
}

const categoryLearningMetrics = {
  infectious_diseases: { progress: 42, weakness: "항생제 선택" },
  musculoskeletal: { progress: 28, weakness: "외상 처치" },
  endocrinology: { progress: 56, weakness: "부신·대사" },
  immunology_dermatology: { progress: 34, weakness: "피부 병변" },
  reproductive_medicine: { progress: 49, weakness: "산과 응급" },
  growth_development_aging: { progress: 31, weakness: "성장곡선" },
  clinical_intro: { progress: 35, weakness: "응급 감별" },
  gastroenterology_nutrition: { progress: 63, weakness: "간담췌" },
  cardiology: { progress: 71, weakness: "심전도" },
  neuro_special_senses: { progress: 62, weakness: "병변 위치" },
  renal_urology: { progress: 38, weakness: "전해질" },
  human_society_medicine_1: { progress: 44, weakness: "역학 지표" },
  human_society_medicine_2: { progress: 58, weakness: "법규 적용" },
  psychiatry: { progress: 46, weakness: "면담·진단" },
  disease_pharmacology: { progress: 53, weakness: "금기 약물" },
  hematology_oncology: { progress: 39, weakness: "혈액도말" },
  pulmonology: { progress: 67, weakness: "흉부영상" },
};

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

function ontologyGenerationSummary(data) {
  const ontology = data?.ontology || data?.grounding || {};
  if (!ontology.ontology_used || !ontology.disease_concept_id) {
    return " · Ontology 미매칭(일반 생성 fallback)";
  }
  const axes = Number(ontology.axis_node_count || 0);
  const blueprint = data?.question_blueprint || {};
  const target = blueprint?.target || {};
  const targetAxis = target.axis_type ? ` · 평가 축 ${practiceLabelText(target.axis_type)}` : "";
  const blueprintStatus = blueprint.status === "blocked" ? " · 평가 축 확인 필요" : "";
  return ` · Ontology ${ontology.disease_concept_id} · 임상 축 ${axes}개 사용${targetAxis}${blueprintStatus}`;
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
      setProgressMessage("P:accine이 문항과 해설, 참고문헌을 구성하는 중입니다. 현재 단계는 오래 걸려도 정상일 수 있습니다.");
    } else if (elapsed >= 45) {
      setProgressMessage(`강의자료를 바탕으로 ${count || "선택한 개수"}문항 초안을 만드는 중입니다. 보통 2문항 기준 1~3분 정도 걸립니다.`);
    } else if (elapsed >= 15) {
      setProgressMessage("업로드는 완료됐고, 강의록 텍스트와 이미지 후보를 정리한 뒤 문항 초안을 구성하는 중입니다.");
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
      sidebarNoteCopy.textContent = "학교 강의록과 승인 문항을 기준으로 문제, 개념, 복습 카드를 연결합니다.";
    } else {
      sidebarNoteTitle.textContent = "자료 원칙";
      sidebarNoteCopy.textContent = "문항과 제시자료는 출처 확인 후 DB에 반영됩니다.";
    }
  }
}

function showPage(pageId, options = {}) {
  const safePage = pageMeta[pageId] ? pageId : "faculty-dashboard";
  if (safePage === "student-cpx-osce") {
    window.location.assign("/cpx-osce/");
    return;
  }
  if (safePage !== "student-practice") {
    document.body.classList.remove("practice-session-active");
  }
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
  if (safePage === "student-library") {
    if (!courseExamPracticeList.length) {
      loadStudentCourseExams();
    } else {
      renderStudentLibraryCourseBuilder(selectedLibraryCourseKey);
    }
  }
  if (safePage === "student-review") {
    loadStudentPracticeAnalytics();
  }
  if (safePage === "faculty-report") {
    loadFacultyPracticeAnalytics();
    loadFacultyFeedback();
    loadDistractorAnalysis();
  }
  if (safePage === "faculty-evidence") {
    loadEvidenceReview();
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
  imageConfigBlock?.classList.toggle("is-active", enabled);
  updateSelectedMediaInput();
}

function initFeedbackWidget() {
  const fabButton = document.querySelector("#feedbackFabButton");
  const panel = document.querySelector("#feedbackPanel");
  const closeButton = document.querySelector("#feedbackPanelClose");
  const ratingButtons = Array.from(document.querySelectorAll(".feedback-rating button[data-feedback-rating]"));
  const comment = document.querySelector("#feedbackComment");
  const submitButton = document.querySelector("#feedbackSubmitButton");
  const status = document.querySelector("#feedbackStatus");
  if (!fabButton || !panel) return;

  let selectedRating = null;

  const setPanelOpen = (open) => {
    panel.hidden = !open;
  };

  fabButton.addEventListener("click", () => setPanelOpen(panel.hidden));
  closeButton?.addEventListener("click", () => setPanelOpen(false));

  ratingButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedRating = Number(button.dataset.feedbackRating);
      ratingButtons.forEach((btn) => btn.classList.toggle("active", btn === button));
    });
  });

  submitButton?.addEventListener("click", async () => {
    if (!selectedRating) {
      if (status) status.textContent = "먼저 만족도 점수를 선택해주세요.";
      return;
    }
    submitButton.disabled = true;
    if (status) status.textContent = "보내는 중입니다...";
    try {
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          rating: selectedRating,
          comment: comment?.value || "",
          page: window.location.hash.replace("#", "") || "",
          exam_id: currentPracticeExam?.exam_id || "",
        }),
      });
      if (!response.ok) throw new Error("전송 실패");
      if (status) status.textContent = "소중한 의견 감사합니다!";
      if (comment) comment.value = "";
      selectedRating = null;
      ratingButtons.forEach((btn) => btn.classList.remove("active"));
      window.setTimeout(() => setPanelOpen(false), 1200);
    } catch (error) {
      if (status) status.textContent = "전송에 실패했습니다. 다시 시도해주세요.";
    } finally {
      submitButton.disabled = false;
    }
  });
}

function initStudioMethodTabs() {
  const tabButtons = document.querySelectorAll(".studio-method-tabs button[data-studio-method]");
  const panels = document.querySelectorAll(".studio-method-panel[data-studio-panel]");
  if (!tabButtons.length || !panels.length) return;
  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const method = button.dataset.studioMethod;
      tabButtons.forEach((btn) => btn.classList.toggle("active", btn === button));
      panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.studioPanel === method));
      if (method === "simple") renderSimpleImagePicker();
    });
  });
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

function initTopicImageFinder() {
  const button = document.querySelector("#findTopicImagesButton");
  const hint = document.querySelector("#topicImageHint");
  if (!button) return;
  button.addEventListener("click", () => {
    const unit = document.querySelector("#studioUnitInput")?.value?.trim() || "";
    const subject = document.querySelector("#studioSubjectInput")?.value?.trim() || "";
    const topic = unit || subject;
    if (!topic) {
      if (hint) hint.textContent = "먼저 과목명이나 단원명을 입력하세요.";
      return;
    }
    if (mediaSearch) {
      mediaSearch.value = topic;
      renderMediaAssets(mediaAssets);
    }
    // 이미지 삽입을 자동으로 켜서 고른 이미지가 문항에 반영되게 한다.
    if (includeImagesToggle && !includeImagesToggle.checked) {
      includeImagesToggle.checked = true;
      updateImagePolicyState();
    }
    const matched = mediaAssets.filter((asset) => mediaMaterialText(asset).includes(topic.toLowerCase())).length;
    if (hint) {
      hint.textContent = matched
        ? `"${topic}" 관련 이미지 ${matched}개를 오른쪽 제시자료에서 확인하세요.`
        : `"${topic}" 관련 저장 이미지가 없습니다. 오른쪽에서 새로 저장하거나 검색어를 바꿔보세요.`;
    }
    document.querySelector(".media-helper-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function initQuestionPresetChips() {
  const chipWrap = document.querySelector("#questionPresetChips");
  if (!chipWrap) return;
  const chips = Array.from(chipWrap.querySelectorAll(".preset-chip"));
  const difficultySelect = document.querySelector("#difficultySelect");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.toggle("active", c === chip));
      if (questionTypeSelect && chip.dataset.preset) {
        questionTypeSelect.value = chip.dataset.preset;
        // 이미지형 프리셋이 아니면 이미지 자동토글 원복
        syncImagePolicyWithQuestionType();
        syncTargetAxisWithQuestionType();
      }
      if (difficultySelect && chip.dataset.difficulty) {
        difficultySelect.value = chip.dataset.difficulty;
      }
    });
  });
}

function suggestedTargetAxis(questionType) {
  return {
    mechanism: "pathophysiology",
    diagnostic: "diagnosis",
    management: "treatment",
  }[questionType] || "";
}

function syncTargetAxisWithQuestionType() {
  if (!questionTypeSelect || !targetAxisTypeSelect) return;
  const suggested = suggestedTargetAxis(questionTypeSelect.value);
  if (suggested) targetAxisTypeSelect.value = suggested;
}

function initTopicGenerate() {
  const form = document.querySelector("#topicGenerateForm");
  if (!form) return;
  const chips = Array.from(document.querySelectorAll("#topicPresetChips .preset-chip"));
  const qtField = document.querySelector("#topicGenQuestionType");
  const diffField = document.querySelector("#topicGenDifficulty");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.toggle("active", c === chip));
      if (qtField) qtField.value = chip.dataset.preset || "clinical_case";
      if (diffField) diffField.value = chip.dataset.difficulty || "보통";
    });
  });

  const button = document.querySelector("#topicGenerateButton");
  const status = document.querySelector("#topicGenerateStatus");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const topic = document.querySelector("#topicGenTopic")?.value?.trim();
    if (!topic) {
      if (status) status.textContent = "출제 주제를 입력하세요.";
      return;
    }
    const body = {
      topic,
      teaching_points: document.querySelector("#topicGenPoints")?.value || "",
      textbook_reference: document.querySelector("#topicGenRef")?.value || "",
      subject: document.querySelector("#topicGenSubject")?.value || "",
      unit: document.querySelector("#topicGenUnit")?.value || "",
      num_questions: Number(document.querySelector("#topicGenCount")?.value || 5),
      question_type: qtField?.value || "clinical_case",
      target_axis_type: document.querySelector("#topicGenTargetAxisType")?.value || "",
      difficulty: diffField?.value || "보통",
      provider: "auto",
      model: "auto",
    };
    if (button) button.disabled = true;
    if (status) status.textContent = "주제로 문항을 생성하는 중입니다. 잠시만 기다려주세요.";
    try {
      const response = await fetch("/api/generate-from-topic", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "생성 실패");
      if (status) {
        status.textContent = `${payload.question_count || 0}문항 초안을 만들었습니다. 문항 검토 화면으로 이동합니다.`;
      }
      if (payload.set_id) {
        await loadQuestionSet(payload.set_id);
        showPage("faculty-review", { scrollTop: true });
      } else {
        showPage("faculty-review", { scrollTop: true });
        renderQuestions(payload);
      }
      await loadArchiveSets();
    } catch (error) {
      if (status) status.textContent = `생성 실패: ${error.message}`;
    } finally {
      if (button) button.disabled = false;
    }
  });
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
  const year = summary.exam_date ? String(summary.exam_date).slice(0, 4) : "";
  return [
    summary.course_name || "미분류 시험",
    year,
    summary.round_label,
    summary.period_label,
    summary.question_count ? `${summary.question_count}문항` : "",
  ].filter(Boolean).join(" · ");
}

function shuffleArray(items) {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

function practiceSourceTags(question) {
  const summary = question?._source_summary || currentPracticeExam?.summary || {};
  const labels = question?.labels || {};
  const tags = [
    labels.source_label,
    question.source_exam || summary.source_file || summary.course_name,
    question.period || summary.round_label,
    question.source_page ? `p.${question.source_page}` : "",
    question.source_file ? "강의록/기출 기반" : "PNU internal source",
  ].filter(Boolean);
  const uniqueTags = [...new Set(tags)].slice(0, 4);
  return uniqueTags
    .map((tag) => `<span class="provenance-chip">${escapeHtml(tag)}</span>`)
    .join("");
}

function practiceLabelText(value) {
  const normalized = String(value || "").trim();
  const labelMap = {
    application: "적용",
    clinical_reasoning: "임상 추론",
    concept: "개념 확인",
    diagnosis: "진단",
    ethics_policy: "의료윤리/정책",
    image_interpretation: "자료해석",
    interpretation: "자료해석",
    management: "치료/처치",
    recall: "개념 확인",
    treatment: "치료",
  };
  return labelMap[normalized] || normalized.replaceAll("_", " ");
}

function compactUniqueList(values, max = 3) {
  return [...new Set((values || []).map((value) => practiceLabelText(value)).filter(Boolean))]
    .slice(0, max);
}

function questionSourceLabel(question) {
  const labels = question?.labels || {};
  const summary = question?._source_summary || currentPracticeExam?.summary || {};
  return practiceLabelText(labels.source_label || summary.round_label || question?.period || summary.source_file || "");
}

function questionFacultyLabel(question) {
  const labels = question?.labels || {};
  return practiceLabelText(labels.faculty_verified || labels.faculty || labels.professor || "");
}

function questionMajorTopicLabel(question) {
  const labels = question?.labels || {};
  const major = practiceLabelText(labels.major_category || labels.course_name_labeled || "");
  const topic = practiceLabelText(labels.topic || labels.subtopic || "");
  return [major, topic].filter(Boolean).join(" · ");
}

function practiceQuestionMetaChips(question) {
  const chips = [
    questionSourceLabel(question),
    questionFacultyLabel(question) ? `${questionFacultyLabel(question)} 교수` : "",
    questionMajorTopicLabel(question),
  ].filter(Boolean);
  return compactUniqueList(chips, 4)
    .map((chip) => `<span class="question-meta-chip">${escapeHtml(chip)}</span>`)
    .join("");
}

function practiceQuestionTypeLabel(question) {
  const labels = question?.labels || {};
  return practiceLabelText(
    labels.question_type_labeled
      || labels.question_type
      || labels.cognitive_level
      || "과정시험"
  );
}

function explanationNeedsSupplement(explanation) {
  const text = String(explanation || "").trim();
  return text.length < 40 || /해설 없음|해설없음|미기재|검토 필요|없습니다/.test(text);
}

function practiceExplanationInfo(question, answer, labels, conceptTags) {
  const keyInfo = question?.key_info && typeof question.key_info === "object" ? question.key_info : {};
  const importedPieces = [
    keyInfo.core_explanation,
    question?.answer_rationale,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  if (importedPieces.length) {
    return {
      text: importedPieces.join(" "),
      supplemental: false,
      imported: true,
    };
  }
  const original = String(question?.explanation || "").trim();
  const supplemental = explanationNeedsSupplement(original);
  if (!supplemental) {
    return { text: original, supplemental: false };
  }
  return {
    text: "",
    supplemental: true,
  };
}

const practiceCircledDigitMap = {
  "①": "1",
  "②": "2",
  "③": "3",
  "④": "4",
  "⑤": "5",
  "⑥": "6",
  "⑦": "7",
  "⑧": "8",
};

const practiceAnkiStopwords = new Set([
  "this",
  "that",
  "with",
  "from",
  "patient",
  "patients",
  "finding",
  "findings",
  "following",
  "which",
  "대한",
  "다음",
  "가장",
  "문항",
  "환자",
  "정답",
  "선지",
  "근거",
  "설명",
  "확인",
  "필요",
]);

const practiceBadAnkiPhrases = [
  "정답은",
  "이 문항은",
  "지문에서",
  "정답 선지",
  "문항으로 분류",
  "근거 출처",
  "검토",
  "부족",
  "교수",
  "조교",
];

const practiceWeakExplanationPhrases = [
  "정답은",
  "이 문항은",
  "저장된 해설",
  "검토가 필요",
  "검토 필요",
  "근거가 부족",
  "근거 부족",
  "원문 해설이 짧아",
  "보강이 필요",
  "강의록 근거와 교수 검토",
  "지문에서 결정 단서",
  "정답 선지와 나머지 선지",
  "정답 근거 확인이 필요",
];

function normalizePracticeChoiceKey(value) {
  const text = String(value || "").trim();
  if (practiceCircledDigitMap[text]) return practiceCircledDigitMap[text];
  for (const [marker, digit] of Object.entries(practiceCircledDigitMap)) {
    if (text.includes(marker)) return digit;
  }
  const match = text.match(/[1-8]/);
  return match ? match[0] : text;
}

function practiceAnswerKeys(question) {
  const source = Array.isArray(question?.generated_answer) && question.generated_answer.length
    ? question.generated_answer
    : Array.isArray(question?.answer) ? question.answer : [question?.answer];
  return Array.from(
    new Set(source.map(normalizePracticeChoiceKey).filter(Boolean))
  );
}

function practicePrimaryAnswer(question) {
  return practiceAnswerKeys(question)[0] || "";
}

function practiceAnswerLabel(question) {
  const keys = practiceAnswerKeys(question);
  return keys.length ? keys.join(", ") : "미확인";
}

function practiceChoiceIsCorrect(question, choiceKey) {
  return practiceAnswerKeys(question).includes(normalizePracticeChoiceKey(choiceKey));
}

function practiceNormalizeAnswerSelection(value) {
  const source = Array.isArray(value) ? value : value ? [value] : [];
  return Array.from(
    new Set(source.map(normalizePracticeChoiceKey).filter(Boolean))
  );
}

function practiceHasAnswerSelection(value) {
  return practiceNormalizeAnswerSelection(value).length > 0;
}

function practiceSelectionLabel(value) {
  const keys = practiceNormalizeAnswerSelection(value);
  return keys.length ? keys.join(", ") : "";
}

function practiceIsMultiAnswerQuestion(question) {
  return practiceAnswerKeys(question).length > 1;
}

function practiceSelectionIsCorrect(question, selection) {
  const answerKeys = practiceAnswerKeys(question);
  const selectedKeys = practiceNormalizeAnswerSelection(selection);
  return answerKeys.length > 0
    && answerKeys.length === selectedKeys.length
    && answerKeys.every((key) => selectedKeys.includes(key));
}

function isPlaceholderStimulus(value) {
  return /^<\s*(그림|사진|표|자료)\s*>$/.test(String(value || "").trim());
}

function splitPracticeSentences(text) {
  const cleaned = String(text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return [];
  return cleaned
    .split(/(?<=[.!?。！？다])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function extractPracticeMarkedExplanations(explanation) {
  const text = String(explanation || "").trim();
  const markerRegex = /(①|②|③|④|⑤|⑥|⑦|⑧|(?:^|[\s,.;:])([1-8])[\).])\s*/g;
  const matches = Array.from(text.matchAll(markerRegex));
  if (!matches.length) return {};
  const rows = {};
  matches.forEach((match, index) => {
    const marker = practiceCircledDigitMap[match[1]] || match[2] || normalizePracticeChoiceKey(match[1]);
    const start = (match.index || 0) + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index || text.length : text.length;
    const body = text.slice(start, end).trim().replace(/^[\s:;.-]+|[\s:;.-]+$/g, "");
    if (marker && body) rows[marker] = body;
  });
  return rows;
}

function normalizePracticeEducationalMediaItems(value) {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  return items
    .map((item) => {
      if (typeof item === "string") {
        const url = item.trim();
        return url ? { url, title: "해설 보조자료" } : null;
      }
      if (!item || typeof item !== "object") return null;
      const url = String(item.url || item.src || item.image_url || "").trim();
      const sourceUrl = String(item.source_url || item.sourceUrl || item.source || "").trim();
      const title = String(item.title || item.caption || item.name || "해설 보조자료").trim();
      if (!url && !sourceUrl && !title) return null;
      return {
        title,
        url,
        sourceUrl,
        type: String(item.type || item.kind || "diagram").trim(),
        note: String(item.note || item.description || "").trim(),
        license: String(item.license || "").trim(),
        attribution: String(item.attribution || "").trim(),
      };
    })
    .filter(Boolean);
}

function existingChoiceExplanationDetailMap(question) {
  const candidates = [
    question?.choice_explanations,
    question?.pma_solution?.choice_explanations,
    question?.explanations_by_choice,
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (Array.isArray(candidate)) {
      const rows = {};
      candidate.forEach((value, index) => {
        if (String(value || "").trim()) {
          rows[String(index + 1)] = { rationale: String(value).trim() };
        }
      });
      if (Object.keys(rows).length) return rows;
    }
    if (typeof candidate === "object") {
      const rows = {};
      Object.entries(candidate).forEach(([key, value]) => {
        if (typeof value === "object" && value) {
          const body = String(value.rationale || value.explanation || value.text || "").trim();
          if (body) {
            rows[normalizePracticeChoiceKey(key)] = {
              choiceText: value.choice_text || value.choiceText || "",
              rationale: body,
              isCorrect: Boolean(value.is_correct ?? value.isCorrect),
              needsReview: Boolean(value.needs_review ?? value.needsReview),
              learningPoints: Array.isArray(value.learning_points)
                ? value.learning_points
                : Array.isArray(value.learningPoints) ? value.learningPoints : [],
              educationalMedia: normalizePracticeEducationalMediaItems(
                value.educational_media || value.educationalMedia || value.media || value.media_refs
              ),
              source: value.source || "existing_choice_explanation",
              evidence: Array.isArray(value.evidence) ? value.evidence : [],
            };
          }
        } else {
          const body = String(value || "").trim();
          if (body) rows[normalizePracticeChoiceKey(key)] = { rationale: body };
        }
      });
      if (Object.keys(rows).length) return rows;
    }
  }
  return {};
}

function existingChoiceExplanationMap(question) {
  const details = existingChoiceExplanationDetailMap(question);
  return Object.fromEntries(
    Object.entries(details).map(([key, value]) => [key, value?.rationale || ""])
  );
}

function choiceKeywords(choiceText) {
  return Array.from(
    new Set(
      String(choiceText || "")
        .match(/[A-Za-z][A-Za-z0-9+\-/]{2,}|[가-힣]{2,}/g) || []
    )
  )
    .map((token) => token.toLowerCase())
    .filter((token) => !practiceAnkiStopwords.has(token));
}

function findChoiceMentionSentence(choiceText, explanation) {
  const keywords = choiceKeywords(choiceText);
  if (!keywords.length) return "";
  return splitPracticeSentences(explanation).find((sentence) => {
    const lower = sentence.toLowerCase();
    return keywords.some((keyword) => lower.includes(keyword));
  }) || "";
}

function isWeakPracticeExplanationText(text) {
  const value = String(text || "").trim();
  if (!value) return true;
  return practiceWeakExplanationPhrases.some((phrase) => value.includes(phrase));
}

function practiceChoiceLookup(question) {
  return Object.fromEntries(
    practiceChoiceEntries(question).map(([key, value]) => [
      normalizePracticeChoiceKey(key),
      String(value || "").trim(),
    ])
  );
}

function practiceQuestionFocus(question) {
  const stem = String(question?.stem || "").replace(/\s+/g, " ").trim();
  if (/가장\s*흔한\s*원인/.test(stem)) return "가장 흔한 원인";
  if (/초기\s*처치|우선.*처치|가장\s*적절한\s*처치/.test(stem)) return "가장 적절한 초기 처치";
  if (/치료|처방|투여/.test(stem)) return "가장 적절한 치료";
  if (/진단|의심/.test(stem)) return "가장 가능성 높은 진단";
  if (/검사|소견/.test(stem)) return "가장 중요한 검사/소견";
  if (/옳지\s*않|틀린\s*것|아닌\s*것|부적절/.test(stem)) return "틀린 진술";
  return "지문이 묻는 핵심 기준";
}

function isPracticeNegativeQuestion(question) {
  return /틀린\s*것|옳지\s*않|아닌\s*것|부적절|잘못|거리가\s*먼|해당하지/.test(String(question?.stem || ""));
}

function isCraniosynostosisQuestion(question) {
  const haystack = [
    question?.stem,
    question?.stimulus,
    question?.explanation,
    ...practiceChoiceEntries(question).map(([, value]) => value),
  ].join(" ");
  return /두개유합증|craniosynostosis|cranial\s*vault|두개천장|시상봉합|sagittal\s+suture/i.test(haystack);
}

function craniosynostosisLearningPoints(choiceText, isCorrect) {
  const lowerChoice = String(choiceText || "").toLowerCase();
  if (/cranial vault|두개천장/.test(lowerChoice)) {
    return [
      { label: "두개천장", body: "두개천장(cranial vault, calvaria)은 뇌를 덮는 두개골의 지붕 부분으로, 전두골·두정골·후두골 등이 봉합선으로 연결되어 성장합니다." },
      { label: "봉합선", body: "두개골 봉합선은 단순한 선이 아니라 성장판처럼 작동하는 섬유성 결합부입니다. 영아기와 소아기 두개골 성장은 이 봉합선을 통해 일어납니다." },
      { label: "핵심 법칙", body: "봉합이 조기에 유합되면 그 봉합선에 수직인 방향의 성장이 제한되고, 상대적으로 열린 봉합 방향으로 보상성 성장이 일어납니다." },
    ];
  }
  if (/crouzon|크루존|brachycephaly|단두/.test(lowerChoice)) {
    return [
      { label: "질환 연결", body: "Crouzon syndrome은 craniosynostosis를 동반할 수 있는 대표적 증후군성 두개유합증입니다." },
      { label: "형태", body: "양측 관상봉합 유합이 있으면 앞뒤 길이가 짧고 좌우 폭이 넓은 단두증(brachycephaly) 형태가 나타날 수 있습니다." },
      { label: "동반 소견", body: "안구돌출, 중안면 저형성, 상악 저형성 같은 얼굴뼈 발달 이상이 함께 나타날 수 있습니다." },
    ];
  }
  if (/lambdoid|삼각봉합|plagiocephaly|편평두/.test(lowerChoice)) {
    return [
      { label: "봉합 위치", body: "Lambdoid suture는 후두골과 두정골 사이에 있는 뒤쪽 봉합입니다." },
      { label: "형태", body: "한쪽 lambdoid suture가 조기에 유합되면 뒤쪽 두개골 성장이 비대칭이 되어 posterior plagiocephaly가 나타날 수 있습니다." },
      { label: "임상 구분", body: "위치성 사두증과 달리 lambdoid synostosis는 봉합 조기 유합에 따른 구조적 비대칭입니다." },
    ];
  }
  if (/sagittal|시상봉합/.test(lowerChoice)) {
    return [
      { label: "봉합 위치", body: "시상봉합(sagittal suture)은 양쪽 두정골 사이를 정중선에서 잇는 봉합입니다." },
      { label: "정상 유합", body: "이 정답지 기준에서는 시상봉합의 정상 유합 시작 시점을 10세 초반으로 봅니다. 1세 전후 시작이라는 서술은 정상 유합 시점으로는 너무 이릅니다." },
      { label: "조기 유합", body: "시상봉합이 병적으로 조기 유합되면 좌우 방향 성장이 제한되고 전후 방향 성장이 상대적으로 두드러져 주상두(scaphocephaly)가 나타날 수 있습니다." },
    ];
  }
  if (/metopic|전두봉합|trigonocephaly|삼각두/.test(lowerChoice)) {
    return [
      { label: "봉합 위치", body: "Metopic suture는 이마 중앙에서 양측 전두골 사이를 연결하는 봉합입니다." },
      { label: "형태", body: "Metopic suture가 조기에 유합되면 이마가 삼각형처럼 좁아지는 trigonocephaly가 나타날 수 있습니다." },
      { label: "임상 소견", body: "전두부 중앙 융기, 양측 전두부 협소화, 안와 사이 거리 감소가 함께 관찰될 수 있습니다." },
    ];
  }
  return [
    { label: "개념", body: "두개유합증은 두개골 봉합이 정상보다 일찍 닫혀 두개골 성장 방향과 머리 모양이 달라지는 질환군입니다." },
    { label: "검토 기준", body: "봉합 위치, 조기 유합 시 성장 제한 방향, 결과적 두개골 형태를 각각 분리해 연결합니다." },
  ];
}

function buildCraniosynostosisChoiceExplanation(question, choiceKey, answer) {
  const choices = practiceChoiceLookup(question);
  const choiceText = choices[choiceKey] || "해당 보기";
  const lowerChoice = choiceText.toLowerCase();
  const isCorrect = choiceKey === answer;
  let rationale = "";

  if (/cranial vault|두개천장/.test(lowerChoice)) {
    rationale = "두개천장(cranial vault)은 뇌를 덮는 두개골 지붕이고, 봉합선은 두개골 뼈 사이의 성장판 역할을 합니다. 두개유합증에서는 봉합이 너무 일찍 닫히면 그 봉합선에 수직인 방향의 골성장이 제한되고, 열린 봉합 방향으로 보상성 성장이 일어납니다.";
  } else if (/crouzon|크루존|brachycephaly|단두/.test(lowerChoice)) {
    rationale = "Crouzon syndrome은 증후군성 두개유합증의 대표 질환입니다. 관상봉합, 특히 양측 관상봉합이 조기에 유합되면 두개골의 앞뒤 성장이 제한되어 전후경이 짧아지는 단두증(brachycephaly)이 나타날 수 있습니다.";
  } else if (/lambdoid|삼각봉합|plagiocephaly|편평두/.test(lowerChoice)) {
    rationale = "Lambdoid suture는 뒤쪽 두개골에서 두정골과 후두골 사이를 잇는 봉합입니다. 한쪽 lambdoid suture가 조기에 유합되면 후두부 성장이 비대칭이 되어 posterior plagiocephaly로 나타날 수 있습니다.";
  } else if (/sagittal|시상봉합/.test(lowerChoice)) {
    rationale = "시상봉합(sagittal suture)은 양쪽 두정골 사이를 정중선에서 잇는 봉합입니다. 이 정답지 기준에서는 시상봉합의 정상 유합 시작 시점을 10세 초반으로 보므로, 정상 유합이 1세 전후에 시작된다는 서술은 너무 이릅니다. 시상봉합이 병적으로 조기 유합되면 전후로 긴 주상두(scaphocephaly)가 나타날 수 있습니다.";
  } else if (/metopic|전두봉합|trigonocephaly|삼각두/.test(lowerChoice)) {
    rationale = "Metopic suture는 이마 중앙에서 양측 전두골 사이를 잇는 봉합입니다. 전두봉합이 조기에 유합되면 이마가 삼각형처럼 좁아지고 안와 사이가 좁아지는 trigonocephaly가 나타날 수 있습니다.";
  } else {
    rationale = isCorrect
      ? "두개유합증에서는 봉합 위치, 조기 유합 시 성장 제한 방향, 결과적 두개골 형태를 함께 비교해야 합니다."
      : "두개유합증은 봉합 위치와 조기 유합 후 나타나는 두개골 형태를 연결해 이해합니다.";
  }

  return {
    choiceText,
    isCorrect,
    needsReview: false,
    rationale,
    learningPoints: craniosynostosisLearningPoints(choiceText, isCorrect),
    source: "concept_comparison",
    evidence: [],
    questionPolarity: "negative",
    statementStatus: isCorrect ? "false_statement" : "true_statement",
  };
}

function buildAutonomicDysreflexiaChoiceExplanation(question, choiceKey, answer) {
  const choices = practiceChoiceLookup(question);
  const choiceText = choices[choiceKey] || "해당 보기";
  const lowerChoice = choiceText.toLowerCase();
  const isCorrect = choiceKey === answer;
  let rationale = "";
  let learningPoints = [];

  if (isCorrect) {
    rationale = "방광팽창은 척수손상 환자의 자율신경 이상반사증에서 가장 먼저 떠올려야 하는 유발 요인입니다. 방광 과팽창, 요정체, 도뇨관 폐쇄 같은 방광 자극이 병변 아래쪽의 구심성 자극을 만들고, 상위 중추의 억제가 끊긴 상태에서 과도한 교감신경 반응이 발생합니다. 그래서 이 문항처럼 ‘가장 흔한 원인’을 묻는 경우에는 방광팽창이 정답입니다.";
    learningPoints = [
      ["개념", "자율신경 이상반사증은 대개 T6 이상 척수손상에서 병변 아래쪽 유해 자극이 과도한 교감신경 반응을 일으키는 상태입니다."],
      ["정답 근거", "방광팽창, 요정체, 도뇨관 폐쇄 같은 방광 자극은 가장 흔하고 먼저 확인해야 하는 trigger입니다."],
      ["기억 포인트", "AD 의심 시 우선 앉히고 혈압을 확인한 뒤 방광 문제를 먼저 해결합니다."],
    ];
  } else if (/fecal|대변|매복/.test(lowerChoice)) {
    rationale = "대변매복은 장 팽창이나 직장 자극을 통해 자율신경 이상반사증을 유발할 수 있으므로 헷갈릴 수 있는 보기입니다. 실제로 bowel problem은 중요한 유발 요인이지만, 시험에서 ‘가장 흔한 원인’을 묻는다면 우선순위는 방광팽창 또는 도뇨관 폐쇄 같은 urinary trigger입니다. 따라서 이 선지는 ‘가능한 원인’일 수는 있어도 ‘가장 흔한 원인’으로는 방광팽창보다 밀립니다.";
    learningPoints = [
      ["개념", "대변매복은 장 팽창·직장 자극을 통해 AD를 유발할 수 있는 실제 trigger입니다."],
      ["왜 헷갈리는가", "AD의 유발 요인을 묻는 문항이면 bowel problem도 맞는 후보가 될 수 있습니다."],
      ["배제 기준", "이 문항은 ‘가장 흔한 원인’을 묻기 때문에, bowel trigger보다 urinary trigger인 방광팽창이 우선입니다."],
      ["기억 포인트", "AD trigger는 bladder first, bowel second 순서로 떠올리면 안전합니다."],
    ];
  } else if (/pressure|압박|injury/.test(lowerChoice)) {
    rationale = "압박손상은 척수손상 환자에서 흔히 관리해야 하는 피부 합병증이고, 통증성 피부 자극이 자율신경 이상반사증의 trigger가 될 수는 있습니다. 그러나 이 보기는 AD의 병태생리 자체보다 욕창 예방·피부 관리 쪽에 더 가까운 보기입니다. ‘가장 흔한 원인’을 묻는 이 문항에서는 피부 자극보다 방광팽창 같은 비뇨기계 자극을 먼저 선택해야 합니다.";
    learningPoints = [
      ["개념", "압박손상은 척수손상 환자의 주요 합병증이며 통증성 피부 자극이 AD를 유발할 수 있습니다."],
      ["왜 헷갈리는가", "병변 아래쪽 피부 자극도 AD trigger가 될 수 있다는 점에서 완전히 무관한 보기는 아닙니다."],
      ["배제 기준", "가장 흔한 원인을 묻는 경우에는 피부 자극보다 방광팽창·도뇨관 폐쇄 같은 비뇨기계 자극이 우선입니다."],
      ["기억 포인트", "욕창은 척수손상 관리 포인트, AD 최빈 trigger는 방광 문제입니다."],
    ];
  } else if (/scrotal|torsion|음낭|꼬임/.test(lowerChoice)) {
    rationale = "음낭꼬임은 급성 음낭 통증을 일으키는 비뇨기 응급질환입니다. 통증 자극이라는 점 때문에 AD의 ‘유해 자극’과 연결해 생각할 수 있지만, 척수손상 환자에서 반복적으로 문제 되는 대표적 유발 요인은 방광 또는 장 자극입니다. 따라서 이 선지는 질환 자체는 중요하지만, 이 문항의 ‘가장 흔한 원인’ 기준에는 맞지 않습니다.";
    learningPoints = [
      ["개념", "음낭꼬임은 급성 음낭 통증과 고환 허혈을 일으키는 응급질환입니다."],
      ["왜 헷갈리는가", "통증성 자극이라는 점에서는 AD의 유해 자극 범주와 연결될 수 있습니다."],
      ["배제 기준", "하지만 척수손상 환자의 AD에서 반복적으로 먼저 확인하는 최빈 원인은 방광팽창입니다."],
      ["기억 포인트", "질환 자체의 응급도와 이 문항의 빈도 기준을 분리해서 봐야 합니다."],
    ];
  } else if (/toenail|발톱|내향성/.test(lowerChoice)) {
    rationale = "내향성발톱은 병변 아래쪽의 통증성 말초 자극이 될 수 있어 자율신경 이상반사증의 유발 요인 목록에는 들어갈 수 있습니다. 하지만 시험적으로 중요한 포인트는 ‘가능한 모든 유해 자극’이 아니라 빈도와 우선순위입니다. 가장 흔하고 먼저 확인해야 하는 원인은 방광팽창이므로, 내향성발톱은 오답입니다.";
    learningPoints = [
      ["개념", "내향성발톱은 국소 통증·염증을 만들 수 있는 말초 유해 자극입니다."],
      ["왜 헷갈리는가", "AD는 병변 아래쪽의 여러 유해 자극으로 발생할 수 있어 말초 통증 자극도 후보가 됩니다."],
      ["배제 기준", "그러나 최빈 원인을 묻는 문항에서는 방광팽창이 내향성발톱보다 훨씬 우선입니다."],
      ["기억 포인트", "가능한 trigger와 가장 흔한 trigger를 구분해야 합니다."],
    ];
  } else {
    rationale = `${choiceText}는 병변 아래쪽 유해 자극으로 자율신경 이상반사증과 연결될 수 있는지 검토할 수 있습니다. 다만 이 문항은 ‘가능한 원인’이 아니라 ‘가장 흔한 원인’을 묻고 있으므로, 빈도가 높고 가장 먼저 확인해야 하는 방광팽창이 우선됩니다.`;
    learningPoints = [
      ["개념", "AD는 병변 아래쪽 유해 자극이 과도한 교감신경 반응을 일으키는 상태입니다."],
      ["배제 기준", "이 문항은 가능한 trigger가 아니라 가장 흔한 trigger를 묻습니다."],
      ["기억 포인트", "가장 흔한 원인은 방광팽창 같은 비뇨기계 자극입니다."],
    ];
  }

  return {
    choiceText,
    isCorrect,
    needsReview: false,
    rationale,
    learningPoints: learningPoints.map(([label, body]) => ({ label, body })),
    source: "concept_comparison",
    evidence: [],
  };
}

function buildPracticeChoiceComparisonFallback(question, choiceKey, answer) {
  const choices = practiceChoiceLookup(question);
  const choiceText = choices[choiceKey] || "해당 보기";
  const correctText = choices[answer] || "기준 개념";
  const stem = String(question?.stem || "");
  if (isCraniosynostosisQuestion(question)) {
    return buildCraniosynostosisChoiceExplanation(question, choiceKey, answer);
  }
  if (/자율신경\s*이상반사|autonomic\s*dysreflexia/i.test(stem)) {
    return buildAutonomicDysreflexiaChoiceExplanation(question, choiceKey, answer);
  }
  const isCorrect = choiceKey === answer;
  const focus = practiceQuestionFocus(question);
  const labels = question?.labels || {};
  const understanding = practiceQuestionUnderstanding(question, labels);
  const concept = understanding.askedConcept || labels.subtopic || labels.topic || focus;
  const assessment = understanding.assessment || focus;
  const isNegative = isPracticeNegativeQuestion(question);
  if (isNegative) {
    return {
      choiceText,
      isCorrect,
      needsReview: true,
      rationale: isCorrect
        ? `${choiceText}는 ${concept}에서 개념·시점·적응증·기전 중 어떤 부분이 어긋나는지 확인해야 하는 진술입니다.`
        : `${choiceText}는 ${concept}에서 함께 비교해야 하는 진술입니다. ${assessment} 기준으로 개념이 성립하는지 확인합니다.`,
      source: "needs_manual_content",
      evidence: [],
      questionPolarity: "negative",
      statementStatus: isCorrect ? "false_statement" : "true_statement",
    };
  }
  return {
    choiceText,
    isCorrect,
    needsReview: true,
    rationale: isCorrect
      ? `${correctText}는 ${concept}에서 ${assessment}을 판단할 때 기준이 되는 개념입니다. 지문 단서와 이 개념이 연결되는 의학적 근거를 별도로 작성해야 합니다.`
      : `${choiceText}는 ${concept}과 함께 비교해야 하는 개념입니다. ${assessment}이라는 같은 기준에서 지문 조건과 맞는지 확인해야 합니다.`,
    source: "needs_manual_content",
    evidence: [],
  };
}

function explanationForVisibleChoice(question, answer, choiceKey, draftRows) {
  if (isCraniosynostosisQuestion(question)) {
    return buildCraniosynostosisChoiceExplanation(question, choiceKey, answer);
  }
  if (/자율신경\s*이상반사|autonomic\s*dysreflexia/i.test(String(question?.stem || ""))) {
    return buildAutonomicDysreflexiaChoiceExplanation(question, choiceKey, answer);
  }
  const existing = draftRows?.[choiceKey];
  if (existing?.rationale) {
    return existing;
  }
  return buildPracticeChoiceComparisonFallback(question, choiceKey, answer);
}

function buildPracticeChoiceExplanationDraft(question, answer, explanationInfo) {
  const existingDetails = existingChoiceExplanationDetailMap(question);
  const existingMap = Object.fromEntries(
    Object.entries(existingDetails).map(([key, value]) => [key, value?.rationale || ""])
  );
  const markedMap = extractPracticeMarkedExplanations(question?.explanation || "");
  const correctAnswer = normalizePracticeChoiceKey(answer);
  const originalExplanation = String(question?.explanation || "").trim();
  const fallbackCorrect = explanationInfo?.text || originalExplanation || "정답 근거 확인이 필요합니다.";
  const rows = {};
  practiceChoiceEntries(question).forEach(([key, text]) => {
    const normalizedKey = normalizePracticeChoiceKey(key);
    const isCorrect = normalizedKey === correctAnswer;
    let source = "existing_choice_explanation";
    let rationale = existingMap[normalizedKey] || "";
    if (!rationale) {
      source = "marked_explanation";
      rationale = markedMap[normalizedKey] || "";
    }
    if (!rationale) {
      source = "choice_mention";
      rationale = findChoiceMentionSentence(text, originalExplanation);
    }
    if (!rationale && isCorrect) {
      source = explanationInfo?.supplemental ? "supplemental_correct_rationale" : "correct_rationale";
      rationale = fallbackCorrect;
    }
    if (!rationale) {
      return;
    }
    rows[normalizedKey] = {
      choiceText: text,
      isCorrect,
      needsReview: Boolean(existingDetails[normalizedKey]?.needsReview) || isWeakPracticeExplanationText(rationale),
      rationale,
      learningPoints: existingDetails[normalizedKey]?.learningPoints || [],
      educationalMedia: existingDetails[normalizedKey]?.educationalMedia || [],
      evidence: existingDetails[normalizedKey]?.evidence || [],
      source,
    };
  });
  return rows;
}

function normalizePracticeChoiceExplanationPayload(payload, question) {
  const choiceRows = Object.fromEntries(practiceChoiceEntries(question));
  const rows = {};
  Object.entries(payload?.choice_explanations || {}).forEach(([key, value]) => {
    const normalizedKey = normalizePracticeChoiceKey(key);
    const rationale = String(value?.rationale || value?.explanation || value?.text || "").trim();
    rows[normalizedKey] = {
      choiceText: value?.choice_text || choiceRows[normalizedKey] || "",
      isCorrect: Boolean(value?.is_correct),
      needsReview: Boolean(value?.needs_review) || isWeakPracticeExplanationText(rationale),
      rationale,
      learningPoints: Array.isArray(value?.learning_points)
        ? value.learning_points
        : Array.isArray(value?.learningPoints) ? value.learningPoints : [],
      educationalMedia: normalizePracticeEducationalMediaItems(
        value?.educational_media || value?.educationalMedia || value?.media || value?.media_refs
      ),
      questionPolarity: value?.question_polarity || value?.questionPolarity || "",
      statementStatus: value?.statement_status || value?.statementStatus || "",
      source: value?.source || "server_choice_explanation",
      evidence: Array.isArray(value?.evidence) ? value.evidence : [],
    };
  });
  return rows;
}

function practiceChoiceExplanationCourseId(question, labels = {}, conceptTags = []) {
  return practiceRagCourseId(question, labels, conceptTags);
}

function practiceChoiceExplanationCacheKey(question, labels = {}, conceptTags = []) {
  const questionKey = practiceQuestionKey(question, currentPracticeIndex);
  const courseId = practiceChoiceExplanationCourseId(question, labels, conceptTags) || "no_rag";
  const contentKey = hashString(
    [
      question?.stem,
      question?.stimulus,
      question?.answer,
      question?.explanation,
      JSON.stringify(question?.choices || {}),
    ].join("\n")
  );
  return `choice_explanations:${courseId}:${questionKey}:${contentKey}`;
}

function shouldRefreshPracticeChoiceExplanations(cacheKey) {
  const question = currentPracticeExam?.questions?.[currentPracticeIndex];
  if (!question) return false;
  const labels = question.labels || {};
  const conceptTags = Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
  return practiceChoiceExplanationCacheKey(question, labels, conceptTags) === cacheKey;
}

async function fetchPracticeChoiceExplanations(question, labels, conceptTags, cacheKey) {
  const fallback = buildPracticeChoiceExplanationDraft(
    question,
    normalizePracticeChoiceKey(question?.answer || ""),
    practiceExplanationInfo(question, normalizePracticeChoiceKey(question?.answer || ""), labels, conceptTags)
  );
  const courseId = practiceChoiceExplanationCourseId(question, labels, conceptTags);
  try {
    const response = await fetch("/api/questions/choice-explanations/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: {
          ...question,
          source_exam: question?.source_exam || currentPracticeExam?.summary?.source_exam,
          source_file: question?.source_file || currentPracticeExam?.summary?.source_file,
        },
        course_id: courseId || undefined,
        use_rag: true,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "선지별 해설 생성 실패");
    }
    practiceChoiceExplanationCache[cacheKey] = {
      status: "ready",
      rows: normalizePracticeChoiceExplanationPayload(payload, question),
      fallback,
      ragCourseId: payload.rag_course_id || "",
      policy: payload.draft_policy || "",
      questionUnderstanding: payload.question_understanding || null,
    };
    if (payload.question_understanding) {
      question.question_understanding = payload.question_understanding;
    }
  } catch (error) {
    practiceChoiceExplanationCache[cacheKey] = {
      status: "error",
      rows: fallback,
      fallback,
      message: error.message || "선지별 해설 생성 실패",
    };
  }
  if (shouldRefreshPracticeChoiceExplanations(cacheKey)) {
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
  }
}

function practiceQuestionUnderstanding(question, labels = {}) {
  const saved = question?.question_understanding || {};
  const conceptPath = saved.concept_path || [
    labels.major_category,
    labels.topic,
    labels.subtopic,
  ].filter(Boolean).join(" > ");
  const askedConcept = saved.asked_concept || labels.subtopic || labels.topic || labels.major_category || "";
  const assessment = saved.assessment_domain || labels.assessment_domain || "";
  const questionType = saved.question_type || labels.question_type || "";
  const task = saved.task || (
    assessment
      ? `${practiceLabelText(assessment)}을 판단하는 데 필요한 핵심 기준을 찾습니다.`
      : "문항이 묻는 개념을 먼저 정리한 뒤 선지를 비교합니다."
  );
  const decisionRule = saved.decision_rule || (
    askedConcept
      ? `${practiceLabelText(askedConcept)}와 가장 잘 맞는 선지를 선택합니다.`
      : "문항이 묻는 기준을 세운 뒤 각 선지의 개념을 비교합니다."
  );
  const tags = Array.isArray(saved.concept_tags)
    ? saved.concept_tags
    : Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
  return {
    conceptPath,
    askedConcept,
    assessment,
    questionType,
    polarity: saved.polarity || "",
    task,
    decisionRule,
    tags,
  };
}

function renderPracticeQuestionUnderstanding(question, labels) {
  const understanding = practiceQuestionUnderstanding(question, labels);
  const chips = [
    understanding.questionType,
    understanding.assessment,
    understanding.polarity === "negative" ? "틀린 진술 찾기" : "",
  ].filter(Boolean).map((item) => `<span class="provenance-chip">${escapeHtml(practiceLabelText(item))}</span>`).join("");
  const tagChips = (understanding.tags || []).slice(0, 6)
    .map((tag) => `<span>${escapeHtml(practiceLabelText(tag))}</span>`)
    .join("");
  return `
    <section class="question-understanding-card">
      <div class="tool-panel-kicker">문항 이해</div>
      <h3>${escapeHtml(practiceLabelText(understanding.askedConcept) || "평가 개념 정리")}</h3>
      <p>${escapeHtml(understanding.task)}</p>
      <dl>
        <div>
          <dt>판단 기준</dt>
          <dd>${escapeHtml(understanding.decisionRule)}</dd>
        </div>
        ${understanding.conceptPath ? `
          <div>
            <dt>라벨 경로</dt>
            <dd>${escapeHtml(understanding.conceptPath)}</dd>
          </div>
        ` : ""}
      </dl>
      ${chips ? `<div class="question-understanding-chips">${chips}</div>` : ""}
      ${tagChips ? `<div class="question-understanding-tags">${tagChips}</div>` : ""}
    </section>
  `;
}

function getPracticeChoiceExplanationState(question, answer, explanationInfo, labels, conceptTags) {
  const cacheKey = practiceChoiceExplanationCacheKey(question, labels, conceptTags);
  const fallback = buildPracticeChoiceExplanationDraft(question, answer, explanationInfo);
  if (!practiceChoiceExplanationCache[cacheKey]) {
    practiceChoiceExplanationCache[cacheKey] = {
      status: "loading",
      rows: fallback,
      fallback,
    };
    window.setTimeout(() => fetchPracticeChoiceExplanations(question, labels, conceptTags, cacheKey), 0);
  }
  return practiceChoiceExplanationCache[cacheKey];
}

function renderPracticeChoiceExplanation(choiceKey, explanation, sourceTags) {
  if (!explanation?.rationale) return "";
  const sourceLabel = {
    choice_comparison: "개념 비교",
    choice_mention: "원해설 기반",
    concept_comparison: "개념 비교",
    correct_rationale: "기준 개념",
    existing_choice_explanation: "선지별 해설",
    marked_explanation: "번호별 해설",
    needs_manual_content: "해설 작성 필요",
    needs_manual_review: "검토 필요",
    rag_evidence_draft: "근거 DB 초안",
    server_choice_explanation: "저장 해설",
    supplemental_correct_rationale: "보강 해설 초안",
  }[explanation?.source] || "해설 초안";
  const questionPolarity = explanation?.questionPolarity || explanation?.question_polarity || "";
  const metaLabel = questionPolarity === "negative"
    ? (explanation?.isCorrect ? "틀린 진술" : "맞는 설명")
    : (explanation?.isCorrect ? "기준 개념" : "구분 포인트");
  const className = [
    explanation?.isCorrect ? "correct" : "wrong",
    explanation?.needsReview ? "needs-review" : "",
  ].filter(Boolean).join(" ");
  const evidence = Array.isArray(explanation?.evidence) ? explanation.evidence : [];
  const learningPoints = Array.isArray(explanation?.learningPoints)
    ? explanation.learningPoints
    : Array.isArray(explanation?.learning_points) ? explanation.learning_points : [];
  const educationalMedia = normalizePracticeEducationalMediaItems(
    explanation?.educationalMedia || explanation?.educational_media || explanation?.media || []
  );
  const evidenceHtml = evidence.length
    ? evidence.map((item) => `
      <span class="provenance-chip">
        ${escapeHtml(item.title || item.source_name || "근거 DB")}
        ${item.page_start ? ` p.${escapeHtml(item.page_start)}` : ""}
      </span>
      ${item.snippet ? `<small>${escapeHtml(item.snippet)}</small>` : ""}
    `).join("")
    : sourceTags || '<span class="provenance-chip">출처 확인 필요</span>';
  const isManualPlaceholder = ["needs_manual_content", "needs_manual_review"].includes(explanation?.source)
    && isWeakPracticeExplanationText(explanation?.rationale);
  const rationaleHtml = isManualPlaceholder
    ? `
      <p class="choice-explanation-pending">
        이 선지는 아직 완성된 선지별 해설이 없습니다. 문항이 묻는 기준을 먼저 정한 뒤,
        해당 선지의 개념 정의와 지문 조건에서 벗어나는 지점을 근거 자료로 작성해야 합니다.
      </p>
    `
    : `<p>${escapeHtml(explanation?.rationale || "")}</p>`;
  return `
    <div class="axioma-choice-explanation ${className}">
      <div class="choice-explanation-meta">
        <span>${escapeHtml(choiceKey)}번 ${escapeHtml(metaLabel)}</span>
        <em>${escapeHtml(sourceLabel)}</em>
      </div>
      ${rationaleHtml}
      ${learningPoints.length ? `
        <div class="choice-learning-points">
          ${learningPoints.map((point) => `
            <article>
              <strong>${escapeHtml(point.label || "학습 포인트")}</strong>
              <span>${escapeHtml(point.body || "")}</span>
            </article>
          `).join("")}
        </div>
      ` : ""}
      ${educationalMedia.length ? `
        <div class="choice-educational-media" aria-label="해설 보조자료">
          ${educationalMedia.map((item) => `
            <article>
              ${item.url ? `
                <figure>
                  <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.title || "해설 보조자료")}" loading="lazy">
                </figure>
              ` : ""}
              <div>
                <strong>${escapeHtml(item.title || "해설 보조자료")}</strong>
                ${item.note ? `<p>${escapeHtml(item.note)}</p>` : ""}
                <small>
                  ${escapeHtml(item.type || "diagram")}
                  ${item.license ? ` · ${escapeHtml(item.license)}` : ""}
                  ${item.attribution ? ` · ${escapeHtml(item.attribution)}` : ""}
                  ${item.sourceUrl ? ` · <a href="${escapeHtml(item.sourceUrl)}" target="_blank" rel="noreferrer">원자료</a>` : ""}
                </small>
              </div>
            </article>
          `).join("")}
        </div>
      ` : ""}
      <div class="source-stack choice-evidence-stack"><span>근거</span><div>${evidenceHtml}</div></div>
    </div>
  `;
}

function regexEscape(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function practiceAnkiTerms({ question, labels, conceptTags, correctChoice, sentence }) {
  const rawTerms = [
    correctChoice,
    labels?.subtopic,
    labels?.topic,
    labels?.unit,
    ...(conceptTags || []),
    ...((String(sentence || "").match(/[A-Za-z][A-Za-z0-9+\-/]{3,}(?:\s+[A-Za-z][A-Za-z0-9+\-/]{3,}){0,2}|[가-힣]{2,}/g)) || []),
    ...((String(question?.stem || "").match(/[A-Za-z][A-Za-z0-9+\-/]{4,}|[가-힣]{2,}/g)) || []),
  ];
  const terms = rawTerms
    .map((term) => String(term || "").replace(/[(){}\[\],.;:!?]/g, "").trim())
    .filter((term) => term.length >= 2)
    .filter((term) => !practiceAnkiStopwords.has(term.toLowerCase()));
  return Array.from(new Set(terms)).sort((left, right) => right.length - left.length).slice(0, 12);
}

function buildClozeSentence(sentence, terms) {
  let output = String(sentence || "").replace(/\s+/g, " ").trim();
  if (!output) return "";
  let clozeIndex = 1;
  for (const term of terms || []) {
    if (clozeIndex > 3) break;
    if (output.includes("{{c") && output.includes(`::${term}`)) continue;
    const pattern = new RegExp(regexEscape(term), "i");
    if (!pattern.test(output)) continue;
    output = output.replace(pattern, (match) => `{{c${clozeIndex}::${match}}}`);
    clozeIndex += 1;
  }
  return output;
}

function firstPracticeSentence(text, maxLength = 240) {
  const sentence = splitPracticeSentences(text)[0] || String(text || "").replace(/\s+/g, " ").trim();
  if (sentence.length <= maxLength) return sentence;
  return `${sentence.slice(0, maxLength).replace(/\s+\S*$/, "")}...`;
}

function buildPracticeAnkiCandidates({ answer, conceptTags, explanationInfo, labels, question, ragAnkiState }) {
  const correctChoice = practiceChoiceEntries(question)
    .find(([key]) => normalizePracticeChoiceKey(key) === normalizePracticeChoiceKey(answer))?.[1]
    || "정답 선지";
  const cards = [];
  const seen = new Set();
  const pushCard = ({ plainText, ankiText, source, tags = [] }) => {
    const plain = firstPracticeSentence(plainText, 260);
    if (!plain || seen.has(plain)) return;
    if (plain.length < 18 || practiceBadAnkiPhrases.some((phrase) => plain.includes(phrase))) return;
    const terms = practiceAnkiTerms({ question, labels, conceptTags, correctChoice, sentence: plain });
    const cloze = ankiText && String(ankiText).includes("{{c")
      ? String(ankiText)
      : buildClozeSentence(plain, terms);
    const hasCloze = cloze.includes("{{c");
    if (!hasCloze || practiceBadAnkiPhrases.some((phrase) => cloze.includes(phrase))) return;
    seen.add(plain);
    cards.push({
      cardId: `anki_${cards.length + 1}_${Math.abs(hashString(plain))}`,
      plainText: plain,
      ankiText: hasCloze ? cloze : plain,
      source,
      tags,
      needsReview: !hasCloze,
    });
  };

  (question?.anki_cards || question?.anki_card_candidates || []).forEach((card) => {
    if (!card) return;
    pushCard({
      plainText: card.plain_text || card.front || card.text || card.anki_text || card.back,
      ankiText: card.anki_text || card.back || card.cloze || card.text,
      source: card.source || "저장된 Anki 후보",
      tags: card.tags || ["stored_anki_candidate"],
    });
  });

  splitPracticeSentences(explanationInfo?.text || "")
    .slice(0, 3)
    .forEach((sentence) => pushCard({
      plainText: sentence,
      source: explanationInfo?.supplemental ? "보강 해설 초안" : "문항 해설",
      tags: ["question_explanation"],
    }));

  if (ragAnkiState?.status === "ready") {
    (ragAnkiState.cards || []).forEach((card) => {
      pushCard({
        plainText: card.plain_text || card.front || card.back,
        ankiText: card.anki_text || card.back,
        source: card.source || "근거 DB",
        tags: card.tags || ["rag_draft"],
      });
    });
  }

  return cards.slice(0, 6);
}

function hashString(value) {
  let hash = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(index);
    hash |= 0;
  }
  return hash;
}

function renderPracticeAnkiCandidatePreview(cards, ragAnkiState) {
  const statusCopy = ragAnkiState?.status === "loading"
    ? "근거 DB 카드 후보를 불러오는 중입니다."
    : ragAnkiState?.status === "error"
      ? `근거 DB 연결 오류: ${ragAnkiState.message}`
      : cards.length
        ? "해설 문장과 근거 DB에서 복습 후보를 만들었습니다."
        : "아직 신뢰할 수 있는 카드 후보가 없습니다. 원해설 또는 선지별 해설 보강 후 생성합니다.";
  return `
    <div class="anki-candidate-preview">
      <div>
        <span>관련 카드 후보</span>
        <strong>${escapeHtml(cards.length)} cards</strong>
        <p>${escapeHtml(statusCopy)}</p>
      </div>
      ${cards.slice(0, 3).map((card) => `
        <article>
          <small>${escapeHtml(card.source || "출처 확인 필요")}</small>
          <p>${escapeHtml(practiceAnkiStyleText ? card.ankiText : card.plainText)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function practiceRagHaystack(question, labels = {}, conceptTags = []) {
  const summary = currentPracticeExam?.summary || {};
  return [
    summary.course_name,
    summary.source_file,
    summary.source_exam,
    question?.source_exam,
    question?.source_file,
    labels.topic,
    labels.subtopic,
    labels.unit,
    labels.question_type,
    labels.cognitive_level,
    ...(conceptTags || []),
    question?.stem,
    question?.stimulus,
    question?.explanation,
    ...(question?.choices ? Object.values(question.choices) : []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function isHematologyOncologyPracticeQuestion(question, labels = {}, conceptTags = []) {
  const haystack = practiceRagHaystack(question, labels, conceptTags);
  return /혈액|종양|빈혈|백혈|림프종|골수종|항암|수혈|혈소판|응고|호중구|heme|hemat|oncolog|anemia|leukemia|lymphoma|myeloma|blast|neutropenia|transfusion|platelet|coagulation|cancer|tumou?r/.test(haystack);
}

function isNeuroSpecialSensesPracticeQuestion(question, labels = {}, conceptTags = []) {
  const haystack = practiceRagHaystack(question, labels, conceptTags);
  return /신경|특수감각|감각기|척수|말초신경|뇌전증|치매|실어증|시신경|망막|백내장|녹내장|청력|난청|전정|어지럼|이명|중이염|사시|척추|neuro|neurolog|spinal|cord|nerve|seizure|epilepsy|aphasia|dementia|optic|retina|glaucoma|cataract|hearing|vestibular|vertigo|tinnitus|strabismus/.test(haystack);
}

function practiceRagCourseId(question, labels = {}, conceptTags = []) {
  if (isHematologyOncologyPracticeQuestion(question, labels, conceptTags)) {
    return "hematology_oncology";
  }
  if (isNeuroSpecialSensesPracticeQuestion(question, labels, conceptTags)) {
    return "neuro_special_senses";
  }
  return "";
}

function practiceRagCourseLabel(courseId) {
  return {
    hematology_oncology: "혈액종양 근거 DB",
    neuro_special_senses: "신경·특수감각 근거 DB",
  }[courseId] || "근거 DB";
}

// ---------------------------------------------------------------------------
// 원서/공개 근거 바로가기 — 해설 확인 시 과목별로 맞는 교과서·공개 자료 링크를 부착.
//
// 기본 원칙:
// 1) 직접 문서 URL을 안정적으로 알 수 있는 주제는 direct link를 먼저 보여준다.
// 2) 유료 교과서는 교내/도서관 인증이 필요하므로 전자책 랜딩 또는 검증된 챕터까지만 연결한다.
// 3) 직접 링크가 없거나 기관 인증이 막히면 검색 fallback을 함께 제공한다.
const MSD_SEARCH_BASE = "https://www.msdmanuals.com/professional/SearchResults";
const ACCESSMEDICINE_BASE = "https://accessmedicine.mhmedical.com";
const ACCESS_OBGYN_BASE = "https://obgyn.mhmedical.com";
const PNU_DISCOVERY_BASE = "https://lib.pusan.ac.kr/search/i-discovery";

function buildPnuDiscoveryLink(search, extraParams = "") {
  const baseParams = `tabIndex=4&search=${encodeURIComponent(search)}`;
  return `${PNU_DISCOVERY_BASE}?${baseParams}${extraParams ? `&${extraParams}` : ""}`;
}

function buildMsdSearchLink(topic) {
  return `${MSD_SEARCH_BASE}?query=${encodeURIComponent(topic)}`;
}

function directReferenceHaystack(question, labels = {}, conceptTags = [], topic = "") {
  return [
    topic,
    labels.course_name,
    labels.major_category,
    labels.topic,
    labels.subtopic,
    labels.unit,
    labels.question_type,
    labels.cognitive_level,
    ...(conceptTags || []),
    question?.stem,
    question?.stimulus,
    question?.explanation,
    ...(question?.choices ? Object.values(question.choices) : []),
  ].filter(Boolean).join(" ").replace(/_/g, " ").toLowerCase();
}

const DIRECT_REFERENCE_RULES = [
  {
    id: "primary_dysmenorrhea",
    pattern: /원발\s*월경통|월경통|dysmenorrhea|dysmenorrhoea|prostaglandin|프로스타글란딘|nsaid|비스테로이드/i,
    links: [
      {
        label: "🔓 MSD Manual: Dysmenorrhea",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/abnormal-uterine-bleeding/dysmenorrhea",
        type: "open",
      },
      {
        label: "📗 Williams Gynecology: Pelvic Pain",
        url: `${ACCESS_OBGYN_BASE}/content.aspx?legacysectionid=hoff4-ch012`,
        type: "institutional",
      },
      {
        label: "📘 Williams Obstetrics 전자책",
        url: `${ACCESS_OBGYN_BASE}/book.aspx?bookid=2977`,
        type: "institutional",
      },
    ],
  },
  {
    id: "pid_toa",
    pattern: /골반염|골반\s*염증|난관난소농양|tubo.?ovarian|pelvic inflammatory|pid\b|toa\b|cervical motion tenderness|자궁경부\s*운동\s*압통/i,
    links: [
      {
        label: "🔓 MSD Manual: Pelvic inflammatory disease",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/vaginitis-cervicitis-and-pelvic-inflammatory-disease/pelvic-inflammatory-disease-pid",
        type: "open",
      },
      {
        label: "🔓 MSD Manual: PID 치료 표",
        url: "https://www.msdmanuals.com/professional/multimedia/table/regimens-for-treatment-of-pelvic-inflammatory-disease",
        type: "open",
      },
      {
        label: "📗 Williams Gynecology: Benign Adnexal Mass",
        url: `${ACCESS_OBGYN_BASE}/content.aspx?bookId=2658&sectionId=241008530`,
        type: "institutional",
      },
    ],
  },
  {
    id: "ectopic_pregnancy",
    pattern: /자궁외임신|이소성\s*임신|ectopic pregnancy|adnexal mass|beta.?hcg|β.?hcg|임신.*복통.*질출혈/i,
    links: [
      {
        label: "🔓 MSD Manual: Ectopic pregnancy",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/early-pregnancy-disorders/ectopic-pregnancy",
        type: "open",
      },
      {
        label: "📘 Williams Obstetrics 전자책",
        url: `${ACCESS_OBGYN_BASE}/book.aspx?bookid=2977`,
        type: "institutional",
      },
    ],
  },
  {
    id: "uterine_inversion",
    pattern: /자궁내번|uterine inversion|태반만출.*질출혈|자궁저부.*만져지지|fundus.*cervix/i,
    links: [
      {
        label: "🔓 MSD Manual: Uterine inversion",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/intrapartum-complications/uterine-inversion",
        type: "open",
      },
      {
        label: "🎞 MSD Manual: Uterine inversion 처치 영상",
        url: "https://www.msdmanuals.com/professional/multimedia/video/how-to-manage-uterine-inversion",
        type: "open",
      },
      {
        label: "📘 Williams Obstetrics 전자책",
        url: `${ACCESS_OBGYN_BASE}/book.aspx?bookid=2977`,
        type: "institutional",
      },
    ],
  },
  {
    id: "postpartum_hemorrhage",
    pattern: /산후출혈|분만.*출혈|postpartum hemorrhage|postpartum haemorrhage|uterine atony|자궁무력|retained placenta/i,
    links: [
      {
        label: "🔓 MSD Manual: Postpartum hemorrhage",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/intrapartum-complications/postpartum-hemorrhage",
        type: "open",
      },
      {
        label: "📘 Williams Obstetrics 전자책",
        url: `${ACCESS_OBGYN_BASE}/book.aspx?bookid=2977`,
        type: "institutional",
      },
    ],
  },
  {
    id: "uterine_rupture",
    pattern: /자궁파열|uterine rupture|vbac|previous cesarean|previous c.?section|제왕절개.*과거력/i,
    links: [
      {
        label: "🔓 MSD Manual: Uterine rupture",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/intrapartum-complications/uterine-rupture",
        type: "open",
      },
      {
        label: "🔓 MSD Manual: Cesarean delivery",
        url: "https://www.msdmanuals.com/professional/gynecology-and-obstetrics/labor-and-delivery/cesarean-delivery",
        type: "open",
      },
    ],
  },
  // ── 혈액종양: MSD Manual 공개 질환 페이지 직접 연결 (URL 검증 완료) ──
  {
    id: "heme_mds",
    pattern: /골수형성이상|myelodysplastic|\bmds\b/i,
    links: [{ label: "🔓 MSD: Myelodysplastic Syndromes (MDS)", url: "https://www.msdmanuals.com/professional/oncology/leukemias/myelodysplastic-syndromes-mds", type: "open" }],
  },
  {
    id: "heme_aml",
    pattern: /급성\s*골수(성)?\s*백혈병|acute myeloid|\baml\b/i,
    links: [{ label: "🔓 MSD: Acute Myeloid Leukemia (AML)", url: "https://www.msdmanuals.com/professional/oncology/leukemias/acute-myeloid-leukemia-aml", type: "open" }],
  },
  {
    id: "heme_all",
    pattern: /급성\s*림프(모|구)?구?성?\s*백혈병|acute lymphoblastic|acute lymphocytic leukemia/i,
    links: [{ label: "🔓 MSD: Acute Lymphoblastic Leukemia (ALL)", url: "https://www.msdmanuals.com/professional/oncology/leukemias/acute-lymphoblastic-leukemia-all", type: "open" }],
  },
  {
    id: "heme_cml",
    pattern: /만성\s*골수(성)?\s*백혈병|chronic myeloid|\bcml\b/i,
    links: [{ label: "🔓 MSD: Chronic Myeloid Leukemia (CML)", url: "https://www.msdmanuals.com/professional/oncology/leukemias/chronic-myeloid-leukemia-cml", type: "open" }],
  },
  {
    id: "heme_cll",
    pattern: /만성\s*림프구(성)?\s*백혈병|chronic lymphocytic|\bcll\b/i,
    links: [{ label: "🔓 MSD: Chronic Lymphocytic Leukemia (CLL)", url: "https://www.msdmanuals.com/professional/oncology/leukemias/chronic-lymphocytic-leukemia-cll", type: "open" }],
  },
  {
    id: "heme_hodgkin",
    pattern: /호지킨|hodgkin/i,
    links: [{ label: "🔓 MSD: Hodgkin Lymphoma", url: "https://www.msdmanuals.com/professional/oncology/lymphomas/hodgkin-lymphoma", type: "open" }],
  },
  {
    id: "heme_nhl",
    pattern: /비호지킨|non.?hodgkin/i,
    links: [{ label: "🔓 MSD: Non-Hodgkin Lymphomas", url: "https://www.msdmanuals.com/professional/oncology/lymphomas/non-hodgkin-lymphomas", type: "open" }],
  },
  {
    id: "heme_myeloma",
    pattern: /다발(성)?\s*골수종|multiple myeloma/i,
    links: [{ label: "🔓 MSD: Multiple Myeloma", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/plasma-cell-disorders/multiple-myeloma", type: "open" }],
  },
  {
    id: "heme_itp",
    pattern: /면역\s*혈소판\s*감소|특발성\s*혈소판|immune thrombocytopenia|\bitp\b/i,
    links: [{ label: "🔓 MSD: Immune Thrombocytopenia (ITP)", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/thrombocytopenia-and-platelet-dysfunction/immune-thrombocytopenia-itp", type: "open" }],
  },
  {
    id: "heme_ttp",
    pattern: /혈전\s*혈소판\s*감소성?\s*자반|thrombotic thrombocytopenic|\bttp\b/i,
    links: [{ label: "🔓 MSD: Thrombotic Thrombocytopenic Purpura (TTP)", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/thrombocytopenia-and-platelet-dysfunction/thrombotic-thrombocytopenic-purpura-ttp", type: "open" }],
  },
  {
    id: "heme_dic",
    pattern: /파종성?\s*혈관내\s*응고|disseminated intravascular|\bdic\b/i,
    links: [{ label: "🔓 MSD: Disseminated Intravascular Coagulation (DIC)", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/coagulation-disorders/disseminated-intravascular-coagulation-dic", type: "open" }],
  },
  {
    id: "heme_vwd",
    pattern: /폰\s*빌레브란트|von willebrand|\bvwd\b/i,
    links: [{ label: "🔓 MSD: Von Willebrand Disease", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/thrombocytopenia-and-platelet-dysfunction/von-willebrand-disease", type: "open" }],
  },
  {
    id: "heme_hemophilia",
    pattern: /혈우병|hemophilia|haemophilia/i,
    links: [{ label: "🔓 MSD: Hemophilia", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/coagulation-disorders/hemophilia", type: "open" }],
  },
  {
    id: "heme_aplastic",
    pattern: /재생\s*불량성?\s*빈혈|aplastic anemia|aplastic anaemia/i,
    links: [{ label: "🔓 MSD: Aplastic Anemia", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/anemias-caused-by-deficient-erythropoiesis/aplastic-anemia", type: "open" }],
  },
  {
    id: "heme_ida",
    pattern: /철\s*결핍성?\s*빈혈|iron deficiency an[ae]mia/i,
    links: [{ label: "🔓 MSD: Iron Deficiency Anemia", url: "https://www.msdmanuals.com/professional/hematology-and-oncology/anemias-caused-by-deficient-erythropoiesis/iron-deficiency-anemia", type: "open" }],
  },
];

function dedupeReferenceLinks(links = []) {
  const seen = new Set();
  return links.filter((link) => {
    if (!link?.url || seen.has(link.url)) return false;
    seen.add(link.url);
    return true;
  });
}

function directReferenceLinksForTopic(topic, question, labels = {}, conceptTags = []) {
  const haystack = directReferenceHaystack(question, labels, conceptTags, topic);
  return dedupeReferenceLinks(
    DIRECT_REFERENCE_RULES
      .filter((rule) => rule.pattern.test(haystack))
      .flatMap((rule) => rule.links || [])
  );
}

// 약어·한글 개념 → 교과서(영문 MSD/해리슨) 검색용 표준 질환명.
// key는 소문자 부분일치로 매칭(예: "골수형성이상/증식" ⊃ "골수형성이상").
const CONCEPT_CANONICAL = [
  ["myelodysplastic", "myelodysplastic syndrome"],
  ["골수형성이상", "myelodysplastic syndrome"],
  ["mds", "myelodysplastic syndrome"],
  ["chronic myelomonocytic", "chronic myelomonocytic leukemia"],
  ["cmml", "chronic myelomonocytic leukemia"],
  ["acute myeloid", "acute myeloid leukemia"],
  ["aml", "acute myeloid leukemia"],
  ["acute lymphoblastic", "acute lymphoblastic leukemia"],
  ["acute lymphocytic", "acute lymphoblastic leukemia"],
  ["chronic myeloid", "chronic myeloid leukemia"],
  ["cml", "chronic myeloid leukemia"],
  ["chronic lymphocytic", "chronic lymphocytic leukemia"],
  ["cll", "chronic lymphocytic leukemia"],
  ["myeloproliferative", "myeloproliferative neoplasm"],
  ["multiple myeloma", "multiple myeloma"],
  ["다발골수종", "multiple myeloma"],
  ["hodgkin", "hodgkin lymphoma"],
  ["non-hodgkin", "non-hodgkin lymphoma"],
  ["lymphoma", "lymphoma"],
  ["림프종", "lymphoma"],
  ["neuroblastoma", "neuroblastoma"],
  ["신경모세포종", "neuroblastoma"],
  ["wilms", "wilms tumor"],
  ["윌름", "wilms tumor"],
  ["von willebrand", "von willebrand disease"],
  ["vwd", "von willebrand disease"],
  ["hemophilia", "hemophilia"],
  ["haemophilia", "hemophilia"],
  ["혈우병", "hemophilia"],
  ["immune thrombocytopenia", "immune thrombocytopenia"],
  ["itp", "immune thrombocytopenia"],
  ["thrombotic thrombocytopenic", "thrombotic thrombocytopenic purpura"],
  ["ttp", "thrombotic thrombocytopenic purpura"],
  ["disseminated intravascular", "disseminated intravascular coagulation"],
  ["aplastic", "aplastic anemia"],
  ["재생불량", "aplastic anemia"],
  ["iron deficiency", "iron deficiency anemia"],
  ["철결핍", "iron deficiency anemia"],
  ["hemolytic anemia", "hemolytic anemia"],
  ["thalassemia", "thalassemia"],
  ["lymphadenopathy", "lymphadenopathy"],
  ["림프절", "lymphadenopathy"],
];

// 유전자·변이패널·점수·수치 같은 비질환 태그는 검색어에서 제외한다.
function isNonDiseaseConceptToken(token) {
  const t = String(token || "").trim();
  if (!t) return true;
  if (/^[A-Z0-9]{2,}(_[A-Z0-9]+)+$/.test(t)) return true; // ALLCAPS_WITH_UNDERSCORES = 유전자패널
  return /\b(tet2|sf3b1|dnmt3a|flt3|npm1|jak2|bcr|abl1?|kras|nras|idh[12]|ipss|r[_ ]?ipss|cytogenetics?|karyotype|blast|mutation|variant|threshold|score|점수|기준|평가|예후|유전자|변이|수치|under\d+)\b/i.test(t);
}

function canonicalDiseaseName(candidates) {
  // candidates는 우선순위 순서(구체적인 concept_tag가 앞). 앞 후보에서 먼저 잡힌 표준명을 쓴다.
  for (const cand of candidates.filter(Boolean)) {
    const s = String(cand).replace(/_/g, " ").toLowerCase();
    for (const [key, name] of CONCEPT_CANONICAL) {
      if (s.includes(key)) return name;
    }
  }
  return "";
}

function buildSearchTopic(question, labels = {}, conceptTags = []) {
  const tags = (conceptTags || []).map(String);
  // 1) 표준 질환명이 잡히면 그것만 쓴다 (영문 교과서 검색 정확도↑, MDS→myelodysplastic syndrome).
  const canon = canonicalDiseaseName([
    ...tags,
    labels.subtopic,
    labels.topic,
    labels.major_category,
    question?.stem,
  ]);
  if (canon) return canon;
  // 2) 질환처럼 보이는 첫 concept_tag (유전자/점수 태그 제외, 밑줄 정리).
  const diseaseTag = tags.find((t) => !isNonDiseaseConceptToken(t));
  if (diseaseTag) return diseaseTag.replace(/_/g, " ").trim();
  // 3) 라벨에서 군더더기(유전자/예후/평가 등) 제거 후 사용.
  const label = String(labels.topic || labels.subtopic || labels.major_category || "").trim();
  if (label && !isNonDiseaseConceptToken(label)) return label.replace(/_/g, " ");
  // 4) 최후: 지문 앞부분(짧게).
  return String(question?.stem || "").slice(0, 50);
}

const TEXTBOOK_ACCESS_ENTRIES = [
  {
    id: "harrison",
    displayName: "Harrison's Principles of Internal Medicine",
    // 내과·신경과 커버, 소아/외과/산부인과/정신과 등은 구조적으로 미커버(별도 검토에서 오매칭 확인)
    eligibleKeywords: ["내과", "신경과"],
    excludedKeywords: ["소아", "산부", "외과", "정신", "이비인후", "예방", "법의학", "피부", "비뇨", "안과", "응급"],
    note: "직접 문서가 매칭되는 경우 공개 근거를 먼저 열고, 나머지는 해리슨 검색/목차에서 확인하세요.",
    buildLinks(topic, context = {}) {
      const q = encodeURIComponent(topic);
      const directLinks = directReferenceLinksForTopic(topic, context.question, context.labels, context.conceptTags);
      return dedupeReferenceLinks([
        ...directLinks,
        { label: "📖 해리슨 검색 (교내 직접접속)", url: `${ACCESSMEDICINE_BASE}/searchresults.aspx?q=${q}`, type: "institutional" },
        { label: "📕 해리슨 목차", url: `${ACCESSMEDICINE_BASE}/book.aspx?bookid=3541`, type: "institutional" },
        {
          label: "🏛 부산대 도서관 검색 fallback",
          url: buildPnuDiscoveryLink("Harrison's principles of internal medicine", "resourceType=book&resourceType=book%20series"),
          type: "fallback",
        },
        { label: "🔎 MSD Manual 검색 fallback", url: buildMsdSearchLink(topic), type: "fallback" },
      ]);
    },
  },
  {
    id: "williams_obstetrics",
    displayName: "Williams Obstetrics",
    eligibleKeywords: ["산부인과"],
    excludedKeywords: [],
    note: "직접 연결 가능한 MSD/Williams 링크를 먼저 열고, 기관 인증이 막히면 부산대 도서관 fallback을 사용하세요.",
    buildLinks(topic, context = {}) {
      const q = encodeURIComponent(topic);
      const directLinks = directReferenceLinksForTopic(topic, context.question, context.labels, context.conceptTags);
      return dedupeReferenceLinks([
        ...directLinks,
        {
          label: "📘 Williams Obstetrics 전자책",
          url: `${ACCESS_OBGYN_BASE}/book.aspx?bookid=2977`,
          type: "institutional",
        },
        {
          label: "🔎 Williams 내부 검색",
          url: `${ACCESS_OBGYN_BASE}/searchresults.aspx?q=${q}`,
          type: "institutional",
        },
        {
          label: "🏛 부산대 도서관 검색 fallback",
          url: buildPnuDiscoveryLink("Williams obstetrics", "resourceType=book&resourceType=book%20series&resourceType=audio%20book&resourceType=streaming%20audio&resourceType=streaming%20video"),
          type: "fallback",
        },
        { label: "🔎 MSD Manual 검색 fallback", url: buildMsdSearchLink(topic), type: "fallback" },
      ]);
    },
  },
  {
    id: "pediatrics_pnu",
    displayName: "소아과 참고교재 (부산대 도서관 확인)",
    eligibleKeywords: ["소아"],
    excludedKeywords: [],
    note: "정확한 서명은 부산대 도서관·ClinicalKey에서 직접 확인하세요(자동 매칭 아님).",
    buildLinks(topic, context = {}) {
      const directLinks = directReferenceLinksForTopic(topic, context.question, context.labels, context.conceptTags);
      return dedupeReferenceLinks([
        ...directLinks,
        {
          label: "🏛 부산대 도서관 자료",
          url: "https://lib.pusan.ac.kr/search/i-discovery/106295901?index=1&type=pubIq",
          type: "institutional",
        },
        {
          label: "📕 ClinicalKey 교재",
          url: "https://www.clinicalkey.com/#!/browse/book/3-s2.0-C2020103101X",
          type: "institutional",
        },
        { label: "🔎 MSD Manual 검색 fallback", url: buildMsdSearchLink(topic), type: "fallback" },
      ]);
    },
  },
  {
    id: "hematology_oncology",
    displayName: "MSD Manual · 혈액종양",
    eligibleKeywords: ["혈액", "종양"],
    excludedKeywords: [],
    note: "질환에 맞는 공개 MSD Manual 페이지로 바로 연결됩니다. 해당 페이지가 없으면 검색·부산대 도서관으로 이동하세요.",
    buildLinks(topic, context = {}) {
      const directLinks = directReferenceLinksForTopic(topic, context.question, context.labels, context.conceptTags);
      return dedupeReferenceLinks([
        ...directLinks,
        { label: "🔎 MSD Manual 검색", url: buildMsdSearchLink(topic), type: "fallback" },
        { label: "🏛 부산대 도서관 검색", url: buildPnuDiscoveryLink(topic), type: "fallback" },
      ]);
    },
  },
];

function findEligibleTextbookEntry(question, labels = {}) {
  const courseName = String(labels.course_name || question?.labels?.course_name || "").trim();
  if (!courseName) return null;
  return TEXTBOOK_ACCESS_ENTRIES.find((entry) => {
    if ((entry.excludedKeywords || []).some((kw) => courseName.includes(kw))) return false;
    return entry.eligibleKeywords.some((kw) => courseName.includes(kw));
  }) || null;
}

function renderTextbookEvidenceLinks(question, labels = {}, conceptTags = []) {
  const entry = findEligibleTextbookEntry(question, labels);
  if (!entry) return "";
  const topic = buildSearchTopic(question, labels, conceptTags);
  const links = entry.buildLinks(topic, { question, labels, conceptTags });
  return `
    <div class="rag-evidence-box textbook-links-box">
      <div class="rag-evidence-header">
        <span>${escapeHtml(entry.displayName)} 근거 원문 바로 열기</span>
        <small>${escapeHtml(topic)}</small>
      </div>
      <div class="harrison-link-row">
        ${links.map((link) => `<a class="reference-link-${escapeHtml(link.type || "default")}" href="${escapeHtml(link.url)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>`).join("")}
      </div>
      <p class="harrison-link-note">${escapeHtml(entry.note)}</p>
    </div>
  `;
}

// concept_tags 기반으로 부착된 1차 문헌·가이드라인 인용 렌더 (PubMed, DOI 링크).
function renderQuestionCitations(question) {
  const evidence = Array.isArray(question?.evidence) ? question.evidence : [];
  const status = question?.evidence_status || "";
  // 학생 화면에는 사람이 승인(verified)한 근거만 노출한다. draft/needs_review는 교수 근거검토 화면에서만.
  if (status !== "verified" || !evidence.length) {
    return "";
  }
  const typeLabel = { guideline: "가이드라인", review: "리뷰", rct: "RCT", meta: "메타분석" };
  return `
    <div class="rag-evidence-box citation-box">
      <div class="rag-evidence-header">
        <span>논문 근거 (PubMed)</span>
        <small>검토 완료</small>
      </div>
      <div class="citation-list">
        ${evidence.map((c) => {
          const href = c.url || (c.doi ? `https://doi.org/${c.doi}` : c.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/` : "#");
          const meta = [c.journal, c.year].filter(Boolean).join(" · ");
          return `
          <a class="citation-card" href="${escapeHtml(href)}" target="_blank" rel="noopener">
            <span class="citation-type">${escapeHtml(typeLabel[c.type] || c.type || "근거")}</span>
            <strong>${escapeHtml(c.title || "제목 미상")}</strong>
            <small>${escapeHtml(meta)}${c.doi ? ` · DOI ${escapeHtml(c.doi)}` : ""}</small>
          </a>`;
        }).join("")}
      </div>
      <p class="citation-attribution">출처: PubMed · 개념 태그 기반 검색 · 사람 검토 후 확정</p>
    </div>`;
}

function practiceRagQuery(question, labels = {}, conceptTags = []) {
  const values = [
    labels.subtopic,
    labels.topic,
    labels.unit,
    ...(conceptTags || []),
    question?.stem,
    question?.stimulus,
  ].filter(Boolean);
  const query = values.join(" ").replace(/\s+/g, " ").trim();
  return query.slice(0, 320) || "medical education concept";
}

function practiceRagCacheKey(question, labels = {}, conceptTags = [], kind = "evidence") {
  const questionKey = practiceQuestionKey(question, currentPracticeIndex);
  const query = practiceRagQuery(question, labels, conceptTags).slice(0, 80);
  const courseId = practiceRagCourseId(question, labels, conceptTags) || "no_rag";
  return `${kind}:${courseId}:${questionKey}:${query}`;
}

function shouldRefreshPracticeRag(cacheKey) {
  const question = currentPracticeExam?.questions?.[currentPracticeIndex];
  if (!question) return false;
  const labels = question.labels || {};
  const conceptTags = Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
  return practiceRagCacheKey(question, labels, conceptTags, "evidence") === cacheKey
    || practiceRagCacheKey(question, labels, conceptTags, "anki") === cacheKey;
}

async function fetchPracticeRagEvidence(question, labels, conceptTags, cacheKey) {
  const query = practiceRagQuery(question, labels, conceptTags);
  const courseId = practiceRagCourseId(question, labels, conceptTags);
  try {
    const params = new URLSearchParams({
      q: query,
      course_id: courseId,
      limit: "5",
    });
    const response = await fetch(`/api/rag/search?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "근거 DB 검색 실패");
    }
    practiceRagEvidenceCache[cacheKey] = {
      status: "ready",
      query,
      results: payload.results || [],
      resultCount: payload.result_count || 0,
    };
  } catch (error) {
    practiceRagEvidenceCache[cacheKey] = {
      status: "error",
      query,
      message: error.message || "근거 DB 검색 실패",
      results: [],
    };
  }
  if (shouldRefreshPracticeRag(cacheKey)) {
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
  }
}

function getPracticeRagEvidenceState(question, labels, conceptTags) {
  const courseId = practiceRagCourseId(question, labels, conceptTags);
  if (!courseId) {
    return {
      status: "unavailable",
      message: "현재 이 과목에는 연결된 근거 DB가 없습니다.",
    };
  }
  const cacheKey = practiceRagCacheKey(question, labels, conceptTags, "evidence");
  if (!practiceRagEvidenceCache[cacheKey]) {
    practiceRagEvidenceCache[cacheKey] = {
      status: "loading",
      query: practiceRagQuery(question, labels, conceptTags),
      results: [],
    };
    window.setTimeout(() => fetchPracticeRagEvidence(question, labels, conceptTags, cacheKey), 0);
  }
  return practiceRagEvidenceCache[cacheKey];
}

async function fetchPracticeRagAnki(question, labels, conceptTags, cacheKey) {
  const query = practiceRagQuery(question, labels, conceptTags);
  const courseId = practiceRagCourseId(question, labels, conceptTags);
  try {
    const response = await fetch("/api/rag/anki-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        course_id: courseId,
        limit: 3,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Anki 초안 생성 실패");
    }
    practiceRagAnkiCache[cacheKey] = {
      status: "ready",
      query,
      cards: payload.cards || [],
      note: payload.note || "",
    };
  } catch (error) {
    practiceRagAnkiCache[cacheKey] = {
      status: "error",
      query,
      message: error.message || "Anki 초안 생성 실패",
      cards: [],
    };
  }
  if (shouldRefreshPracticeRag(cacheKey)) {
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
  }
}

function getPracticeRagAnkiState(question, labels, conceptTags) {
  const courseId = practiceRagCourseId(question, labels, conceptTags);
  if (!courseId) {
    return {
      status: "unavailable",
      message: "현재 이 과목에는 연결된 근거 기반 Anki 초안 생성기가 없습니다.",
    };
  }
  const cacheKey = practiceRagCacheKey(question, labels, conceptTags, "anki");
  if (!practiceRagAnkiCache[cacheKey]) {
    practiceRagAnkiCache[cacheKey] = {
      status: "loading",
      query: practiceRagQuery(question, labels, conceptTags),
      cards: [],
    };
    window.setTimeout(() => fetchPracticeRagAnki(question, labels, conceptTags, cacheKey), 0);
  }
  return practiceRagAnkiCache[cacheKey];
}

function renderPracticeRagEvidence(state, { compact = false } = {}) {
  if (state.status === "unavailable") {
    return `
      <div class="rag-evidence-box muted-state">
        <span>근거 DB</span>
        <p>${escapeHtml(state.message)}</p>
      </div>
    `;
  }
  if (state.status === "loading") {
    return `
      <div class="rag-evidence-box loading-state">
        <span>연결된 학습 근거</span>
        <p>로컬 근거 DB에서 관련 근거를 찾는 중입니다.</p>
      </div>
    `;
  }
  if (state.status === "error") {
    return `
      <div class="rag-evidence-box error-state">
        <span>근거 DB 연결 오류</span>
        <p>${escapeHtml(state.message)}</p>
      </div>
    `;
  }
  if (!state.results?.length) {
    return `
      <div class="rag-evidence-box muted-state">
        <span>연결된 학습 근거</span>
        <p>현재 문항과 직접 연결되는 근거를 찾지 못했습니다.</p>
      </div>
    `;
  }
  const visibleResults = state.results.slice(0, compact ? 2 : 5);
  return `
    <div class="rag-evidence-box">
      <div class="rag-evidence-header">
        <span>연결된 학습 근거</span>
        <small>${escapeHtml(state.query || "")}</small>
      </div>
      <div class="rag-evidence-list">
        ${visibleResults.map((item, index) => `
          <article class="rag-evidence-card">
            <div>
              <strong>${escapeHtml(item.title || item.source_name || "근거 자료")}</strong>
              <small>p.${escapeHtml(item.page_start || "-")} · ${escapeHtml(practiceLabelText(item.source_type || "reference"))} · score ${escapeHtml(item.score ?? "-")}</small>
            </div>
            <p>${escapeHtml(item.snippet || "")}</p>
            <em>${escapeHtml(index + 1)}번째 후보</em>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderPracticeRagAnkiCards(state) {
  if (state.status === "unavailable") {
    return `
      <div class="rag-evidence-box muted-state">
        <span>근거 기반 Anki</span>
        <p>${escapeHtml(state.message)}</p>
      </div>
    `;
  }
  if (state.status === "loading") {
    return `
      <div class="rag-evidence-box loading-state">
        <span>근거 기반 Anki</span>
        <p>로컬 근거 DB에서 복습 카드 초안을 만드는 중입니다.</p>
      </div>
    `;
  }
  if (state.status === "error") {
    return `
      <div class="rag-evidence-box error-state">
        <span>Anki 초안 오류</span>
        <p>${escapeHtml(state.message)}</p>
      </div>
    `;
  }
  if (!state.cards?.length) {
    return `
      <div class="rag-evidence-box muted-state">
        <span>근거 기반 Anki</span>
        <p>현재 문항에서 만들 수 있는 근거 기반 카드 초안을 찾지 못했습니다.</p>
      </div>
    `;
  }
  return `
    <div class="rag-anki-list">
      ${state.cards.map((card) => `
        <article class="anki-preview-card rag-anki-card">
          <span>검수용 초안 · ${escapeHtml(card.source || "출처 확인 필요")}</span>
          <strong>${escapeHtml(card.front || "Front")}</strong>
          <p>${escapeHtml(card.back || "")}</p>
        </article>
      `).join("")}
    </div>
  `;
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
    studentPracticeStatus.textContent = `${playableExams.length}개 문항 세트를 불러왔습니다. 세트를 열고 원하는 문항부터 선택할 수 있습니다.`;
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
    renderStudentLibraryCourseBuilder(selectedLibraryCourseKey);
    refreshStudentCategoryQuestionCounts().catch(() => {});
  } catch (error) {
    if (studentPracticeStatus) {
      studentPracticeStatus.textContent = `구조화 문항 목록을 불러오지 못했습니다: ${error.message}`;
    }
    if (studentCourseBuilder) {
      studentCourseBuilder.innerHTML = `
        <div class="library-empty-state">
          <strong>문항 인덱스를 불러오지 못했습니다.</strong>
          <p>${escapeHtml(error.message)}</p>
        </div>
      `;
    }
  }
}

function categoryByKey(courseKey) {
  return departmentCategories.find((category) => category.key === courseKey) || departmentCategories[0];
}

function normalizeCourseMatchText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[()\[\]{}·ㆍ\-\s_.,/]+/g, "");
}

const curriculumCoursePatternMap = {
  infectious_diseases: [
    /감염|항생|항균|바이러스|세균|진균|결핵|패혈|균혈|말라리아|hiv|후천성면역결핍|예방접종|crbsi|staph|sepsis/i,
  ],
  musculoskeletal: [
    /근골격|정형|골절|관절|근육|외상|화상|류마티스|척추|압박손상|염좌|탈구|수부|사지/i,
  ],
  endocrinology: [
    /내분비|당뇨|갑상|부신|뇌하수체|대사|인슐린|저혈당|고혈당|cushing|addison|thyroid/i,
  ],
  immunology_dermatology: [
    /면역|피부|알레르기|두드러기|아토피|자가면역|발진|피부질환|홍반|수포|dermat/i,
  ],
  reproductive_medicine: [
    /산부인과|임신|분만|산과|부인과|자궁|난소|태아|유방|월경|질출혈|난관|placenta|obstetric|gyne/i,
  ],
  growth_development_aging: [
    /성장|발달|노화|소아|신생아|영아|청소년|소아청소년|growth|aging|pediatric/i,
  ],
  clinical_intro: [
    /임상의학입문|급성\s*복증|acute\s*abdomen|탈장|hernia|기본진료|기본임상|clinical\s*intro/i,
  ],
  gastroenterology_nutrition: [
    /소화기|위장|식도|위암|대장|소장|간질환|간경|간염|담도|담관|담석|췌장|췌염|장폐색|장간막|크론|궤양성대장|영양|유미|복부|췌십이지장|ercp|biliary|pancrea|gastro/i,
  ],
  cardiology: [
    /순환기|심장|심근|협심|심부전|부정맥|심전도|심장판막|고혈압|대동맥|혈관|관상동맥|cardio|aortic|arrhythm/i,
  ],
  neuro_special_senses: [
    /신경|뇌|척수|말초신경|뇌졸중|뇌출혈|두통|발작|시각|청각|안과|이비인후|감각|cranial|spinal|neuro/i,
  ],
  renal_urology: [
    /신장|비뇨|요로|전해질|사구체|요관|방광|전립|산염기|콩팥|투석|renal|urology|kidney/i,
  ],
  human_society_medicine_1: [
    /인간.?사회.?의료.?1|인간.?사회.?의료\(i\)|의료사회|윤리|예방의학|역학|보건|의료윤리|공중보건|vaccination|감염병.?예방법/i,
  ],
  human_society_medicine_2: [
    /인간.?사회.?의료.?2|인간.?사회.?의료Ⅱ|인간.?사회.?의료ii|법규|의료법|정책|직업환경|의료관리|보험급여|보건행정|검역법|국민건강보험/i,
  ],
  psychiatry: [
    /정신|우울|조현|불안|양극성|중독|치매|섬망|급식|섭식|식이장애|eating\s*disorder|면담|psychi/i,
  ],
  disease_pharmacology: [
    /약물|약리|부작용|금기|독성|중독|치료원칙|질병의이해|pharm|drug|toxicity/i,
  ],
  hematology_oncology: [
    /혈액종양|혈액및종양|혈종|hematology|oncology|빈혈|백혈병|림프종|골수|혈우병|응고|출혈|수혈|항암|고형암|종양|암|방사선종양|다발골수|조혈|aPTT|blast|leukemia|lymphoma|myeloma/i,
  ],
  pulmonology: [
    /호흡기|폐|기관지|천식|copd|기흉|흉막|흉부|산소|환기|호흡부전|폐렴|폐쇄성|제한성|pulmon|respir/i,
  ],
};

const curriculumCourseExactPatterns = {
  infectious_diseases: [/^감염학$/i, /^infectiousdiseases$/i],
  musculoskeletal: [/^근골격학$/i],
  endocrinology: [/^내분비학$/i],
  immunology_dermatology: [/^면역및피부질환$/i, /^면역피부질환$/i],
  reproductive_medicine: [/^생식계의학$/i, /^산부인과$/i],
  growth_development_aging: [/^성장발달노화$/i],
  clinical_intro: [/^임상의학입문$/i, /^기본진료수행$/i, /^기본임상술기$/i, /^clinicalintro$/i],
  gastroenterology_nutrition: [/^소화기및영양학$/i, /^소화기학및영양학$/i],
  cardiology: [/^순환기학$/i],
  neuro_special_senses: [/^신경및특수감각기학$/i],
  renal_urology: [/^신장비뇨기학$/i],
  human_society_medicine_1: [/^인간사회의료1$/i, /^인간사회의료i$/i],
  human_society_medicine_2: [/^인간사회의료2$/i, /^인간사회의료ii$/i, /^인간사회의료Ⅱ$/i],
  psychiatry: [/^정신의학$/i],
  disease_pharmacology: [/^질병의이해와약물요법$/i],
  hematology_oncology: [/^혈액및종양학$/i, /^혈액종양내과$/i, /^혈액종양학$/i],
  pulmonology: [/^호흡기학$/i],
};

function courseTextParts(item = {}) {
  return [
    item.course_id,
    item.course_name,
    item.exam_id,
    item.source_exam,
    item.source_file,
    item.round_label,
    item.period_label,
  ].filter(Boolean);
}

function isBroadCompositeExamSummary(item = {}) {
  const rawText = courseTextParts(item).join(" ");
  return /pma|임상의학종합평가|임상종합|clinical.*comprehensive/i.test(rawText);
}

function exactCourseKeyFromText(value) {
  const normalized = normalizeCourseMatchText(value);
  if (!normalized) return null;
  for (const [courseKey, patterns] of Object.entries(curriculumCourseExactPatterns)) {
    if (patterns.some((pattern) => pattern.test(normalized))) {
      return courseKey;
    }
  }
  return null;
}

function courseSummaryDirectlyMatches(item, courseKey) {
  if (!item || !courseKey) return false;
  if (item.course_id === courseKey) return true;
  const category = categoryByKey(courseKey);
  const targetTokens = [
    category?.title,
    category?.key,
    category?.title?.replaceAll("및", ""),
  ].map(normalizeCourseMatchText).filter(Boolean);
  const haystack = normalizeCourseMatchText([
    item.course_id,
    item.course_name,
    item.exam_id,
    item.source_file,
  ].filter(Boolean).join(" "));
  if (targetTokens.some((token) => token && haystack.includes(token))) return true;

  const rawText = courseTextParts(item).join(" ");
  return (curriculumCoursePatternMap[courseKey] || []).some((pattern) => pattern.test(rawText));
}

function matchesCourseSummary(item, courseKey) {
  return courseSummaryDirectlyMatches(item, courseKey);
}

function questionLabelText(question = {}, summary = {}) {
  const labels = question.labels || {};
  const conceptTags = Array.isArray(labels.concept_tags)
    ? labels.concept_tags.join(" ")
    : labels.concept_tags || labels.concept_tags_raw;
  return [
    labels.course_name_labeled,
    labels.course_name,
    labels.major_category,
    labels.topic,
    labels.subtopic,
    labels.assessment_domain,
    labels.question_type_labeled,
    labels.question_type,
    labels.source_label,
    labels.faculty_verified,
    conceptTags,
    question.question_type,
  ].filter(Boolean).join(" ");
}

function questionRoutingText(question = {}, summary = {}) {
  const choices = question.choices && typeof question.choices === "object"
    ? Object.values(question.choices).join(" ")
    : "";
  return [
    questionLabelText(question, summary),
    question.stem,
    question.raw_text,
    question.explanation,
    choices,
    courseTextParts(summary).join(" "),
  ].filter(Boolean).join(" ");
}

const curriculumCourseRouteOverrides = [
  {
    from: "pulmonology",
    to: "clinical_intro",
    pattern: /급성\s*복증|acute\s*abdomen/i,
  },
  {
    from: "renal_urology",
    to: "psychiatry",
    pattern: /급식|섭식\s*장애|식이\s*장애|eating\s*disorder/i,
  },
  {
    from: "renal_urology",
    to: "clinical_intro",
    pattern: /탈장|hernia/i,
  },
  {
    from: "gastroenterology_nutrition",
    to: "psychiatry",
    pattern: /섬망|delirium/i,
  },
  {
    from: "gastroenterology_nutrition",
    to: "cardiology",
    pattern: /복부\s*대동맥류(?:\s*파열)?|abdominal\s*aortic\s*aneurysm|aaa\s*rupture/i,
  },
];

function applyCourseRouteOverrides(courseKey, question = {}, summary = {}) {
  if (!courseKey) return courseKey;
  const text = questionRoutingText(question, summary);
  const override = curriculumCourseRouteOverrides.find((rule) => (
    rule.from === courseKey
      && departmentCategories.some((category) => category.key === rule.to)
      && rule.pattern.test(text)
  ));
  return override?.to || courseKey;
}

function questionCourseMatchScore(question = {}, summary = {}, courseKey) {
  if (!courseKey) return 0;
  const directSummaryMatch = courseSummaryDirectlyMatches(summary, courseKey);
  const broadComposite = isBroadCompositeExamSummary(summary);
  let score = directSummaryMatch && !broadComposite ? 100 : 0;

  const labels = question.labels || {};
  const exactLabelKey = exactCourseKeyFromText(labels.course_name_labeled || labels.course_name);
  if (exactLabelKey === courseKey) {
    score += 80;
  }

  const category = categoryByKey(courseKey);
  const labelText = questionLabelText(question, summary);
  const stemText = String(question.stem || "");
  const normalizedLabelText = normalizeCourseMatchText(labelText);
  const normalizedCategoryTitle = normalizeCourseMatchText(category?.title);
  if (normalizedCategoryTitle && normalizedLabelText.includes(normalizedCategoryTitle)) {
    score += 35;
  }

  (curriculumCoursePatternMap[courseKey] || []).forEach((pattern) => {
    if (pattern.test(labelText)) score += 24;
    if (pattern.test(stemText)) score += 5;
  });

  return score;
}

function bestCourseKeyForQuestion(question = {}, summary = {}) {
  const directCourseKey = summary.course_id && departmentCategories.some((category) => category.key === summary.course_id)
    ? summary.course_id
    : null;
  if (directCourseKey && !isBroadCompositeExamSummary(summary)) {
    return applyCourseRouteOverrides(directCourseKey, question, summary);
  }

  let best = { key: null, score: 0 };
  departmentCategories.forEach((category) => {
    const score = questionCourseMatchScore(question, summary, category.key);
    if (score > best.score) {
      best = { key: category.key, score };
    }
  });
  return best.score >= 20 ? applyCourseRouteOverrides(best.key, question, summary) : null;
}

function questionMatchesCourse(question = {}, summary = {}, courseKey) {
  return bestCourseKeyForQuestion(question, summary) === courseKey;
}

async function fetchCourseExamDetail(examId) {
  if (!examId) throw new Error("시험지 ID가 없습니다.");
  if (courseExamDetailCache[examId]) return courseExamDetailCache[examId];
  const response = await fetch(`/api/course-exams/extracted/${encodeURIComponent(examId)}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "문항 세트 로드 실패");
  }
  courseExamDetailCache[examId] = payload;
  return payload;
}

function mergedCourseExamSummary(detail = {}, fallbackSummary = {}) {
  return {
    ...(detail.exam || {}),
    ...(detail.summary || {}),
    ...fallbackSummary,
    exam_id: detail.exam_id || fallbackSummary.exam_id,
  };
}

function makeLibraryFilterId(parts) {
  return parts
    .filter(Boolean)
    .join("__")
    .replace(/[^\w가-힣.-]+/g, "_")
    .slice(0, 120);
}

function addQuestionToLibraryGroup(group, question) {
  group.questions.push(question);
  const labels = question.labels || {};
  [
    labels.source_label,
    question?._source_summary?.round_label,
    question?._source_summary?.exam_date,
  ].filter(Boolean).forEach((value) => group.sources.add(value));
  [
    labels.faculty_verified,
    labels.faculty,
    labels.professor,
  ].filter(Boolean).forEach((value) => group.faculty.add(value));
  [
    labels.subtopic,
    labels.assessment_domain,
    labels.question_type_labeled || labels.question_type,
  ].filter(Boolean).forEach((value) => group.subtopics.add(value));
}

function libraryMajorSortValue(title, courseKey) {
  const hemeOrder = [
    "혈액",
    "빈혈",
    "출혈/응고질환",
    "림프종",
    "백혈병",
    "골수증식질환",
    "형질세포질환",
    "항암치료",
    "암",
    "고형암",
    "수혈",
    "종양응급",
    "완화의료",
  ];
  if (courseKey === "hematology_oncology") {
    const index = hemeOrder.indexOf(title);
    return index >= 0 ? index : 999;
  }
  return 999;
}

function sortLibraryGroups(left, right, courseKey) {
  const leftOrder = libraryMajorSortValue(left.title, courseKey);
  const rightOrder = libraryMajorSortValue(right.title, courseKey);
  if (leftOrder !== rightOrder) return leftOrder - rightOrder;
  if (right.questions.length !== left.questions.length) return right.questions.length - left.questions.length;
  return left.title.localeCompare(right.title, "ko");
}

async function buildStudentLibraryIndex(courseKey = selectedLibraryCourseKey) {
  const category = categoryByKey(courseKey);
  const summaries = courseExamPracticeList
    .filter((item) => Number(item.practice_ready_count || item.question_count || 0) > 0);

  const details = await Promise.all(summaries.map((item) => fetchCourseExamDetail(item.exam_id)));
  const majors = new Map();
  const allQuestions = [];
  const contributingSources = new Map();

  details.forEach((detail) => {
    const fallbackSummary = summaries.find((item) => item.exam_id === detail.exam_id) || {};
    const summary = mergedCourseExamSummary(detail, fallbackSummary);
    (detail.questions || []).forEach((rawQuestion) => {
      if (!rawQuestion?.stem || !practiceChoiceEntries(rawQuestion).length) return;
      if (!questionMatchesCourse(rawQuestion, summary, courseKey)) return;
      const question = {
        ...rawQuestion,
        _source_summary: summary,
        _source_exam_id: detail.exam_id,
        _source_exam: detail.exam || {},
        _curriculum_course_key: courseKey,
        _curriculum_course_title: category?.title || summary.course_name || "과목",
      };
      contributingSources.set(detail.exam_id, summary);
      const labels = question.labels || {};
      const majorTitle = practiceLabelText(
        labels.major_category
          || labels.course_name_labeled
          || labels.course_name
          || summary.course_name
          || category?.title
          || "미분류"
      );
      const topicTitle = practiceLabelText(
        labels.topic
          || labels.subtopic
          || labels.assessment_domain
          || labels.question_type_labeled
          || labels.question_type
          || "기타 문항"
      );
      const majorId = makeLibraryFilterId([courseKey, "major", majorTitle]);
      const topicId = makeLibraryFilterId([courseKey, "topic", majorTitle, topicTitle]);

      if (!majors.has(majorTitle)) {
        majors.set(majorTitle, {
          id: majorId,
          title: majorTitle,
          questions: [],
          topics: new Map(),
          sources: new Set(),
          faculty: new Set(),
          subtopics: new Set(),
        });
      }
      const major = majors.get(majorTitle);
      if (!major.topics.has(topicTitle)) {
        major.topics.set(topicTitle, {
          id: topicId,
          title: topicTitle,
          parentId: majorId,
          parentTitle: majorTitle,
          questions: [],
          sources: new Set(),
          faculty: new Set(),
          subtopics: new Set(),
        });
      }
      const topic = major.topics.get(topicTitle);
      addQuestionToLibraryGroup(major, question);
      addQuestionToLibraryGroup(topic, question);
      allQuestions.push(question);
    });
  });

  const majorList = Array.from(majors.values())
    .map((major) => ({
      ...major,
      topics: Array.from(major.topics.values())
        .sort((left, right) => right.questions.length - left.questions.length || left.title.localeCompare(right.title, "ko")),
    }))
    .sort((left, right) => sortLibraryGroups(left, right, courseKey));

  studentLibraryMajorLookup = {};
  studentLibraryTopicLookup = {};
  majorList.forEach((major) => {
    studentLibraryMajorLookup[major.id] = major;
    major.topics.forEach((topic) => {
      studentLibraryTopicLookup[topic.id] = topic;
    });
  });

  return {
    courseKey,
    courseTitle: category?.title || "과목",
    summaries: Array.from(contributingSources.values()),
    majors: majorList,
    questions: allQuestions,
    sourceCount: contributingSources.size,
  };
}

async function refreshStudentCategoryQuestionCounts() {
  const playableSummaries = courseExamPracticeList
    .filter((item) => Number(item.practice_ready_count || item.question_count || 0) > 0);
  if (!playableSummaries.length) {
    studentCategoryQuestionCounts = {};
    renderCategoryGrid(studentCategoryGrid, "student");
    return;
  }

  const details = await Promise.all(playableSummaries.map((item) => fetchCourseExamDetail(item.exam_id)));
  const counts = {};
  details.forEach((detail) => {
    const fallbackSummary = playableSummaries.find((item) => item.exam_id === detail.exam_id) || {};
    const summary = mergedCourseExamSummary(detail, fallbackSummary);
    (detail.questions || []).forEach((question) => {
      if (!question?.stem || !practiceChoiceEntries(question).length) return;
      const courseKey = bestCourseKeyForQuestion(question, summary);
      if (!courseKey) return;
      counts[courseKey] = (counts[courseKey] || 0) + 1;
    });
  });
  studentCategoryQuestionCounts = counts;
  renderCategoryGrid(studentCategoryGrid, "student");
}

function renderLibraryGroupMeta(group) {
  const sources = compactUniqueList(Array.from(group.sources || []), 3);
  const faculty = compactUniqueList(Array.from(group.faculty || []), 3);
  const subtopics = compactUniqueList(Array.from(group.subtopics || []), 3);
  return `
    <div class="library-topic-meta">
      ${sources.length ? `<span>${escapeHtml(sources.join(" · "))}</span>` : ""}
      ${faculty.length ? `<span>${escapeHtml(faculty.join(" · "))}</span>` : ""}
      ${subtopics.length ? `<span>${escapeHtml(subtopics.join(" · "))}</span>` : ""}
    </div>
  `;
}

function renderStudentLibraryIndex(index) {
  if (!studentCourseBuilder) return;
  if (!index.questions.length) {
    studentCourseBuilder.innerHTML = `
      <div class="library-empty-state">
        <strong>${escapeHtml(index.courseTitle)} 문항 인덱스 준비 중</strong>
        <p>이 과목은 아직 라벨링된 문항 세트가 없습니다. 시험지 구조화와 라벨링을 마치면 같은 화면에서 단원별로 풀 수 있습니다.</p>
      </div>
    `;
    return;
  }

  const firstOpenId = index.majors[0]?.id || "";
  // 인덱스가 새로 그려지면 이전 선택은 유효하지 않은 topic id를 가리킬 수 있으니 정리.
  selectedLibraryTopicIds = new Set(
    Array.from(selectedLibraryTopicIds).filter((id) => studentLibraryTopicLookup[id])
  );
  studentCourseBuilder.innerHTML = `
    <div class="library-course-head">
      <div>
        <span>문항 세트 구성</span>
        <h3>${escapeHtml(index.courseTitle)}</h3>
        <p>단원을 선택하면 오른쪽에서 문항 수와 예상 풀이 시간을 바로 확인할 수 있습니다.</p>
      </div>
      <div class="library-course-stats">
        <article><strong>${escapeHtml(index.questions.length)}</strong><span>풀이 가능 문항</span></article>
        <article><strong>${escapeHtml(index.majors.length)}</strong><span>대분류</span></article>
        <article><strong>${escapeHtml(index.sourceCount)}</strong><span>시험지/자료</span></article>
      </div>
    </div>
    <div class="migration-builder-grid">
      <section class="migration-builder-main" aria-label="단원 선택">
        <div class="library-session-toolbar">
          <input
            type="search"
            class="library-search"
            placeholder="단원 또는 개념 검색"
            aria-label="세부 주제 검색"
          />
          <div class="library-toolbar-actions">
            <button type="button" class="library-select-all" data-library-select-all>전체 선택</button>
            <button
              type="button"
              class="library-course-all"
              data-library-practice-start
              data-library-filter-id="__course__"
              data-library-practice-scope="course"
            >
              전체 문항 바로 풀기
            </button>
          </div>
        </div>
        <div class="library-unit-list">
          ${index.majors.map((major, majorIndex) => `
            <article class="library-unit-card ${major.id === firstOpenId ? "is-open" : ""}" data-library-major-card="${escapeHtml(major.id)}">
              <div class="library-unit-toggle">
                <label class="library-check" title="${escapeHtml(major.title)} 전체 담기">
                  <input type="checkbox" data-library-major-check="${escapeHtml(major.id)}" />
                  <span class="library-index-num">${String(majorIndex + 1).padStart(2, "0")}</span>
                </label>
                <button type="button" class="library-unit-title" data-library-major-select="${escapeHtml(major.id)}">
                  <strong>${escapeHtml(major.title)}</strong>
                </button>
                <b class="library-unit-count">${escapeHtml(major.questions.length)}문항</b>
                <button type="button" class="library-unit-expand" data-library-major-toggle="${escapeHtml(major.id)}" aria-label="세부 주제 펼치기">
                  <i aria-hidden="true">⌄</i>
                </button>
              </div>
              <div class="library-topic-list">
                ${major.topics.map((topic) => `
                  <label class="library-topic-row" data-library-topic-item="${escapeHtml(topic.id)}">
                    <input type="checkbox" data-library-topic-check="${escapeHtml(topic.id)}" />
                    <span class="library-topic-name"><strong>${escapeHtml(topic.title)}</strong></span>
                    <b class="library-topic-count">${escapeHtml(topic.questions.length)}</b>
                  </label>
                `).join("")}
              </div>
            </article>
          `).join("")}
        </div>
      </section>
      <aside class="library-session-bar migration-selection-panel is-empty" data-library-session-bar aria-label="선택한 문항 요약">
        <div class="migration-selection-head">
          <div>
            <span>이번 학습 세트</span>
            <strong><b data-library-selected-count>0</b>문항 선택</strong>
          </div>
          <div class="migration-time-estimate">
            <span>예상 시간</span>
            <b data-library-estimated-time>0분</b>
          </div>
        </div>
        <div class="migration-selection-empty" data-library-selection-empty>
          <span aria-hidden="true">＋</span>
          <strong>풀 단원을 선택하세요</strong>
          <p>왼쪽 목록에서 한 개 이상의 단원을 담으면 문항 미리보기가 표시됩니다.</p>
        </div>
        <div class="migration-selection-preview" data-library-selection-preview hidden></div>
        <p class="migration-more-count" data-library-more-count hidden></p>
        <button type="button" class="library-primary-action" data-library-start-selection disabled>
          선택 문항 풀기
        </button>
      </aside>
    </div>
  `;
  syncLibrarySelectionUI();
}

async function renderStudentLibraryCourseBuilder(courseKey = selectedLibraryCourseKey) {
  if (!studentCourseBuilder) return;
  selectedLibraryCourseKey = courseKey || selectedLibraryCourseKey;
  const category = categoryByKey(selectedLibraryCourseKey);
  const renderSeq = ++studentLibraryRenderSeq;
  if (!courseExamPracticeList.length) {
    studentCourseBuilder.innerHTML = `
      <div class="library-empty-state">
        <strong>${escapeHtml(category?.title || "과목")} 문항 인덱스를 불러오는 중입니다.</strong>
        <p>구조화된 시험지 목록을 확인하고 있습니다.</p>
      </div>
    `;
    return;
  }
  studentCourseBuilder.innerHTML = `
    <div class="library-empty-state">
      <strong>${escapeHtml(category?.title || "과목")} 라벨 인덱스를 구성하는 중입니다.</strong>
      <p>시험지별 문항을 대분류와 세부 주제로 묶고 있습니다.</p>
    </div>
  `;
  try {
    const index = await buildStudentLibraryIndex(selectedLibraryCourseKey);
    if (renderSeq !== studentLibraryRenderSeq) return;
    studentLibraryIndex = index;
    renderStudentLibraryIndex(index);
  } catch (error) {
    if (renderSeq !== studentLibraryRenderSeq) return;
    studentCourseBuilder.innerHTML = `
      <div class="library-empty-state">
        <strong>문항 인덱스 구성 실패</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  }
}

function librarySelectionByScope(filterId, scope) {
  if (!studentLibraryIndex) return null;
  if (scope === "course" || filterId === "__course__") {
    return {
      id: makeLibraryFilterId([studentLibraryIndex.courseKey, "course"]),
      title: `${studentLibraryIndex.courseTitle} 전체`,
      questions: studentLibraryIndex.questions,
    };
  }
  if (scope === "major") return studentLibraryMajorLookup[filterId] || null;
  return studentLibraryTopicLookup[filterId] || studentLibraryMajorLookup[filterId] || null;
}

function activatePracticePayload(payload, statusText = "") {
  currentPracticeExam = payload;
  currentPracticeIndex = 0;
  currentPracticeAnswers = {};
  currentPracticePendingAnswers = {};
  currentPracticeAnswerEvents = {};
  currentPracticeTimeByQuestion = {};
  currentPracticeViewed = new Set();
  currentPracticeBookmarks = new Set();
  currentPracticeFlags = {};
  currentPracticeExpandedChoices = {};
  currentPracticeTab = "key";
  currentPracticeSidebarCollapsed = false;
  currentPracticeSessionId = `session_${Date.now()}`;
  currentPracticeSessionStartedAt = new Date().toISOString();
  currentPracticeActiveQuestionKey = null;
  currentPracticeQuestionStartedAt = null;
  currentPracticeTimerPaused = false;
  loadPracticeState();
  document.body.classList.add("practice-session-active");
  studentPracticePage?.classList.add("practice-active");
  if (studentPracticeStatus && statusText) {
    studentPracticeStatus.textContent = statusText;
  }
  renderStudentPracticeQuestion({ preserveSidebarScroll: false });
}

async function startStudentLibraryPractice(filterId, scope = "topic") {
  const selection = librarySelectionByScope(filterId, scope);
  if (!selection?.questions?.length || !studentLibraryIndex) return;
  finalizePracticeQuestionTime();
  const questions = selection.questions.map((question) => ({ ...question }));
  const payload = {
    exam_id: `library_${studentLibraryIndex.courseKey}_${selection.id}`,
    summary: {
      course_id: studentLibraryIndex.courseKey,
      course_name: studentLibraryIndex.courseTitle,
      round_label: selection.title,
      question_count: questions.length,
      source_file: "라벨 기반 문항 세트",
    },
    questions,
  };
  showPage("student-practice", { scrollTop: false });
  activatePracticePayload(
    payload,
    `${studentLibraryIndex.courseTitle} · ${selection.title} ${questions.length}문항 세트를 열었습니다.`
  );
}

// ── 세션 빌더(AMBOSS풍): 여러 세부주제를 담아 한 세션으로 시작 ──────────────
function selectedLibraryQuestions() {
  const seen = new Set();
  const questions = [];
  selectedLibraryTopicIds.forEach((topicId) => {
    const topic = studentLibraryTopicLookup[topicId];
    if (!topic) return;
    (topic.questions || []).forEach((question) => {
      const key = question.question_id
        || `${question._source_exam_id || ""}:${question.question_number || ""}`;
      if (seen.has(key)) return;
      seen.add(key);
      questions.push(question);
    });
  });
  return questions;
}

function syncLibrarySelectionUI() {
  if (!studentCourseBuilder) return;
  studentCourseBuilder.querySelectorAll("[data-library-topic-check]").forEach((box) => {
    box.checked = selectedLibraryTopicIds.has(box.dataset.libraryTopicCheck);
  });
  studentCourseBuilder.querySelectorAll("[data-library-major-check]").forEach((box) => {
    const major = studentLibraryMajorLookup[box.dataset.libraryMajorCheck];
    const topicIds = (major?.topics || []).map((topic) => topic.id);
    const chosen = topicIds.filter((id) => selectedLibraryTopicIds.has(id)).length;
    box.checked = topicIds.length > 0 && chosen === topicIds.length;
    box.indeterminate = chosen > 0 && chosen < topicIds.length;
    box.closest(".library-unit-card")?.classList.toggle("is-selected", chosen > 0);
  });
  const questions = selectedLibraryQuestions();
  const bar = studentCourseBuilder.querySelector("[data-library-session-bar]");
  const countEl = studentCourseBuilder.querySelector("[data-library-selected-count]");
  const estimatedEl = studentCourseBuilder.querySelector("[data-library-estimated-time]");
  const emptyEl = studentCourseBuilder.querySelector("[data-library-selection-empty]");
  const previewEl = studentCourseBuilder.querySelector("[data-library-selection-preview]");
  const moreEl = studentCourseBuilder.querySelector("[data-library-more-count]");
  const selectAllBtn = studentCourseBuilder.querySelector("[data-library-select-all]");
  const startBtn = studentCourseBuilder.querySelector("[data-library-start-selection]");
  if (countEl) countEl.textContent = String(questions.length);
  if (estimatedEl) estimatedEl.textContent = questions.length
    ? `${Math.max(1, Math.ceil(questions.length * 1.25))}분`
    : "0분";
  if (bar) {
    bar.hidden = false;
    bar.classList.toggle("is-empty", questions.length === 0);
  }
  if (emptyEl) emptyEl.hidden = questions.length > 0;
  if (previewEl) {
    previewEl.hidden = questions.length === 0;
    previewEl.innerHTML = questions.slice(0, 5).map((question, index) => {
      const stem = String(question.stem || "문항 지문 미추출").replace(/\s+/g, " ").trim();
      const preview = `${stem.slice(0, 54)}${stem.length > 54 ? "..." : ""}`;
      return `
        <div class="migration-preview-row">
          <span>${String(index + 1).padStart(2, "0")}</span>
          <p>${escapeHtml(preview)}</p>
        </div>
      `;
    }).join("");
  }
  if (moreEl) {
    const remaining = Math.max(0, questions.length - 5);
    moreEl.hidden = remaining === 0;
    moreEl.textContent = remaining ? `외 ${remaining}문항` : "";
  }
  if (selectAllBtn) {
    const allIds = Object.keys(studentLibraryTopicLookup);
    const allSelected = allIds.length > 0 && allIds.every((id) => selectedLibraryTopicIds.has(id));
    selectAllBtn.textContent = allSelected ? "전체 해제" : "전체 선택";
  }
  if (startBtn) {
    startBtn.disabled = questions.length === 0;
    startBtn.textContent = questions.length ? `${questions.length}문항으로 시작` : "단원을 먼저 선택하세요";
  }
}

function setLibraryTopicSelected(topicId, selected) {
  if (!studentLibraryTopicLookup[topicId]) return;
  if (selected) selectedLibraryTopicIds.add(topicId);
  else selectedLibraryTopicIds.delete(topicId);
}

function setLibraryMajorSelected(majorId, selected) {
  const major = studentLibraryMajorLookup[majorId];
  if (!major) return;
  (major.topics || []).forEach((topic) => setLibraryTopicSelected(topic.id, selected));
}

function isLibraryMajorFullySelected(majorId) {
  const major = studentLibraryMajorLookup[majorId];
  const topicIds = (major?.topics || []).map((topic) => topic.id);
  return topicIds.length > 0 && topicIds.every((id) => selectedLibraryTopicIds.has(id));
}

function toggleLibrarySelectAll() {
  const allIds = Object.keys(studentLibraryTopicLookup);
  const allSelected = allIds.length > 0 && allIds.every((id) => selectedLibraryTopicIds.has(id));
  if (allSelected) selectedLibraryTopicIds.clear();
  else allIds.forEach((id) => selectedLibraryTopicIds.add(id));
  syncLibrarySelectionUI();
}

function filterLibraryTopics(query) {
  if (!studentCourseBuilder) return;
  const q = (query || "").trim().toLowerCase();
  studentCourseBuilder.querySelectorAll(".library-unit-card").forEach((card) => {
    const majorTitle = card.querySelector(".library-unit-title")?.textContent.toLowerCase() || "";
    const majorMatch = !q || majorTitle.includes(q);
    let visibleTopics = 0;
    card.querySelectorAll("[data-library-topic-item]").forEach((row) => {
      const name = row.textContent.toLowerCase();
      const match = !q || majorMatch || name.includes(q);
      row.hidden = !match;
      if (match) visibleTopics += 1;
    });
    card.hidden = Boolean(q) && visibleTopics === 0 && !majorMatch;
    if (q && !card.hidden) card.classList.add("is-open");
  });
}

async function startStudentLibrarySelection() {
  if (!studentLibraryIndex) return;
  const questions = selectedLibraryQuestions().map((question) => ({ ...question }));
  if (!questions.length) return;
  finalizePracticeQuestionTime();
  const majorTitles = compactUniqueList(
    Array.from(selectedLibraryTopicIds)
      .map((id) => studentLibraryTopicLookup[id]?.parentTitle)
      .filter(Boolean),
    3
  );
  const title = majorTitles.length <= 1
    ? (majorTitles[0] || "선택")
    : `${majorTitles[0]} 외 ${majorTitles.length - 1}개 대분류`;
  const payload = {
    exam_id: `library_${studentLibraryIndex.courseKey}_selection_${selectedLibraryTopicIds.size}`,
    summary: {
      course_id: studentLibraryIndex.courseKey,
      course_name: studentLibraryIndex.courseTitle,
      round_label: `${title} 세션`,
      question_count: questions.length,
      source_file: "라벨 기반 선택 세션",
    },
    questions,
  };
  showPage("student-practice", { scrollTop: false });
  activatePracticePayload(
    payload,
    `${studentLibraryIndex.courseTitle} · ${questions.length}문항 세션을 열었습니다.`
  );
}

function practiceChoiceEntries(question) {
  const choices = question?.choices || question?.options || {};
  if (Array.isArray(choices)) {
    return choices.map((choice, index) => [String(index + 1), choice]);
  }
  return Object.entries(choices || {})
    .sort(([left], [right]) => Number(left) - Number(right));
}

function practiceQuestionKey(question, fallbackIndex = currentPracticeIndex) {
  return question?.question_id || String(question?.question_number || fallbackIndex);
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function practiceStorageKey() {
  const examId = currentPracticeExam?.exam_id;
  return examId ? `paccine.practice.${examId}` : null;
}

function savePracticeState() {
  const key = practiceStorageKey();
  if (!key) return;
  try {
    window.sessionStorage?.setItem(
      key,
      JSON.stringify({
        session_id: currentPracticeSessionId,
        started_at: currentPracticeSessionStartedAt,
        answers: currentPracticeAnswers,
        pending_answers: currentPracticePendingAnswers,
        answer_events: currentPracticeAnswerEvents,
        time_by_question: currentPracticeTimeByQuestion,
        viewed: Array.from(currentPracticeViewed),
        bookmarks: Array.from(currentPracticeBookmarks),
        flags: currentPracticeFlags,
        expanded_choices: currentPracticeExpandedChoices,
        timer_paused: currentPracticeTimerPaused,
      })
    );
  } catch (error) {
    // Local persistence is optional; the study session still works without it.
  }
}

function loadPracticeState() {
  const key = practiceStorageKey();
  if (!key) return;
  try {
    const restored = JSON.parse(window.sessionStorage?.getItem(key) || "{}");
    currentPracticeSessionId = restored.session_id || `session_${Date.now()}`;
    currentPracticeSessionStartedAt = restored.started_at || new Date().toISOString();
    currentPracticeAnswers = restored.answers && typeof restored.answers === "object" ? restored.answers : {};
    currentPracticePendingAnswers = restored.pending_answers && typeof restored.pending_answers === "object" ? restored.pending_answers : {};
    currentPracticeAnswerEvents = restored.answer_events && typeof restored.answer_events === "object" ? restored.answer_events : {};
    currentPracticeTimeByQuestion = restored.time_by_question && typeof restored.time_by_question === "object" ? restored.time_by_question : {};
    currentPracticeViewed = new Set(Array.isArray(restored.viewed) ? restored.viewed : []);
    currentPracticeBookmarks = new Set(Array.isArray(restored.bookmarks) ? restored.bookmarks : []);
    currentPracticeFlags = restored.flags && typeof restored.flags === "object" ? restored.flags : {};
    currentPracticeExpandedChoices = restored.expanded_choices && typeof restored.expanded_choices === "object" ? restored.expanded_choices : {};
    currentPracticeTimerPaused = Boolean(restored.timer_paused);
  } catch (error) {
    currentPracticeSessionId = `session_${Date.now()}`;
    currentPracticeSessionStartedAt = new Date().toISOString();
    currentPracticeAnswers = {};
    currentPracticePendingAnswers = {};
    currentPracticeAnswerEvents = {};
    currentPracticeTimeByQuestion = {};
    currentPracticeViewed = new Set();
    currentPracticeBookmarks = new Set();
    currentPracticeFlags = {};
    currentPracticeExpandedChoices = {};
    currentPracticeTimerPaused = false;
  }
}

function finalizePracticeQuestionTime(now = Date.now()) {
  if (!currentPracticeActiveQuestionKey || !currentPracticeQuestionStartedAt) return;
  const elapsed = Math.max(0, Math.floor((now - currentPracticeQuestionStartedAt) / 1000));
  if (elapsed > 0) {
    currentPracticeTimeByQuestion[currentPracticeActiveQuestionKey] =
      Number(currentPracticeTimeByQuestion[currentPracticeActiveQuestionKey] || 0) + elapsed;
  }
  currentPracticeQuestionStartedAt = now;
}

function stopPracticeQuestionTimer() {
  finalizePracticeQuestionTime();
  currentPracticeActiveQuestionKey = null;
  currentPracticeQuestionStartedAt = null;
  currentPracticeTimerPaused = false;
}

function beginPracticeQuestionTimer(questionKey) {
  if (!questionKey) return;
  if (currentPracticeActiveQuestionKey === questionKey && currentPracticeQuestionStartedAt) return;
  finalizePracticeQuestionTime();
  currentPracticeActiveQuestionKey = questionKey;
  if (currentPracticeTimerPaused) {
    currentPracticeQuestionStartedAt = null;
    return;
  }
  currentPracticeQuestionStartedAt = Date.now();
}

function pausePracticeQuestionTimer() {
  if (!currentPracticeActiveQuestionKey) return;
  finalizePracticeQuestionTime();
  currentPracticeQuestionStartedAt = null;
  currentPracticeTimerPaused = true;
  updateLivePracticeTime();
}

function resumePracticeQuestionTimer(questionKey) {
  if (!questionKey) return;
  currentPracticeActiveQuestionKey = questionKey;
  currentPracticeQuestionStartedAt = Date.now();
  currentPracticeTimerPaused = false;
  updateLivePracticeTime();
}

function getPracticeTimeForQuestion(questionKey) {
  const saved = Number(currentPracticeTimeByQuestion[questionKey] || 0);
  if (!currentPracticeTimerPaused && currentPracticeActiveQuestionKey === questionKey && currentPracticeQuestionStartedAt) {
    return saved + Math.max(0, Math.floor((Date.now() - currentPracticeQuestionStartedAt) / 1000));
  }
  return saved;
}

function currentPracticeExamIdForAttempt(question) {
  return String(
    question?._source_exam_id
      || question?._source_summary?.exam_id
      || currentPracticeExam?.exam_id
      || currentPracticeExam?.summary?.exam_id
      || ""
  );
}

function currentPracticeSourceMeta(question) {
  const summary = question?._source_summary || currentPracticeExam?.summary || {};
  return {
    ...summary,
    exam_id: currentPracticeExamIdForAttempt(question),
    source_file: summary.source_file || question?.source_exam || question?.source_file || "",
  };
}

function buildPracticeAttemptEvent(question, questionKey, selectedKeys) {
  const sourceMeta = currentPracticeSourceMeta(question);
  const labels = question?.labels || {};
  const choiceTexts = Object.fromEntries(
    practiceChoiceEntries(question).map(([choiceKey, choiceText]) => [String(choiceKey), String(choiceText || "")])
  );
  return {
    event_id: `attempt_${Date.now()}_${questionKey}`,
    session_id: currentPracticeSessionId,
    user_id: "local_student",
    role: "student",
    exam_id: sourceMeta.exam_id,
    course_id: sourceMeta.course_id || question?._curriculum_course_key || labels.course_id || "",
    course_name: sourceMeta.course_name || question?._curriculum_course_title || labels.course_name_labeled || labels.course_name || "",
    source_file: sourceMeta.source_file || "",
    question_id: questionKey,
    question_number: question?.question_number,
    stem_preview: String(question?.stem || "").trim().slice(0, 180),
    question_type: practiceQuestionTypeLabel(question),
    choice_texts: choiceTexts,
    selected_choice_numbers: practiceNormalizeAnswerSelection(selectedKeys),
    answer_keys: practiceAnswerKeys(question),
    is_correct: practiceSelectionIsCorrect(question, selectedKeys),
    time_ms: getPracticeTimeForQuestion(questionKey) * 1000,
    answered_at: new Date().toISOString(),
    is_bookmarked: currentPracticeBookmarks.has(questionKey),
    flag_type: currentPracticeFlags[questionKey] || null,
    labels,
    source_meta: sourceMeta,
  };
}

async function submitPracticeAttempt(attemptEvent) {
  if (!attemptEvent?.question_id) return;
  const response = await fetch("/api/practice/attempts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(attemptEvent),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "풀이 기록 저장 실패");
  }
}

function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(number % 1 === 0 ? 0 : 1)}%` : "0%";
}

function renderStudentPracticeAnalytics(payload) {
  if (!studentReviewAnalytics) return;
  const summary = payload?.summary || {};
  const weaknessRows = payload?.weakness || [];
  const ontologyWeaknessRows = payload?.ontology_weakness || [];
  const recentAttempts = payload?.recent_attempts || [];
  if (!summary.attempt_count) {
    studentReviewAnalytics.innerHTML = `
      <div class="student-analytics-empty">
        <strong>아직 저장된 풀이 기록이 없습니다.</strong>
        <p>문제를 하나 풀고 정답을 확인하면 이곳에 정답률, 풀이 시간, 취약 라벨이 자동으로 쌓입니다.</p>
        <button type="button" class="secondary-button" data-page-link="student-practice">문제 풀러 가기</button>
      </div>
    `;
    return;
  }

  const weaknessHtml = weaknessRows.slice(0, 8).map((row) => `
    <tr>
      <td>${escapeHtml(row.label_path || "미분류")}</td>
      <td>${escapeHtml(row.attempt_count || 0)}</td>
      <td><strong>${escapeHtml(formatPercent(row.correct_rate_pct || 0))}</strong></td>
      <td>${escapeHtml(formatDuration(row.avg_time_sec || 0))}</td>
    </tr>
  `).join("");

  const recentHtml = recentAttempts.slice(0, 5).map((event) => `
    <li>
      <span>${event.is_correct ? "정답" : "오답"}</span>
      <strong>Q${escapeHtml(event.question_number || event.question_id || "-")}</strong>
      <em>${escapeHtml(attemptLabelSummary(event))}</em>
    </li>
  `).join("");

  const ontologyWeaknessHtml = ontologyWeaknessRows.slice(0, 10).map((row) => {
    const topMisconception = row.misconceptions?.[0];
    const signal = topMisconception
      ? `오개념 ${topMisconception.misconception_id} · ${topMisconception.count}회`
      : "오개념 표본 없음";
    return `
      <tr>
        <td>${escapeHtml(practiceLabelText(row.disease_concept_id) || "개념 미지정")}</td>
        <td>${escapeHtml(practiceLabelText(row.axis_type) || "축 미지정")}</td>
        <td>${escapeHtml(row.sample_size || 0)}</td>
        <td><strong>${escapeHtml(formatPercent(row.correct_rate_pct || 0))}</strong></td>
        <td>${escapeHtml(signal)}</td>
      </tr>
    `;
  }).join("");

  studentReviewAnalytics.innerHTML = `
    <div class="student-analytics-summary">
      <article>
        <span>풀이 문항</span>
        <strong>${escapeHtml(summary.attempt_count || 0)}</strong>
        <p>저장된 풀이 이벤트 기준</p>
      </article>
      <article>
        <span>누적 정답률</span>
        <strong>${escapeHtml(formatPercent(summary.correct_rate_pct || 0))}</strong>
        <p>${escapeHtml(summary.correct_count || 0)}문항 정답</p>
      </article>
      <article>
        <span>학습한 날</span>
        <strong>${escapeHtml(payload?.heatmap?.active_days || 0)}일</strong>
        <p>최근 약 17주 기준</p>
      </article>
      <article>
        <span>평균 풀이 시간</span>
        <strong>${escapeHtml(formatDuration(summary.avg_time_sec || 0))}</strong>
        <p>문항별 기록 시간</p>
      </article>
    </div>
    ${renderPracticeHeatmap(payload?.heatmap)}
    <div class="student-analytics-grid">
      <section class="student-analytics-table-card">
        <div>
          <span class="section-label">Weakness Map</span>
          <h3>취약 라벨</h3>
        </div>
        <table>
          <thead>
            <tr>
              <th>분류</th>
              <th>풀이</th>
              <th>정답률</th>
              <th>평균</th>
            </tr>
          </thead>
          <tbody>${weaknessHtml || '<tr><td colspan="4">아직 라벨 기반 기록이 없습니다.</td></tr>'}</tbody>
        </table>
      </section>
      <section class="student-analytics-recent-card">
        <div>
          <span class="section-label">Recent</span>
          <h3>최근 풀이</h3>
        </div>
        <ul>${recentHtml || "<li><em>최근 풀이가 없습니다.</em></li>"}</ul>
      </section>
    </div>
    <section class="student-analytics-table-card">
      <div>
        <span class="section-label">Ontology Learning Map</span>
        <h3>질환 × 임상 축 취약점</h3>
        <p>문항 설계도가 연결된 풀이만 집계합니다. 표본이 적을 때는 숙련도 판정이 아니라 복습 우선순위 신호로 보세요.</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>질환 개념</th>
            <th>평가 축</th>
            <th>표본</th>
            <th>정답률</th>
            <th>오답 신호</th>
          </tr>
        </thead>
        <tbody>${ontologyWeaknessHtml || '<tr><td colspan="5">QuestionBlueprint가 연결된 풀이 기록이 아직 없습니다.</td></tr>'}</tbody>
      </table>
    </section>
    ${renderQuestionHistory(payload?.question_history)}
  `;
}

function heatmapLevel(attempts, maxAttempts) {
  if (!attempts) return 0;
  if (maxAttempts <= 1) return 4;
  const ratio = attempts / maxAttempts;
  if (ratio <= 0.25) return 1;
  if (ratio <= 0.5) return 2;
  if (ratio <= 0.75) return 3;
  return 4;
}

function renderPracticeHeatmap(heatmap) {
  const cells = heatmap?.cells || [];
  if (!cells.length) return "";
  const maxAttempts = heatmap.max_attempts || 0;
  // 일요일 시작 정렬을 위해 첫 셀의 요일만큼 앞을 빈칸으로 채움
  const firstDow = new Date(`${cells[0].date}T00:00:00`).getDay();
  const padded = Array.from({ length: firstDow }, () => null).concat(cells);
  const cellsHtml = padded.map((cell) => {
    if (!cell) return `<span class="heatmap-cell empty" aria-hidden="true"></span>`;
    const level = heatmapLevel(cell.attempts, maxAttempts);
    const title = cell.attempts
      ? `${cell.date} · ${cell.attempts}문항 (정답 ${cell.correct})`
      : `${cell.date} · 학습 없음`;
    return `<span class="heatmap-cell level-${level}" title="${escapeHtml(title)}"></span>`;
  }).join("");
  return `
    <section class="student-heatmap-card">
      <div class="student-heatmap-head">
        <div>
          <span class="section-label">Study Heatmap</span>
          <h3>학습 히트맵</h3>
        </div>
        <div class="heatmap-legend">
          <span>적음</span>
          <span class="heatmap-cell level-0"></span>
          <span class="heatmap-cell level-1"></span>
          <span class="heatmap-cell level-2"></span>
          <span class="heatmap-cell level-3"></span>
          <span class="heatmap-cell level-4"></span>
          <span>많음</span>
        </div>
      </div>
      <div class="heatmap-grid">${cellsHtml}</div>
    </section>
  `;
}

function renderQuestionHistory(history) {
  const rows = history || [];
  if (!rows.length) return "";
  const rowsHtml = rows.map((row) => {
    const dots = (row.results || []).slice(-8).map((correct) =>
      `<span class="attempt-dot ${correct ? "correct" : "wrong"}" title="${correct ? "정답" : "오답"}"></span>`
    ).join("");
    const trend = row.last_correct === null ? "" : row.last_correct ? "최근 정답" : "최근 오답";
    return `
      <tr>
        <td><strong>Q${escapeHtml(row.question_number || row.question_id || "-")}</strong></td>
        <td>${escapeHtml(row.label_summary || "미분류")}</td>
        <td>${escapeHtml(row.attempt_count || 0)}회</td>
        <td>${escapeHtml(formatPercent(row.correct_rate_pct || 0))}</td>
        <td><div class="attempt-dots">${dots}</div></td>
        <td class="${row.last_correct ? "trend-correct" : "trend-wrong"}">${escapeHtml(trend)}</td>
      </tr>
    `;
  }).join("");
  return `
    <section class="student-history-card">
      <div>
        <span class="section-label">Question Log</span>
        <h3>문항별 풀이 기록</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>문항</th>
            <th>분류</th>
            <th>풀이</th>
            <th>정답률</th>
            <th>정오답 이력</th>
            <th>추세</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </section>
  `;
}

function attemptLabelSummary(event) {
  const labels = event?.labels || {};
  return [
    event?.course_name || labels.course_name_labeled,
    labels.major_category,
    labels.topic || labels.subtopic,
  ].filter(Boolean).join(" · ") || event?.source_file || "라벨 미분류";
}

function ratingStars(value) {
  const full = Math.round(Number(value) || 0);
  return "★★★★★".slice(0, full) + "☆☆☆☆☆".slice(0, 5 - full);
}

async function loadFacultyFeedback() {
  const body = document.querySelector("#facultyFeedbackBody");
  if (!body) return;
  body.innerHTML = `<p class="faculty-feedback-loading">학생 피드백을 불러오는 중입니다.</p>`;
  try {
    const response = await fetch("/api/feedback/summary");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "피드백 로드 실패");
    const count = payload.count || 0;
    if (!count) {
      body.innerHTML = `
        <div class="faculty-feedback-empty">
          <strong>아직 수집된 학생 피드백이 없습니다.</strong>
          <p>학생 화면 우측 하단의 "피드백 보내기"로 들어온 평점과 의견이 이곳에 모입니다.</p>
        </div>`;
      return;
    }
    const recent = payload.recent || [];
    const commentsHtml = recent
      .filter((item) => (item.comment || "").trim())
      .slice(0, 8)
      .map((item) => `
        <li>
          <div class="feedback-item-head">
            <span class="feedback-item-stars">${ratingStars(item.rating)}</span>
            <time>${escapeHtml((item.submitted_at || "").replace("T", " "))}</time>
          </div>
          <p>${escapeHtml(item.comment)}</p>
        </li>
      `)
      .join("");
    body.innerHTML = `
      <div class="faculty-feedback-stats">
        <article>
          <span>받은 피드백</span>
          <strong>${escapeHtml(count)}건</strong>
        </article>
        <article>
          <span>평균 만족도</span>
          <strong>${escapeHtml(payload.avg_rating || 0)} <em>${ratingStars(payload.avg_rating)}</em></strong>
        </article>
      </div>
      ${commentsHtml
        ? `<ul class="faculty-feedback-list">${commentsHtml}</ul>`
        : `<p class="faculty-feedback-empty">평점은 들어왔지만 자유 의견은 아직 없습니다.</p>`}
    `;
  } catch (error) {
    body.innerHTML = `<p class="faculty-feedback-empty">피드백을 불러오지 못했습니다: ${escapeHtml(error.message)}</p>`;
  }
}

function renderDistractorQuestion(q) {
  const maxCount = Math.max(1, ...q.choices.map((c) => c.count));
  const barsHtml = q.choices
    .map((c) => {
      const width = Math.round((c.count / maxCount) * 100);
      const cls = c.is_answer ? "answer" : (c.choice === q.top_distractor?.choice ? "top-wrong" : "wrong");
      return `
        <div class="distractor-bar-row">
          <span class="distractor-choice-key">${escapeHtml(c.choice)}</span>
          <div class="distractor-bar-track">
            <div class="distractor-bar ${cls}" style="width:${width}%"></div>
            <span class="distractor-bar-text">${escapeHtml(c.text || "선지 텍스트 없음")}</span>
          </div>
          <span class="distractor-bar-pct">${escapeHtml(c.pct)}%${c.is_answer ? " · 정답" : ""}</span>
        </div>
      `;
    })
    .join("");
  // "공통" 오개념이라 부르려면 응답자가 충분해야 한다(1~2명 100%는 신호 아님).
  const stuckNote = q.top_distractor && q.attempt_count >= 4 && q.distractor_concentration_pct >= 40
    ? `<p class="distractor-flag">⚠ ${escapeHtml(q.attempt_count)}명 중 ${escapeHtml(q.distractor_concentration_pct)}%가 "${escapeHtml((q.top_distractor.text || q.top_distractor.choice).slice(0, 40))}"에 몰림 — 공통 오개념 가능성</p>`
    : "";
  const fewNote = q.attempt_count < 4
    ? `<p class="distractor-fewnote">응답 ${escapeHtml(q.attempt_count)}명 — 표본이 쌓이면 더 정확해집니다.</p>`
    : "";
  return `
    <article class="distractor-question">
      <div class="distractor-q-head">
        <strong>Q${escapeHtml(q.question_number || q.question_id || "-")}</strong>
        <span class="distractor-q-label">${escapeHtml(q.label_summary || "미분류")}</span>
        <span class="distractor-q-stats">정답률 ${escapeHtml(q.correct_rate_pct)}% · ${escapeHtml(q.attempt_count)}명 · 평균 ${escapeHtml(formatDuration(q.avg_time_sec))}</span>
      </div>
      ${q.stem_preview ? `<p class="distractor-stem">${escapeHtml(q.stem_preview)}</p>` : ""}
      <div class="distractor-bars">${barsHtml}</div>
      ${stuckNote}
      ${fewNote}
    </article>
  `;
}

async function loadDistractorAnalysis() {
  const body = document.querySelector("#distractorBody");
  if (!body) return;
  body.innerHTML = `<p class="distractor-loading">오답 분포를 불러오는 중입니다.</p>`;
  try {
    const response = await fetch("/api/practice/analytics/distractors");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "오답 분석 로드 실패");
    const questions = payload.questions || [];
    if (!questions.length) {
      body.innerHTML = `
        <div class="distractor-empty">
          <strong>아직 분석할 풀이 기록이 없습니다.</strong>
          <p>학생들이 문제를 풀면 문항별로 어떤 선지에 몰렸는지 자동으로 집계됩니다.</p>
        </div>`;
      return;
    }
    body.innerHTML = questions.slice(0, 12).map(renderDistractorQuestion).join("");
  } catch (error) {
    body.innerHTML = `<p class="distractor-empty">오답 분석을 불러오지 못했습니다: ${escapeHtml(error.message)}</p>`;
  }
}

async function loadStudentPracticeAnalytics() {
  if (!studentReviewAnalytics) return;
  studentReviewAnalytics.innerHTML = `
    <div class="student-analytics-empty">
      <strong>풀이 기록을 불러오는 중입니다.</strong>
      <p>저장된 정답률과 취약 라벨을 정리하고 있습니다.</p>
    </div>
  `;
  try {
    const response = await fetch("/api/practice/analytics/student?user_id=local_student");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "학습 리포트 로드 실패");
    }
    renderStudentPracticeAnalytics(payload);
  } catch (error) {
    studentReviewAnalytics.innerHTML = `
      <div class="student-analytics-empty error">
        <strong>학습 리포트를 불러오지 못했습니다.</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  }
}

function facultyLabelSummary(row) {
  const labels = row?.labels || {};
  return [
    labels.course_name_labeled || labels.course_name,
    labels.major_category,
    labels.topic || labels.subtopic,
    labels.assessment_domain,
  ].filter(Boolean).join(" · ") || "라벨 미분류";
}

function renderFacultyChoiceDistribution(row) {
  const choices = Array.isArray(row?.choices) ? row.choices : [];
  const attemptedChoices = choices.filter((choice) => Number(choice.selected_count || 0) > 0 || choice.is_correct);
  if (!attemptedChoices.length) {
    return `<p class="faculty-choice-empty">아직 선택지별 풀이 분포가 없습니다.</p>`;
  }
  return `
    <div class="faculty-choice-distribution">
      ${attemptedChoices.map((choice) => `
        <span class="${choice.is_correct ? "correct" : "incorrect"}">
          ${escapeHtml(choice.choice)}번
          <b>${escapeHtml(formatPercent(choice.selected_pct || 0))}</b>
        </span>
      `).join("")}
    </div>
  `;
}

function renderFacultyPracticeAnalytics(payload) {
  if (!facultyReportAnalytics) return;
  const rows = (payload?.item_reports || [])
    .filter((row) => Number(row.attempt_count || 0) > 0)
    .sort((left, right) => {
      const leftWrong = left.top_wrong_choice?.selected_pct || 0;
      const rightWrong = right.top_wrong_choice?.selected_pct || 0;
      return (left.correct_rate_pct - right.correct_rate_pct) || (rightWrong - leftWrong);
    });

  if (!rows.length) {
    facultyReportAnalytics.innerHTML = `
      <div class="student-analytics-empty">
        <strong>아직 교수 리포트에 표시할 풀이 기록이 없습니다.</strong>
        <p>학생이 문제를 풀고 정답을 확인하면 문항별 정답률, 평균 풀이 시간, 오답 선택지 분포가 자동으로 쌓입니다.</p>
      </div>
    `;
    return;
  }

  facultyReportAnalytics.innerHTML = rows.slice(0, 12).map((row) => {
    const topWrong = row.top_wrong_choice;
    const statusClass = Number(row.correct_rate_pct || 0) < 50 ? "incorrect" : "review-needed";
    const topWrongCopy = topWrong && Number(topWrong.selected_count || 0) > 0
      ? `${topWrong.choice}번 오답 ${formatPercent(topWrong.selected_pct || 0)}`
      : "공통 오답 없음";
    return `
      <article class="faculty-item-report">
        <span class="question-status ${statusClass}">${escapeHtml(formatPercent(row.correct_rate_pct || 0))}</span>
        <div>
          <strong>Q${escapeHtml(row.question_number || row.question_id || "-")}</strong>
          <p>${escapeHtml(facultyLabelSummary(row))}</p>
        </div>
        <p>${escapeHtml(row.stem_preview || "지문 요약 없음")}</p>
        <dl>
          <div><dt>풀이</dt><dd>${escapeHtml(row.attempt_count || 0)}</dd></div>
          <div><dt>정답</dt><dd>${escapeHtml(row.correct_count || 0)}</dd></div>
          <div><dt>평균 시간</dt><dd>${escapeHtml(formatDuration(row.avg_time_sec || 0))}</dd></div>
          <div><dt>최다 오답</dt><dd>${escapeHtml(topWrongCopy)}</dd></div>
        </dl>
        ${renderFacultyChoiceDistribution(row)}
      </article>
    `;
  }).join("");
}

async function loadFacultyPracticeAnalytics() {
  if (!facultyReportAnalytics) return;
  facultyReportAnalytics.innerHTML = `
    <div class="student-analytics-empty">
      <strong>문항별 리포트를 불러오는 중입니다.</strong>
      <p>학생 풀이 기록에서 정답률과 오답 선택지 분포를 계산하고 있습니다.</p>
    </div>
  `;
  try {
    const response = await fetch("/api/practice/analytics/faculty");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "교수 리포트 로드 실패");
    }
    renderFacultyPracticeAnalytics(payload);
  } catch (error) {
    facultyReportAnalytics.innerHTML = `
      <div class="student-analytics-empty error">
        <strong>교수 리포트를 불러오지 못했습니다.</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  }
}

const weaknessTargetingBtn = document.querySelector("#weaknessTargetingBtn");
const weaknessTargetingResult = document.querySelector("#weaknessTargetingResult");

async function runWeaknessTargeting() {
  if (!weaknessTargetingResult) return;
  weaknessTargetingResult.innerHTML = `
    <div class="student-analytics-empty">
      <strong>약점 영역을 분석하고 기출 부모를 찾는 중입니다.</strong>
      <p>정답률이 낮은 영역 → 같은 라벨의 기출 → 변형 생성 프롬프트를 준비합니다.</p>
    </div>`;
  try {
    const response = await fetch("/api/practice/weakness-targeting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_areas: 3, parents_per_area: 2, n_each: 1 }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "약점 보강 출제 준비 실패");
    if (!payload.weak_area_count) {
      weaknessTargetingResult.innerHTML = `
        <div class="student-analytics-empty">
          <strong>아직 보강 출제할 약점이 없습니다.</strong>
          <p>학생 풀이 기록이 쌓이면 정답률이 낮은 영역에 대한 보강 출제를 준비합니다.</p>
        </div>`;
      return;
    }
    const areas = payload.plan.map((area) => {
      const packets = area.packets.map((pk) => `
        <li>
          <strong>${escapeHtml(pk.parent_question_id || "")}</strong>
          <span class="muted"> ${escapeHtml(pk.stem_preview || "")}…</span>
          <em> → 변형 ${escapeHtml(String(pk.expected_variants))}개 (${escapeHtml((pk.variant_types || []).join(", "))})</em>
        </li>`).join("");
      return `
        <article class="weakness-area-card">
          <header><strong>${escapeHtml(area.label_path)}</strong>
          <span class="badge light">정답률 ${escapeHtml(String(area.correct_rate_pct))}% · ${escapeHtml(String(area.attempt_count))}회</span></header>
          <ul>${packets || "<li class='muted'>해당 라벨의 기출 부모를 찾지 못했습니다.</li>"}</ul>
        </article>`;
    }).join("");
    weaknessTargetingResult.innerHTML = `
      <p class="weakness-summary">약점 ${escapeHtml(String(payload.weak_area_count))}개 · 기출 부모 ${escapeHtml(String(payload.total_packets))}건 · 변형 생성 예정 <strong>${escapeHtml(String(payload.total_expected_variants))}개</strong> → 검토 큐(승인 후 의학교육실 HWP 제출)</p>
      ${areas}`;
  } catch (error) {
    weaknessTargetingResult.innerHTML = `
      <div class="student-analytics-empty error">
        <strong>약점 보강 출제 준비에 실패했습니다.</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>`;
  }
}

if (weaknessTargetingBtn) {
  weaknessTargetingBtn.addEventListener("click", async () => {
    weaknessTargetingBtn.disabled = true;
    const original = weaknessTargetingBtn.textContent;
    weaknessTargetingBtn.textContent = "준비 중";
    try {
      await runWeaknessTargeting();
    } finally {
      weaknessTargetingBtn.disabled = false;
      weaknessTargetingBtn.textContent = original;
    }
  });
}

function updateLivePracticeTime() {
  const node = document.querySelector("[data-practice-elapsed]");
  if (!node || !currentPracticeActiveQuestionKey) return;
  node.textContent = formatDuration(getPracticeTimeForQuestion(currentPracticeActiveQuestionKey));
  const status = document.querySelector("[data-practice-timer-status]");
  if (status) status.textContent = currentPracticeTimerPaused ? "일시정지" : "기록 중";
}

function startPracticeTimerInterval() {
  window.clearInterval(practiceTimerInterval);
  practiceTimerInterval = window.setInterval(updateLivePracticeTime, 1000);
}

function stopPracticeTimerInterval() {
  window.clearInterval(practiceTimerInterval);
  practiceTimerInterval = null;
}

function resetPracticeRuntimeState({ clearStored = false } = {}) {
  stopPracticeQuestionTimer();
  stopPracticeTimerInterval();
  if (clearStored) {
    const key = practiceStorageKey();
    if (key) {
      try {
        window.sessionStorage?.removeItem(key);
      } catch (error) {
        // Ignore storage cleanup failures.
      }
    }
  }
  currentPracticeExam = null;
  currentPracticeIndex = 0;
  currentPracticeAnswers = {};
  currentPracticePendingAnswers = {};
  currentPracticeAnswerEvents = {};
  currentPracticeTimeByQuestion = {};
  currentPracticeViewed = new Set();
  currentPracticeBookmarks = new Set();
  currentPracticeFlags = {};
  currentPracticeExpandedChoices = {};
  currentPracticeTab = "key";
  currentPracticeSidebarCollapsed = false;
  currentPracticeSessionId = null;
  practiceRagEvidenceCache = {};
  practiceRagAnkiCache = {};
  currentPracticeSessionStartedAt = null;
  currentPracticeTimerPaused = false;
}

function computePracticeSessionStats(questions) {
  const total = questions.length || 0;
  const answered = Object.values(currentPracticeAnswers).filter(practiceHasAnswerSelection).length;
  const correct = questions.filter((item, index) => {
    const key = practiceQuestionKey(item, index);
    return practiceSelectionIsCorrect(item, currentPracticeAnswers[key]);
  }).length;
  const timeValues = questions
    .map((item, index) => getPracticeTimeForQuestion(practiceQuestionKey(item, index)))
    .filter((value) => value > 0);
  const totalTime = timeValues.reduce((sum, value) => sum + value, 0);
  const avgTime = timeValues.length ? Math.round(totalTime / timeValues.length) : 0;
  const weakLabels = {};
  questions.forEach((item, index) => {
    const key = practiceQuestionKey(item, index);
    const selected = currentPracticeAnswers[key];
    if (!practiceHasAnswerSelection(selected) || practiceSelectionIsCorrect(item, selected)) return;
    const labels = item.labels || {};
    const conceptTags = Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
    const label = practiceLabelText(conceptTags[0] || labels.subtopic || labels.topic || labels.question_type || "미분류");
    weakLabels[label] = (weakLabels[label] || 0) + 1;
  });
  const weakSummary = Object.entries(weakLabels)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([label, count]) => `${label} ${count}문항`);
  return {
    total,
    viewed: currentPracticeViewed.size,
    answered,
    correct,
    accuracy: answered ? Math.round((correct / answered) * 100) : 0,
    avgTime,
    totalTime,
    bookmarked: currentPracticeBookmarks.size,
    flagged: Object.keys(currentPracticeFlags).length,
    weakSummary,
  };
}

function practiceSessionQuestionState(question, index) {
  const key = practiceQuestionKey(question, index);
  const selection = practiceNormalizeAnswerSelection(currentPracticeAnswers[key]);
  const answered = selection.length > 0;
  const correct = answered && practiceSelectionIsCorrect(question, selection);
  return {
    key,
    selection,
    answered,
    correct,
    wrong: answered && !correct,
    bookmarked: currentPracticeBookmarks.has(key),
    flagged: currentPracticeFlags[key] || "",
    time: getPracticeTimeForQuestion(key),
  };
}

function practiceSessionIsComplete(questions) {
  return Boolean(questions?.length)
    && questions.every((question, index) => practiceSessionQuestionState(question, index).answered);
}

function renderPracticeSessionSnapshot(questions) {
  const stats = computePracticeSessionStats(questions);
  const remaining = Math.max(0, stats.total - stats.answered);
  return `
    <section class="practice-session-snapshot" aria-label="세션 요약">
      <article><span>정답률</span><strong>${escapeHtml(stats.accuracy)}%</strong><small>${escapeHtml(stats.correct)} / ${escapeHtml(stats.answered || 0)} 풀이</small></article>
      <article><span>평균 시간</span><strong>${escapeHtml(formatDuration(stats.avgTime))}</strong><small>문항당 기록</small></article>
      <article><span>북마크</span><strong>${escapeHtml(stats.bookmarked)}</strong><small>다시 볼 문항</small></article>
      <article><span>남은 문항</span><strong>${escapeHtml(remaining)}</strong><small>세트 완료까지</small></article>
    </section>
  `;
}

function buildPracticeAnkiCandidatesForQuestion(question, index) {
  if (!question) return [];
  const answer = practicePrimaryAnswer(question);
  const labels = question.labels || {};
  const conceptTags = Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
  const explanationInfo = practiceExplanationInfo(question, answer, labels, conceptTags);
  const ragAnkiState = getPracticeRagAnkiState(question, labels, conceptTags);
  return buildPracticeAnkiCandidates({
    answer,
    conceptTags,
    explanationInfo,
    labels,
    question,
    ragAnkiState,
  }).map((card, cardIndex) => ({
    ...card,
    cardId: `${practiceQuestionKey(question, index)}_${card.cardId || cardIndex}`,
    questionIndex: index,
    questionNumber: question.question_number || index + 1,
  }));
}

function practiceAnkiCardsForIndexes(indexes) {
  const questions = currentPracticeExam?.questions || [];
  const seen = new Set();
  return indexes
    .map((index) => Number(index))
    .filter((index) => Number.isInteger(index) && index >= 0 && index < questions.length)
    .flatMap((index) => buildPracticeAnkiCandidatesForQuestion(questions[index], index))
    .filter((card) => {
      const text = String(card.ankiText || card.plainText || "").trim();
      const key = `${card.cardId}_${text}`;
      if (!text || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function practiceAnkiImportText(cards) {
  const rows = cards.map((card) => {
    const text = String(card.ankiText || card.plainText || "")
      .replace(/\t/g, " ")
      .replace(/\r?\n/g, "<br>")
      .trim();
    const tags = compactUniqueList([
      "paccine",
      "practice",
      currentPracticeExam?.summary?.course_id,
      currentPracticeExam?.summary?.course_name,
      `q${card.questionNumber || card.questionIndex + 1}`,
      ...(Array.isArray(card.tags) ? card.tags : []),
    ], 10)
      .map((tag) => String(tag || "").replace(/\s+/g, "_"))
      .filter(Boolean)
      .join(" ");
    return `${text}\t${tags}`;
  });
  return [
    "#separator:tab",
    "#html:true",
    "#notetype:Cloze",
    "#deck:P:accine::Practice",
    "#columns:Text\tTags",
    ...rows,
    "",
  ].join("\n");
}

function safeDownloadFilename(value) {
  return String(value || "paccine")
    .normalize("NFKC")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 80);
}

function downloadTextFile(filename, text, type = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

function practiceIndexesByResult(kind, questions = currentPracticeExam?.questions || []) {
  return questions
    .map((question, index) => ({ index, state: practiceSessionQuestionState(question, index) }))
    .filter(({ state }) => {
      if (kind === "wrong") return state.wrong;
      if (kind === "bookmarked") return state.bookmarked;
      if (kind === "unanswered") return !state.answered;
      return true;
    })
    .map(({ index }) => index);
}

function selectedPracticeCompletionIndexes() {
  return Array.from(document.querySelectorAll("[data-session-anki-select]:checked"))
    .map((input) => Number(input.value))
    .filter((index) => Number.isInteger(index));
}

function downloadPracticeAnkiCards(indexes, label = "selected") {
  const cards = practiceAnkiCardsForIndexes(indexes);
  if (!cards.length) {
    setStatus("선택한 문항에서 다운로드할 Anki 카드가 없습니다.");
    return;
  }
  const examName = safeDownloadFilename(examTitle(currentPracticeExam?.summary || {}) || "practice");
  const date = new Date().toISOString().slice(0, 10);
  downloadTextFile(
    `paccine_${examName}_${safeDownloadFilename(label)}_anki_${date}.txt`,
    practiceAnkiImportText(cards)
  );
  setStatus(`${cards.length}개 Anki 카드 텍스트를 다운로드했습니다.`, "muted");
}

function renderPracticeCompletionReport(questions) {
  const stats = computePracticeSessionStats(questions);
  const wrongIndexes = practiceIndexesByResult("wrong", questions);
  const bookmarkedIndexes = practiceIndexesByResult("bookmarked", questions);
  const unansweredIndexes = practiceIndexesByResult("unanswered", questions);
  const rows = questions.map((question, index) => {
    const state = practiceSessionQuestionState(question, index);
    const selectedLabel = practiceSelectionLabel(state.selection) || "-";
    const answerLabel = practiceAnswerLabel(question);
    const stem = String(question.stem || "문항 지문 미추출").trim();
    const statusText = state.correct ? "정답" : state.answered ? "오답" : "미응답";
    const statusClass = state.correct ? "correct" : state.answered ? "wrong" : "unanswered";
    return `
      <article class="completion-question-row ${statusClass}">
        <label class="completion-check">
          <input type="checkbox" data-session-anki-select value="${escapeHtml(index)}" checked />
          <span></span>
        </label>
        <span class="completion-status-dot" aria-hidden="true"></span>
        <button type="button" class="completion-question-main" data-practice-jump="${escapeHtml(index)}">
          <strong><b>Q${escapeHtml(question.question_number || index + 1)}</b>${escapeHtml(stem.slice(0, 88))}${stem.length > 88 ? "..." : ""}</strong>
          <small>${escapeHtml(statusText)}</small>
        </button>
        <div class="completion-question-meta">
          <span>${escapeHtml(selectedLabel)} 선택</span>
          <span>${escapeHtml(answerLabel)} 정답</span>
          <span>${escapeHtml(formatDuration(state.time))}</span>
        </div>
        <button
          type="button"
          class="completion-bookmark ${state.bookmarked ? "is-active" : ""}"
          data-session-bookmark-index="${escapeHtml(index)}"
        >
          ${state.bookmarked ? "북마크됨" : "북마크"}
        </button>
      </article>
    `;
  }).join("");

  const nextTitle = wrongIndexes.length
    ? `${wrongIndexes.length}개 오답부터 다시 확인하세요`
    : bookmarkedIndexes.length
      ? `${bookmarkedIndexes.length}개 북마크를 이어서 확인하세요`
      : "이번 세트를 모두 마쳤습니다";
  const nextDescription = wrongIndexes.length
    ? "오답 문항만 모아 다시 풀거나, 관련 Anki 카드를 한 번에 내려받을 수 있습니다."
    : "필요한 문항을 북마크하거나 Anki 카드로 내보내 다음 복습 세트에 활용하세요.";

  return `
    <section class="practice-completion-report migration-completion-report" aria-label="세트 완료 리포트">
      <div class="completion-report-head">
        <div class="completion-result-copy">
          <span>학습 세션 완료</span>
          <h3>${escapeHtml(stats.correct)}문항을 맞혔습니다</h3>
          <p>문항별 결과와 풀이 시간을 확인하고, 필요한 문항만 골라 다음 복습으로 이어가세요.</p>
        </div>
        <div class="completion-score-ring" style="--score: ${escapeHtml(Number(stats.accuracy) || 0)}" aria-label="정답률 ${escapeHtml(stats.accuracy)}퍼센트">
          <div><strong>${escapeHtml(stats.accuracy)}%</strong><span>정답률</span></div>
        </div>
      </div>
      <div class="completion-report-layout">
        <div class="completion-report-main">
          <div class="completion-score-grid">
            <article><span>정답</span><strong>${escapeHtml(stats.correct)} / ${escapeHtml(stats.total)}</strong></article>
            <article><span>총 풀이 시간</span><strong>${escapeHtml(formatDuration(stats.totalTime))}</strong></article>
            <article><span>문항당 평균</span><strong>${escapeHtml(formatDuration(stats.avgTime))}</strong></article>
            <article><span>북마크</span><strong>${escapeHtml(bookmarkedIndexes.length)}</strong></article>
          </div>
          <div class="completion-list-title">
            <div><span>문항별 결과</span><strong>${escapeHtml(stats.total)}문항</strong></div>
            <small>체크된 문항만 Anki 카드로 내보냅니다.</small>
          </div>
          <div class="completion-question-list">
            ${rows}
          </div>
        </div>
        <aside class="completion-review-rail" aria-label="다음 학습 추천">
          <span>다음 학습</span>
          <h4>${escapeHtml(nextTitle)}</h4>
          <p>${escapeHtml(nextDescription)}</p>
          <dl>
            <div><dt>오답</dt><dd>${escapeHtml(wrongIndexes.length)}</dd></div>
            <div><dt>미응답</dt><dd>${escapeHtml(unansweredIndexes.length)}</dd></div>
            <div><dt>북마크</dt><dd>${escapeHtml(bookmarkedIndexes.length)}</dd></div>
          </dl>
          <div class="completion-actions">
            <button type="button" data-session-result-action="review-wrong" ${wrongIndexes.length ? "" : "disabled"}>오답 다시 풀기</button>
            <button type="button" class="secondary-button" data-session-result-action="review-bookmarked" ${bookmarkedIndexes.length ? "" : "disabled"}>북마크 복습</button>
            <button type="button" class="secondary-button" data-session-anki-download="selected">선택 문항 Anki</button>
            <button type="button" class="text-button" data-session-anki-download="wrong" ${wrongIndexes.length ? "" : "disabled"}>오답 Anki 내려받기</button>
          </div>
        </aside>
      </div>
    </section>
  `;
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
        const answered = practiceHasAnswerSelection(currentPracticeAnswers[key]);
        const viewed = currentPracticeViewed.has(key);
        const active = index === currentPracticeIndex;
        return `
          <button
            type="button"
            class="${active ? "active" : ""} ${answered ? "answered" : ""} ${viewed ? "viewed" : ""}"
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

function renderPracticeQuestionPicker(questions) {
  if (!questions.length) return "";
  const answeredCount = Object.values(currentPracticeAnswers).filter(practiceHasAnswerSelection).length;
  const viewedCount = currentPracticeViewed.size;
  return `
    <details class="practice-picker">
      <summary>
        <span>문항 선택</span>
        <strong>원하는 문제부터 풀기</strong>
        <em>${escapeHtml(viewedCount)}개 열람 · ${escapeHtml(answeredCount)}개 풀이</em>
      </summary>
      <div class="practice-picker-grid">
        ${questions.map((item, index) => {
          const key = item.question_id || String(item.question_number || index);
          const labels = item.labels || {};
          const answered = practiceHasAnswerSelection(currentPracticeAnswers[key]);
          const viewed = currentPracticeViewed.has(key);
          const active = index === currentPracticeIndex;
          return `
            <button
              type="button"
              class="${active ? "active" : ""} ${answered ? "answered" : ""} ${viewed ? "viewed" : ""}"
              data-practice-jump="${escapeHtml(index)}"
            >
              <span>Q${escapeHtml(item.question_number || index + 1)}</span>
              <strong>${escapeHtml(practiceLabelText(labels.question_type || labels.cognitive_level) || "문항")}</strong>
              <small>${escapeHtml(item.stem || "문항 지문 미추출").slice(0, 46)}</small>
            </button>
          `;
        }).join("")}
      </div>
    </details>
  `;
}

function renderPracticeSessionSidebar(questions) {
  const summary = currentPracticeExam?.summary || {};
  const stats = computePracticeSessionStats(questions);
  return `
    <aside class="axioma-session-sidebar">
      <div class="axioma-session-summary">
        <span>문항 탐색</span>
        <strong>${escapeHtml(examTitle(summary) || "문항 세트")}</strong>
        <p>${escapeHtml(stats.viewed)} / ${escapeHtml(questions.length)} 열람 · ${escapeHtml(stats.answered)}개 풀이</p>
      </div>
      <div class="axioma-question-list" aria-label="문항 선택 목록">
        ${questions.map((item, index) => {
          const key = item.question_id || String(item.question_number || index);
          const selected = currentPracticeAnswers[key];
          const hasSelected = practiceHasAnswerSelection(selected);
          const isCorrect = hasSelected && practiceSelectionIsCorrect(item, selected);
          const isWrong = hasSelected && !practiceSelectionIsCorrect(item, selected);
          const viewed = currentPracticeViewed.has(key);
          const active = index === currentPracticeIndex;
          const correctRate = practiceQuestionCorrectRateLabel(item);
          const difficulty = practiceQuestionDifficultyLabel(item);
          const mediaCount = (item.media_refs || []).filter((media) => media?.url).length;
          const bookmarked = currentPracticeBookmarks.has(key);
          return `
            <button
              type="button"
              class="${active ? "active" : ""} ${viewed ? "viewed" : ""} ${hasSelected ? "answered" : ""}"
              data-practice-jump="${escapeHtml(index)}"
            >
              <span class="axioma-status ${isCorrect ? "correct" : isWrong ? "wrong" : viewed ? "viewed" : ""}">
                ${isCorrect ? "✓" : isWrong ? "×" : viewed ? "•" : ""}
              </span>
              <em>${escapeHtml(item.question_number || index + 1)}</em>
              <span class="axioma-question-copy">
                <strong>${escapeHtml(item.stem || "문항 지문 미추출").slice(0, 40)}</strong>
                ${mediaCount ? `<small><i>제시자료 ${escapeHtml(mediaCount)}개</i></small>` : ""}
              </span>
              <span class="axioma-question-metrics">
                ${bookmarked ? `<b class="is-bookmark" title="북마크됨">북마크</b>` : ""}
                ${correctRate ? `<b>${escapeHtml(correctRate)}</b>` : difficulty ? `<b>${escapeHtml(difficulty)}</b>` : ""}
              </span>
            </button>
          `;
        }).join("")}
      </div>
      <div class="axioma-session-footer">
        <div><strong>${escapeHtml(stats.accuracy)}%</strong><span>정답률</span></div>
        <div><strong>${escapeHtml(formatDuration(stats.avgTime))}</strong><span>평균 시간</span></div>
        <button type="button" data-practice-reset>세트 선택</button>
      </div>
    </aside>
  `;
}

function practiceQuestionDifficultyLabel(question) {
  const labels = question?.labels || {};
  const raw = labels.difficulty_labeled || labels.difficulty || question?.difficulty || "";
  const normalized = String(raw || "").trim().toLowerCase();
  const map = {
    easy: "쉬움",
    low: "쉬움",
    basic: "기본",
    normal: "보통",
    medium: "보통",
    moderate: "보통",
    hard: "어려움",
    high: "어려움",
    advanced: "심화",
  };
  if (map[normalized]) return map[normalized];
  return practiceLabelText(raw);
}

function normalizePercentLabel(value) {
  if (value === null || value === undefined || value === "") return "";
  const numeric = Number(String(value).replace("%", "").trim());
  if (!Number.isFinite(numeric)) return "";
  const percent = numeric > 0 && numeric <= 1 ? numeric * 100 : numeric;
  return `${Math.round(percent)}%`;
}

function practiceQuestionCorrectRateLabel(question) {
  const labels = question?.labels || {};
  const analytics = question?.analytics || question?.stats || {};
  const value = labels.correct_rate_pct
    ?? labels.correct_rate
    ?? labels.item_correct_rate_pct
    ?? labels.item_correct_rate
    ?? question?.correct_rate_pct
    ?? question?.correct_rate
    ?? analytics.correct_rate_pct
    ?? analytics.correct_rate;
  const label = normalizePercentLabel(value);
  return label ? `정답률 ${label}` : "";
}

function practiceQuestionSidebarMeta(question) {
  const labels = question?.labels || {};
  const topic = questionMajorTopicLabel(question);
  const type = practiceLabelText(labels.question_type_labeled || labels.question_type || labels.cognitive_level);
  const professor = practiceLabelText(labels.professor || labels.faculty || labels.instructor);
  return compactUniqueList([topic, type, professor], 2).join(" · ");
}

function practiceMediaTypeLabel(item) {
  const raw = String(item?.modality || item?.media_type || item?.type || "").toLowerCase();
  if (raw.includes("ct")) return "CT";
  if (raw.includes("mri")) return "MRI";
  if (raw.includes("xray") || raw.includes("x-ray") || raw.includes("radiograph") || raw.includes("cxr")) return "X-ray";
  if (raw.includes("ultrasound") || raw.includes("sono") || raw === "us") return "초음파";
  if (raw.includes("path") || raw.includes("slide")) return "병리";
  if (raw.includes("ecg") || raw.includes("ekg")) return "심전도";
  if (raw.includes("eeg")) return "뇌파";
  if (raw.includes("pbs") || raw.includes("smear")) return "말초혈액";
  if (raw.includes("photo")) return "사진";
  return "제시자료";
}

function practiceMediaDisplayCaption(item, index) {
  const raw = String(item?.caption || item?.description || item?.finding || "").trim();
  const looksLikeFilename = /\.(png|jpe?g|webp|bmp|gif|svg)$/i.test(raw) || /^PAGE\d+_IMG\d+/i.test(raw);
  if (raw && !looksLikeFilename && raw.length <= 72) return raw;
  return `제시자료 ${index + 1}`;
}

function practiceMediaProvenanceTitle(item) {
  const filename = item?.filename || item?.media_id || item?.storage_id || "";
  const confidence = normalizePercentLabel(item?.match_confidence);
  return compactUniqueList([filename, confidence ? `출처 매칭 ${confidence}` : ""], 2).join(" · ");
}

function renderPracticeLabValues(labValues) {
  const rows = (labValues || []).filter((row) => row && (row.item || row.name));
  if (!rows.length) return "";
  return `
    <div class="practice-lab-box">
      <div class="practice-lab-title">검사 결과</div>
      <table class="practice-lab-table">
        <tbody>
          ${rows.map((row) => {
            const item = String(row.item || row.name || "").trim();
            const ref = String(row.ref || "").trim();
            return `<tr><td class="lab-item">${escapeHtml(item)}</td><td class="lab-ref">${ref ? `참고치 ${escapeHtml(ref)}` : ""}</td></tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPracticeMedia(mediaRefs) {
  const media = (mediaRefs || []).filter((item) => item.url);
  if (!media.length) return "";
  return `
    <div class="practice-media-grid">
      ${media.map((item, index) => {
        const typeLabel = practiceMediaTypeLabel(item);
        const displayCaption = practiceMediaDisplayCaption(item, index);
        const lightboxCaption = compactUniqueList([displayCaption, typeLabel], 2).join(" · ");
        return `
        <figure class="practice-media-card">
          <img
            src="${escapeHtml(item.url)}"
            alt="${escapeHtml(displayCaption || "제시자료")}"
            data-lightbox-src="${escapeHtml(item.url)}"
            data-lightbox-caption="${escapeHtml(lightboxCaption || "제시자료")}"
          />
          <figcaption>
            <strong>${escapeHtml(displayCaption)}</strong>
            ${typeLabel ? `<span>${escapeHtml(typeLabel)}</span>` : ""}
          </figcaption>
        </figure>
      `;
      }).join("")}
    </div>
  `;
}

function renderPracticeToolTabs(activeTab) {
  const tabs = [
    ["key", "핵심 정보"],
    ["point", "출제 포인트"],
    ["media", "검사/자료"],
    ["note", "개념 노트"],
    ["anki", "Anki 카드"],
  ];
  return tabs
    .map(([key, label]) => `
      <button
        type="button"
        class="${activeTab === key ? "active" : ""}"
        data-practice-tab="${escapeHtml(key)}"
      >
        ${escapeHtml(label)}
      </button>
    `)
    .join("");
}

function renderPracticeTabPanel(context) {
  const {
    answer,
    answerPanel,
    conceptTags,
    explanationInfo,
    helperStatus,
    keyInfo,
    labels,
    question,
    revealAnswer,
    selectedAnswer,
    sourceTags,
  } = context;
  const conceptLabel = practiceLabelText(conceptTags[0] || labels.cognitive_level || labels.question_type) || "개념 매핑 필요";
  const correctChoice = practiceAnswerKeys(question)
    .map((key) => question?.choices?.[key])
    .filter(Boolean)
    .join(" / ") || "기준 개념";
  const mediaCount = (question?.media_refs || []).filter((item) => item.url).length;
  const stimulus = String(question?.stimulus || "").trim();
  const stimulusIsPlaceholder = isPlaceholderStimulus(stimulus);
  const sourceBlock = sourceTags || '<span class="provenance-chip">출처 확인 필요</span>';
  const ragEvidenceState = ["point", "note"].includes(currentPracticeTab)
    ? getPracticeRagEvidenceState(question, labels, conceptTags)
    : null;
  const ragAnkiState = currentPracticeTab === "anki"
    ? getPracticeRagAnkiState(question, labels, conceptTags)
    : null;

  if (currentPracticeTab === "point") {
    return `
      <section class="practice-tool-panel point-panel">
        <div class="tool-panel-kicker">출제 포인트</div>
        <h3>${escapeHtml(conceptLabel)}</h3>
        <div class="practice-insight-grid">
          <article>
            <span>묻는 능력</span>
            <strong>${escapeHtml(practiceLabelText(labels.question_type || labels.cognitive_level) || "문항 유형")}</strong>
            <p>지문에서 핵심 단서를 찾고, 각 선지의 개념을 같은 기준으로 판단하는 능력을 확인합니다.</p>
          </article>
          <article>
            <span>기준 개념</span>
            <strong>${escapeHtml(practiceAnswerLabel(question))}번</strong>
            <p>${escapeHtml(correctChoice)}</p>
          </article>
          <article>
            <span>해설 상태</span>
            <strong>${explanationInfo.supplemental ? "선지 비교 중심" : "원해설 연결"}</strong>
            <p>${explanationInfo.supplemental ? "각 선지가 어떤 개념을 가리키는지 먼저 설명합니다." : "정답지 해설과 근거 DB를 함께 연결합니다."}</p>
          </article>
        </div>
        <div class="point-checklist">
          <span>풀이 순서</span>
          <ol>
            <li>질문이 묻는 평가 항목을 먼저 확인합니다.</li>
            <li>지문·제시자료에서 결정 단서를 찾습니다.</li>
            <li>각 선지의 개념이 그 기준에 맞는지 확인합니다.</li>
          </ol>
        </div>
        ${renderPracticeRagEvidence(ragEvidenceState, { compact: true })}
      </section>
    `;
  }

  if (currentPracticeTab === "media") {
    return `
      <section class="practice-tool-panel media-panel">
        <div class="tool-panel-kicker">검사/자료</div>
        <h3>제시자료 ${escapeHtml(mediaCount)}개 · 추가 지문 ${stimulus && !stimulusIsPlaceholder ? "있음" : "없음"}</h3>
        ${stimulus && !stimulusIsPlaceholder ? `<blockquote class="practice-stimulus">${escapeHtml(stimulus)}</blockquote>` : '<p class="muted">이 문항에는 별도 제시문이 저장되어 있지 않습니다.</p>'}
        ${renderPracticeMedia(question.media_refs || []) || (stimulusIsPlaceholder
          ? '<p class="muted">원본 문항에는 그림 표시가 있으나, 아직 해당 이미지 파일이 문항과 연결되지 않았습니다. 이미지 인덱싱 시 이 영역에 제시자료가 표시됩니다.</p>'
          : '<p class="muted">연결된 이미지/검사자료가 없습니다. 추후 자료 DB와 매핑하면 이 영역에 X-ray, CT, ECG, 병리 이미지가 표시됩니다.</p>'
        )}
        <div class="source-stack"><span>문항 출처</span><div>${sourceBlock}</div></div>
      </section>
    `;
  }

  if (currentPracticeTab === "note") {
    const conceptChips = (conceptTags.length ? conceptTags : [conceptLabel])
      .map((tag) => `<span class="provenance-chip">${escapeHtml(practiceLabelText(tag))}</span>`)
      .join("");
    const sourceTitle = currentPracticeExam?.summary?.course_name || question?.source_exam || "학교 기출/강의자료";
    return `
      <section class="practice-tool-panel note-panel">
        <div class="tool-panel-kicker">개념 노트</div>
        <h3>${escapeHtml(conceptLabel)}</h3>
        <p>이 문항은 ${escapeHtml(sourceTitle)}에서 추출된 개념 노드로 저장됩니다. 같은 태그의 기출, 강의록 페이지, 오답률 데이터를 묶으면 파트별 랜덤 풀이와 교수 리포트의 기준이 됩니다.</p>
        <div class="source-stack"><span>연결 태그</span><div>${conceptChips}</div></div>
        <div class="source-stack"><span>근거 자료</span><div>${sourceBlock}</div></div>
        ${renderPracticeRagEvidence(ragEvidenceState)}
        <div class="concept-note-actions">
          <button type="button" class="secondary-button compact-action" data-page-link="student-library">관련 세트 보기</button>
          <button type="button" class="secondary-button compact-action" data-practice-bookmark>북마크에 추가</button>
        </div>
      </section>
    `;
  }

  if (currentPracticeTab === "anki") {
    const ankiCandidates = buildPracticeAnkiCandidates({
      answer,
      conceptTags,
      explanationInfo,
      labels,
      question,
      ragAnkiState,
    });
    return `
      <section class="practice-tool-panel anki-panel">
        <div class="tool-panel-kicker">Anki 카드</div>
        <h3>핵심 문장 기반 cloze 카드</h3>
        <p>정답 근거와 연결 근거에서 자연스러운 개념 문장을 뽑고, 외워야 할 키워드만 빈칸 처리합니다.</p>
        ${renderPracticeAnkiCandidatePreview(ankiCandidates, ragAnkiState)}
        <div class="anki-action-row">
          <button type="button" class="compact-action" data-anki-dialog-open>관련 카드 찾기</button>
          <button type="button" class="secondary-button compact-action" data-practice-bookmark>카드 후보로 저장</button>
        </div>
      </section>
    `;
  }

  return `
    <section class="axioma-key-info">
      <span class="axioma-avatar">P</span>
      <div>
        <small>${escapeHtml(helperStatus)}</small>
        <p>${escapeHtml(keyInfo)}</p>
      </div>
    </section>
    ${selectedAnswer && revealAnswer ? answerPanel : ""}
  `;
}

function capturePracticeScrollState({ includeQuestionPane = false } = {}) {
  return {
    sidebarScrollTop: document.querySelector(".axioma-question-list")?.scrollTop ?? null,
    questionPaneScrollTop: includeQuestionPane ? document.querySelector(".axioma-question-pane")?.scrollTop ?? null : null,
  };
}

function restorePracticeScrollState(scrollState, { restoreSidebar = true, restoreQuestionPane = false } = {}) {
  if (!scrollState) return;
  window.requestAnimationFrame(() => {
    const sidebar = document.querySelector(".axioma-question-list");
    if (restoreSidebar && sidebar && scrollState.sidebarScrollTop !== null) {
      sidebar.scrollTop = scrollState.sidebarScrollTop;
    }

    const questionPane = document.querySelector(".axioma-question-pane");
    if (restoreQuestionPane && questionPane && scrollState.questionPaneScrollTop !== null) {
      questionPane.scrollTop = scrollState.questionPaneScrollTop;
    }
  });
}

function renderStudentPracticeQuestion(options = {}) {
  if (!studentPracticeStage) return;
  const {
    preserveSidebarScroll = true,
    preserveQuestionScroll = false,
  } = options;
  const scrollState = capturePracticeScrollState({
    includeQuestionPane: preserveQuestionScroll,
  });
  studentPracticeStage.className = "practice-layout axioma-layout";
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

  const questionKey = practiceQuestionKey(question, currentPracticeIndex);
  currentPracticeViewed.add(questionKey);
  const confirmedSelection = practiceNormalizeAnswerSelection(currentPracticeAnswers[questionKey]);
  const pendingSelection = practiceNormalizeAnswerSelection(currentPracticePendingAnswers[questionKey]);
  const hasConfirmedAnswer = confirmedSelection.length > 0;
  const isMultiAnswer = practiceIsMultiAnswerQuestion(question);
  const activeSelection = hasConfirmedAnswer ? confirmedSelection : pendingSelection;
  const selectedAnswer = practiceSelectionLabel(confirmedSelection);
  const pendingAnswer = practiceSelectionLabel(pendingSelection);
  if (hasConfirmedAnswer) {
    if (currentPracticeActiveQuestionKey === questionKey) stopPracticeQuestionTimer();
  } else {
    beginPracticeQuestionTimer(questionKey);
  }
  savePracticeState();
  startPracticeTimerInterval();
  const answer = practicePrimaryAnswer(question);
  const answerKeys = practiceAnswerKeys(question);
  const answerLabel = practiceAnswerLabel(question);
  const selectedIsCorrect = hasConfirmedAnswer ? practiceSelectionIsCorrect(question, confirmedSelection) : false;
  const expandedChoice = currentPracticeExpandedChoices[questionKey] || activeSelection[0] || answer;
  const revealAnswer = hasConfirmedAnswer && (studentPracticeMode?.value || "study") === "study";
  const correctCount = questions.filter((item, index) => {
    const key = item.question_id || String(item.question_number || index);
    return practiceSelectionIsCorrect(item, currentPracticeAnswers[key]);
  }).length;
  const answeredCount = Object.values(currentPracticeAnswers).filter(practiceHasAnswerSelection).length;
  const viewedCount = currentPracticeViewed.size;

  const labels = question.labels || {};
  const conceptTags = Array.isArray(labels.concept_tags) ? labels.concept_tags : [];
  const sourceTags = practiceSourceTags(question);
  const stimulusText = String(question.stimulus || "").trim();
  const stimulusIsPlaceholder = isPlaceholderStimulus(stimulusText);
  const hasVisibleMedia = (question.media_refs || []).some((item) => item.url);
  const explanationInfo = practiceExplanationInfo(question, answer, labels, conceptTags);
  const isBookmarked = currentPracticeBookmarks.has(questionKey);
  const elapsedLabel = formatDuration(getPracticeTimeForQuestion(questionKey));
  const timerButtonLabel = hasConfirmedAnswer
    ? "기록 완료"
    : currentPracticeTimerPaused ? "시간 재개" : "일시정지";
  const timerStatusLabel = hasConfirmedAnswer
    ? "기록 완료"
    : currentPracticeTimerPaused ? "일시정지" : "기록 중";
  const helperStatus = hasConfirmedAnswer
    ? revealAnswer
      ? selectedIsCorrect ? "정답입니다." : `오답입니다. 정답은 ${answerLabel}번입니다.`
      : "선택이 저장됐습니다. 시험 모드에서는 마지막에 해설을 확인합니다."
    : isMultiAnswer && pendingSelection.length
      ? `${pendingAnswer}번 선택 중입니다. 정답 확인을 눌러 채점하세요.`
    : "풀이 후 정답과 근거를 확인할 수 있습니다.";
  const answerPanel = hasConfirmedAnswer
    ? `
      <section class="axioma-explanation-card ${revealAnswer && selectedIsCorrect ? "correct" : revealAnswer ? "incorrect" : ""}">
        <span>${revealAnswer ? selectedIsCorrect ? "정답" : "오답" : "선택 저장"}</span>
        <strong>${revealAnswer ? selectedIsCorrect ? `${escapeHtml(answerLabel)}번` : `정답 ${escapeHtml(answerLabel)}번` : `${escapeHtml(selectedAnswer)}번 선택됨`}</strong>
        ${revealAnswer
          ? `
            ${explanationInfo.text ? `<p>${escapeHtml(explanationInfo.text)}</p>` : ""}
            ${renderQuestionCitations(question)}
            ${renderTextbookEvidenceLinks(question, labels, conceptTags)}
          `
          : "<p>시험 모드에서는 세션 종료 후 해설을 확인하도록 설계할 수 있습니다.</p>"
        }
      </section>
    `
    : `
      <section class="axioma-explanation-card pending">
        <span>학습 패널</span>
        <strong>풀이 후 근거를 확인합니다.</strong>
        <p>정답, 해설, 출제 포인트, 복습 카드 초안을 한 화면에 모읍니다.</p>
      </section>
    `;
  const keyInfo = selectedAnswer
    ? explanationInfo.text || "선지를 눌러 정답 근거와 오답 배제를 확인하세요."
    : "풀이 후 정답 근거와 출제 포인트가 표시됩니다.";
  const choiceExplanationDraft = revealAnswer
    ? getPracticeChoiceExplanationState(question, answer, explanationInfo, labels, conceptTags).rows
    : {};
  const choiceRows = practiceChoiceEntries(question)
    .map(([key, text]) => {
      const normalizedKey = normalizePracticeChoiceKey(key);
      const isSelected = activeSelection.includes(normalizedKey);
      const isPendingSelected = !hasConfirmedAnswer && isSelected;
      const isCorrect = revealAnswer && answerKeys.includes(normalizedKey);
      const isWrong = revealAnswer && answerKeys.length && !answerKeys.includes(normalizedKey);
      const className = [
        isSelected ? "selected" : "",
        isPendingSelected ? "pending-selected" : "",
        isCorrect ? "correct" : "",
        isWrong && isSelected ? "incorrect selected-wrong" : "",
        isWrong && !isSelected ? "review-wrong" : "",
        revealAnswer && expandedChoice === normalizedKey ? "expanded" : "",
      ].filter(Boolean).join(" ");
      const choiceExplanation = revealAnswer
        ? explanationForVisibleChoice(question, answer, normalizedKey, choiceExplanationDraft)
        : null;
      const shouldShowChoiceExplanation = revealAnswer
        && choiceExplanation
        && (
          normalizedKey === expandedChoice
          || confirmedSelection.includes(normalizedKey)
          || answerKeys.includes(normalizedKey)
        );
      return `
        <button type="button" class="axioma-choice ${className}" data-practice-choice="${escapeHtml(normalizedKey)}">
          <span>${escapeHtml(normalizedKey)}</span>
          <strong>${escapeHtml(text)}</strong>
          <em>${isCorrect ? "정답" : isWrong && isSelected ? "내 선택" : isPendingSelected ? "선택됨" : revealAnswer ? "오답" : ""}</em>
        </button>
        ${shouldShowChoiceExplanation ? renderPracticeChoiceExplanation(normalizedKey, choiceExplanation, sourceTags) : ""}
      `;
    })
    .join("");
  const multiAnswerConfirmPanel = isMultiAnswer && !hasConfirmedAnswer
    ? `
      <section class="practice-answer-confirm-row">
        <div>
          <strong>복수정답 문항</strong>
          <p>${pendingSelection.length ? `${escapeHtml(pendingAnswer)}번 선택 중` : "정답이라고 생각하는 선지를 모두 선택하세요."}</p>
        </div>
        <button
          type="button"
          data-practice-confirm-answer
          ${pendingSelection.length ? "" : "disabled"}
        >
          정답 확인
        </button>
      </section>
    `
    : "";

  studentPracticeStage.innerHTML = `
    <section class="axioma-practice-shell ${currentPracticeSidebarCollapsed ? "sidebar-collapsed" : ""}">
      <header class="axioma-topbar">
        <button
          type="button"
          class="axioma-menu-button"
          data-practice-sidebar-toggle
          aria-expanded="${currentPracticeSidebarCollapsed ? "false" : "true"}"
          aria-label="${currentPracticeSidebarCollapsed ? "문항 목록 열기" : "문항 목록 닫기"}"
        >
          ${currentPracticeSidebarCollapsed ? "문항 열기" : "문항 닫기"}
        </button>
        <div class="axioma-search">
          <span>${escapeHtml(currentPracticeExam?.summary?.course_name || currentPracticeExam?.exam?.title || "P:accine Library")}</span>
          <kbd>${escapeHtml(answeredCount)}/${escapeHtml(questions.length)} 풀이</kbd>
        </div>
        <div class="axioma-user">
          <span>Y</span>
          <div><strong>Yunseong</strong><small>PNU Medicine</small></div>
        </div>
      </header>
      <button type="button" class="axioma-sidebar-rail" data-practice-sidebar-toggle>문항 목록 열기</button>

      <div class="axioma-session-body">
        ${renderPracticeSessionSidebar(questions)}
        <main class="axioma-question-pane">
          <div class="axioma-reader-toolbar">
            <div class="reader-title-group">
              <span>문항 ${escapeHtml(currentPracticeIndex + 1)}</span>
            </div>
            <strong>
              ${escapeHtml(viewedCount)} 열람 · ${escapeHtml(answeredCount)} 풀이 · ${escapeHtml(correctCount)} 정답 ·
              <span data-practice-elapsed>${escapeHtml(elapsedLabel)}</span>
              <em data-practice-timer-status>${escapeHtml(timerStatusLabel)}</em>
            </strong>
            <div class="reader-actions">
              <button
                type="button"
                class="secondary-button timer-toggle ${currentPracticeTimerPaused ? "is-active" : ""}"
                data-practice-timer-toggle
                ${hasConfirmedAnswer ? "disabled" : ""}
              >
                ${escapeHtml(timerButtonLabel)}
              </button>
              <button type="button" class="secondary-button ${isBookmarked ? "is-active" : ""}" data-practice-bookmark>
                ${isBookmarked ? "북마크됨" : "북마크"}
              </button>
              <button type="button" class="secondary-button" data-practice-reset>세트 변경</button>
            </div>
          </div>

          <article class="axioma-vignette-card">
            <p class="axioma-stem">${escapeHtml(question.stem || "문항 지문 미추출")}</p>
            ${renderPracticeLabValues(question.lab_values)}
            ${stimulusText && !stimulusIsPlaceholder ? `<blockquote class="practice-stimulus">${escapeHtml(stimulusText)}</blockquote>` : ""}
            ${stimulusIsPlaceholder && !hasVisibleMedia ? '<div class="practice-media-missing">원본 문항의 제시 이미지가 아직 문항과 연결되지 않았습니다.</div>' : ""}
            ${renderPracticeMedia(question.media_refs || [])}
          </article>

          <div class="axioma-choice-list">${choiceRows}</div>
          ${multiAnswerConfirmPanel}

          ${revealAnswer ? `
            <nav class="axioma-info-tabs" aria-label="문항 학습 도구">
              ${renderPracticeToolTabs(currentPracticeTab)}
            </nav>

            ${renderPracticeTabPanel({
              answer,
              answerPanel,
              conceptTags,
              explanationInfo,
              helperStatus,
              keyInfo,
              labels,
              question,
              revealAnswer,
              selectedAnswer,
              sourceTags,
            })}
          ` : ""}

          <section class="axioma-study-footer">
            ${practiceSessionIsComplete(questions)
              ? renderPracticeCompletionReport(questions)
              : renderPracticeSessionSnapshot(questions)
            }
          </section>
        </main>
      </div>

      <footer class="axioma-bottom-nav">
        <button type="button" class="secondary-button" data-practice-reset>세트 선택</button>
        <button type="button" class="secondary-button" data-practice-nav="prev" ${currentPracticeIndex <= 0 ? "disabled" : ""}>‹ 이전 문항</button>
        <button type="button" data-practice-nav="next" ${currentPracticeIndex >= questions.length - 1 ? "disabled" : ""}>다음 문항 ›</button>
      </footer>
    </section>
  `;
  restorePracticeScrollState(scrollState, {
    restoreSidebar: preserveSidebarScroll,
    restoreQuestionPane: preserveQuestionScroll,
  });
}

function currentPracticeAnkiCards() {
  const question = currentPracticeExam?.questions?.[currentPracticeIndex];
  if (!question) return [];
  return buildPracticeAnkiCandidatesForQuestion(question, currentPracticeIndex);
}

function selectedPracticeAnkiText() {
  return practiceAnkiDialogCards
    .filter((card) => practiceSelectedAnkiCardIds.has(card.cardId))
    .map((card) => practiceAnkiStyleText ? card.ankiText : card.plainText)
    .join("\n");
}

function renderAnkiCardDialogBody() {
  if (!ankiCardDialogBody) return;
  const selectedCount = practiceAnkiDialogCards
    .filter((card) => practiceSelectedAnkiCardIds.has(card.cardId))
    .length;
  ankiCardDialogBody.innerHTML = `
    <section class="anki-related-panel">
      <div class="anki-dialog-toolbar">
        <div>
          <h3>Relevant cards</h3>
          <p>문장 안에서 핵심 개념만 빈칸 처리한 카드 후보입니다.</p>
        </div>
        <label class="anki-style-switch">
          <span>Anki-style text</span>
          <input type="checkbox" data-anki-style-toggle ${practiceAnkiStyleText ? "checked" : ""} />
          <i></i>
        </label>
      </div>
      <div class="anki-candidate-list">
        ${practiceAnkiDialogCards.length ? practiceAnkiDialogCards.map((card) => {
          const selected = practiceSelectedAnkiCardIds.has(card.cardId);
          const text = practiceAnkiStyleText ? card.ankiText : card.plainText;
          return `
            <button
              type="button"
              class="anki-candidate-row ${selected ? "selected" : ""} ${card.needsReview ? "needs-review" : ""}"
              data-anki-card-toggle="${escapeHtml(card.cardId)}"
            >
              <span class="anki-check">${selected ? "✓" : ""}</span>
              <div>
                <p>${escapeHtml(text)}</p>
                <small>${escapeHtml(card.source || "출처 확인 필요")}${card.needsReview ? " · cloze 검토 필요" : ""}</small>
              </div>
            </button>
          `;
        }).join("") : `
          <div class="anki-empty-state">
            <strong>카드 후보 없음</strong>
            <p>현재 문항은 원해설이나 선지별 해설이 부족해 자동 카드 생성을 보류했습니다.</p>
          </div>
        `}
      </div>
      <footer class="anki-dialog-footer">
        <span>${escapeHtml(selectedCount)} cards selected</span>
        <button type="button" data-copy-anki-cards>Copy Anki text</button>
      </footer>
    </section>
  `;
}

function openPracticeAnkiDialog() {
  if (!ankiCardDialog || !ankiCardDialogBody) return;
  practiceAnkiDialogCards = currentPracticeAnkiCards();
  practiceSelectedAnkiCardIds = new Set(practiceAnkiDialogCards.map((card) => card.cardId));
  renderAnkiCardDialogBody();
  ankiCardDialog.showModal();
}

function commitPracticeAnswer(question, questionKey, selectionValue) {
  const selectedKeys = practiceNormalizeAnswerSelection(selectionValue);
  if (!question || !questionKey || !selectedKeys.length) return false;
  stopPracticeQuestionTimer();
  currentPracticeAnswers[questionKey] = practiceIsMultiAnswerQuestion(question)
    ? selectedKeys
    : selectedKeys[0];
  delete currentPracticePendingAnswers[questionKey];
  currentPracticeExpandedChoices[questionKey] = selectedKeys[0];
  const attemptEvent = buildPracticeAttemptEvent(question, questionKey, selectedKeys);
  currentPracticeAnswerEvents[questionKey] = attemptEvent;
  submitPracticeAttempt(attemptEvent).catch((error) => {
    console.warn("practice attempt sync failed", error);
  });
  savePracticeState();
  return true;
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
    const summary = payload.summary || {};
    const shuffle = Boolean(studentPracticeShuffle?.checked);
    const allQuestions = payload.questions || [];
    let questions = shuffle ? shuffleArray(allQuestions) : [...allQuestions];
    const countRaw = studentPracticeCount?.value || "all";
    let limited = false;
    if (countRaw !== "all") {
      const limit = Number(countRaw);
      if (Number.isFinite(limit) && limit > 0 && questions.length > limit) {
        // 부분 세트를 뽑을 땐 항상 무작위로 골라야 편향이 없다(랜덤 미체크여도 표본은 랜덤 추출).
        questions = (shuffle ? questions : shuffleArray(questions)).slice(0, limit);
        limited = true;
      }
    }
    const modifiedPayload = { ...payload, questions };
    const parts = [];
    if (limited) parts.push(`${allQuestions.length}문항 중 ${questions.length}문항을 뽑았습니다.`);
    if (shuffle) parts.push("순서는 랜덤입니다.");
    const statusSuffix = parts.length ? ` ${parts.join(" ")}` : "";
    activatePracticePayload(
      modifiedPayload,
      `${examTitle(summary)} 세트를 열었습니다. ${questions?.length || 0}문항을 풀 수 있습니다.${statusSuffix}`
    );
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
  syncSimpleImageSelection();
}

// ── 간단 생성 모드: 기존 이미지 썸네일 피커 (미디어 뱅크와 selectedMediaIds 공유) ──
function updateSimpleImageCount() {
  const el = document.querySelector("#simpleImageCount");
  if (el) el.textContent = `기존 이미지 ${selectedMediaIds.size}개 선택`;
}

function syncSimpleImageSelection() {
  document.querySelectorAll("#simpleImagePicker [data-simple-media-id]").forEach((btn) => {
    btn.classList.toggle("is-selected", selectedMediaIds.has(btn.dataset.simpleMediaId));
  });
  updateSimpleImageCount();
}

function renderSimpleImagePicker() {
  const grid = document.querySelector("#simpleImagePicker");
  if (!grid) return;
  if (!mediaAssets.length) {
    grid.className = "simple-image-grid empty";
    grid.textContent = "저장된 이미지가 없습니다. 위 '직접 업로드'로 새 이미지를 넣거나, 오른쪽 제시자료에서 먼저 저장하세요.";
    updateSimpleImageCount();
    return;
  }
  const query = (document.querySelector("#simpleImageSearch")?.value || "").trim().toLowerCase();
  const assets = mediaAssets.filter((asset) => !query || mediaMaterialText(asset).includes(query));
  if (!assets.length) {
    grid.className = "simple-image-grid empty";
    grid.textContent = "검색 결과가 없습니다.";
    return;
  }
  grid.className = "simple-image-grid";
  grid.innerHTML = assets
    .map((asset) => {
      const selected = selectedMediaIds.has(asset.asset_id) ? " is-selected" : "";
      const cap = asset.caption || asset.diagnosis || asset.original_name || asset.modality || "이미지";
      const tag = [asset.modality || asset.asset_type, asset.diagnosis].filter(Boolean).join(" · ");
      return `
        <button type="button" class="simple-image-thumb${selected}" data-simple-media-id="${escapeHtml(asset.asset_id)}" title="${escapeHtml(cap)}">
          <img src="${escapeHtml(asset.url)}" alt="${escapeHtml(cap)}" loading="lazy" />
          ${tag ? `<span class="simple-image-cap">${escapeHtml(tag)}</span>` : ""}
          <span class="simple-image-check" aria-hidden="true">✓</span>
        </button>`;
    })
    .join("");
  updateSimpleImageCount();
}

let archiveAllSets = [];
let archiveStatusMode = "all";
let archiveSelectedSetId = "";

function archiveStatusMeta(status) {
  const raw = String(status || "draft");
  if (raw.includes("approved")) return { label: "승인 완료", cls: "approved" };
  if (raw.includes("pending") || raw.includes("review")) return { label: "검토 대기", cls: "pending" };
  return { label: "초안", cls: "draft" };
}

function archiveMatchesStatus(set) {
  if (archiveStatusMode === "all") return true;
  const cls = archiveStatusMeta(set.review_status).cls;
  return archiveStatusMode === cls;
}

function renderArchiveSets(sets) {
  archiveAllSets = sets || [];
  renderFilteredArchiveSets();
}

function renderFilteredArchiveSets() {
  if (!archiveList) return;
  const query = (document.querySelector("#archiveSearch")?.value || "").trim().toLowerCase();
  const filtered = archiveAllSets.filter((set) => {
    if (!archiveMatchesStatus(set)) return false;
    if (!query) return true;
    const hay = `${set.source_name || ""} ${set.subject || ""} ${set.unit || ""} ${set.set_id || ""}`.toLowerCase();
    return hay.includes(query);
  });
  if (!archiveAllSets.length) {
    archiveList.className = "archive-empty";
    archiveList.textContent = "아직 아카이브된 문항 세트가 없습니다.";
    return;
  }
  if (!filtered.length) {
    archiveList.className = "archive-empty";
    archiveList.textContent = "조건에 맞는 문항 세트가 없습니다.";
    return;
  }
  archiveList.className = "archive-list";
  archiveList.innerHTML = filtered
    .map((set) => {
      const status = archiveStatusMeta(set.review_status);
      return `
      <article class="archive-card">
        <div class="archive-card-head">
          <div class="archive-card-title">
            <strong>${escapeHtml(set.source_name || set.set_id)}</strong>
            <span>${escapeHtml(set.subject || "-")} · ${escapeHtml(set.unit || "-")}</span>
          </div>
          <span class="archive-status-badge ${status.cls}">${escapeHtml(status.label)}</span>
        </div>
        <div class="archive-stats">
          <span><b>${escapeHtml(set.question_count || 0)}</b>문항</span>
          <span><b>${escapeHtml(set.image_question_count || 0)}</b>이미지</span>
          <span><b>${escapeHtml(set.needs_review_count || 0)}</b>확인 필요</span>
          <span><b>${escapeHtml(set.approved_count || 0)}</b>승인</span>
        </div>
        <div class="archive-actions">
          <button type="button" class="secondary-button" data-open-set="${escapeHtml(set.set_id)}">문항 열기</button>
          <button type="button" class="primary-button" data-export-cbt-docx="${escapeHtml(set.set_id)}">의학교육실 HWP(.docx)</button>
          <button type="button" class="secondary-button" data-export-cbt-hwp="${escapeHtml(set.set_id)}">CBT HWP</button>
          <button type="button" class="secondary-button" data-export-anki="${escapeHtml(set.set_id)}">Anki</button>
        </div>
      </article>
    `;
    })
    .join("");
}

function initArchiveControls() {
  const search = document.querySelector("#archiveSearch");
  search?.addEventListener("input", renderFilteredArchiveSets);
  const chips = Array.from(document.querySelectorAll("#archiveStatusFilter .archive-status-chip"));
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.toggle("active", c === chip));
      archiveStatusMode = chip.dataset.archiveStatus || "all";
      renderFilteredArchiveSets();
    });
  });
}

function renderCategoryGrid(container, mode) {
  if (!container) return;
  container.innerHTML = departmentCategories
    .map((category) => {
      const metric = categoryLearningMetrics[category.key] || { progress: 0, weakness: "학습 데이터 없음" };
      const facultyCopy = mode === "faculty" ? "보강 제안" : "취약 마커";
      const questionCount = mode === "student" ? Number(studentCategoryQuestionCounts[category.key] || 0) : null;
      const footCopy = mode === "student"
        ? (questionCount > 0 ? `Q ${questionCount} · ${metric.weakness}` : "라벨 준비중")
        : `${facultyCopy} · ${metric.weakness}`;
      return `
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
          ${mode === "student" ? `<span class="category-count-badge">${escapeHtml(questionCount)}문항</span>` : ""}
          <span class="category-progress" aria-label="${escapeHtml(category.title)} 진행도 ${escapeHtml(metric.progress)}%">
            <b style="width: ${escapeHtml(metric.progress)}%"></b>
          </span>
          <span class="category-foot">
            <em>${escapeHtml(metric.progress)}%</em>
            <i>${escapeHtml(footCopy)}</i>
          </span>
        </button>
      `;
    })
    .join("");
}

function selectCategory(categoryTitle, mode, categoryKey) {
  const subjectInput = form?.querySelector('input[name="subject"]');
  const unitInput = form?.querySelector('input[name="unit"]');
  if (subjectInput) subjectInput.value = categoryTitle;
  if (unitInput && !unitInput.value.trim()) unitInput.value = "미분류";
  if (mode === "student") {
    selectedLibraryCourseKey = categoryKey || selectedLibraryCourseKey;
    showPage("student-library");
    renderStudentLibraryCourseBuilder(selectedLibraryCourseKey);
    window.requestAnimationFrame(() => {
      studentCourseBuilder?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
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
    <p>생성 엔진 호출 없이 검토용 설계 자료와 추출 텍스트를 준비했습니다.</p>
    <ul class="choices">
      <li>프롬프트: ${escapeHtml(data.paths?.prompt)}</li>
      <li>추출 텍스트: ${escapeHtml(data.paths?.extracted_text)}</li>
      <li>출력 패킷: ${escapeHtml(data.paths?.output)}</li>
    </ul>
  `;
}

function renderItemQuality(item) {
  const quality = item?.item_quality || {};
  const flaws = Array.isArray(quality.flaws) ? quality.flaws : [];
  const hardFailures = Array.isArray(quality.hard_rule_failures) ? quality.hard_rule_failures : [];
  const cognitive = item?.cognitive_level || "";
  if (!flaws.length && !hardFailures.length && !cognitive) return "";
  return `
    <div class="quality-grid" aria-label="자동 품질 검사 결과">
      <span><b>${escapeHtml(flaws.length)}</b>형식 결함</span>
      <span><b>${escapeHtml(hardFailures.length)}</b>NBME 재검토</span>
      ${cognitive ? `<span><b>${escapeHtml(cognitive)}</b>인지수준</span>` : ""}
    </div>
    ${flaws.length ? `<p class="warning-banner">자동 QC: ${escapeHtml(flaws.join(", "))}</p>` : ""}
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
          ${renderItemQuality(item)}
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
      const blueprint = item.question_blueprint || {};
      const blueprintTarget = blueprint.target || {};
      const blueprintLabel = blueprintTarget.axis_type
        ? `${practiceLabelText(blueprintTarget.axis_type)} · 축 ${blueprintTarget.axis_ids?.length || 0}개`
        : "평가 축 미지정";
      const blueprintWarning = blueprint.status === "blocked"
        ? ` · ${blueprint.block_reasons?.join(", ") || "설계도 확인 필요"}`
        : "";
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
          ${blueprint.blueprint_id ? `<p class="policy-copy"><strong>문항 설계도:</strong> ${escapeHtml(blueprintLabel)}${escapeHtml(blueprintWarning)} · 의료 승인 전 초안</p>` : ""}
          ${renderItemQuality(item)}
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

// ── 근거 검토 (Evidence Review) ────────────────────────────────────
let evidenceReviewStatus = "draft";

async function loadEvidenceReview() {
  const listEl = document.querySelector("#evidenceReviewList");
  if (!listEl) return;
  listEl.textContent = "불러오는 중…";
  try {
    const response = await fetch(`/api/evidence/review?status=${encodeURIComponent(evidenceReviewStatus)}&limit=80`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "근거 목록 로드 실패");
    document.querySelectorAll("#evidenceStatusTabs [data-count]").forEach((el) => {
      el.textContent = data.counts?.[el.dataset.count] ?? 0;
    });
    renderEvidenceReviewList(data.items || [], data.total || 0);
  } catch (error) {
    listEl.className = "evidence-review-list";
    listEl.innerHTML = `<p class="inline-error">${escapeHtml(error.message)}</p>`;
  }
}

function renderEvidenceReviewList(items, total) {
  const listEl = document.querySelector("#evidenceReviewList");
  if (!listEl) return;
  if (!items.length) {
    listEl.className = "evidence-review-list empty";
    listEl.textContent = evidenceReviewStatus === "draft"
      ? "검토 대기 중인 근거가 없습니다."
      : "해당 상태의 문항이 없습니다.";
    return;
  }
  const typeLabel = { guideline: "가이드라인", review: "리뷰", rct: "RCT", meta: "메타분석" };
  listEl.className = "evidence-review-list";
  listEl.innerHTML = `${total > items.length ? `<p class="evidence-review-count">${items.length} / ${total}건 표시 (상위 80건)</p>` : ""}` +
    items.map((it) => {
      const ev = (it.evidence || [])[0];
      const tags = (it.concept_tags || []).slice(0, 4).map((t) => `<span class="ev-tag">${escapeHtml(String(t).replace(/_/g, " "))}</span>`).join("");
      const evHtml = ev
        ? `<a class="ev-cite" href="${escapeHtml(ev.url || "#")}" target="_blank" rel="noopener">
             <span class="ev-cite-type">${escapeHtml(typeLabel[ev.type] || ev.type || "근거")}</span>
             <strong>${escapeHtml(ev.title || "")}</strong>
             <small>${escapeHtml([ev.journal, ev.year].filter(Boolean).join(" · "))}${ev.matched_concept ? ` · 검색어: ${escapeHtml(ev.matched_concept)}` : ""}</small>
           </a>`
        : `<p class="ev-none">자동 매칭 실패${it.evidence_note ? ` — ${escapeHtml(it.evidence_note)}` : ""}</p>`;
      const actions = ev
        ? `<button type="button" class="ev-approve" data-ev-action="approve" data-ev-exam="${escapeHtml(it.exam_id)}" data-ev-qid="${escapeHtml(it.question_id)}">승인</button>
           <button type="button" class="ev-reject" data-ev-action="reject" data-ev-exam="${escapeHtml(it.exam_id)}" data-ev-qid="${escapeHtml(it.question_id)}">반려</button>`
        : `<button type="button" class="ev-reject" data-ev-action="reject" data-ev-exam="${escapeHtml(it.exam_id)}" data-ev-qid="${escapeHtml(it.question_id)}">근거 없음으로 확정</button>`;
      return `
        <article class="evidence-review-item" data-ev-row="${escapeHtml(it.question_id)}">
          <div class="ev-item-head">
            <span class="ev-src">${escapeHtml(it.source_name || it.exam_id)} · ${escapeHtml(String(it.question_number || ""))}번</span>
            <span class="ev-status ${escapeHtml(it.evidence_status)}">${escapeHtml(it.evidence_status)}</span>
          </div>
          <p class="ev-stem">${escapeHtml(it.stem)}…</p>
          <div class="ev-tags">${tags}</div>
          ${evHtml}
          <div class="ev-actions">${actions}</div>
        </article>`;
    }).join("");
}

document.querySelector("#evidenceStatusTabs")?.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-evidence-status]");
  if (!btn) return;
  document.querySelectorAll("#evidenceStatusTabs button").forEach((b) => b.classList.toggle("active", b === btn));
  evidenceReviewStatus = btn.dataset.evidenceStatus;
  loadEvidenceReview();
});

document.querySelector("#evidenceReloadButton")?.addEventListener("click", () => loadEvidenceReview());

document.querySelector("#evidenceReviewList")?.addEventListener("click", async (event) => {
  const btn = event.target.closest("[data-ev-action]");
  if (!btn) return;
  btn.disabled = true;
  try {
    const response = await fetch("/api/evidence/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exam_id: btn.dataset.evExam,
        question_id: btn.dataset.evQid,
        action: btn.dataset.evAction,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "업데이트 실패");
    document.querySelector(`[data-ev-row="${window.CSS.escape(btn.dataset.evQid)}"]`)?.remove();
    loadEvidenceReview();
  } catch (error) {
    btn.disabled = false;
    btn.textContent = "실패 · 다시";
  }
});

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

async function loadMediaAssets() {
  try {
    const response = await fetch("/api/media");
    if (!response.ok) throw new Error("media load failed");
    const payload = await response.json();
    mediaAssets = payload.assets || [];
    if (metricMedia) metricMedia.textContent = mediaAssets.length;
    renderMediaAssets(mediaAssets);
    renderSimpleImagePicker();
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

bindChange(includeImagesToggle, handleImageToggleChange);
bindChange(questionTypeSelect, syncImagePolicyWithQuestionType);
bindChange(questionTypeSelect, syncTargetAxisWithQuestionType);

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
    if (role === "student") {
      window.location.assign("/student-v2/home.html");
      return;
    }
    showPage("faculty-dashboard");
  });
});

document.addEventListener("click", (event) => {
  const categoryCard = event.target.closest("[data-category-title]");
  if (!categoryCard) return;
  selectCategory(
    categoryCard.dataset.categoryTitle,
    categoryCard.dataset.categoryMode,
    categoryCard.dataset.categoryKey
  );
});

studentCourseBuilder?.addEventListener("click", (event) => {
  // 챕터 펼치기/접기 (셰브런 전용)
  const majorToggle = event.target.closest("[data-library-major-toggle]");
  if (majorToggle) {
    majorToggle.closest(".library-unit-card")?.classList.toggle("is-open");
    return;
  }

  // 대분류 헤더 클릭 = 그 대분류 전체 담기(+펼치기)
  const majorSelect = event.target.closest("[data-library-major-select]");
  if (majorSelect) {
    const majorId = majorSelect.dataset.libraryMajorSelect;
    const nextSelected = !isLibraryMajorFullySelected(majorId);
    setLibraryMajorSelected(majorId, nextSelected);
    if (nextSelected) majorSelect.closest(".library-unit-card")?.classList.add("is-open");
    syncLibrarySelectionUI();
    return;
  }

  // 전체 선택/해제
  if (event.target.closest("[data-library-select-all]")) {
    toggleLibrarySelectAll();
    return;
  }

  // 선택 문항으로 세션 시작
  if (event.target.closest("[data-library-start-selection]")) {
    startStudentLibrarySelection();
    return;
  }

  // 과목 전체 풀기(즉시)
  const startButton = event.target.closest("[data-library-practice-start]");
  if (!startButton) return;
  startStudentLibraryPractice(
    startButton.dataset.libraryFilterId,
    startButton.dataset.libraryPracticeScope
  );
});

studentCourseBuilder?.addEventListener("change", (event) => {
  const topicBox = event.target.closest("[data-library-topic-check]");
  if (topicBox) {
    setLibraryTopicSelected(topicBox.dataset.libraryTopicCheck, topicBox.checked);
    syncLibrarySelectionUI();
    return;
  }
  const majorBox = event.target.closest("[data-library-major-check]");
  if (majorBox) {
    setLibraryMajorSelected(majorBox.dataset.libraryMajorCheck, majorBox.checked);
    syncLibrarySelectionUI();
  }
});

studentCourseBuilder?.addEventListener("input", (event) => {
  const search = event.target.closest(".library-search");
  if (search) filterLibraryTopics(search.value);
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
    const cbtHwpButton = event.target.closest("[data-export-cbt-hwp]");
    if (cbtHwpButton) {
      cbtHwpButton.disabled = true;
      const originalText = cbtHwpButton.textContent;
      cbtHwpButton.textContent = "생성 중";
      try {
        const response = await fetch(
          `/api/question-sets/${encodeURIComponent(cbtHwpButton.dataset.exportCbtHwp)}/export/cbt-hwp`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              include_unapproved: false,
              include_answers: true,
              include_explanations: true,
              include_references: true,
            }),
          }
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "CBT HWP 양식 생성 실패");
        }
        window.location.href = payload.download_url;
      } catch (error) {
        archiveList.insertAdjacentHTML(
          "afterbegin",
          `<p class="inline-error">CBT HWP 양식 생성 실패: ${escapeHtml(error.message)}</p>`
        );
      } finally {
        cbtHwpButton.disabled = false;
        cbtHwpButton.textContent = originalText;
      }
      return;
    }

    const cbtDocxButton = event.target.closest("[data-export-cbt-docx]");
    if (cbtDocxButton) {
      cbtDocxButton.disabled = true;
      const originalText = cbtDocxButton.textContent;
      cbtDocxButton.textContent = "생성 중";
      try {
        const response = await fetch(
          `/api/question-sets/${encodeURIComponent(cbtDocxButton.dataset.exportCbtDocx)}/export/cbt-docx`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              include_unapproved: false,
              include_explanations: true,
            }),
          }
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "의학교육실 HWP(.docx) 양식 생성 실패");
        }
        window.location.href = payload.download_url;
      } catch (error) {
        archiveList.insertAdjacentHTML(
          "afterbegin",
          `<p class="inline-error">의학교육실 HWP(.docx) 양식 생성 실패: ${escapeHtml(error.message)}</p>`
        );
      } finally {
        cbtDocxButton.disabled = false;
        cbtDocxButton.textContent = originalText;
      }
      return;
    }

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

  const sidebarToggle = event.target.closest("[data-practice-sidebar-toggle]");
  if (sidebarToggle) {
    currentPracticeSidebarCollapsed = !currentPracticeSidebarCollapsed;
    renderStudentPracticeQuestion();
    return;
  }

  const tabButton = event.target.closest("[data-practice-tab]");
  if (tabButton) {
    currentPracticeTab = tabButton.dataset.practiceTab || "key";
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const timerToggleButton = event.target.closest("[data-practice-timer-toggle]");
  if (timerToggleButton) {
    const question = currentPracticeExam?.questions?.[currentPracticeIndex];
    if (!question) return;
    const questionKey = practiceQuestionKey(question, currentPracticeIndex);
    if (currentPracticeTimerPaused) {
      resumePracticeQuestionTimer(questionKey);
    } else {
      pausePracticeQuestionTimer();
    }
    savePracticeState();
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const bookmarkButton = event.target.closest("[data-practice-bookmark]");
  if (bookmarkButton) {
    const question = currentPracticeExam?.questions?.[currentPracticeIndex];
    if (!question) return;
    const questionKey = practiceQuestionKey(question, currentPracticeIndex);
    if (currentPracticeBookmarks.has(questionKey)) {
      currentPracticeBookmarks.delete(questionKey);
    } else {
      currentPracticeBookmarks.add(questionKey);
    }
    savePracticeState();
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const indexedBookmarkButton = event.target.closest("[data-session-bookmark-index]");
  if (indexedBookmarkButton) {
    const index = Number(indexedBookmarkButton.dataset.sessionBookmarkIndex);
    const question = currentPracticeExam?.questions?.[index];
    if (!question || !Number.isInteger(index)) return;
    const questionKey = practiceQuestionKey(question, index);
    if (currentPracticeBookmarks.has(questionKey)) {
      currentPracticeBookmarks.delete(questionKey);
    } else {
      currentPracticeBookmarks.add(questionKey);
    }
    savePracticeState();
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const flagButton = event.target.closest("[data-practice-flag]");
  if (flagButton) {
    const question = currentPracticeExam?.questions?.[currentPracticeIndex];
    if (!question) return;
    const questionKey = practiceQuestionKey(question, currentPracticeIndex);
    const flagValue = flagButton.dataset.practiceFlag || "other";
    if (flagValue === "clear" || currentPracticeFlags[questionKey] === flagValue) {
      delete currentPracticeFlags[questionKey];
    } else {
      currentPracticeFlags[questionKey] = flagValue;
    }
    savePracticeState();
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const ankiDialogButton = event.target.closest("[data-anki-dialog-open]");
  if (ankiDialogButton) {
    openPracticeAnkiDialog();
    return;
  }

  const sessionAnkiButton = event.target.closest("[data-session-anki-download]");
  if (sessionAnkiButton) {
    const action = sessionAnkiButton.dataset.sessionAnkiDownload || "selected";
    const questions = currentPracticeExam?.questions || [];
    let indexes = selectedPracticeCompletionIndexes();
    if (action === "wrong") indexes = practiceIndexesByResult("wrong", questions);
    if (action === "bookmarked") indexes = practiceIndexesByResult("bookmarked", questions);
    if (action === "all") indexes = questions.map((_, index) => index);
    downloadPracticeAnkiCards(indexes, action);
    return;
  }

  const sessionResultButton = event.target.closest("[data-session-result-action]");
  if (sessionResultButton) {
    const action = sessionResultButton.dataset.sessionResultAction;
    const indexes = action === "review-bookmarked"
      ? practiceIndexesByResult("bookmarked")
      : practiceIndexesByResult("wrong");
    if (!indexes.length) {
      setStatus("복습할 문항이 없습니다.");
      return;
    }
    finalizePracticeQuestionTime();
    savePracticeState();
    currentPracticeIndex = indexes[0];
    currentPracticeTab = "key";
    renderStudentPracticeQuestion();
    return;
  }

  const pageLinkButton = event.target.closest("[data-page-link]");
  if (pageLinkButton) {
    showPage(pageLinkButton.dataset.pageLink);
    return;
  }

  const confirmAnswerButton = event.target.closest("[data-practice-confirm-answer]");
  if (confirmAnswerButton) {
    const question = currentPracticeExam?.questions?.[currentPracticeIndex];
    if (!question) return;
    const questionKey = practiceQuestionKey(question, currentPracticeIndex);
    const pendingSelection = practiceNormalizeAnswerSelection(currentPracticePendingAnswers[questionKey]);
    if (!pendingSelection.length) return;
    commitPracticeAnswer(question, questionKey, pendingSelection);
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const choiceButton = event.target.closest("[data-practice-choice]");
  if (choiceButton) {
    const question = currentPracticeExam?.questions?.[currentPracticeIndex];
    if (!question) return;
    const questionKey = practiceQuestionKey(question, currentPracticeIndex);
    const chosen = choiceButton.dataset.practiceChoice;
    const alreadyAnswered = practiceHasAnswerSelection(currentPracticeAnswers[questionKey]);
    if (alreadyAnswered && (studentPracticeMode?.value || "study") === "study") {
      currentPracticeExpandedChoices[questionKey] = chosen;
      savePracticeState();
      renderStudentPracticeQuestion({ preserveQuestionScroll: true });
      return;
    }
    if (practiceIsMultiAnswerQuestion(question)) {
      const pendingSelection = practiceNormalizeAnswerSelection(currentPracticePendingAnswers[questionKey]);
      const nextSelection = pendingSelection.includes(chosen)
        ? pendingSelection.filter((key) => key !== chosen)
        : [...pendingSelection, chosen];
      if (nextSelection.length) {
        currentPracticePendingAnswers[questionKey] = nextSelection;
      } else {
        delete currentPracticePendingAnswers[questionKey];
      }
      currentPracticeExpandedChoices[questionKey] = chosen;
      savePracticeState();
      renderStudentPracticeQuestion({ preserveQuestionScroll: true });
      return;
    }
    commitPracticeAnswer(question, questionKey, [chosen]);
    renderStudentPracticeQuestion({ preserveQuestionScroll: true });
    return;
  }

  const resetButton = event.target.closest("[data-practice-reset]");
  if (resetButton) {
    resetPracticeRuntimeState();
    document.body.classList.remove("practice-session-active");
    studentPracticePage?.classList.remove("practice-active");
    studentPracticeStage.className = "practice-layout";
    studentPracticeStage.innerHTML = `
      <article class="practice-question empty-practice">
        <p>기출/과정시험 세트를 선택하면 문항 목록이 열리고, 원하는 문제부터 풀 수 있습니다.</p>
      </article>
      <aside class="practice-helper">
        <h3>문항 선택형 학습</h3>
        <button type="button" class="secondary-button" data-page-link="student-review">풀이 기록 보기</button>
        <p>끝까지 풀지 않아도 문항별 정답/해설, 출제 포인트, 복습 카드 초안을 바로 확인할 수 있습니다.</p>
      </aside>
    `;
    if (studentPracticeStatus) {
      studentPracticeStatus.textContent = `${studentExamSelect?.options?.length || 0}개 문항 세트를 불러왔습니다. 세트를 열고 원하는 문항부터 선택할 수 있습니다.`;
    }
    return;
  }

  const navButton = event.target.closest("[data-practice-nav]");
  if (navButton) {
    finalizePracticeQuestionTime();
    savePracticeState();
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
    finalizePracticeQuestionTime();
    savePracticeState();
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

ankiCardDialogClose?.addEventListener("click", () => {
  ankiCardDialog?.close();
});

ankiCardDialog?.addEventListener("click", async (event) => {
  if (event.target === ankiCardDialog) {
    ankiCardDialog.close();
    return;
  }

  const toggle = event.target.closest("[data-anki-style-toggle]");
  if (toggle) {
    practiceAnkiStyleText = Boolean(toggle.checked);
    renderAnkiCardDialogBody();
    return;
  }

  const cardButton = event.target.closest("[data-anki-card-toggle]");
  if (cardButton) {
    const cardId = cardButton.dataset.ankiCardToggle;
    if (practiceSelectedAnkiCardIds.has(cardId)) {
      practiceSelectedAnkiCardIds.delete(cardId);
    } else {
      practiceSelectedAnkiCardIds.add(cardId);
    }
    renderAnkiCardDialogBody();
    return;
  }

  const copyButton = event.target.closest("[data-copy-anki-cards]");
  if (copyButton) {
    const text = selectedPracticeAnkiText();
    if (!text) return;
    const originalText = copyButton.textContent;
    try {
      await navigator.clipboard.writeText(text);
      copyButton.textContent = "Copied";
    } catch (error) {
      copyButton.textContent = "Copy failed";
    }
    window.setTimeout(() => {
      copyButton.textContent = originalText;
    }, 1300);
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
    results.textContent = "파일을 서버로 보내고 있습니다. 큰 PDF/HWP 문항 생성은 몇 분 걸릴 수 있습니다.";
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
    setProgressMessage((
      data.status === "generated"
        ? "문항 초안 생성이 완료됐습니다. 이제 문항 검토 화면에서 문제, 해설, 참고문헌을 확인하면 됩니다."
        : "현재 생성 엔진을 사용할 수 없어 검토용 설계 자료만 준비됐습니다. 연결 상태를 확인한 뒤 다시 시도해주세요."
    ) + ontologyGenerationSummary(data));
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

// ── 간단 생성 모드 배선: 기존 이미지 피커 토글 · 검색 · 직접 업로드 라벨 · 생성 제출 ──
document.querySelector("#simpleImagePicker")?.addEventListener("click", (event) => {
  const thumb = event.target.closest("[data-simple-media-id]");
  if (!thumb) return;
  const id = thumb.dataset.simpleMediaId;
  if (selectedMediaIds.has(id)) selectedMediaIds.delete(id);
  else selectedMediaIds.add(id);
  updateSelectedMediaInput();
  // 미디어 뱅크 체크박스도 동기화
  const bankBox = document.querySelector(`#mediaBank input[type="checkbox"][value="${CSS.escape(id)}"]`);
  if (bankBox) bankBox.checked = selectedMediaIds.has(id);
});

document.querySelector("#simpleImageSearch")?.addEventListener("input", () => {
  renderSimpleImagePicker();
});

document.querySelector("#simpleImageFiles")?.addEventListener("change", (event) => {
  const label = document.querySelector("#simpleImageFilesLabel");
  const count = event.target.files?.length || 0;
  if (label) label.textContent = count ? `${count}장 선택됨` : "새 이미지 선택 (여러 장 가능)";
});

const simpleGenerateForm = document.querySelector("#simpleGenerateForm");
const simpleGenerateButton = document.querySelector("#simpleGenerateButton");
if (simpleGenerateForm) {
  simpleGenerateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const topicInput = document.querySelector("#simpleTopic");
    const topic = (topicInput?.value || "").trim();
    if (!topic) {
      topicInput?.focus();
      return;
    }
    if (simpleGenerateButton) simpleGenerateButton.disabled = true;
    setStatus("생성 준비 중");
    if (results) {
      results.className = "results-empty";
      results.textContent = "주제로 문항을 생성하고 있습니다. 생성에는 몇 분 걸릴 수 있습니다.";
    }
    try {
      const payload = new FormData();
      payload.set("topic", topic);
      payload.set("subject", "General");
      payload.set("unit", topic.slice(0, 40));
      payload.set("num_questions", document.querySelector("#simpleNumQuestions")?.value || "5");
      payload.set("generation_profile", "fast");
      payload.set("difficulty", document.querySelector("#simpleDifficulty")?.value || "보통");
      const hasImages = selectedMediaIds.size > 0 || (document.querySelector("#simpleImageFiles")?.files?.length || 0) > 0;
      payload.set("question_type", hasImages ? "image_based" : "clinical_case");
      payload.set("image_policy", hasImages ? "clinical_visuals" : "none");
      payload.set("selected_media_ids", Array.from(selectedMediaIds).join(","));
      Array.from(document.querySelector("#simpleImageFiles")?.files || []).forEach((file) => {
        payload.append("image_files", file);
      });
      startProgressTimer(payload);
      if (results?.scrollIntoView) results.scrollIntoView({ behavior: "smooth", block: "start" });
      const response = await fetch("/api/generate", { method: "POST", body: payload });
      const contentType = response.headers.get("content-type") || "";
      const data = contentType.includes("application/json")
        ? await response.json()
        : { detail: await response.text() };
      if (!response.ok) throw new Error(data.detail || "생성 실패");
      setStatus(data.status === "generated" ? "생성 완료" : "프롬프트 준비");
      finishProgress();
      setProgressMessage((
        data.status === "generated"
          ? "문항 초안 생성이 완료됐습니다. 검토 화면에서 문제·해설·참고문헌을 확인하세요."
          : "현재 생성 엔진을 사용할 수 없어 검토용 설계 자료만 준비됐습니다. 연결 상태를 확인한 뒤 다시 시도해주세요."
      ) + ontologyGenerationSummary(data));
      if (metricQuestions) metricQuestions.textContent = data.question_count || 0;
      setReviewCount((data.sample || []).filter((item) => item.needs_review).length);
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
      setProgressMessage("생성 중 문제가 발생했습니다. 생성 개수를 2~3개로 줄여 다시 시도해보세요.");
      if (results) {
        results.className = "results-empty";
        results.textContent = `처리 실패: ${error.message}`;
      }
    } finally {
      clearProgressTimer();
      if (simpleGenerateButton) simpleGenerateButton.disabled = false;
    }
  });
}

function cpxData() {
  return window.CPX_OSCE_DATA || {
    STATION_SECONDS: 720,
    cases: [],
    studyGuides: {},
    diagnosticNotes: {},
    referenceLinks: {},
    caseReferenceMap: {},
    coachReply: {},
    treatmentPlanReply: {},
    studyFlowReply: {},
    diagnosisReply: {},
  };
}

function cpxEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function cpxLoadState() {
  try {
    const saved = JSON.parse(window.localStorage?.getItem(CPX_OSCE_STORAGE_KEY) || "{}");
    if (saved && typeof saved === "object") {
      cpxOsceState = {
        ...cpxOsceState,
        ...saved,
        checked: saved.checked && typeof saved.checked === "object" ? saved.checked : {},
        notes: saved.notes && typeof saved.notes === "object" ? saved.notes : {},
        coachMessages: saved.coachMessages && typeof saved.coachMessages === "object" ? saved.coachMessages : {},
      };
    }
  } catch (error) {
    cpxOsceState = { ...cpxOsceState };
  }
}

function cpxSaveState() {
  try {
    window.localStorage?.setItem(CPX_OSCE_STORAGE_KEY, JSON.stringify(cpxOsceState));
  } catch (error) {
    console.warn("CPX/OSCE 상태 저장 실패:", error);
  }
}

function cpxCases() {
  return Array.isArray(cpxData().cases) ? cpxData().cases : [];
}

function cpxCurrentCase() {
  const cases = cpxCases();
  return cases.find((item) => item.id === cpxOsceState.selectedCaseId) || cases[0] || null;
}

function cpxCaseKindLabel(caseItem) {
  return caseItem?.category === "OSCE" ? "OSCE 술기" : "CPX 케이스";
}

function cpxCaseCategory(caseItem) {
  return caseItem?.category || cpxCaseKindLabel(caseItem);
}

function cpxCaseTitle(caseItem) {
  if (!caseItem) return "실전 스테이션";
  if (caseItem.title) return caseItem.title;
  const presentation = caseItem.presentation || cpxCaseKindLabel(caseItem);
  const diagnosis = caseItem.diagnosis ? ` · ${caseItem.diagnosis}` : "";
  return `${presentation}${diagnosis}`;
}

function cpxCaseSections(caseItem) {
  return Array.isArray(caseItem?.sections) ? caseItem.sections : [];
}

function cpxChecklistKey(caseId, sectionId, index) {
  return `${caseId}::${sectionId}::${index}`;
}

function cpxIsChecked(caseId, sectionId, index) {
  return Boolean(cpxOsceState.checked[cpxChecklistKey(caseId, sectionId, index)]);
}

function cpxScore(caseItem) {
  const sections = cpxCaseSections(caseItem);
  let total = 0;
  let done = 0;
  let criticalTotal = 0;
  const missedCritical = [];
  const bySection = sections.map((section) => {
    const items = Array.isArray(section.items) ? section.items : [];
    let sectionDone = 0;
    items.forEach((item, index) => {
      total += 1;
      const checked = cpxIsChecked(caseItem.id, section.id, index);
      if (checked) {
        done += 1;
        sectionDone += 1;
      }
      if (item.critical) {
        criticalTotal += 1;
        if (!checked) missedCritical.push({ sectionTitle: section.title, text: item.text });
      }
    });
    return {
      id: section.id,
      title: section.title,
      done: sectionDone,
      total: items.length,
      percent: items.length ? Math.round((sectionDone / items.length) * 100) : 0,
    };
  });
  return {
    total,
    done,
    percent: total ? Math.round((done / total) * 100) : 0,
    criticalTotal,
    missedCritical,
    bySection,
  };
}

function cpxFilteredCases() {
  const query = cpxOsceState.query.trim().toLowerCase();
  return cpxCases().filter((caseItem) => {
    const kindLabel = cpxCaseKindLabel(caseItem);
    const categoryMatch = cpxOsceState.category === "전체" || cpxCaseCategory(caseItem) === cpxOsceState.category || kindLabel === cpxOsceState.category;
    const haystack = [
      cpxCaseTitle(caseItem),
      caseItem.presentation,
      caseItem.diagnosis,
      caseItem.category,
      kindLabel,
      ...(caseItem.mustNotMiss || []),
    ].join(" ").toLowerCase();
    return categoryMatch && (!query || haystack.includes(query));
  });
}

function cpxCategories() {
  const labels = new Set(["전체", "CPX 케이스", "OSCE 술기"]);
  cpxCases().forEach((caseItem) => {
    const category = cpxCaseCategory(caseItem);
    if (category !== "OSCE") labels.add(category);
  });
  return Array.from(labels);
}

function initCpxOsceModule() {
  if (!cpxOsceModule) return;
  cpxLoadState();
  if (!CPX_OSCE_TABS.has(cpxOsceState.activeTab)) {
    cpxOsceState.activeTab = "study";
  }
  const firstCase = cpxCases()[0];
  if (!cpxOsceState.selectedCaseId && firstCase) {
    cpxOsceState.selectedCaseId = firstCase.id;
  }
  if (!cpxOsceState.timerCaseId && firstCase) {
    cpxOsceState.timerCaseId = cpxOsceState.selectedCaseId;
  }
  cpxSyncTimerInterval();
}

function formatStationTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function cpxTimerSeconds(caseItem) {
  const base = Number(cpxData().STATION_SECONDS) || 720;
  if (!caseItem) return base;
  if (cpxOsceState.timerCaseId !== caseItem.id) return base;
  return Math.max(0, Number(cpxOsceState.timerRemaining) || base);
}

function cpxSyncTimerInterval() {
  if (cpxOsceTimerInterval) {
    window.clearInterval(cpxOsceTimerInterval);
    cpxOsceTimerInterval = null;
  }
  if (!cpxOsceState.timerRunning) return;
  cpxOsceTimerInterval = window.setInterval(() => {
    cpxOsceState.timerRemaining = Math.max(0, (Number(cpxOsceState.timerRemaining) || 0) - 1);
    if (cpxOsceState.timerRemaining <= 0) {
      cpxOsceState.timerRunning = false;
      window.clearInterval(cpxOsceTimerInterval);
      cpxOsceTimerInterval = null;
    }
    const timerValue = document.querySelector("#cpxTimerValue");
    const timerShell = document.querySelector("#cpxStationTimer");
    if (timerValue) timerValue.textContent = formatStationTime(cpxOsceState.timerRemaining);
    timerShell?.classList.toggle("is-running", cpxOsceState.timerRunning);
    cpxSaveState();
  }, 1000);
}

function renderCpxOsceModule() {
  if (!cpxOsceModule) return;
  const data = cpxData();
  if (!data.cases?.length) {
    cpxOsceModule.innerHTML = `<div class="results-empty">CPX/OSCE 케이스 데이터를 불러오지 못했습니다.</div>`;
    return;
  }
  const current = cpxCurrentCase();
  const categories = cpxCategories();
  cpxOsceModule.innerHTML = `
    <div class="cpx-shell">
      <aside class="cpx-case-panel">
        <div class="cpx-panel-head">
          <div>
            <p class="section-label">CPX/OSCE Station</p>
            <h2>케이스 선택</h2>
          </div>
          <button type="button" class="secondary-button" data-cpx-action="random-case">랜덤</button>
        </div>
        <div class="cpx-filter-stack">
          <input type="search" id="cpxCaseSearch" value="${cpxEscape(cpxOsceState.query)}" placeholder="증상, 진단, 술기 검색" />
          <select id="cpxCategoryFilter" aria-label="CPX/OSCE 카테고리 필터">
            ${categories.map((label) => `<option value="${cpxEscape(label)}" ${label === cpxOsceState.category ? "selected" : ""}>${cpxEscape(label)}</option>`).join("")}
          </select>
        </div>
        <div class="cpx-case-list" role="list">
          ${renderCpxCaseList()}
        </div>
      </aside>
      <section class="cpx-workspace">
        ${current ? renderCpxStation(current) : `<div class="results-empty">선택 가능한 케이스가 없습니다.</div>`}
      </section>
    </div>
  `;
}

function renderCpxCaseList() {
  const filtered = cpxFilteredCases();
  if (!filtered.length) {
    return `<div class="results-empty compact">검색 조건에 맞는 케이스가 없습니다.</div>`;
  }
  return filtered.map((caseItem) => {
    const score = cpxScore(caseItem);
    const selected = caseItem.id === cpxOsceState.selectedCaseId;
    return `
      <button type="button" class="cpx-case-card ${selected ? "is-active" : ""}" data-cpx-case-id="${cpxEscape(caseItem.id)}">
        <span class="cpx-case-card-top">
          <b>${cpxEscape(cpxCaseTitle(caseItem))}</b>
          <small>${cpxEscape(cpxCaseKindLabel(caseItem))}</small>
        </span>
        <span>${cpxEscape(caseItem.presentation || caseItem.diagnosis || "")}</span>
        <span class="cpx-mini-progress"><i style="width:${score.percent}%"></i></span>
        <span class="cpx-card-foot">
          <small>${score.done}/${score.total} 완료</small>
          <small>${score.missedCritical.length} 필수 누락</small>
        </span>
      </button>
    `;
  }).join("");
}

function renderCpxStation(caseItem) {
  const score = cpxScore(caseItem);
  const timerSeconds = cpxTimerSeconds(caseItem);
  const missedCount = score.missedCritical.length;
  const tabItems = [
    ["study", "공부대본"],
    ["diagnosis", "진단노트"],
    ["checklist", "체크리스트"],
    ["patient", "환자답변"],
    ["summary", "정리"],
    ["coach", "실전 코치"],
  ];
  const activeTab = tabItems.some(([id]) => id === cpxOsceState.activeTab) ? cpxOsceState.activeTab : "study";
  return `
    <header class="cpx-station-head">
      <div>
        <p class="section-label">${cpxEscape(cpxCaseKindLabel(caseItem))}</p>
        <h2>${cpxEscape(cpxCaseTitle(caseItem))}</h2>
        <p>${cpxEscape(caseItem.presentation || caseItem.diagnosis || "실전 스테이션")}</p>
        <div class="cpx-chip-row">
          <span>${cpxEscape(caseItem.diagnosis || "진단/술기")}</span>
          <span>${score.percent}% 진행</span>
          <span class="${missedCount ? "danger-text" : "success-text"}">필수 누락 ${missedCount}</span>
        </div>
      </div>
      <div class="cpx-station-actions">
        <div class="cpx-timer ${cpxOsceState.timerRunning && cpxOsceState.timerCaseId === caseItem.id ? "is-running" : ""}" id="cpxStationTimer">
          <span>12분 스테이션</span>
          <strong id="cpxTimerValue">${formatStationTime(timerSeconds)}</strong>
        </div>
        <div class="cpx-action-row">
          <button type="button" class="secondary-button" data-cpx-action="toggle-timer">${cpxOsceState.timerRunning && cpxOsceState.timerCaseId === caseItem.id ? "일시정지" : "시작"}</button>
          <button type="button" class="secondary-button" data-cpx-action="reset-timer">초기화</button>
          <button type="button" class="secondary-button" data-cpx-action="print">인쇄</button>
          <button type="button" data-cpx-action="export">내보내기</button>
        </div>
      </div>
    </header>
    <nav class="cpx-tabs" aria-label="CPX/OSCE 학습 탭">
      ${tabItems.map(([id, label]) => `<button type="button" class="${activeTab === id ? "is-active" : ""}" data-cpx-tab="${id}">${label}</button>`).join("")}
    </nav>
    <div class="cpx-tab-body">
      ${renderCpxActiveTab(caseItem)}
    </div>
  `;
}

function renderCpxActiveTab(caseItem) {
  if (cpxOsceState.activeTab === "diagnosis") return renderCpxDiagnosticNote(caseItem);
  if (cpxOsceState.activeTab === "checklist") return renderCpxChecklist(caseItem);
  if (cpxOsceState.activeTab === "patient") return renderCpxPatientCards(caseItem);
  if (cpxOsceState.activeTab === "summary") return renderCpxSummary(caseItem);
  if (cpxOsceState.activeTab === "coach") return renderCpxCoach(caseItem);
  return renderCpxStudyGuide(caseItem);
}

function cpxStudyGuide(caseItem) {
  return cpxData().studyGuides?.[caseItem.id] || {};
}

function cpxDiagnosticNote(caseItem) {
  return cpxData().diagnosticNotes?.[caseItem.id] || {};
}

function renderCpxStudyGuide(caseItem) {
  const guide = cpxStudyGuide(caseItem);
  const blocks = [
    ["첫 문장", guide.opening || guide.firstSentence],
    ["문진 순서", guide.history || guide.historyFlow],
    ["진찰/검사 선언", guide.exam || guide.examDeclaration],
    ["설명/치료계획", guide.explain || guide.plan || guide.explanation || guide.treatment],
    ["마무리 문장", guide.closing || guide.finish],
  ].filter(([, value]) => value);
  if (!blocks.length) {
    return `<div class="cpx-empty">이 케이스의 공부대본이 아직 정리되지 않았습니다.</div>`;
  }
  return `
    <div class="cpx-script-grid">
      ${blocks.map(([title, value]) => `
        <article class="cpx-script-card">
          <span>${cpxEscape(title)}</span>
          <p>${cpxFormatText(value)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderCpxDiagnosticNote(caseItem) {
  const note = cpxDiagnosticNote(caseItem);
  const blocks = [
    ["정의", note.definition],
    ["진단 기준/핵심 단서", note.criteria || note.clues],
    ["확인 검사", note.tests || note.confirmation],
    ["감별 함정", note.pitfalls || note.differential],
  ].filter(([, value]) => value);
  const refs = cpxReferenceList(caseItem);
  return `
    <div class="cpx-note-grid">
      ${blocks.length ? blocks.map(([title, value]) => `
        <article class="cpx-note-card">
          <span>${cpxEscape(title)}</span>
          <p>${cpxFormatText(value)}</p>
        </article>
      `).join("") : `<div class="cpx-empty">진단노트가 아직 정리되지 않았습니다.</div>`}
      <article class="cpx-note-card cpx-reference-card">
        <span>근거 연결</span>
        ${refs.length ? refs.map((ref) => `<a href="${cpxEscape(ref.url)}" target="_blank" rel="noreferrer">${cpxEscape(ref.title)}</a>`).join("") : `<p>공식 자료 연결이 준비 중입니다.</p>`}
      </article>
    </div>
  `;
}

function renderCpxChecklist(caseItem) {
  const sections = cpxCaseSections(caseItem);
  const selectedSection = sections.find((section) => section.id === cpxOsceState.checklistSectionId) || sections[0];
  if (!selectedSection) return `<div class="cpx-empty">체크리스트가 없습니다.</div>`;
  const items = Array.isArray(selectedSection.items) ? selectedSection.items : [];
  const score = cpxScore(caseItem);
  return `
    <div class="cpx-check-layout">
      <aside class="cpx-section-tabs">
        ${sections.map((section) => {
          const sectionScore = score.bySection.find((item) => item.id === section.id);
          return `<button type="button" class="${selectedSection.id === section.id ? "is-active" : ""}" data-cpx-section="${cpxEscape(section.id)}">
            <strong>${cpxEscape(section.title)}</strong>
            <small>${sectionScore?.done || 0}/${sectionScore?.total || 0}</small>
          </button>`;
        }).join("")}
      </aside>
      <div class="cpx-checklist">
        ${items.map((item, index) => {
          const checked = cpxIsChecked(caseItem.id, selectedSection.id, index);
          return `
            <label class="cpx-check-row ${checked ? "is-done" : ""} ${item.critical ? "is-critical" : ""}">
              <input type="checkbox" ${checked ? "checked" : ""} data-cpx-check="${cpxEscape(selectedSection.id)}" data-cpx-index="${index}" />
              <span>${cpxEscape(item.text)}</span>
              ${item.critical ? "<em>필수</em>" : ""}
            </label>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function renderCpxPatientCards(caseItem) {
  const script = Array.isArray(caseItem.script) ? caseItem.script : [];
  if (!script.length) {
    return `<div class="cpx-empty">환자 역할 답변이 준비되지 않았습니다.</div>`;
  }
  return `
    <div class="cpx-patient-grid">
      ${script.map((line) => `
        <article class="cpx-patient-card">
          <span>${cpxEscape(Array.isArray(line) ? line[0] : line.q || line.question || "질문")}</span>
          <p>${cpxEscape(Array.isArray(line) ? line[1] : line.a || line.answer || "")}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderCpxSummary(caseItem) {
  const score = cpxScore(caseItem);
  const noteValue = cpxOsceState.notes[caseItem.id] || "";
  return `
    <div class="cpx-summary-grid">
      <section class="cpx-score-card">
        <div class="cpx-score-ring" style="--score:${score.percent}%"><strong>${score.percent}%</strong></div>
        <div>
          <h3>영역별 점수</h3>
          <p>${score.done}/${score.total}개 완료 · 필수 누락 ${score.missedCritical.length}개</p>
        </div>
      </section>
      <section class="cpx-progress-list">
        ${score.bySection.map((section) => `
          <div>
            <span>${cpxEscape(section.title)}</span>
            <b>${section.percent}%</b>
            <i><em style="width:${section.percent}%"></em></i>
          </div>
        `).join("")}
      </section>
      <section class="cpx-missing-card">
        <h3>필수 누락 항목</h3>
        ${score.missedCritical.length ? `<ul>${score.missedCritical.map((item) => `<li><strong>${cpxEscape(item.sectionTitle)}</strong> ${cpxEscape(item.text)}</li>`).join("")}</ul>` : `<p class="success-text">필수 항목을 모두 확인했습니다.</p>`}
      </section>
      <section class="cpx-note-save-card">
        <h3>케이스 메모</h3>
        <textarea id="cpxCaseNote" rows="6" placeholder="내가 놓친 문장, 다음 연습 때 볼 포인트를 적어두세요.">${cpxEscape(noteValue)}</textarea>
      </section>
    </div>
  `;
}

function renderCpxCoach(caseItem) {
  const messages = cpxOsceState.coachMessages[caseItem.id] || [];
  const quickPrompts = cpxCaseKindLabel(caseItem) === "OSCE 술기"
    ? ["공부 흐름", "술기 순서", "누락", "마무리"]
    : ["공부 흐름", "진단 기준", "첫 문장", "치료계획", "누락", "마무리"];
  return `
    <div class="cpx-coach">
      <div class="cpx-coach-prompts">
        ${quickPrompts.map((prompt) => `<button type="button" class="secondary-button" data-cpx-coach-prompt="${cpxEscape(prompt)}">${cpxEscape(prompt)}</button>`).join("")}
      </div>
      <div class="cpx-coach-log" aria-live="polite">
        ${messages.length ? messages.map((message) => `
          <article class="${message.role === "user" ? "is-user" : "is-coach"}">
            <span>${message.role === "user" ? "나" : "실전 코치"}</span>
            <p>${cpxFormatText(message.text)}</p>
          </article>
        `).join("") : `<div class="cpx-empty">궁금한 흐름을 누르면 실전 코치가 케이스에 맞춰 짧게 답합니다.</div>`}
      </div>
      <div class="cpx-coach-input">
        <input type="text" id="cpxCoachDraft" value="${cpxEscape(cpxOsceState.coachDraft)}" placeholder="예: 보호자에게 치료계획을 어떻게 말하지?" />
        <button type="button" data-cpx-action="send-coach">질문</button>
      </div>
    </div>
  `;
}

function cpxFormatText(value) {
  if (Array.isArray(value)) {
    return `<ul>${value.map((item) => `<li>${cpxEscape(item)}</li>`).join("")}</ul>`;
  }
  return cpxEscape(value).replace(/\n/g, "<br />");
}

function cpxReferenceList(caseItem) {
  const data = cpxData();
  const keys = data.caseReferenceMap?.[caseItem.id] || [];
  return keys
    .map((key) => ({ key, ...(data.referenceLinks?.[key] || {}) }))
    .filter((reference) => {
      if (!reference.title && !reference.url) return false;
      const searchable = `${reference.key} ${reference.title || ""} ${reference.url || ""}`;
      return !/amboss|uptodate|allen/i.test(searchable);
    });
}

function cpxMissingTexts(caseItem) {
  return cpxScore(caseItem).missedCritical.map((item) => item.text);
}

function cpxCoachContext(caseItem, userQuestion) {
  return {
    caseId: caseItem.id,
    presentation: caseItem.presentation,
    diagnosis: caseItem.diagnosis,
    mustNotMiss: caseItem.mustNotMiss || [],
    studyGuide: cpxStudyGuide(caseItem),
    diagnosticNote: cpxDiagnosticNote(caseItem),
    missingItems: cpxMissingTexts(caseItem),
    userQuestion,
  };
}

function cpxLocalCoachReply(caseItem, prompt) {
  const data = cpxData();
  const lower = prompt.toLowerCase();
  const guide = cpxStudyGuide(caseItem);
  const note = cpxDiagnosticNote(caseItem);
  const missing = cpxMissingTexts(caseItem);
  if (lower.includes("asd") || caseItem.id === "development-delay-asd" || /자폐|발달/.test(prompt)) {
    return data.treatmentPlanReply?.asd || "청력검사와 발달평가를 확인하고, 조기개입·언어치료·부모교육·추적관찰 계획을 설명합니다.";
  }
  if (/치료|계획|설명/.test(prompt)) {
    return cpxFormatCoachPlain(guide.explain || guide.plan || guide.explanation || guide.treatment || data.treatmentPlanReply?.default);
  }
  if (/진단|기준|단서/.test(prompt)) {
    return cpxFormatCoachPlain(note.criteria || note.clues || note.definition || data.diagnosisReply?.default);
  }
  if (/첫|시작|opening/.test(lower)) {
    return cpxFormatCoachPlain(guide.opening || guide.firstSentence || "안녕하세요. 오늘 불편하신 점을 확인하고 필요한 질문과 진찰을 진행하겠습니다.");
  }
  if (/흐름|순서|공부|술기/.test(prompt)) {
    return cpxFormatCoachPlain(guide.history || guide.historyFlow || guide.steps || data.studyFlowReply?.default);
  }
  if (/누락|빠뜨|필수/.test(prompt)) {
    return missing.length ? `지금은 ${missing.slice(0, 5).join(", ")} 항목이 남아 있습니다. 먼저 필수 항목부터 말하고 넘어가세요.` : "필수 누락 항목은 없습니다. 마지막에 이해 여부와 추가 질문을 확인하면 좋습니다.";
  }
  if (/마무리|끝/.test(prompt)) {
    return cpxFormatCoachPlain(guide.closing || guide.finish || "오늘 설명드린 내용을 확인하고, 악화되거나 위험 신호가 있으면 바로 내원하시도록 안내합니다.");
  }
  cpxCoachContext(caseItem, prompt);
  return "이 케이스에서는 주소증을 한 문장으로 정리한 뒤, 필수 누락 항목과 진단 기준을 먼저 확인하세요.";
}

function cpxFormatCoachPlain(value) {
  if (Array.isArray(value)) return value.slice(0, 5).join(" → ");
  return String(value || "").replace(/\s+/g, " ").trim();
}

function cpxSendCoachMessage(prompt) {
  const caseItem = cpxCurrentCase();
  if (!caseItem || !prompt.trim()) return;
  const messages = cpxOsceState.coachMessages[caseItem.id] || [];
  const text = prompt.trim();
  cpxOsceState.coachMessages[caseItem.id] = [
    ...messages,
    { role: "user", text },
    { role: "coach", text: cpxLocalCoachReply(caseItem, text) },
  ].slice(-16);
  cpxOsceState.coachDraft = "";
  cpxSaveState();
  renderCpxOsceModule();
}

function cpxExportProgress() {
  const payload = {
    exported_at: new Date().toISOString(),
    selected_case_id: cpxOsceState.selectedCaseId,
    checked: cpxOsceState.checked,
    notes: cpxOsceState.notes,
    scores: cpxCases().map((caseItem) => ({
      id: caseItem.id,
      title: cpxCaseTitle(caseItem),
      diagnosis: caseItem.diagnosis,
      score: cpxScore(caseItem),
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `paccine_cpx_osce_progress_${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function cpxHandleClick(event) {
  if (!(event.target instanceof Element)) return;
  const caseButton = event.target.closest("[data-cpx-case-id]");
  if (caseButton) {
    cpxOsceState.selectedCaseId = caseButton.dataset.cpxCaseId;
    cpxOsceState.activeTab = "study";
    cpxOsceState.checklistSectionId = "history";
    cpxOsceState.timerCaseId = cpxOsceState.selectedCaseId;
    cpxOsceState.timerRemaining = cpxData().STATION_SECONDS || 720;
    cpxOsceState.timerRunning = false;
    cpxSaveState();
    cpxSyncTimerInterval();
    renderCpxOsceModule();
    return;
  }
  const tabButton = event.target.closest("[data-cpx-tab]");
  if (tabButton) {
    cpxOsceState.activeTab = tabButton.dataset.cpxTab;
    cpxSaveState();
    renderCpxOsceModule();
    return;
  }
  const sectionButton = event.target.closest("[data-cpx-section]");
  if (sectionButton) {
    cpxOsceState.checklistSectionId = sectionButton.dataset.cpxSection;
    cpxSaveState();
    renderCpxOsceModule();
    return;
  }
  const promptButton = event.target.closest("[data-cpx-coach-prompt]");
  if (promptButton) {
    cpxSendCoachMessage(promptButton.dataset.cpxCoachPrompt || "");
    return;
  }
  const categoryButton = event.target.closest("[data-cpx-category]");
  if (categoryButton) {
    cpxOsceState.category = categoryButton.dataset.cpxCategory || "전체";
    const filtered = cpxFilteredCases();
    const next = filtered[0];
    if (next && !filtered.some((item) => item.id === cpxOsceState.selectedCaseId)) {
      cpxOsceState.selectedCaseId = next.id;
      cpxOsceState.timerCaseId = next.id;
      cpxOsceState.timerRemaining = cpxData().STATION_SECONDS || 720;
      cpxOsceState.timerRunning = false;
    }
    cpxSaveState();
    cpxSyncTimerInterval();
    renderCpxOsceModule();
    return;
  }
  const action = event.target.closest("[data-cpx-action]")?.dataset.cpxAction;
  if (!action) return;
  const caseItem = cpxCurrentCase();
  if (action === "random-case") {
    const filtered = cpxFilteredCases();
    const pool = filtered.length ? filtered : cpxData().cases;
    const next = pool[Math.floor(Math.random() * pool.length)];
    if (next) {
      cpxOsceState.selectedCaseId = next.id;
      cpxOsceState.activeTab = "study";
      cpxOsceState.checklistSectionId = "history";
      cpxOsceState.timerCaseId = next.id;
      cpxOsceState.timerRemaining = cpxData().STATION_SECONDS || 720;
      cpxOsceState.timerRunning = false;
      cpxSaveState();
      cpxSyncTimerInterval();
      renderCpxOsceModule();
    }
  } else if (action === "toggle-timer" && caseItem) {
    cpxOsceState.timerCaseId = caseItem.id;
    if (!cpxOsceState.timerRemaining || cpxOsceState.timerRemaining <= 0) {
      cpxOsceState.timerRemaining = cpxData().STATION_SECONDS || 720;
    }
    cpxOsceState.timerRunning = !cpxOsceState.timerRunning;
    cpxSaveState();
    cpxSyncTimerInterval();
    renderCpxOsceModule();
  } else if (action === "reset-timer" && caseItem) {
    cpxOsceState.timerCaseId = caseItem.id;
    cpxOsceState.timerRemaining = cpxData().STATION_SECONDS || 720;
    cpxOsceState.timerRunning = false;
    cpxSaveState();
    cpxSyncTimerInterval();
    renderCpxOsceModule();
  } else if (action === "export") {
    cpxExportProgress();
  } else if (action === "print") {
    window.print();
  } else if (action === "send-coach") {
    cpxSendCoachMessage(cpxOsceState.coachDraft);
  }
}

function cpxHandleInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLTextAreaElement)) return;
  if (target.id === "cpxCaseSearch") {
    cpxOsceState.query = target.value;
    cpxSaveState();
    const list = document.querySelector(".cpx-case-list");
    if (list) list.innerHTML = renderCpxCaseList();
    return;
  }
  if (target.id === "cpxCaseNote") {
    const caseItem = cpxCurrentCase();
    if (!caseItem) return;
    cpxOsceState.notes[caseItem.id] = target.value;
    cpxSaveState();
    return;
  }
  if (target.id === "cpxCoachDraft") {
    cpxOsceState.coachDraft = target.value;
    cpxSaveState();
  }
}

function cpxHandleChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLSelectElement)) return;
  if (target.id === "cpxCategoryFilter") {
    cpxOsceState.category = target.value;
    const filtered = cpxFilteredCases();
    const next = filtered[0];
    if (next && !filtered.some((item) => item.id === cpxOsceState.selectedCaseId)) {
      cpxOsceState.selectedCaseId = next.id;
    }
    cpxSaveState();
    renderCpxOsceModule();
    return;
  }
  if (target.matches("[data-cpx-check]")) {
    const caseItem = cpxCurrentCase();
    if (!caseItem) return;
    const key = cpxChecklistKey(caseItem.id, target.dataset.cpxCheck, target.dataset.cpxIndex);
    cpxOsceState.checked[key] = target.checked;
    cpxSaveState();
    renderCpxOsceModule();
  }
}

function cpxHandleKeydown(event) {
  const target = event.target;
  if (target instanceof HTMLTextAreaElement && target.id === "cpxCoachDraft" && event.key === "Enter") {
    event.preventDefault();
    cpxSendCoachMessage(cpxOsceState.coachDraft);
  }
}

document.addEventListener("click", cpxHandleClick);
document.addEventListener("input", cpxHandleInput);
document.addEventListener("change", cpxHandleChange);
document.addEventListener("keydown", cpxHandleKeydown);

checkHealth();
initWorkspaceRail();
renderCategoryGrid(facultyCategoryGrid, "faculty");
renderCategoryGrid(studentCategoryGrid, "student");
loadMediaAssets();
loadArchiveSets();
loadStudentCourseExams();
initStudioMethodTabs();
initQuestionPresetChips();
initTopicGenerate();
initTopicImageFinder();
initArchiveControls();
initFeedbackWidget();
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

// PWA 서비스워커 등록 — 앱 셸만 캐시(API는 항상 네트워크). HTTPS 또는 localhost에서만 등록 가능.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.warn("서비스워커 등록 실패:", error);
    });
  });
}
