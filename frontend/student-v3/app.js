const app = document.querySelector("#app");
const toastEl = document.querySelector("#toast");

const COPILOT_FOCUS_STORAGE_KEY = "paccine.medical_copilot.focus_mode.v1";
function activeCopilotExamplePrompts() {
  const now = new Date();
  const registry = Array.isArray(state.copilotStatus?.verified_examples)
    ? state.copilotStatus.verified_examples
    : [];
  return registry
    .filter((item) => item?.verification_status === "passed"
      && item?.expected_answer_status === "grounded_learning_draft"
      && item?.prompt
      && item?.expires_at
      && new Date(item.expires_at) >= now)
    .slice(0, 3)
    .map((item) => item.prompt);
}

function initialCopilotFocusMode() {
  try { return localStorage.getItem(COPILOT_FOCUS_STORAGE_KEY) !== "off"; } catch (_) { return true; }
}

const state = {
  qbank: null,
  catalog: null,
  bookmarks: [],
  review: null,
  claimReview: {counts: {overdue: 0, due: 0, new: 0, scheduled: 0}, items: []},
  concepts: null,
  analytics: null,
  libraryTab: "my",
  query: "",
  statusFilter: "all",
  clinicalTab: "chat",
  copilotStatus: null,
  clinicalMessages: [],
  copilotFocusMode: initialCopilotFocusMode(),
  guidelineQuery: "",
  guidelineSpecialty: "all",
  guidelineStatus: "all",
  guidelineView: "list",
  selectedGuidelineId: "",
  guidelineFilterOpen: false,
  guidelineVisibleLimit: 20,
  guidelineLoading: false,
  guidelineStatusError: "",
  assistantBusy: false,
  assistantResult: null,
  assistantQuery: "",
  pendingCopilotConceptId: "",
  clearChatConfirm: false,
  activeCopilotJobId: "",
  copilotRunToken: 0,
  copilotJobStage: "",
  copilotStartedAt: 0,
  copilotTimer: null,
  copilotRevealTimer: null,
  guidelineError: "",
};

const COPILOT_JOB_STORAGE_KEY = "paccine.medical_copilot.active_job.v1";

let guidelineCatalog = {
  snapshotDate: "",
  summary: {sources: 0, verifiedLatest: 0, latestUncertain: 0, catalogOnly: 0, approvedClaims: 0},
  items: [],
};

async function loadCopilotStatus() {
  try {
    state.copilotStatus = await api("/api/student/medical-copilot/status");
    return state.copilotStatus;
  } catch (error) {
    state.copilotStatus = {ready: false, error: error.message, counts: {}, provider: {available: false}};
    return state.copilotStatus;
  }
}

const specialtyLabel = {
  allergy_immunology: "알레르기",
  anesthesiology: "마취통증",
  cardiology: "순환기",
  dermatology: "피부과",
  emergency_critical_care: "응급·중환자",
  endocrinology: "내분비",
  endocrinology_metabolism: "내분비·대사",
  gastroenterology: "소화기",
  gastroenterology_hepatology: "소화기·간",
  genetics: "유전",
  geriatrics: "노인의학",
  hematology_oncology: "혈액종양",
  infectious_disease: "감염",
  laboratory_medicine: "진단검사",
  maternal_fetal_medicine: "모체태아",
  neonatology: "신생아",
  nephrology: "신장",
  neurology: "신경",
  nuclear_medicine: "핵의학",
  obstetrics_gynecology: "산부인과",
  orthopedics: "정형외과",
  pathology: "병리",
  pediatrics: "소아",
  primary_care_prevention: "예방·일차진료",
  psychiatry: "정신건강",
  pulmonology: "호흡기",
  radiation_oncology: "방사선종양",
  radiology: "영상의학",
  rehabilitation: "재활",
  rehabilitation_medicine: "재활의학",
  rheumatology: "류마티스",
  surgery_procedure: "외과·시술",
  urology: "비뇨의학",
};

const guidelineStatus = {
  verified: {label: "공식 출처 최신판 확인", detail: "공식 출처에서 현재판을 확인한 서지 레코드입니다."},
  uncertain: {label: "최신성 재확인 필요", detail: "후속 개정 여부를 다시 확인해야 합니다."},
  catalog: {label: "목록 등록 확인", detail: "목록은 확인했지만 최신판 검증은 완료되지 않았습니다."},
};

const clinicalAxisLabel = {
  contraindication: "금기",
  diagnosis: "진단",
  epidemiology: "역학",
  follow_up: "추적 관찰",
  indication: "적응증",
  prevention: "예방",
  procedure: "시술",
  prognosis: "예후",
  public_health: "공중보건",
  rehabilitation: "재활",
  risk_factor: "위험 요인",
  screening: "선별검사",
  treatment: "치료",
};

const statusLabel = {
  released: "학습 가능",
  preparing: "준비 중",
  no_public_questions: "공개 문항 없음",
};

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toastEl.classList.remove("show"), 2400);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {"content-type": "application/json", ...(options.headers || {})},
  });
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const error = new Error(payload.detail || "요청을 처리하지 못했습니다.");
    error.status = response.status;
    throw error;
  }
  return payload;
}

function normalizedGuidelineStatus(value) {
  const raw = value && typeof value === "object" ? value.status : value;
  const status = String(raw || "").toLowerCase();
  if (status === "verified" || status.includes("verified_latest")) return "verified";
  if (status === "catalog" || status.includes("cataloged")) return "catalog";
  return "uncertain";
}

function normalizeGuidelineItem(item) {
  const version = item.version || {};
  const currentness = item.currentness || {};
  const release = item.release || {};
  return {
    id: item.source_id || item.id || item.guideline_id || "",
    title: item.title || item.name || "제목 미등록",
    body: item.issuing_body || item.body || item.publisher || "발행기관 미등록",
    year: Number(item.publication_year || item.year || 0),
    status: normalizedGuidelineStatus(item.currentness || item.latest_status || item.status),
    priority: item.priority || "",
    specialties: Array.isArray(item.specialties) ? item.specialties : [],
    clinicalAxes: Array.isArray(item.clinical_axes) ? item.clinical_axes : [],
    url: item.official_landing_url || item.url || "",
    checkedAt: currentness.checked_at || item.checked_at || "",
    catalogProvider: item.catalog_provider || "",
    catalogRecordId: item.catalog_record_id || "",
    documents: Array.isArray(item.documents) ? item.documents.map((document) => ({
      role: document.role || "document",
      fileType: document.file_type || "",
      pageCount: Number(document.page_count || 0),
    })) : [],
    version: {
      display: version.display_version || "",
      printedYear: Number(version.printed_publication_year || 0),
      operationalRelease: version.operational_release || "",
      lastCorrectedAt: version.last_corrected_at || "",
      conflict: Boolean(version.version_conflict),
      reviewDue: Boolean(version.currency_review_due),
    },
    needsReview: item.needs_review !== false,
    medicalApproval: Boolean(item.medical_approval || release.medical_approval),
    studentVisible: Boolean(item.student_visible || release.student_visible_source),
    claimReleaseAvailable: Boolean(release.student_claim_release_available),
    useScope: release.use_scope || "",
  };
}

async function fetchGuidelinePages() {
  const firstPage = await api("/api/student/guidelines?currentness=all&offset=0&limit=50");
  const pages = [firstPage];
  let paginationError = "";
  let pagination = firstPage.pagination || {};
  while (pagination.has_more) {
    const offset = Number(pagination.offset || 0) + Number(pagination.limit || 50);
    try {
      const nextPage = await api(`/api/student/guidelines?currentness=all&offset=${offset}&limit=50`);
      pages.push(nextPage);
      pagination = nextPage.pagination || {};
    } catch (error) {
      paginationError = error.message;
      break;
    }
  }
  return {firstPage, pages, paginationError};
}

async function loadGuidelineCatalog() {
  state.guidelineLoading = true;
  state.guidelineError = "";
  state.guidelineStatusError = "";
  const [listResult, statusResult] = await Promise.allSettled([
    fetchGuidelinePages(),
    api("/api/student/guidelines/status"),
  ]);
  try {
    const listPayload = listResult.status === "fulfilled" ? listResult.value : null;
    const statusPayload = statusResult.status === "fulfilled" ? statusResult.value : {};
    if (!listPayload) throw listResult.reason || new Error("가이드라인 목록을 불러오지 못했습니다.");
    if (statusResult.status === "rejected") state.guidelineStatusError = statusResult.reason?.message || "상태 정보를 불러오지 못했습니다.";
    if (listPayload.paginationError) state.guidelineError = `일부 목록을 불러오지 못했습니다. ${listPayload.paginationError}`;
    const {firstPage, pages} = listPayload;
    const rawItems = pages.flatMap((payload) => payload.results || payload.items || payload.sources || payload.guidelines || []);
    const items = rawItems.map(normalizeGuidelineItem);
    const sourceSummary = firstPage.summary || {};
    const statusCounts = statusPayload.counts || firstPage.counts || sourceSummary.latest_statuses || sourceSummary.currentness || {};
    const currentnessCounts = items.reduce((counts, item) => ({...counts, [item.status]: (counts[item.status] || 0) + 1}), {});
    guidelineCatalog = {
      snapshotDate: statusPayload.latest_checked_at || firstPage.latest_checked_at || firstPage.snapshot_date || firstPage.generated_at || "",
      summary: {
        sources: Number(statusCounts.sources ?? sourceSummary.sources ?? firstPage.total ?? rawItems.length),
        verifiedLatest: Number(currentnessCounts.verified ?? statusCounts.verified_current_sources ?? sourceSummary.verified_current_sources ?? 0),
        latestUncertain: Number(currentnessCounts.uncertain ?? sourceSummary.latest_uncertain ?? statusCounts.latest_uncertain ?? 0),
        catalogOnly: Number(currentnessCounts.catalog ?? sourceSummary.catalog_only ?? statusCounts.cataloged_not_latest_verified ?? 0),
        approvedClaims: Number(statusCounts.approved_claims_connected ?? sourceSummary.approved_claims_connected ?? sourceSummary.approved_claims ?? 0),
      },
      items,
    };
    return guidelineCatalog;
  } catch (error) {
    state.guidelineError = error.message;
    return guidelineCatalog;
  } finally {
    state.guidelineLoading = false;
  }
}

function route() {
  return (location.hash || "#home").slice(1).split("/")[0] || "home";
}

function routeDetail() {
  return (location.hash || "").slice(1).split("/")[1] || "";
}

function normalizedSearch(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, "").replace(/[^0-9a-z가-힣]/g, "");
}

function guidelineSearchText(item) {
  return [item.title, item.body, item.year, item.catalogProvider, ...(item.specialties || []).map((key) => specialtyLabel[key] || key), ...(item.clinicalAxes || []).map((key) => clinicalAxisLabel[key] || key)].join(" ");
}

function matchingGuidelines(query, {specialty = "all", status = "all", limit = 65} = {}) {
  const needle = normalizedSearch(query);
  const tokens = String(query || "").split(/[\s,./()]+/).map(normalizedSearch).filter((token) => token.length >= 2);
  return guidelineCatalog.items
    .filter((item) => specialty === "all" || (item.specialties || []).includes(specialty))
    .filter((item) => status === "all" || item.status === status)
    .map((item) => {
      const haystack = normalizedSearch(guidelineSearchText(item));
      const searchScore = !needle ? 0 : (haystack.includes(needle) ? 20 : tokens.reduce((score, token) => score + (haystack.includes(token) ? token.length : 0), 0));
      return {item, searchScore};
    })
    .filter(({searchScore}) => !needle || searchScore > 0)
    .sort((a, b) => b.searchScore - a.searchScore || Number(b.item.status === "verified") - Number(a.item.status === "verified") || b.item.year - a.item.year || a.item.title.localeCompare(b.item.title, "ko"))
    .slice(0, limit)
    .map(({item}) => item);
}

function assistantGuidelines(query, limit = 5) {
  const normalized = normalizedSearch(query);
  if (!normalized) return [];
  const tokens = String(query || "").toLowerCase().split(/[\s,./()]+/).map(normalizedSearch).filter((token) => token.length >= 2);
  return guidelineCatalog.items
    .map((item) => {
      const haystack = normalizedSearch(guidelineSearchText(item));
      const score = tokens.reduce((sum, token) => sum + (haystack.includes(token) ? Math.min(token.length, 8) : 0), haystack.includes(normalized) ? 12 : 0);
      return {item, score};
    })
    .filter(({score}) => score > 0)
    .sort((a, b) => b.score - a.score || Number(b.item.status === "verified") - Number(a.item.status === "verified") || b.item.year - a.item.year)
    .slice(0, limit)
    .map(({item}) => item);
}

function reasonLabel(reason) {
  const labels = {
    direct_identifiers_detected: "환자 직접 식별정보로 보이는 내용이 감지되었습니다.",
    approved_student_visible_claims_unavailable: "학생 공개 승인을 받은 임상 claim이 아직 없습니다.",
    grounded_answer_unavailable: "인용 검증을 통과한 학습 답변을 만들지 못했습니다.",
    direct_answer_evidence_missing: "질문의 핵심 결론을 직접 뒷받침하는 승인 근거가 없습니다.",
    current_korean_guideline_claim_pending: "최신 국내 가이드라인은 연결됐지만 세부 권고가 아직 사람 검토를 통과하지 않았습니다.",
    ontology_or_harrison_evidence_not_found: "질환명과 직접 연결되는 Harrison 근거를 찾지 못했습니다.",
  };
  return labels[reason] || reason;
}

function syncNav() {
  const current = route();
  document.querySelectorAll("[data-route]").forEach((node) => node.classList.toggle("active", node.dataset.route === current));
}

function startUrl({courseId = "", exam = "", mode = "study", count = 20, ids = ""} = {}) {
  const params = new URLSearchParams({mode, count: String(count)});
  if (courseId) params.set("courseId", courseId);
  if (exam) params.set("exam", exam);
  if (ids) params.set("ids", ids);
  return `/student/reader.html?${params}`;
}

function courseCard(course) {
  const initial = course.name.replace(/[^가-힣A-Za-z0-9]/g, "").slice(0, 1) || "과";
  const readyCount = Number(course.practice_ready_count ?? course.question_count ?? 0);
  const mediaReviewCount = Number(course.media_review_count || 0);
  const topicText = course.question_count
    ? (course.topics || []).slice(0, 3).map((topic) => topic.name).join(" · ")
    : course.status === "preparing" ? "자료 검수와 문항 연결을 준비하고 있습니다." : "학생에게 공개된 문항이 아직 없습니다.";
  return `
    <article class="card course-card" data-course-id="${esc(course.id)}">
      <button class="star ${course.is_favorite ? "on" : ""}" data-favorite="${esc(course.id)}" aria-label="${course.is_favorite ? "내 과목에서 해제" : "내 과목에 추가"}">${course.is_favorite ? "★" : "☆"}</button>
      <div class="course-icon">${esc(initial)}</div>
      <h3>${esc(course.name)}</h3>
      <p>${esc(topicText)}${mediaReviewCount ? `<br><small>제시자료 연결 검토 ${mediaReviewCount}문항</small>` : ""}</p>
      <footer>
        <span class="status-chip ${esc(course.status)}">${esc(statusLabel[course.status])}${readyCount ? ` · ${readyCount}문항` : ""}</span>
        ${course.status === "released" && readyCount ? `<a class="button primary small" href="${startUrl({courseId: course.id, count: Math.min(20, readyCount)})}">풀기 →</a>` : `<button class="button secondary small" disabled>준비 중</button>`}
      </footer>
    </article>`;
}

function pageHead(eyebrow, title, description, action = "") {
  return `<header class="page-head"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${action}</header>`;
}

function renderHome() {
  const favoriteCourses = state.catalog.courses.filter((course) => course.is_favorite);
  const counts = state.review.counts;
  const analyticsSummary = state.analytics?.summary || state.analytics || {};
  const attemptCount = analyticsSummary.attempt_count || 0;
  const todayTarget = Math.min(18, counts.overdue + counts.due + Math.min(12, counts.new));
  const completed = Math.min(todayTarget, 0);
  app.innerHTML = `
    ${pageHead("Student Learning OS", "오늘의 학습", "실제 문항·복습 일정·개념 연결을 한 흐름에서 이어갑니다.", `<a class="button primary" href="${startUrl({courseId: favoriteCourses[0]?.id || "neuro", count: 12})}">오늘 학습 시작 →</a>`)}
    <section class="hero-grid">
      <article class="card continue-card">
        <span class="eyebrow">Live Question Bank</span>
        <h2>${state.qbank.practice_ready_count ?? state.qbank.question_count}개 문항을 바로 학습할 수 있습니다</h2>
        <p>전체 ${state.qbank.question_count}개 실제 문항이 연결됐습니다. 필수 제시자료가 없는 ${state.qbank.media_review_count || 0}개 문항은 검토가 끝날 때까지 자동으로 제외됩니다.</p>
        <div class="continue-kpis"><span><b>${attemptCount}</b>누적 풀이</span><span><b>${favoriteCourses.length}</b>내 과목</span><span><b>${counts.overdue + counts.due}</b>복습 예정</span></div>
        <a class="button primary" href="#library">나의 서재 열기 →</a>
      </article>
      <article class="card today-card">
        <div><span class="eyebrow">FSRS-6 · 90% Retention</span><h2>오늘의 복습</h2></div>
        <div class="ring-row"><div class="ring" style="--progress:${todayTarget ? (completed / todayTarget) * 360 : 0}deg" data-label="${completed}/${todayTarget}"></div>
          <div class="metric-list"><div><span>기한 지남</span><b>${counts.overdue}</b></div><div><span>오늘 복습</span><b>${counts.due}</b></div><div><span>새 문항</span><b>${counts.new}</b></div></div>
        </div>
        <a class="button secondary" href="#review">복습 대기열 보기</a>
      </article>
    </section>
    <section class="section"><div class="section-head"><div><span class="eyebrow">My Courses</span><h2>내 과목</h2></div><a href="#library">전체 과목 보기 →</a></div>
      <div class="course-strip">${favoriteCourses.map(courseCard).join("") || `<div class="card empty-card"><strong>내 과목이 없습니다</strong>서재에서 별표를 눌러 과목을 추가하세요.</div>`}</div>
    </section>`;
  bindCourseActions();
}

function renderLibrary() {
  const all = state.catalog.courses;
  const query = state.query.trim().toLowerCase();
  const visible = all.filter((course) => {
    if (state.libraryTab === "my" && !course.is_favorite) return false;
    if (state.statusFilter !== "all" && course.status !== state.statusFilter) return false;
    return !query || course.name.toLowerCase().includes(query) || (course.topics || []).some((topic) => topic.name.toLowerCase().includes(query));
  });
  app.innerHTML = `
    ${pageHead("My Library", "나의 서재", "공식 과목은 즐겨찾기로 관리하고, 시험지 세트는 별도 컬렉션에서 풉니다.")}
    <div class="tabs" role="tablist"><button data-library-tab="my" class="${state.libraryTab === "my" ? "active" : ""}">내 과목 ${all.filter((c) => c.is_favorite).length}</button><button data-library-tab="all" class="${state.libraryTab === "all" ? "active" : ""}">전체 과목 ${all.length}</button><button data-library-tab="exams" class="${state.libraryTab === "exams" ? "active" : ""}">시험지 세트 ${state.catalog.assessments.length}</button></div>
    ${state.libraryTab === "exams" ? renderAssessments() : `
      <section class="card filters"><input id="course-search" value="${esc(state.query)}" placeholder="과목·주제 검색"><select id="course-status"><option value="all">전체 상태</option><option value="released" ${state.statusFilter === "released" ? "selected" : ""}>학습 가능</option><option value="preparing" ${state.statusFilter === "preparing" ? "selected" : ""}>준비 중</option><option value="no_public_questions" ${state.statusFilter === "no_public_questions" ? "selected" : ""}>공개 문항 없음</option></select><button class="button secondary" id="reset-filter">초기화</button></section>
      <section class="course-grid">${visible.map(courseCard).join("") || `<div class="card empty-card"><strong>조건에 맞는 과목이 없습니다</strong>검색어 또는 상태 필터를 바꿔보세요.</div>`}</section>`}`;
  document.querySelectorAll("[data-library-tab]").forEach((button) => button.addEventListener("click", () => { state.libraryTab = button.dataset.libraryTab; renderLibrary(); }));
  document.querySelector("#course-search")?.addEventListener("input", (event) => { state.query = event.target.value; renderLibrary(); requestAnimationFrame(() => { const el = document.querySelector("#course-search"); el?.focus(); el?.setSelectionRange(state.query.length, state.query.length); }); });
  document.querySelector("#course-status")?.addEventListener("change", (event) => { state.statusFilter = event.target.value; renderLibrary(); });
  document.querySelector("#reset-filter")?.addEventListener("click", () => { state.query = ""; state.statusFilter = "all"; renderLibrary(); });
  bindCourseActions();
}

function renderAssessments() {
  return `<div class="notice"><b>i</b><span>시험지 세트는 원본 평가 단위를 유지합니다. 같은 문항이 과목별 학습에 연결돼도 풀이·북마크·FSRS 기록은 문항 ID 기준으로 한 번만 저장됩니다.</span></div><section class="section assessment-list">${state.catalog.assessments.map((item) => `
    <article class="assessment-row"><span class="row-icon">시</span><div class="row-main"><h3>${esc(item.name)}</h3><p>${item.practice_ready_count ?? item.question_count}문항 학습 가능 · 전체 ${item.question_count}문항${item.media_review_count ? ` · 자료 검토 ${item.media_review_count}` : ""}</p></div><a class="button primary small" href="${startUrl({exam: item.name, count: item.practice_ready_count ?? item.question_count})}">세트 풀기 →</a></article>`).join("")}</section>`;
}

function bindCourseActions() {
  document.querySelectorAll("[data-favorite]").forEach((button) => button.addEventListener("click", async () => {
    const course = state.catalog.courses.find((item) => item.id === button.dataset.favorite);
    if (!course) return;
    const next = !course.is_favorite;
    button.disabled = true;
    try {
      await api(`/api/student/courses/${encodeURIComponent(course.id)}/favorite`, {method: "PATCH", body: JSON.stringify({on: next})});
      course.is_favorite = next;
      toast(next ? "내 과목에 추가했습니다." : "내 과목에서 해제했습니다.");
      render();
    } catch (error) { toast(error.message); button.disabled = false; }
  }));
}

function renderConcepts() {
  const approved = state.concepts.approved || [];
  app.innerHTML = `
    ${pageHead("Concept Notes", "개념 노트", "교수 검수가 끝난 Ontology 기반 개념만 학생에게 공개됩니다.")}
    <div class="notice"><b>✓</b><span>검수 전 개념 연결과 내부 Ontology ID는 학생 화면에 노출하지 않습니다. 현재 <strong>${state.concepts.reviewing_count}개</strong> 노트가 검수 대기 중입니다.</span></div>
    <section class="section concept-list">${approved.length ? approved.map((note) => `<article class="concept-row"><span class="row-icon">개</span><div class="row-main"><h3>${esc(note.title)}</h3><p>교수 승인 완료 · 관련 문항에서 다시 열 수 있습니다.</p></div><button class="button secondary small">열기</button></article>`).join("") : `<div class="card empty-card"><strong>공개된 개념 노트가 아직 없습니다</strong>초안은 준비되어 있지만 교수 검수가 끝날 때까지 잠겨 있습니다.</div>`}</section>`;
}

function renderReview() {
  const counts = state.review.counts;
  const items = state.review.items.filter((item) => item.status !== "scheduled");
  const claimItems = (state.claimReview?.items || []).filter((item) => item.status !== "scheduled");
  const claimCounts = state.claimReview?.counts || {overdue: 0, due: 0, new: 0, scheduled: 0};
  const focusMedical = routeDetail() === "medical";
  const claimTitleTag = focusMedical ? "h1" : "h2";
  const claimSection = `<section id="medical-review" class="section claim-review-section ${focusMedical ? "medical-review-focus" : ""}">${focusMedical ? `<a class="medical-review-back" href="#clinical">← 의료 챗봇으로</a>` : ""}<div class="section-head"><div><span class="eyebrow">Approved Guideline · FSRS-6 · 서버 일정</span><${claimTitleTag}>의학 지식 복습</${claimTitleTag}><p>교수 검토 후 FSRS 복습 사용이 허용된 국내 가이드라인 claim만 표시합니다.</p></div><span class="claim-review-count">기한 ${claimCounts.overdue + claimCounts.due} · 새 항목 ${claimCounts.new}</span></div>
      <div class="claim-review-list">${claimItems.length ? claimItems.map((item) => `<article class="card claim-review-card"><div class="claim-review-top"><span class="queue-status ${esc(item.status)}">${{overdue:"기한 지남",due:"오늘",new:"새 지식"}[item.status] || "예정"}</span><small>${esc(item.source_title)}</small></div><h3>${esc(item.prompt)}</h3><p>${esc(item.population)}</p><details><summary>승인된 핵심 문장 보기</summary><div>${esc(item.answer)}</div></details><div class="claim-rating" data-claim-id="${esc(item.claim_id)}"><span>기억 상태</span><button type="button" data-rating="1">다시</button><button type="button" data-rating="2">어려움</button><button type="button" data-rating="3">보통</button><button type="button" data-rating="4">쉬움</button></div></article>`).join("") : `<div class="card empty-card"><strong>아직 승인된 복습 항목이 없어요</strong>교수 검토를 통과해 복습용으로 공개된 국내 지침 claim이 생기면 이곳에 나타납니다. 현재는 챗봇 답변의 공식 문서 링크로 원문을 확인해 주세요.</div>`}</div>
    </section>`;
  app.innerHTML = focusMedical ? claimSection : `
    ${pageHead("FSRS Review", "복습", "FSRS-6가 각 문항의 기억 상태와 다음 복습 시점을 계산합니다.", items.length ? `<a class="button primary" href="${startUrl({ids: items.map((item) => item.question_id).join(","), count: items.length})}">대기열 풀기 →</a>` : "")}
    <section class="queue-summary"><article class="card summary-card danger"><span>기한 지남</span><strong>${counts.overdue}</strong></article><article class="card summary-card"><span>오늘 복습</span><strong>${counts.due}</strong></article><article class="card summary-card accent"><span>새 문항</span><strong>${counts.new}</strong></article><article class="card summary-card"><span>예약됨</span><strong>${counts.scheduled}</strong></article></section>
    <section class="queue-list">${items.length ? items.map((item) => `<article class="queue-row"><span class="queue-status ${item.status}">${{overdue:"기한 지남",due:"오늘",new:"새 문항"}[item.status] || "예정"}</span><div class="row-main"><h3>${esc(item.topic)}</h3><p>${esc(item.stem_preview)}</p></div><a class="button secondary small" href="${startUrl({ids:item.question_id,count:1})}">풀기</a></article>`).join("") : `<div class="card empty-card"><strong>지금 복습할 문항이 없습니다</strong>다음 일정이 되면 자동으로 대기열에 올라옵니다.</div>`}</section>
    ${claimSection}`;
  document.querySelectorAll(".claim-rating button").forEach((button) => button.addEventListener("click", async () => {
    const group = button.closest(".claim-rating");
    group.querySelectorAll("button").forEach((item) => { item.disabled = true; });
    try {
      await api(`/api/student/medical-copilot/claims/${encodeURIComponent(group.dataset.claimId)}/fsrs`, {method: "POST", body: JSON.stringify({rating: Number(button.dataset.rating)})});
      state.claimReview = await api("/api/student/medical-copilot/review?limit=30");
      toast("의학 지식 복습 일정을 저장했습니다.");
      renderReview();
    } catch (error) {
      toast(error.message);
      group.querySelectorAll("button").forEach((item) => { item.disabled = false; });
    }
  }));
}

function renderReport() {
  const analytics = state.analytics || {};
  const summary = analytics.summary || analytics;
  const attempts = summary.attempt_count || 0;
  const weakness = analytics.weakness || [];
  const rate = Math.round(Number(summary.correct_rate_pct || 0));
  const avg = Math.round(Number(summary.avg_time_sec || 0));
  app.innerHTML = `
    ${pageHead("Learning Report", "학습 리포트", "서버에 저장된 실제 풀이 기록만 집계합니다.")}
    <section class="report-kpis"><article class="card summary-card accent"><span>누적 풀이</span><strong>${attempts}</strong></article><article class="card summary-card"><span>평균 정답률</span><strong>${rate}%</strong></article><article class="card summary-card"><span>평균 풀이 시간</span><strong>${avg}초</strong></article><article class="card summary-card"><span>Ontology 분석 가능 축</span><strong>${(analytics.ontology_weakness || []).length}</strong></article></section>
    <section class="card" style="padding:22px"><div class="section-head"><div><span class="eyebrow">Weakness</span><h2>취약 영역</h2><p>표본 수와 정답률을 함께 표시합니다.</p></div></div><div class="weakness-list">${weakness.length ? weakness.slice(0, 12).map((row) => `<div class="weakness-row"><div><strong>${esc(row.label_path)}</strong><small style="display:block;color:var(--muted);margin-top:4px">${row.attempt_count}회 풀이 · 평균 ${row.avg_time_sec}초</small></div><div class="progress"><i style="width:${row.correct_rate_pct}%"></i></div><strong>${row.correct_rate_pct}%</strong></div>`).join("") : `<div class="empty-card"><strong>아직 집계할 풀이 기록이 없습니다</strong>문항을 풀면 과목·주제별 분석이 시작됩니다.</div>`}</div></section>`;
}

function clinicalTabs(active) {
  return `<nav class="clinical-subnav" aria-label="의료 학습 도구">
    <a href="#clinical/chat" class="${active === "chat" ? "active" : ""}">의료 챗봇</a>
    <a href="#clinical/library" class="${active === "library" ? "active" : ""}">가이드라인 라이브러리</a>
  </nav>`;
}

function clinicalSafetyNotice() {
  return `<div class="clinical-safety" role="note">
    <span class="safety-icon">i</span>
    <div><strong>의대생 학습·실습 준비용 의료 챗봇입니다</strong><p>Harrison 근거는 개념 설명에, 국내 가이드라인은 현재 확인할 원문 안내에 사용합니다. 실제 환자 진단·처방은 담당 의료진과 병원 지침을 따르세요.</p></div>
    <span class="release-badge">승인 claim ${guidelineCatalog.summary.approvedClaims || 0}</span>
  </div>`;
}

function guidelineStatusBadge(item) {
  const currentness = guidelineStatus[item.status] || guidelineStatus.uncertain;
  return `<span class="guideline-v1-status ${esc(item.status)}"><i></i>${esc(currentness.label)}</span>`;
}

function renderGuidelineFilterControls(specialties, location = "desktop") {
  return `<div class="guideline-v1-filter-controls ${esc(location)}">
    <div class="guideline-v1-filter-group"><span>분과</span><div class="guideline-v1-chips">
      <button type="button" data-guideline-specialty="all" class="${state.guidelineSpecialty === "all" ? "active" : ""}">전체</button>
      ${specialties.map((key) => `<button type="button" data-guideline-specialty="${esc(key)}" class="${state.guidelineSpecialty === key ? "active" : ""}">${esc(specialtyLabel[key] || key)}</button>`).join("")}
    </div></div>
    <div class="guideline-v1-filter-group"><span>최신성</span><div class="guideline-v1-chips">
      <button type="button" data-guideline-status="all" class="${state.guidelineStatus === "all" ? "active" : ""}">전체</button>
      <button type="button" data-guideline-status="verified" class="${state.guidelineStatus === "verified" ? "active" : ""}">최신판 확인</button>
      <button type="button" data-guideline-status="uncertain" class="${state.guidelineStatus === "uncertain" ? "active" : ""}">재확인 필요</button>
      <button type="button" data-guideline-status="catalog" class="${state.guidelineStatus === "catalog" ? "active" : ""}">목록 등록</button>
    </div></div>
  </div>`;
}

function renderGuidelineRow(item) {
  const version = item.version.display || item.year || "판 정보 확인 중";
  const specialtyNames = (item.specialties || []).slice(0, 3).map((key) => specialtyLabel[key] || key);
  return `<article class="guideline-v1-row">
    <button type="button" data-open-guideline="${esc(item.id)}" aria-label="${esc(item.title)} 상세 보기">
      <div class="guideline-v1-row-status">${guidelineStatusBadge(item)}<span>${esc(String(version))}</span></div>
      <div class="guideline-v1-row-copy"><h3>${esc(item.title)}</h3><p>${esc(item.body)}${specialtyNames.length ? ` · ${esc(specialtyNames.join(" · "))}` : ""}</p></div>
      <span class="guideline-v1-row-arrow" aria-hidden="true">→</span>
    </button>
  </article>`;
}

function guidelineDocumentSummary(item) {
  if (!item.documents.length) return "연결 문서 정보 확인 중";
  return item.documents.map((document) => {
    const type = String(document.fileType || "문서").toUpperCase();
    return `${type}${document.pageCount ? ` · ${document.pageCount}쪽` : ""}`;
  }).join(" / ");
}

function renderGuidelineDetail(item) {
  const currentness = guidelineStatus[item.status] || guidelineStatus.uncertain;
  const version = item.version.display || item.year || "확인 중";
  const checkedAt = item.checkedAt || guidelineCatalog.snapshotDate || "확인 중";
  const releaseMessage = guidelineCatalog.summary.approvedClaims > 0
    ? "승인된 claim은 의료 챗봇 답변에서 해당 근거가 직접 연결된 경우에만 표시됩니다."
    : "현재 승인된 진단·치료 claim이 없어 문서 탐색과 원문 확인만 제공합니다. 권고 내용을 추측해 요약하지 않습니다.";
  return `<div class="guideline-v1-detail-view">
    <button type="button" class="guideline-v1-back" data-back-guidelines>← 목록으로</button>
    <article class="guideline-v1-detail">
      <header>
        ${guidelineStatusBadge(item)}
        <h1>${esc(item.title)}</h1>
        <p>${esc(item.body)}</p>
      </header>
      <dl class="guideline-v1-metadata">
        <div><dt>판·발행연도</dt><dd>${esc(String(version))}${item.year && String(version) !== String(item.year) ? ` · ${item.year}` : ""}</dd></div>
        <div><dt>최신성 점검일</dt><dd>${esc(String(checkedAt).slice(0, 10))}</dd></div>
        <div><dt>연결 문서</dt><dd>${esc(guidelineDocumentSummary(item))}</dd></div>
        <div><dt>문서 목록 제공처</dt><dd>${esc(item.catalogProvider || "공식 발행기관")}</dd></div>
      </dl>
      ${item.version.operationalRelease || item.version.lastCorrectedAt ? `<div class="guideline-v1-version-note"><strong>버전 기록</strong><span>${item.version.operationalRelease ? `운영 반영 ${esc(item.version.operationalRelease)}` : ""}${item.version.lastCorrectedAt ? ` · 최종 정정 ${esc(item.version.lastCorrectedAt)}` : ""}</span></div>` : ""}
      ${item.version.conflict || item.version.reviewDue || item.status !== "verified" ? `<div class="guideline-v1-review-note"><strong>${esc(currentness.label)}</strong><span>${esc(currentness.detail)}${item.version.conflict ? " 원문과 레지스트리의 판 표기를 추가 확인 중입니다." : ""}</span></div>` : ""}
      <section class="guideline-v1-detail-section"><span class="eyebrow">Specialty</span><h2>관련 분과</h2><div class="guideline-v1-tag-list">${(item.specialties || []).map((key) => `<span>${esc(specialtyLabel[key] || key)}</span>`).join("") || "<span>분과 분류 확인 중</span>"}</div></section>
      <section class="guideline-v1-detail-section"><span class="eyebrow">Ontology routing</span><h2>연결 탐색 축</h2><p>아래 항목은 문서 탐색을 위한 분류이며, 진단·치료 사실을 승인한 근거가 아닙니다.</p><div class="guideline-v1-tag-list outlined">${(item.clinicalAxes || []).map((key) => `<span>${esc(clinicalAxisLabel[key] || key)}</span>`).join("") || "<span>탐색 축 확인 중</span>"}</div></section>
      <div class="guideline-v1-boundary" role="note"><strong>학생 공개 범위</strong><p>${esc(releaseMessage)}</p><span>현재 상태: 승인 claim ${guidelineCatalog.summary.approvedClaims || 0}개 · ${esc(item.useScope || "서지 탐색 및 검토용")}</span></div>
      <footer class="guideline-v1-detail-actions">
        ${item.url ? `<a class="button secondary" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">공식 원문 페이지 ↗</a>` : `<span class="button secondary disabled">공식 링크 확인 중</span>`}
        <button type="button" class="button primary" data-ask-guideline="${esc(item.id)}">이 문서에 대해 챗봇에게 질문</button>
      </footer>
    </article>
  </div>`;
}

function renderGuidelineLibrary() {
  const specialties = [...new Set(guidelineCatalog.items.flatMap((item) => item.specialties || []))]
    .sort((a, b) => (specialtyLabel[a] || a).localeCompare(specialtyLabel[b] || b, "ko"));
  const visible = matchingGuidelines(state.guidelineQuery, {specialty: state.guidelineSpecialty, status: state.guidelineStatus});
  const selected = guidelineCatalog.items.find((item) => item.id === state.selectedGuidelineId);
  const summary = guidelineCatalog.summary;
  if (state.guidelineView === "detail" && selected) return renderGuidelineDetail(selected);
  const shown = visible.slice(0, state.guidelineVisibleLimit);
  const activeFilterCount = Number(state.guidelineSpecialty !== "all") + Number(state.guidelineStatus !== "all");
  return `<section class="guideline-v1-library">
    <header class="guideline-v1-hero"><span class="eyebrow">Korean Guideline Library</span><h1>대한민국 임상 가이드라인</h1><p>실습과 학습에 필요한 국내 공식 문서를 빠르게 찾습니다. 원문을 복제하지 않고 발행기관 페이지로 연결합니다.</p></header>
    <div class="guideline-v1-kpis" aria-label="가이드라인 레지스트리 현황">
      <span><b>${summary.sources || guidelineCatalog.items.length}</b>등록 출처</span>
      <span class="verified"><b>${summary.verifiedLatest || 0}</b>최신판 확인</span>
      <span class="uncertain"><b>${summary.latestUncertain || 0}</b>재확인 필요</span>
      <span class="catalog"><b>${summary.catalogOnly || 0}</b>목록 등록</span>
      <span><b>${summary.approvedClaims || 0}</b>승인 claim</span>
    </div>
    ${state.guidelineStatusError ? `<div class="guideline-v1-alert compact"><div><strong>현황 정보 연결 지연</strong><p>문서 목록은 사용할 수 있지만 점검 현황 갱신에 실패했습니다.</p></div><button type="button" data-retry-guidelines>다시 시도</button></div>` : ""}
    <div class="guideline-v1-searchbar">
      <label><span aria-hidden="true">⌕</span><input id="guideline-search" value="${esc(state.guidelineQuery)}" placeholder="질환·학회·키워드 검색 (예: 심방세동, 폐렴)" autocomplete="off"></label>
      <button type="button" class="guideline-v1-mobile-filter" data-open-guideline-filters>필터${activeFilterCount ? ` ${activeFilterCount}` : ""}</button>
    </div>
    ${renderGuidelineFilterControls(specialties)}
    <div class="guideline-v1-result-head"><span><strong>${visible.length}</strong>개 문서</span><small>메타데이터 점검일 ${esc(String(guidelineCatalog.snapshotDate || "확인 중").slice(0, 10))}</small></div>
    ${state.guidelineLoading ? `<div class="guideline-v1-loading"><span class="spinner"></span><strong>가이드라인 목록을 불러오는 중입니다</strong></div>` : state.guidelineError && !guidelineCatalog.items.length ? `<div class="guideline-v1-alert"><div><strong>가이드라인 목록을 불러오지 못했습니다</strong><p>${esc(state.guidelineError)}</p></div><button type="button" data-retry-guidelines>다시 시도</button></div>` : ""}
    ${!state.guidelineLoading && guidelineCatalog.items.length ? `<div class="guideline-v1-list">${shown.map(renderGuidelineRow).join("") || `<div class="guideline-v1-empty"><strong>조건에 맞는 문서가 없습니다</strong><p>검색어나 필터를 바꿔보세요.</p><button type="button" data-reset-guideline-filters>검색·필터 초기화</button></div>`}</div>` : ""}
    ${state.guidelineError && guidelineCatalog.items.length ? `<div class="guideline-v1-alert compact"><div><strong>일부 목록 연결 지연</strong><p>${esc(state.guidelineError)}</p></div><button type="button" data-retry-guidelines>다시 시도</button></div>` : ""}
    ${shown.length < visible.length ? `<button type="button" class="guideline-v1-more" data-more-guidelines>문서 더 보기 <span>${visible.length - shown.length}개 남음</span></button>` : ""}
    ${state.guidelineFilterOpen ? `<div class="guideline-v1-filter-layer"><button type="button" class="guideline-v1-filter-backdrop" data-close-guideline-filters aria-label="필터 닫기"></button><section class="guideline-v1-filter-sheet" role="dialog" aria-modal="true" aria-label="가이드라인 필터"><header><strong>필터</strong><button type="button" data-close-guideline-filters aria-label="닫기">×</button></header>${renderGuidelineFilterControls(specialties, "sheet")}<footer><button type="button" data-reset-guideline-filters>초기화</button><button type="button" class="primary" data-close-guideline-filters>${visible.length}개 문서 보기</button></footer></section></div>` : ""}
  </section>`;
}

function assistantSourceRows(items) {
  return (items || []).map((raw) => {
    const item = raw.source || raw.guideline || raw;
    const title = item.title || item.name || item.source_title || "출처";
    const body = item.issuing_body || item.body || item.publisher || item.source_name || "";
    const year = item.publication_year || item.year || "";
    const url = item.official_landing_url || item.url || "";
    const status = normalizedGuidelineStatus(item.latest_status || item.currentness || item.status);
    return `<li><span class="source-dot ${status}"></span><div><strong>${esc(title)}</strong><small>${esc([body, year].filter(Boolean).join(" · "))} · ${esc(guidelineStatus[status].label)}</small></div>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">원문 ↗</a>` : ""}</li>`;
  }).join("");
}

function citationIds(section) {
  const explicit = Array.isArray(section?.citations) ? section.citations : [];
  const inline = String(section?.body || "").match(/\[(H|G)\d+\]/g) || [];
  return [...new Set([...explicit, ...inline.map((item) => item.slice(1, -1))])]
    .map((item) => String(item || "").trim().toUpperCase())
    .filter((item) => /^(H|G)\d+$/.test(item));
}

function sectionBody(value) {
  return inlineRichText(String(value || "").replace(/\s*\[(H|G)\d+\]/g, "")).replace(/\n/g, "<br>");
}

function inlineRichText(value, {labelPrefix = false} = {}) {
  let safe = esc(String(value || ""));
  safe = safe.replace(/\*\*([^*\n]{1,160})\*\*/g, "<strong>$1</strong>");
  if (labelPrefix && !safe.includes("<strong>")) {
    safe = safe.replace(/^([^:：\n]{1,28})([:：])/, "<strong>$1$2</strong>");
  }
  return safe;
}

function copilotAnswerStatus({result, answer, approvedClaims, blocked}) {
  const status = result?.answer_status || result?.status || "";
  if (status === "blocked_direct_identifiers" || result?.status === "privacy_blocked") return {tone: "blocked", label: "직접 식별정보 감지 · 검색 전 차단", detail: "입력은 저장하지 않았고 검색도 시작하지 않았습니다."};
  if (status === "evidence_insufficient") return {tone: "blocked", label: "직접 연결 근거 부족 · 답변 보류", detail: "질환명이나 핵심 증후군을 더 구체적으로 입력해 주세요."};
  if (status === "answer_withheld_citation_validation_failed") return {tone: "blocked", label: "본문 보류 · 인용 검증 실패", detail: "검증된 Harrison 위치만 유지했습니다."};
  if (status === "answer_withheld_current_guideline_claim_pending") return {tone: "blocked", label: "최신 국내 권고 · 검토 대기", detail: "승인 전 수치나 우선순위를 다른 근거로 대신 확정하지 않았습니다."};
  if (status === "answer_withheld_direct_support_missing") return {tone: "blocked", label: "직접 답변 보류 · 핵심 근거 부족", detail: "관련 주변 지식으로 답을 채우지 않았습니다."};
  if (["retrieval_ready_model_error", "retrieval_ready_model_unavailable"].includes(status)) return {tone: "locator", label: "답변 생성 지연 · 근거 위치 유지", detail: "근거 검색 결과는 아래에서 계속 확인할 수 있습니다."};
  if (status === "job_failed") return {tone: "blocked", label: "답변 작업 실패 · 다시 전송 필요", detail: "질문은 서버에 영구 저장되지 않았습니다."};
  if (result?.status === "network_error") return {tone: "blocked", label: "연결 오류 · 전송 완료 안 됨", detail: "네트워크 상태를 확인한 뒤 다시 시도해 주세요."};
  if (answer && approvedClaims.length) return {tone: "approved", label: "근거 기반 학습 답변", detail: ""};
  if (answer) return {tone: "harrison", label: "학습용 답변", detail: ""};
  return {tone: blocked ? "blocked" : "locator", label: "근거 위치 안내 · 답변 보류", detail: "확인 가능한 범위만 표시했습니다."};
}

function copilotLead(result) {
  return result?.answer?.answer_summary || result?.message || "직접 연결되는 근거를 찾지 못했습니다.";
}

function plainCopilotLead(result) {
  return String(copilotLead(result)).replace(/\*\*/g, "");
}

function shouldRevealCopilotResult(result) {
  return Boolean(result?.answer && !result?.blocked && !["job_failed", "blocked_direct_identifiers"].includes(result?.answer_status));
}

function renderAssistantResult(result, instanceId = "latest", reveal = null) {
  if (!result) return "";
  const focusMode = Boolean(state.copilotFocusMode);
  const safeInstance = String(instanceId || "latest").replace(/[^a-zA-Z0-9_-]/g, "-");
  const lead = copilotLead(result);
  const plainLead = plainCopilotLead(result);
  const isRevealing = Boolean(reveal?.active);
  const visibleLead = isRevealing ? plainLead.slice(0, Math.max(0, Number(reveal.offset || 0))) : lead;
  const blocked = Boolean(result.blocked || !result.answer);
  const answer = result.answer && typeof result.answer === "object" ? result.answer : null;
  const rawGuidelines = result.guidelines || result.sources || [];
  const harrison = result.harrison_sources || [];
  const approvedClaims = result.approved_guideline_claims || [];
  const concepts = result.ontology_matches || result.ontology?.matches || [];
  const followupConceptId = String(concepts[0]?.concept_id || "").trim();
  const reasons = result.reasons || result.block_reasons || [];
  const answerStatus = copilotAnswerStatus({result, answer, approvedClaims, blocked});
  const keyPoints = (answer?.key_points || []).slice(0, focusMode ? 5 : undefined);
  const sections = answer?.sections || [];
  const tables = answer?.tables || [];
  const followups = (answer?.suggested_followups || []).slice(0, focusMode ? 3 : undefined);
  const ontologyLabels = concepts.slice(0, 8).map((item) => item.label || item.title || item);
  const evidenceId = (cite) => `evidence-${safeInstance}-${String(cite || "")}`;
  const citationButtons = (cites) => cites.map((cite) => `<button type="button" data-citation-source="${esc(cite)}" aria-label="이 답변의 ${esc(cite)} 근거 위치 보기">${esc(cite)}</button>`).join("");
  const sectionRows = sections.map((section, index) => {
    const cites = citationIds(section);
    const content = `<div class="section-copy">${sectionBody(section.body)}</div>${cites.length ? `<div class="citation-row"><span>근거</span>${citationButtons(cites)}</div>` : ""}`;
    return focusMode
      ? `<section class="focus-section-row"><h4>${esc(section.title || `항목 ${index + 1}`)}</h4>${content}</section>`
      : `<details id="copilot-section-${safeInstance}-${index}" open><summary><span>${esc(section.title || `항목 ${index + 1}`)}</span><small>접기</small></summary>${content}</details>`;
  }).join("");
  const sectionsMarkup = sections.length
    ? focusMode
      ? `<details class="focus-detail-group"><summary><span>상세 설명</span><small>${sections.length}개 항목</small></summary><div class="focus-section-content">${sectionRows}</div></details>`
      : `<div class="copilot-sections">${sectionRows}</div>`
    : "";
  const tableRows = tables.map((table) => {
    const cites = citationIds(table);
    return `<section><h4>${esc(table.title || "핵심 비교")}</h4><div class="copilot-table-scroll"><table><thead><tr>${(table.columns || []).map((column) => `<th>${inlineRichText(column)}</th>`).join("")}</tr></thead><tbody>${(table.rows || []).map((row) => `<tr>${row.map((cell) => `<td>${inlineRichText(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${cites.length ? `<div class="citation-row"><span>근거</span>${citationButtons(cites)}</div>` : ""}</section>`;
  }).join("");
  const tablesMarkup = tables.length
    ? focusMode
      ? `<details class="focus-detail-group"><summary><span>표로 비교하기</span><small>${tables.length}개 표</small></summary><div class="copilot-answer-tables">${tableRows}</div></details>`
      : `<div class="copilot-answer-tables">${tableRows}</div>`
    : "";
  const evidenceMarkup = `<div class="copilot-evidence-below">
      <div class="evidence-divider"><span>근거와 탐색 경로</span><small>종류별 역할을 구분해 표시합니다</small></div>
      ${ontologyLabels.length ? `<section class="evidence-group ontology-evidence"><div class="evidence-heading"><h4>Ontology 해석</h4><span>탐색 정보 · 근거 아님</span></div><div class="concept-chips">${ontologyLabels.map((label) => `<span>${esc(label)}</span>`).join("")}</div></section>` : ""}
      ${harrison.length ? `<section class="evidence-group"><div class="evidence-heading"><h4>Harrison 22판 위치</h4><span>원문 발췌 없이 위치만 표시</span></div><div class="harrison-source-grid">${harrison.map((item) => `<article id="${esc(evidenceId(item.source_id))}" data-evidence-source="${esc(item.source_id)}"><b>${esc(item.source_id)}</b><div><strong>${esc(item.title)}</strong><small>${esc(item.edition || "22e")} · Ch.${esc(item.chapter)} · p.${esc(item.printed_page || "확인 필요")}</small></div></article>`).join("")}</div></section>` : `<div class="evidence-empty">직접 연결된 Harrison 위치가 없습니다.</div>`}
      ${approvedClaims.length ? `<section class="evidence-group"><div class="evidence-heading"><h4>교수 승인 국내 가이드라인 claim</h4><span>승인 범위 안에서만 사용</span></div><div class="approved-claim-grid">${approvedClaims.map((claim) => `<article id="${esc(evidenceId(claim.source_id))}" data-evidence-source="${esc(claim.source_id)}"><b>${esc(claim.source_id)}</b><div><strong>${esc(claim.object_text)}</strong><small>${esc(claim.population)} · ${esc(claim.source_title)} · p.${esc(claim.page || "확인")} ${claim.effective_version ? `· ${esc(claim.effective_version)}` : ""}</small><span>원문 변경·재검토 기한 만료 시 자동 차단</span></div><div class="claim-actions">${claim.official_landing_url ? `<a href="${esc(claim.official_landing_url)}" target="_blank" rel="noopener noreferrer">공식 원문 ↗</a>` : `<span>링크 확인 중</span>`}<a href="#review/medical">복습으로 이동 →</a></div></article>`).join("")}</div></section>` : `<div class="guideline-boundary"><strong>승인된 국내 권고 claim이 아직 없습니다</strong><span>관련 문서의 위치만 안내하며 권고 내용을 추측하지 않아요.</span></div>`}
      ${rawGuidelines.length ? `<section class="evidence-group related-documents"><div class="evidence-heading"><h4>함께 확인할 대한민국 가이드라인</h4><span>답변 근거 아님</span></div><ul class="assistant-sources">${assistantSourceRows(rawGuidelines)}</ul></section>` : ""}
    </div>`;
  return `<article data-answer-instance="${esc(safeInstance)}" aria-busy="${isRevealing}" class="assistant-answer copilot-document ${blocked ? "blocked" : ""} ${focusMode ? "focus-mode" : "full-mode"} ${isRevealing ? "is-typing" : ""}">
    <header class="answer-status"><span class="${answerStatus.tone}">${esc(answerStatus.label)}</span><small>${esc(answerStatus.detail)}</small></header>
    ${focusMode && answer && !blocked ? `<div class="focus-path" aria-label="집중 보기 순서"><span><b>1</b> 결론</span><i>→</i><span><b>2</b> ${keyPoints.length ? `핵심 ${keyPoints.length}개` : `상세 ${sections.length}개`}</span><i>→</i><span><b>3</b> ${followups.length ? "다음 질문" : "근거 확인"}</span></div>` : ""}
    <p class="answer-lead" data-answer-lead aria-live="${isRevealing ? "off" : "polite"}">${isRevealing ? esc(visibleLead).replace(/\n/g, "<br>") : inlineRichText(visibleLead).replace(/\n/g, "<br>")}</p>
    ${keyPoints.length ? `<section class="answer-key-points"><h4>Key points <small>${keyPoints.length}/5</small></h4><ul>${keyPoints.map((item) => { const cites = citationIds(item); return `<li><div>${inlineRichText(item.text || item, {labelPrefix: true})}</div>${cites.length ? `<span class="key-point-citations">${citationButtons(cites)}</span>` : ""}</li>`; }).join("")}</ul></section>` : ""}
    ${!focusMode && sections.length >= 3 ? `<nav class="answer-anchors" aria-label="답변 목차">${sections.map((section, index) => `<a href="#copilot-section-${safeInstance}-${index}">${esc(section.title || `항목 ${index + 1}`)}</a>`).join("")}</nav>` : ""}
    ${sectionsMarkup}
    ${tablesMarkup}
    ${reasons.length && !answer ? `<div class="block-reasons"><strong>현재 답변을 보류한 이유</strong>${reasons.map((reason) => `<span>${esc(reasonLabel(reason))}</span>`).join("")}</div>` : ""}
    ${answer?.uncertainties?.length ? `<aside class="answer-uncertainty"><strong>불확실성 · 지도전문의와 확인</strong><ul>${answer.uncertainties.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></aside>` : ""}
    ${focusMode ? `<details class="focus-detail-group focus-evidence"><summary><span>근거·출처 확인</span><small>${harrison.length + approvedClaims.length}개 직접 근거</small></summary>${evidenceMarkup}</details>` : evidenceMarkup}
    ${followups.length ? `<section class="answer-section focus-next"><h4>${focusMode ? "다음 한 가지를 골라 이어가기" : "이어서 물어볼 질문"}</h4><small>현재 Harrison 근거에서 답변 가능한 질문만 표시합니다.</small><div class="prompt-presets followups">${followups.map((item) => `<button type="button" data-prompt="${esc(item)}" data-followup-concept="${esc(followupConceptId)}">${esc(item)}</button>`).join("")}</div></section>` : ""}
    <div class="answer-caveat">학습용 초안이며 환자별 진단·처방 지시가 아닙니다. 실제 실습에서는 지도전문의·병원 지침·원문을 확인하세요.</div>
  </article>`;
}

function formatElapsed(seconds) {
  const safe = Math.max(0, Number(seconds || 0));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

function saveActiveCopilotJob(record) {
  try {
    sessionStorage.setItem(COPILOT_JOB_STORAGE_KEY, JSON.stringify({
      version: 1,
      job_id: record.job_id,
      question: record.question,
      mode: record.mode,
      started_at: record.started_at,
    }));
  } catch (_) {}
}

function loadActiveCopilotJob() {
  try {
    const record = JSON.parse(sessionStorage.getItem(COPILOT_JOB_STORAGE_KEY) || "null");
    if (!record || !/^mcj_[0-9TZ]+_[0-9a-f]{16}$/.test(String(record.job_id || ""))) return null;
    if (!String(record.question || "").trim()) return null;
    return record;
  } catch (_) {
    return null;
  }
}

function clearActiveCopilotJob() {
  try { sessionStorage.removeItem(COPILOT_JOB_STORAGE_KEY); } catch (_) {}
}

function stopCopilotTimer() {
  clearInterval(state.copilotTimer);
  state.copilotTimer = null;
}

function startCopilotTimer() {
  stopCopilotTimer();
  state.copilotTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.copilotStartedAt) / 1000);
    const target = document.querySelector("[data-copilot-elapsed]");
    if (target) target.textContent = formatElapsed(elapsed);
  }, 1000);
}

function scrollCopilotToLatest() {
  requestAnimationFrame(() => {
    const feed = document.querySelector(".chat-feed");
    feed?.scrollTo({top: feed.scrollHeight, behavior: "smooth"});
  });
}

function renderCopilotIfVisible() {
  if (route() === "clinical" && routeDetail() !== "library") renderClinical();
}

function stopCopilotReveal() {
  clearInterval(state.copilotRevealTimer);
  state.copilotRevealTimer = null;
}

function resumeCopilotReveal() {
  const messageIndex = state.clinicalMessages.findIndex((message) => message.role === "assistant" && message.reveal?.active);
  if (messageIndex < 0) {
    stopCopilotReveal();
    return;
  }
  const message = state.clinicalMessages[messageIndex];
  const fullText = plainCopilotLead(message.result);
  if (!fullText || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    message.reveal.active = false;
    message.reveal.offset = fullText.length;
    stopCopilotReveal();
    renderCopilotIfVisible();
    return;
  }
  if (state.copilotRevealTimer) return;
  const duration = Math.min(4200, Math.max(1400, fullText.length * 24));
  const tick = 24;
  const step = Math.max(1, Math.ceil(fullText.length / (duration / tick)));
  state.copilotRevealTimer = setInterval(() => {
    if (!message.reveal?.active) {
      stopCopilotReveal();
      return;
    }
    message.reveal.offset = Math.min(fullText.length, message.reveal.offset + step);
    const article = document.querySelector(`[data-answer-instance="turn-${messageIndex}"]`);
    const lead = article?.querySelector("[data-answer-lead]");
    if (lead) lead.textContent = fullText.slice(0, message.reveal.offset);
    if (message.reveal.offset < fullText.length) return;
    message.reveal.active = false;
    stopCopilotReveal();
    if (!article || !lead) return;
    lead.innerHTML = inlineRichText(copilotLead(message.result)).replace(/\n/g, "<br>");
    lead.setAttribute("aria-live", "polite");
    article.setAttribute("aria-busy", "false");
    article.classList.remove("is-typing");
    article.classList.add("is-revealed");
    scrollCopilotToLatest();
    resumeCopilotReveal();
  }, tick);
}

function renderCopilotConversation() {
  if (!state.clinicalMessages.length && !state.assistantBusy) {
    const counts = state.copilotStatus?.counts || {};
    const examplePrompts = activeCopilotExamplePrompts();
    const examples = examplePrompts.length
      ? `<div class="copilot-examples"><span>검증된 예시 질문</span>${examplePrompts.map((prompt) => `<button type="button" data-prompt="${esc(prompt)}">${esc(prompt)}</button>`).join("")}</div>`
      : "";
    return `<section class="copilot-welcome">
      <span class="eyebrow">Medical Learning Copilot</span>
      <h1>의학 질문은<br>여기에 바로 물어보세요</h1>
      <p>질문 유형을 고를 필요 없이 입력하면 Ontology가 의도와 분과를 해석하고 Harrison 22판 위치와 국내 공식 문서를 자동으로 연결합니다.</p>
      <div class="copilot-auto-route" aria-label="자동 근거 연결"><span>질문 이해</span><i>→</i><span>Ontology</span><i>→</i><span>Harrison 22e</span><i>→</i><span>국내 가이드라인</span></div>
      ${examples}
      <p class="copilot-data-note">Ontology ${counts.ontology_concepts || 616} · Harrison 22e 연결 ${counts.harrison_mapped_concepts || 550} · 국내 source ${guidelineCatalog.summary.sources || 0} (최신판 확인 ${guidelineCatalog.summary.verifiedLatest || 0}) · 승인 claim ${guidelineCatalog.summary.approvedClaims || 0}</p>
    </section>`;
  }
  const turns = state.clinicalMessages.map((message, index) => message.role === "user"
    ? `<div class="chat-turn user-turn"><div class="chat-bubble user-bubble ${message.redacted ? "redacted" : ""}"><small>${message.redacted ? "입력 내용 숨김" : "의학 질문"}</small><p>${esc(message.content)}</p></div></div>`
    : `<div class="chat-turn assistant-turn"><div class="chat-bubble assistant-bubble">${renderAssistantResult(message.result, `turn-${index}`, message.reveal)}</div></div>`).join("");
  const elapsed = state.copilotStartedAt ? Math.floor((Date.now() - state.copilotStartedAt) / 1000) : 0;
  const pending = state.assistantBusy ? `<div class="chat-turn assistant-turn"><div class="chat-bubble thinking copilot-progress"><div class="progress-head"><span class="spinner"></span><div><strong>근거를 확인하고 있습니다</strong><small>경과 <b data-copilot-elapsed>${formatElapsed(elapsed)}</b> · 복잡한 질문은 30–60초 걸릴 수 있어요</small></div></div><ol><li>직접 식별정보 점검</li><li>Ontology 해석과 Harrison 위치 검색</li><li>허용된 근거 범위 안에서 답변 작성</li></ol><p class="copilot-recovery-note">이 작업은 같은 브라우저 탭에서 새로고침해도 이어집니다.</p><button type="button" data-cancel-copilot>답변 작업 취소</button></div></div>` : "";
  return `${turns}${pending}`;
}

function renderStudyQa() {
  const hasConversation = state.clinicalMessages.length || state.assistantBusy;
  const clearControl = state.clearChatConfirm
    ? `<span class="clear-chat-confirm">서버 사본이 없어 되돌릴 수 없어요. <button type="button" data-confirm-clear>지우기</button><button type="button" data-cancel-clear>취소</button></span>`
    : `<button type="button" data-clear-chat ${state.clinicalMessages.length && !state.assistantBusy ? "" : "disabled"}>대화 지우기</button>`;
  return `<section class="copilot-shell">
    <div class="copilot-toolbar"><span>${state.assistantBusy && state.activeCopilotJobId ? "진행 중인 답변 작업은 같은 브라우저 탭에서 새로고침 후 복구돼요" : hasConversation ? "완료된 대화는 브라우저 메모리에만 유지돼요" : "학습·실습 준비용 · 직접 식별정보 입력 금지"}</span><nav><button type="button" class="focus-toggle ${state.copilotFocusMode ? "active" : ""}" data-focus-mode aria-pressed="${state.copilotFocusMode}"><i></i>집중 보기</button><a href="#review/medical">의학 지식 복습</a><a href="#clinical/library">가이드라인 라이브러리</a>${clearControl}</nav></div>
    <div class="chat-feed" aria-live="polite">${renderCopilotConversation()}</div>
    <form id="study-qa-form" class="copilot-composer">
      <div class="composer-box"><textarea id="study-question" rows="2" placeholder="${state.assistantBusy ? "현재 답변이 끝나면 새 질문을 보낼 수 있어요" : "의학 질문을 입력하세요"}" ${state.assistantBusy ? "disabled" : ""}>${esc(state.assistantQuery)}</textarea><button class="composer-send" data-send-question type="submit" aria-label="질문 보내기" ${state.assistantBusy || !state.assistantQuery.trim() ? "disabled" : ""}>↑</button></div>
      <div class="composer-meta"><span>${state.assistantBusy ? "답변 생성 중에는 중복 전송이 잠겨요" : "Enter 전송 · Shift+Enter 줄바꿈"}</span><span>이름·환자번호·연락처는 검색 전에 차단돼요</span></div>
    </form>
  </section>`;
}

function finishCopilotResult(result, {question, mode, runToken}) {
  if (runToken !== state.copilotRunToken) return;
  stopCopilotTimer();
  clearActiveCopilotJob();
  state.activeCopilotJobId = "";
  state.copilotJobStage = "";
  state.copilotStartedAt = 0;
  state.assistantBusy = false;
  state.assistantResult = result;
  if (result?.status === "privacy_blocked" || result?.answer_status === "blocked_direct_identifiers") {
    state.clinicalMessages[state.clinicalMessages.length - 1] = {role: "user", content: "직접 식별정보가 포함된 질문은 화면에 다시 표시하지 않습니다.", mode, redacted: true};
  }
  const shouldReveal = shouldRevealCopilotResult(result);
  state.clinicalMessages.push({role: "assistant", result, reveal: shouldReveal ? {active: true, offset: 0} : null});
  state.assistantQuery = result?.status === "job_failed" ? question : "";
  renderCopilotIfVisible();
  scrollCopilotToLatest();
}

function failedCopilotResult(message) {
  return {
    status: "job_failed",
    answer_status: "job_failed",
    blocked: true,
    message: message || "답변 작업을 완료하지 못했습니다. 질문을 다시 보내 주세요.",
    reasons: [message || "답변 작업 실패"],
    ontology_matches: [],
    harrison_sources: [],
    guidelines: [],
    approved_guideline_claims: [],
  };
}

async function pollCopilotJob({jobId, question, mode, runToken}) {
  let consecutiveErrors = 0;
  while (runToken === state.copilotRunToken && state.activeCopilotJobId === jobId) {
    try {
      const job = await api(`/api/student/medical-copilot/jobs/${encodeURIComponent(jobId)}`);
      consecutiveErrors = 0;
      if (runToken !== state.copilotRunToken || state.activeCopilotJobId !== jobId) return;
      state.copilotJobStage = job.stage || job.status || "running";
      if (job.status === "done") {
        finishCopilotResult(job.result || failedCopilotResult("완료된 답변 내용을 불러오지 못했습니다."), {question, mode, runToken});
        return;
      }
      if (job.status === "failed") {
        finishCopilotResult(failedCopilotResult(job.error), {question, mode, runToken});
        return;
      }
      if (job.status === "cancelled") {
        await cancelActiveCopilotJob({notifyServer: false});
        return;
      }
    } catch (error) {
      consecutiveErrors += 1;
      if (error.status === 404) {
        clearActiveCopilotJob();
        stopCopilotTimer();
        state.activeCopilotJobId = "";
        state.copilotJobStage = "";
        state.copilotStartedAt = 0;
        state.assistantBusy = false;
        if (state.clinicalMessages.at(-1)?.role === "user") state.clinicalMessages.pop();
        state.assistantQuery = question;
        renderCopilotIfVisible();
        toast("복구할 답변 작업을 찾지 못했습니다. 질문을 입력창에 복원했습니다.");
        return;
      }
      if (consecutiveErrors >= 3) {
        finishCopilotResult(failedCopilotResult("답변 작업 상태를 확인하지 못했습니다. 네트워크를 확인한 뒤 다시 보내 주세요."), {question, mode, runToken});
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function cancelActiveCopilotJob({notifyServer = true} = {}) {
  const jobId = state.activeCopilotJobId;
  const question = state.clinicalMessages.at(-1)?.role === "user" ? state.clinicalMessages.at(-1).content : state.assistantQuery;
  state.copilotRunToken += 1;
  state.activeCopilotJobId = "";
  state.copilotJobStage = "";
  state.copilotStartedAt = 0;
  state.assistantBusy = false;
  stopCopilotTimer();
  clearActiveCopilotJob();
  if (state.clinicalMessages.at(-1)?.role === "user") state.clinicalMessages.pop();
  state.assistantQuery = question || "";
  renderCopilotIfVisible();
  if (notifyServer && jobId) {
    try { await api(`/api/student/medical-copilot/jobs/${encodeURIComponent(jobId)}/cancel`, {method: "POST", body: "{}"}); } catch (_) {}
  }
  toast("답변 작업을 취소했습니다. 질문은 입력창에 복원했습니다.");
}

async function submitStudyQa(question) {
  const mode = "concept";
  const conceptId = state.pendingCopilotConceptId;
  state.pendingCopilotConceptId = "";
  const history = state.clinicalMessages.slice(-6).map((message) => message.role === "user"
    ? {role: "user", content: message.redacted ? "" : message.content}
    : {role: "assistant", content: message.result?.answer?.answer_summary || message.result?.message || "근거 검색 결과"});
  const runToken = state.copilotRunToken + 1;
  state.copilotRunToken = runToken;
  state.assistantQuery = "";
  state.assistantBusy = true;
  state.assistantResult = null;
  state.clearChatConfirm = false;
  state.activeCopilotJobId = "";
  state.copilotJobStage = "privacy_preflight";
  state.copilotStartedAt = Date.now();
  state.clinicalMessages.push({role: "user", content: question, mode});
  renderCopilotIfVisible();
  startCopilotTimer();
  try {
    const payload = await api("/api/student/medical-copilot/jobs", {method: "POST", body: JSON.stringify({mode, query: question, history, concept_id: conceptId})});
    const job = payload.job || payload;
    if (runToken !== state.copilotRunToken) return;
    if (job.status === "done") {
      finishCopilotResult(job.result || failedCopilotResult("답변 내용을 불러오지 못했습니다."), {question, mode, runToken});
      return;
    }
    if (!job.job_id) throw new Error("답변 작업 식별자를 받지 못했습니다.");
    state.activeCopilotJobId = job.job_id;
    state.copilotJobStage = job.stage || job.status || "queued";
    saveActiveCopilotJob({job_id: job.job_id, question, mode, started_at: state.copilotStartedAt});
    renderCopilotIfVisible();
    await pollCopilotJob({jobId: job.job_id, question, mode, runToken});
  } catch (error) {
    if (runToken !== state.copilotRunToken) return;
    finishCopilotResult(failedCopilotResult(error.message), {question, mode, runToken});
  }
}

function restoreActiveCopilotJob() {
  const record = loadActiveCopilotJob();
  if (!record) {
    clearActiveCopilotJob();
    return false;
  }
  const question = String(record.question || "").trim();
  const mode = "concept";
  const runToken = state.copilotRunToken + 1;
  state.copilotRunToken = runToken;
  state.assistantBusy = true;
  state.activeCopilotJobId = record.job_id;
  state.copilotJobStage = "recovering";
  state.copilotStartedAt = Number(record.started_at) || Date.now();
  state.assistantQuery = "";
  state.clinicalMessages = [{role: "user", content: question, mode}];
  startCopilotTimer();
  render();
  pollCopilotJob({jobId: record.job_id, question, mode, runToken});
  return true;
}

function bindClinicalActions(active) {
  if (active === "library") {
    document.querySelector("#guideline-search")?.addEventListener("input", (event) => {
      state.guidelineQuery = event.target.value;
      state.guidelineVisibleLimit = 20;
      renderClinical();
      requestAnimationFrame(() => {
        const input = document.querySelector("#guideline-search");
        input?.focus();
        input?.setSelectionRange(state.guidelineQuery.length, state.guidelineQuery.length);
      });
    });
    document.querySelectorAll("[data-guideline-specialty]").forEach((button) => button.addEventListener("click", () => {
      state.guidelineSpecialty = button.dataset.guidelineSpecialty;
      state.guidelineVisibleLimit = 20;
      renderClinical();
    }));
    document.querySelectorAll("[data-guideline-status]").forEach((button) => button.addEventListener("click", () => {
      state.guidelineStatus = button.dataset.guidelineStatus;
      state.guidelineVisibleLimit = 20;
      renderClinical();
    }));
    document.querySelectorAll("[data-open-guideline]").forEach((button) => button.addEventListener("click", () => {
      state.selectedGuidelineId = button.dataset.openGuideline;
      state.guidelineView = "detail";
      renderClinical();
      window.scrollTo({top: 0, behavior: "smooth"});
    }));
    document.querySelector("[data-back-guidelines]")?.addEventListener("click", () => {
      state.guidelineView = "list";
      state.selectedGuidelineId = "";
      renderClinical();
    });
    document.querySelectorAll("[data-ask-guideline]").forEach((button) => button.addEventListener("click", () => {
      const item = guidelineCatalog.items.find((entry) => entry.id === button.dataset.askGuideline);
      if (!item) return;
      state.assistantQuery = `${item.title}의 핵심 개념과 국내 가이드라인에서 직접 확인해야 할 범위를 설명해줘`;
      state.assistantResult = null;
      location.hash = "#clinical";
    }));
    document.querySelector("[data-open-guideline-filters]")?.addEventListener("click", () => { state.guidelineFilterOpen = true; renderClinical(); });
    document.querySelectorAll("[data-close-guideline-filters]").forEach((button) => button.addEventListener("click", () => { state.guidelineFilterOpen = false; renderClinical(); }));
    document.querySelectorAll("[data-reset-guideline-filters]").forEach((button) => button.addEventListener("click", () => {
      state.guidelineQuery = "";
      state.guidelineSpecialty = "all";
      state.guidelineStatus = "all";
      state.guidelineVisibleLimit = 20;
      renderClinical();
    }));
    document.querySelector("[data-more-guidelines]")?.addEventListener("click", () => { state.guidelineVisibleLimit += 20; renderClinical(); });
    document.querySelectorAll("[data-retry-guidelines]").forEach((button) => button.addEventListener("click", async () => {
      state.guidelineLoading = true;
      renderClinical();
      await loadGuidelineCatalog();
      renderClinical();
    }));
  }
  if (active === "chat") {
    document.querySelector("[data-focus-mode]")?.addEventListener("click", () => {
      state.copilotFocusMode = !state.copilotFocusMode;
      try { localStorage.setItem(COPILOT_FOCUS_STORAGE_KEY, state.copilotFocusMode ? "on" : "off"); } catch (_) {}
      renderClinical();
      toast(state.copilotFocusMode ? "집중 보기: 결론·핵심·다음 질문만 먼저 보여요." : "전체 보기: 세부 설명과 근거를 펼쳐 보여요.");
    });
    document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
      state.assistantQuery = button.dataset.prompt;
      state.pendingCopilotConceptId = button.dataset.followupConcept || "";
      const textarea = document.querySelector("#study-question");
      if (textarea) { textarea.value = state.assistantQuery; textarea.focus(); }
      const send = document.querySelector("[data-send-question]");
      if (send) send.disabled = state.assistantBusy || !state.assistantQuery.trim();
    }));
    document.querySelector("[data-clear-chat]")?.addEventListener("click", () => { state.clearChatConfirm = true; renderClinical(); });
    document.querySelector("[data-cancel-clear]")?.addEventListener("click", () => { state.clearChatConfirm = false; renderClinical(); });
    document.querySelector("[data-confirm-clear]")?.addEventListener("click", () => { stopCopilotReveal(); state.clinicalMessages = []; state.assistantResult = null; state.assistantQuery = ""; state.clearChatConfirm = false; renderClinical(); });
    document.querySelector("[data-cancel-copilot]")?.addEventListener("click", () => cancelActiveCopilotJob());
    document.querySelectorAll("[data-citation-source]").forEach((button) => button.addEventListener("click", () => {
      const answerCard = button.closest("[data-answer-instance]");
      const sourceId = button.dataset.citationSource;
      const target = [...(answerCard?.querySelectorAll("[data-evidence-source]") || [])]
        .find((item) => item.dataset.evidenceSource === sourceId);
      if (!target) return;
      let enclosingDetails = target.closest("details");
      while (enclosingDetails && answerCard?.contains(enclosingDetails)) {
        enclosingDetails.open = true;
        enclosingDetails = enclosingDetails.parentElement?.closest("details");
      }
      requestAnimationFrame(() => {
        target.scrollIntoView({behavior: "smooth", block: "center"});
        target.classList.remove("citation-pulse");
        requestAnimationFrame(() => target.classList.add("citation-pulse"));
      });
      setTimeout(() => target.classList.remove("citation-pulse"), 1300);
    }));
    const questionInput = document.querySelector("#study-question");
    questionInput?.addEventListener("input", (event) => {
      state.assistantQuery = event.target.value;
      state.pendingCopilotConceptId = "";
      const send = document.querySelector("[data-send-question]");
      if (send) send.disabled = state.assistantBusy || !state.assistantQuery.trim();
    });
    questionInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && window.matchMedia("(min-width: 721px)").matches) {
        event.preventDefault();
        document.querySelector("#study-qa-form")?.requestSubmit();
      }
    });
    document.querySelector("#study-qa-form")?.addEventListener("submit", (event) => { event.preventDefault(); const question = document.querySelector("#study-question")?.value.trim() || ""; if (!question) return toast("질문을 입력해 주세요."); submitStudyQa(question); });
    resumeCopilotReveal();
  }
}

function renderClinical() {
  const detail = routeDetail();
  if (detail === "case") history.replaceState(null, "", `${location.pathname}${location.search}#clinical`);
  const active = detail === "library" ? "library" : "chat";
  state.clinicalTab = active;
  app.innerHTML = active === "chat"
    ? `<div class="medical-copilot-view">${renderStudyQa()}</div>`
    : `<div class="guideline-v1-shell">${clinicalTabs(active)}${renderGuidelineLibrary()}</div>`;
  bindClinicalActions(active);
}

function render() {
  syncNav();
  if (!state.catalog) return;
  const current = route();
  if (current === "library") renderLibrary();
  else if (current === "concepts") renderConcepts();
  else if (current === "review") renderReview();
  else if (current === "clinical") renderClinical();
  else if (current === "report") renderReport();
  else renderHome();
}

async function boot() {
  try {
    const [qbank, catalog, bookmarks, review, claimReview, concepts, analytics] = await Promise.all([
      api("/api/student/qbank"),
      api("/api/student/catalog"),
      api("/api/student/bookmarks"),
      api("/api/student/review?limit=30"),
      api("/api/student/medical-copilot/review?limit=30"),
      api("/api/student/concepts"),
      api("/api/practice/analytics/student"),
      loadGuidelineCatalog(),
      loadCopilotStatus(),
    ]);
    Object.assign(state, {qbank, catalog, bookmarks: bookmarks.question_ids || [], review, claimReview, concepts, analytics});
    if (!restoreActiveCopilotJob()) render();
  } catch (error) {
    app.innerHTML = `<section class="card empty-card" style="margin-top:50px"><strong>학습 데이터를 불러오지 못했습니다</strong><p>${esc(error.message)}</p><button class="button primary" onclick="location.reload()">다시 시도</button></section>`;
  }
}

window.addEventListener("hashchange", render);
boot();
