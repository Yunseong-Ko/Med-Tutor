const root = document.querySelector("#reader");
const layout = document.querySelector("#reader-layout");
const navigatorRoot = document.querySelector("#question-navigator");
const navigatorMobile = document.querySelector("#navigator-mobile");
const navigatorBackdrop = document.querySelector("#navigator-backdrop");
const modalRoot = document.querySelector("#reader-modal");
const toastEl = document.querySelector("#toast");
const topBookmark = document.querySelector("#bookmark-top");
const params = new URLSearchParams(location.search);

const state = {
  items: [],
  index: 0,
  mode: params.get("mode") === "exam" ? "exam" : "study",
  bookmarks: new Set(),
  answers: new Map(),
  eliminations: new Map(),
  feedbacks: new Map(),
  tabs: new Map(),
  results: new Map(),
  fsrsSaved: new Set(),
  startedAt: Date.now(),
  elapsed: 0,
  saving: false,
  navigatorCollapsed: false,
  navigatorOpen: false,
  unansweredOnly: false,
  submitConfirmOpen: false,
  enteredAt: Date.now(),     // 현재 문항이 화면에 뜬 시각(문항별 풀이 시간 계측)
  dwell: new Map(),          // question.id → 누적 체류 ms (세션 누적이 아니라 문항 단위로 time_ms를 보낸다)
  reviewMode: false,         // 시험 모드 제출 후 문항별 해설 복습
  finishedAt: null,          // 세션 종료 시각 — 결과 '풀이 시간'과 상단 타이머를 여기서 고정
  badgeTips: new Map(),      // question.id → 열린 배지 index (S2 탭하면 의미 표시)
  choiceExplOpen: new Set(), // 나머지 선지 해설 펼침 (S1)
  revisionOpen: new Set(),   // 개정 이력 펼침 (S1)
  lightbox: null,            // {src, caption} (S3 이미지 확대)
  justGraded: null,          // 방금 채점한 문항 id — 채점 직후 렌더 1회만 모션(시험 모드·복습에서는 설정하지 않는다)
};
const GRADE_SCROLL_DELAY_MS = 300;   // 고른 선지의 채점 표시를 먼저 보여 준 뒤 해설로 스크롤
const sessionId = `student_v3_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toastEl.classList.remove("show"), 2300);
}

async function api(url, options = {}) {
  const response = await fetch(url, {...options, headers: {"content-type": "application/json", ...(options.headers || {})}});
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const error = new Error(payload.detail || "요청을 처리하지 못했습니다.");
    error.status = response.status;
    throw error;
  }
  return payload;
}

function current() {
  return state.items[state.index];
}

function selectedFor(question = current()) {
  return question ? (state.answers.get(question.id) || null) : null;
}

function eliminatedFor(question = current()) {
  if (!question) return new Set();
  if (!state.eliminations.has(question.id)) state.eliminations.set(question.id, new Set());
  return state.eliminations.get(question.id);
}

function feedbackFor(question = current()) {
  return question ? (state.feedbacks.get(question.id) || null) : null;
}

function tabFor(question = current()) {
  return question ? (state.tabs.get(question.id) || "explanation") : "explanation";
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function imageUrl(image) {
  return typeof image === "string" ? image : image?.src || image?.url || "";
}

function imageCaption(image) {
  return typeof image === "string" ? "제시자료" : image?.cap || image?.caption || "제시자료";
}

function answeredCount() {
  return state.items.filter((question) => state.answers.has(question.id)).length;
}

// ── 2026-09-06 학생 업데이트(S1~S4, 클로드 디자인 Student_Reader_Updates.dc.html) ──────────────
// S3. lab_box 문자열("백혈구 9,800/mm³(4,000~10,000), CRP 0.8 mg/dL(<0.5)" 또는 줄 단위) → 표 행
function parseLabRows(text) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const tokens = raw.includes("\n") ? raw.split(/\n+/) : raw.split(/,\s+(?=[^\d\s(])/);
  return tokens.map((token) => token.trim()).filter(Boolean).map((token) => {
    const withRef = token.match(/^(.+?)\s+(\S.*?)\s*\(([^()]*)\)\s*$/);
    if (withRef) return {name: withRef[1], value: withRef[2], ref: withRef[3]};
    const attached = token.match(/^(.+?)\s+([^\s(]+)\(([^()]*)\)\s*$/);
    if (attached) return {name: attached[1], value: attached[2], ref: attached[3]};
    const colon = token.match(/^(.+?):\s*(.+)$/);
    if (colon) return {name: colon[1], value: colon[2], ref: ""};
    const spaced = token.match(/^(\S+(?:\s\S+)?)\s+(\S.*)$/);
    if (spaced) return {name: spaced[1], value: spaced[2], ref: ""};
    return {name: token, value: "", ref: ""};
  });
}

function stimulusHtml(question) {
  const text = question.stimulus;
  if (!text) return "";
  const rows = parseLabRows(text);
  // 표로 바꾸는 조건: 행 2개 이상 + 절반 이상에 값 + 절반 이상에 수치/단위(서술형 소견 나열은 문장으로 둔다)
  const quantitative = (row) => /\d/.test(`${row.value} ${row.ref}`) || /(mg|g\/dL|dL|mL|mmol|mEq|IU|U\/L|%|mmHg|×10|x10|\/mm|μ|㎍|㎕|㎗)/i.test(row.value);
  const structured = rows.length >= 2
    && rows.filter((row) => row.value).length >= Math.ceil(rows.length / 2)
    && rows.filter(quantitative).length >= Math.ceil(rows.length / 2);
  if (!structured) return `<span class="stimulus">${esc(text)}</span>\n\n`;
  return `<div class="lab-table" role="table" aria-label="검사 결과"><div class="lab-head" role="row"><span>검사</span><span>결과</span><span>참조치</span></div>${rows.map((row) => `<div class="lab-row" role="row"><span>${esc(row.name)}</span><span class="v">${esc(row.value)}</span><span class="ref">${row.ref ? `(${esc(row.ref)})` : ""}</span></div>`).join("")}</div>`;
}

// S4. 난이도 티어 칩(없으면 표시하지 않음 — '미분류'는 세트 화면에서만 안내)
function tierChipHtml(question) {
  const tier = question?.difficulty_tier;
  if (!tier) return "";
  const cls = {"하": "low", "중": "mid", "상": "high"}[tier] || "";
  return `<span class="tier-chip ${cls}">난이도 ${esc(tier)}</span>`;
}

// S2. 신뢰 배지 3단 — 미충족은 회색 비활성(07 브리프), 탭하면 의미 표시
const BADGE_TIPS = {
  evidence: {fully: "교과서 인용 쪽에서 문항 내용이 완전히 확인됨(✓)", partially: "핵심 내용은 교과서에서 확인됐으나 일부 세부는 미확인(△)", none: "교과서 근거 검증이 아직 완료되지 않은 문항입니다"},
  reviewed: {on: "졸업반 검토단 3인이 평정했고 '그대로/경미 수정' 판정을 받음", off: "검토단 판정이 없거나 수정 검토 중인 문항입니다"},
  faculty: {on: "담당 교수가 문항을 확정 승인함", off: "아직 교수 확정 전 — 승인되면 이 배지가 켜집니다"},
};

function badgeDefs(badges) {
  if (!badges) return [];
  const level = badges.evidence_verified?.level || "none";
  const evidenceOn = level === "fully" || level === "partially";
  return [
    {on: evidenceOn, icon: level === "fully" ? "✓" : "△", label: "교과서 근거 검증", tip: BADGE_TIPS.evidence[evidenceOn ? level : "none"]},
    {on: Boolean(badges.student_reviewed), icon: "✓", label: badges.student_reviewed?.label || "졸업반 3인 검토 통과", tip: BADGE_TIPS.reviewed[badges.student_reviewed ? "on" : "off"]},
    {on: badges.faculty_approved === true, icon: "✓", label: "교수 승인", tip: BADGE_TIPS.faculty[badges.faculty_approved ? "on" : "off"]},
  ];
}

function badgesHtml(question, badges, {interactive = true} = {}) {
  const defs = badgeDefs(badges);
  if (!defs.length) return "";
  const open = state.badgeTips.get(question.id);
  return `<div class="trust-badges">${defs.map((def, index) => interactive
    ? `<button type="button" class="trust-badge ${def.on ? "on" : "off"} ${open === index ? "active" : ""}" data-badge-index="${index}" title="${esc(def.tip)}" aria-pressed="${open === index}">${esc(def.icon)} ${esc(def.label)}</button>`
    : `<span class="trust-badge ${def.on ? "on" : "off"}" title="${esc(def.tip)}">${esc(def.icon)} ${esc(def.label)}</span>`).join("")}${interactive ? `<span class="trust-hint">배지를 탭하면 의미 표시</span>` : ""}</div>${interactive && open != null && defs[open] ? `<div class="trust-tip">${esc(defs[open].tip)}</div>` : ""}`;
}

// 근거 블록: 계약 §C `{locators:[...], badge}` 와 레거시 배열 둘 다 허용
function evidenceEntries(feedback) {
  const evidence = feedback.evidence;
  if (Array.isArray(evidence)) {
    return evidence.map((item) => ({
      label: item.source_id || "근거",
      locator: item.locator || item.title || "학습 근거",
      note: item.support_scope === "chapter_pointer_not_claim_entailment" ? "Harrison 위치 안내" : item.source_type === "answer_key_aligned_learning_explanation" ? "정답키와 대조된 학습 해설" : "공개 가능한 근거 위치",
    }));
  }
  if (evidence && Array.isArray(evidence.locators)) {
    return evidence.locators.map((locator) => {
      const text = String(locator);
      const split = text.match(/^(.+?)\s+(Ch\..*)$/);
      return {label: split ? split[1] : "교과서", locator: split ? split[2] : text, note: "근거 위치(교과서 장·쪽) — 원문은 도서관·교과서에서 확인"};
    });
  }
  return [];
}

// S3. 이미지 라이트박스
function ensureLightboxRoot() {
  let el = document.querySelector("#reader-lightbox");
  if (!el) {
    el = document.createElement("div");
    el.id = "reader-lightbox";
    el.className = "reader-lightbox";
    document.body.appendChild(el);
    el.addEventListener("click", (event) => { if (event.target === el || event.target.closest("[data-close-lightbox]")) closeLightbox(); });
  }
  return el;
}

function openLightbox(src, caption) {
  state.lightbox = {src, caption};
  const el = ensureLightboxRoot();
  el.innerHTML = `<button type="button" class="lightbox-close" data-close-lightbox aria-label="닫기">✕</button><figure><img src="${esc(src)}" alt="${esc(caption)}"><figcaption>${esc(caption)} · 탭하면 닫기</figcaption></figure>`;
  el.classList.add("show");
  document.body.classList.add("lightbox-open");
  el.querySelector("[data-close-lightbox]")?.focus();
}

function closeLightbox() {
  state.lightbox = null;
  const el = document.querySelector("#reader-lightbox");
  if (el) { el.classList.remove("show"); el.innerHTML = ""; }
  document.body.classList.remove("lightbox-open");
}

function mediaFigureHtml(image, {zoom = true, fallbackCaption = ""} = {}) {
  const src = imageUrl(image);
  // 캡션은 modality만(정답 단서 없음). 문자열 이미지는 캡션이 없으므로 문항의 modality(subtopic)로 대체한다.
  const caption = typeof image === "string" && fallbackCaption ? fallbackCaption : imageCaption(image);
  return `<figure ${zoom ? `class="zoomable" data-lightbox-src="${esc(src)}" data-lightbox-caption="${esc(caption)}" title="탭하면 확대" tabindex="0" role="button" aria-label="${esc(caption)} 확대 보기"` : ""}><img src="${esc(src)}" alt="${esc(caption)}">${zoom ? `<span class="zoom-mark" aria-hidden="true">⤢</span>` : ""}<figcaption>${esc(caption)}</figcaption></figure>`;
}

function updateTop() {
  const question = current();
  document.querySelector("#session-title").textContent = question?.exam || question?.course_name || "문항 풀이";
  document.querySelector("#session-progress").textContent = `${state.index + 1}/${state.items.length}`;
  topBookmark.classList.toggle("on", state.bookmarks.has(question?.id));
  topBookmark.textContent = state.bookmarks.has(question?.id) ? "★" : "☆";
  navigatorMobile.textContent = `${state.index + 1}/${state.items.length}`;
}

function navigatorStatus(question, index) {
  const feedback = feedbackFor(question);
  if ((state.mode === "study" || state.reviewMode) && feedback) return feedback.is_correct ? "correct" : "wrong";
  if (state.answers.has(question.id)) return "answered";
  return "unanswered";
}

function closeMobileNavigator() {
  state.navigatorOpen = false;
  document.body.classList.remove("navigator-open");
  navigatorBackdrop.classList.remove("show");
}

// 현재 문항에 머문 시간을 누적하고 시계를 다시 맞춘다. 탭이 숨겨진 동안은 세지 않는다.
function noteDwell() {
  const question = current();
  if (!question || !state.enteredAt) return;
  const spent = Date.now() - state.enteredAt;
  if (spent > 0 && spent < 6 * 60 * 60 * 1000) state.dwell.set(question.id, (state.dwell.get(question.id) || 0) + spent);
  state.enteredAt = Date.now();
}

function questionTimeMs(question) {
  const base = state.dwell.get(question.id) || 0;
  const live = question === current() && state.enteredAt ? Math.max(0, Date.now() - state.enteredAt) : 0;
  return Math.max(1000, Math.round(base + live));
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) noteDwell();          // 떠나는 순간까지 누적
  else state.enteredAt = Date.now();          // 돌아오면 다시 시작
});

function goTo(index) {
  if (index < 0 || index >= state.items.length || state.saving) return;
  noteDwell();
  state.index = index;
  state.enteredAt = Date.now();
  closeMobileNavigator();
  render();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function inReview() {
  return state.reviewMode;
}

function showsFeedback(question) {
  return (state.mode === "study" || state.reviewMode) && Boolean(feedbackFor(question));
}

function renderNavigator() {
  if (!state.items.length) return;
  const answered = answeredCount();
  const visibleIndexes = state.items
    .map((question, index) => ({question, index}))
    .filter(({question}) => !state.unansweredOnly || !state.answers.has(question.id));
  navigatorRoot.innerHTML = `
    <header class="navigator-head">
      <button type="button" class="navigator-collapse" data-collapse-navigator aria-label="${state.navigatorCollapsed ? "문항 탐색 펼치기" : "문항 탐색 접기"}">${state.navigatorCollapsed ? "›" : "‹"}</button>
      <div><span>문항 탐색</span><strong>${answered}/${state.items.length} 응답</strong></div>
      <button type="button" class="navigator-close-mobile" data-close-navigator aria-label="문항 목록 닫기">×</button>
    </header>
    <div class="navigator-content">
      <div class="navigator-progress"><i style="width:${state.items.length ? (answered / state.items.length) * 100 : 0}%"></i></div>
      <label class="unanswered-toggle"><input type="checkbox" data-unanswered-only ${state.unansweredOnly ? "checked" : ""}><span>미응답만 보기</span></label>
      <div class="question-number-grid">
        ${visibleIndexes.length ? visibleIndexes.map(({question, index}) => {
          const status = navigatorStatus(question, index);
          return `<button type="button" class="${status} ${index === state.index ? "current" : ""} ${state.bookmarks.has(question.id) ? "bookmarked" : ""}" data-question-index="${index}" aria-label="${index + 1}번 문항, ${status}">${index + 1}</button>`;
        }).join("") : `<p class="navigator-empty">남은 미응답 문항이 없습니다.</p>`}
      </div>
      <div class="navigator-legend"><span><i class="answered"></i>응답</span>${(state.mode === "study" || state.reviewMode) ? `<span><i class="correct"></i>정답</span><span><i class="wrong"></i>오답</span>` : ""}<span><i class="bookmarked"></i>북마크</span></div>
      <div class="navigator-pager"><button type="button" data-go-previous ${state.index === 0 ? "disabled" : ""}>← 이전</button><button type="button" data-go-next ${state.index === state.items.length - 1 ? "disabled" : ""}>다음 →</button></div>
    </div>`;
  layout.classList.toggle("navigator-collapsed", state.navigatorCollapsed);
  navigatorRoot.querySelector("[data-collapse-navigator]")?.addEventListener("click", () => {
    state.navigatorCollapsed = !state.navigatorCollapsed;
    renderNavigator();
  });
  navigatorRoot.querySelector("[data-close-navigator]")?.addEventListener("click", closeMobileNavigator);
  navigatorRoot.querySelector("[data-unanswered-only]")?.addEventListener("change", (event) => {
    state.unansweredOnly = event.target.checked;
    renderNavigator();
  });
  navigatorRoot.querySelectorAll("[data-question-index]").forEach((button) => button.addEventListener("click", () => goTo(Number(button.dataset.questionIndex))));
  navigatorRoot.querySelector("[data-go-previous]")?.addEventListener("click", () => goTo(state.index - 1));
  navigatorRoot.querySelector("[data-go-next]")?.addEventListener("click", () => goTo(state.index + 1));
}

function choiceHtml(choice, feedback) {
  const question = current();
  const number = String(choice.n);
  const selected = selectedFor(question) === number;
  const eliminated = eliminatedFor(question).has(number);
  let resultClass = "";
  if (feedback) {
    if ((feedback.answer_keys || []).includes(number)) resultClass = "correct";
    else if (selected) resultClass = "wrong";
  }
  return `<button class="choice ${selected ? "selected" : ""} ${eliminated ? "eliminated" : ""} ${resultClass}" data-choice="${esc(number)}">
    <span class="choice-number">${esc(number)}</span><span class="choice-text">${esc(choice.text)}</span>
    <span class="eliminate" data-eliminate="${esc(number)}" title="선택지 지우기">⊘</span>
  </button>`;
}

function safeAxisMessage(feedback) {
  if (feedback.ontology_analytics_approved !== true) return "";
  return feedback.structured_explanation?.axis_focus?.message || feedback.target_axis_label || "";
}

function feedbackBody(question, feedback) {
  const activeTab = tabFor(question);
  if (activeTab === "explanation") {
    const detail = feedback.structured_explanation || {};
    const keyPoints = detail.key_points || feedback.points || [];
    const reasoning = detail.clinical_reasoning || [];
    const reasoningHtml = (reasoning.length ? reasoning : [detail.summary || feedback.explanation || "등록된 해설이 없습니다."])
      .map((paragraph) => `<p>${esc(paragraph)}</p>`).join("");
    const axisMessage = safeAxisMessage(feedback);
    const choiceExpl = feedback.choice_explanations || {};
    const answerKeys = feedback.answer_keys || [];
    const mine = (feedback.selected_choices || [])[0];
    const answerKey = answerKeys[0];
    const wrong = !feedback.is_correct && mine && !answerKeys.includes(mine);
    const whyAttractive = wrong ? String(choiceExpl[String(mine)] || "").trim() : "";
    const whyCorrect = String(choiceExpl[String(answerKey)] || "").trim();
    const guided = Boolean(whyCorrect);          // AIGEN 문항: 선지해설이 있을 때만 ①→⑥ 안내 흐름
    const step = (n) => guided ? `${["①", "②", "③", "④", "⑤"][n - 1]} ` : "";
    const evidence = evidenceEntries(feedback);
    const badges = feedback.trust_badges || question.trust_badges || null;
    const revision = feedback.revision_note;
    const otherChoices = question.choices.filter((choice) => String(choice.n) !== String(answerKey) && !(wrong && String(choice.n) === String(mine)));
    const otherOpen = state.choiceExplOpen.has(question.id) || !guided;
    const revisionOpen = state.revisionOpen.has(question.id);
    const ankiCount = (feedback.anki_cards || []).length;
    return `${wrong && whyAttractive ? `<div class="expl-step attractive"><span>${step(1)}내가 고른 ${esc(mine)}번 — 왜 끌렸는지</span><p>${esc(whyAttractive)}</p></div>` : ""}
      ${whyCorrect ? `<div class="expl-step correct"><span>${step(2)}정답 ${esc(answerKey)}번 — 왜 정답인가</span><p>${esc(whyCorrect)}</p></div>` : ""}
      ${guided ? `<h3 class="feedback-subtitle step-title">${step(3)}정답 해설</h3>` : ""}
      <div class="explanation-hero"><span>핵심 결론</span><strong>${esc(detail.conclusion || detail.summary || feedback.explanation || "등록된 해설이 없습니다.")}</strong>${detail.correct_answer ? `<small>정답 · ${esc(detail.correct_answer)}</small>` : ""}</div>
      ${reasoning.length || !guided ? `<h3 class="feedback-subtitle first">임상 추론</h3><div class="clinical-reasoning">${reasoningHtml}</div>` : ""}
      ${detail.correct_answer_rationale ? `<div class="answer-rationale"><span>정답 근거</span><p>${esc(detail.correct_answer_rationale)}</p></div>` : ""}
      ${axisMessage ? `<div class="axis-focus"><span>10-Axis</span><strong>${esc(axisMessage)}</strong></div>` : ""}
      ${keyPoints.length ? `<h3 class="feedback-subtitle">핵심 학습 포인트</h3><ul class="key-point-list">${keyPoints.map((point) => `<li>${esc(point)}</li>`).join("")}</ul>` : ""}
      <h3 class="feedback-subtitle">${step(4)}근거 · 검증</h3>
      ${evidence.length ? `<div class="evidence-list">${evidence.map((item) => `<article class="evidence-item"><span>${esc(item.label)}</span><div><strong>${esc(item.locator)}</strong><small>${esc(item.note)}</small></div></article>`).join("")}</div>` : `<div class="context-state">연결된 공개 근거 위치가 없습니다.</div>`}
      ${badges ? badgesHtml(question, badges, {interactive: false}) : ""}
      ${revision ? `<div class="revision-box"><button type="button" class="revision-toggle" data-toggle-revision aria-expanded="${revisionOpen}"><span>개정 이력${revision.date ? ` <small>${esc(revision.date)}</small>` : ""}${revision.answer_changed ? ` <em>정답 변경</em>` : ""}</span><span>${revisionOpen ? "⌃" : "⌵"}</span></button>${revisionOpen ? `<p>${esc(revision.summary || "")}</p>` : ""}</div>` : ""}
      ${otherChoices.length ? `<h3 class="feedback-subtitle">${guided ? "나머지 선지 해설" : "선지별 분석"}${guided ? ` <button type="button" class="text-toggle" data-toggle-choice-expl>${otherOpen ? "접기" : `${otherChoices.length}개 보기`}</button>` : ""}</h3>${otherOpen ? `<div class="choice-explanations">${otherChoices.map((choice) => `<div class="choice-expl"><b>${esc(choice.n)}</b><span>${esc(choiceExpl[String(choice.n)] || "선택지별 해설이 없습니다.")}</span></div>`).join("")}</div>` : ""}` : ""}
      ${guided ? `<div class="anki-pointer"><span>${step(5)}연관 Anki 카드 <b>${ankiCount}</b></span>${ankiCount ? `<button type="button" class="text-toggle" data-open-anki>Anki 탭에서 보기 →</button>` : `<small>이 문항에는 연결된 카드가 없습니다.</small>`}</div>` : ""}`;
  }
  if (activeTab === "points") {
    return `<h3>출제 포인트</h3>${(feedback.points || []).length ? `<ul>${feedback.points.map((point) => `<li>${esc(point)}</li>`).join("")}</ul>` : `<div class="context-state">등록된 출제 포인트가 없습니다.</div>`}`;
  }
  if (activeTab === "media") {
    const media = feedback.connected_media || question.imgs || [];
    return `<h3>검사·자료</h3>${media.length ? `<div class="question-media feedback-media">${media.map((image) => mediaFigureHtml(image, {fallbackCaption: question.qtype === "image_interpretation" ? String(question.subtopic || "") : ""})).join("")}</div>` : feedback.media_requirement_satisfied_by_text ? `<div class="context-state ready">필요한 영상 소견이 문제 본문에 문장으로 제시되어 있습니다.</div>` : `<div class="context-state">이 문항에는 연결된 검사·이미지 자료가 없습니다.</div>`}`;
  }
  if (activeTab === "concept") {
    const note = feedback.learning_context?.concept_note || {};
    const hasApprovedRoute = feedback.ontology_analytics_approved === true && Boolean(feedback.concept_label || feedback.target_axis_label);
    const axisMessage = safeAxisMessage(feedback);
    return `<h3>개념 노트</h3>
      ${hasApprovedRoute && feedback.concept_label ? `<div class="ontology-route"><span>개념</span><strong>${esc(feedback.concept_label)}</strong><small>이 문항과 연결된 학습 개념</small></div>` : ""}
      ${hasApprovedRoute && axisMessage ? `<div class="ontology-route"><span>10-Axis</span><strong>${esc(feedback.target_axis_label || axisMessage)}</strong><small>이번 문항이 확인한 사고 축</small></div>` : ""}
      <div class="context-state ${hasApprovedRoute || note.status === "ready" ? "ready" : ""}">${esc(note.message || note.title || (hasApprovedRoute ? "이 문항의 개념과 학습 축이 연결되어 있습니다." : "연결된 개념 노트가 없습니다."))}</div>
      ${note.status === "ready" ? Object.entries(note.sections || {}).map(([title, section]) => `<h3 style="margin-top:18px">${esc(title)}</h3><p>${esc(section?.body || "")}</p>`).join("") : ""}`;
  }
  const cards = feedback.anki_cards || [];
  return `<h3>Anki 카드</h3>${cards.length ? `<div class="anki-list">${cards.map((card, index) => `<article class="anki-item"><span>Card ${index + 1}</span><strong>${esc(card.anki_text || card.front || card.plain_text || "")}</strong>${card.plain_text && card.plain_text !== card.anki_text ? `<p>${esc(card.plain_text)}</p>` : ""}<small>${esc((card.tags || []).join(" · "))}</small></article>`).join("")}</div>` : `<div class="context-state">현재 제공 가능한 Anki 카드가 없습니다.</div>`}<div class="context-state ready">문항의 기억 평가는 FSRS 복습 일정에 반영됩니다.</div>`;
}

function feedbackHtml(question, feedback) {
  const tabs = [["explanation", "해설"], ["points", "출제 포인트"], ["media", "검사·자료"], ["concept", "개념 노트"], ["anki", "Anki"]];
  return `<section class="feedback-wrap"><div class="result-banner ${feedback.is_correct ? "correct" : "wrong"}"><strong>${feedback.is_correct ? "✓ 정답이에요" : "✕ 다시 확인해볼 문항이에요"}</strong><span>· 내 선택 ${esc((feedback.selected_choices || []).join(", "))} · 정답 ${esc((feedback.answer_keys || []).join(", "))}</span></div>
    <div class="feedback-panel"><div class="feedback-tabs">${tabs.map(([id, label]) => `<button class="${tabFor(question) === id ? "active" : ""}" data-feedback-tab="${id}">${label}</button>`).join("")}</div><div class="feedback-body">${feedbackBody(question, feedback)}</div></div>
    <div class="fsrs-card"><div><strong>이 문항을 얼마나 기억했나요?</strong><p>응답에 따라 FSRS-6가 다음 복습 시점을 계산합니다.</p></div><div class="rating-buttons">${[[1, "Again"], [2, "Hard"], [3, "Good"], [4, "Easy"]].map(([value, label]) => `<button data-fsrs-rating="${value}" ${state.fsrsSaved.has(question.id) ? "disabled" : ""}>${label}</button>`).join("")}</div></div>
  </section>`;
}

function renderQuestion() {
  const question = current();
  const selected = selectedFor(question);
  const feedback = feedbackFor(question);
  const feedbackVisible = showsFeedback(question);
  // 채점 직후 첫 렌더에만 모션 클래스를 건다. 탭 전환·배지 토글 같은 재렌더에서는 다시 재생되지 않는다.
  const justGraded = feedbackVisible && state.mode === "study" && !state.reviewMode && state.justGraded === question.id;
  state.justGraded = null;
  root.classList.toggle("just-graded", justGraded);
  const choicesLocked = feedbackVisible || state.reviewMode;
  const primaryDisabled = state.saving || (!state.reviewMode && state.mode === "study" && !feedback && selected == null);
  const primaryLabel = state.saving
    ? "저장 중…"
    : state.reviewMode
      ? (state.index === state.items.length - 1 ? "결과 요약으로" : "다음 문항 →")
      : state.mode === "study" && !feedback
        ? "정답 확인"
        : state.index === state.items.length - 1
          ? state.mode === "exam" ? "시험 제출" : "세션 완료"
          : "다음 문항 →";
  root.innerHTML = `
    <div class="reader-meta"><div><span class="mode-chip ${state.reviewMode ? "review" : ""}">${state.reviewMode ? "복습 · 제출 완료" : state.mode === "study" ? "학습 모드" : "시험 모드"}</span>${tierChipHtml(question)}<span>${esc(question.course_name || question.course || question.subject)}</span><span>·</span><span>${esc(question.major || "미분류")}</span></div><span>문항 ID · ${esc(question.id)}</span></div>
    ${question.trust_badges ? badgesHtml(question, question.trust_badges) : ""}
    <article class="question-card">
      <div class="question-stem">${stimulusHtml(question)}${esc(question.stem)}</div>
      ${(question.imgs || []).length ? `<div class="question-media">${question.imgs.map((image) => mediaFigureHtml(image, {fallbackCaption: question.qtype === "image_interpretation" ? String(question.subtopic || "") : ""})).join("")}</div>` : ""}
      <div class="choices${choicesLocked ? " locked" : ""}">${question.choices.map((choice) => choiceHtml(choice, feedbackVisible ? feedback : null)).join("")}</div>
    </article>
    ${state.mode === "exam" && !state.reviewMode ? `<div class="exam-note">시험 모드에서는 세션 제출 전까지 정답·해설·개념 연결을 공개하지 않습니다. 문항 목록에서 자유롭게 이동하고 답을 바꿀 수 있습니다.</div>` : ""}
    <div class="reader-actionbar"><button type="button" class="button secondary reader-previous" data-main-previous ${state.index === 0 ? "disabled" : ""}>← 이전</button><p>${state.reviewMode ? `제출한 답안은 바뀌지 않습니다 · <a href="#" data-back-to-result>결과 요약으로 돌아가기</a>` : state.mode === "study" ? (feedback ? "아래 학습 피드백을 확인한 뒤 다음 문항으로 이동하세요." : "답안을 선택하면 서버에서 정답을 확인합니다.") : `${answeredCount()}/${state.items.length}문항 응답 · 마지막에 한 번에 제출합니다.`}</p><button id="primary-action" class="button primary" ${primaryDisabled ? "disabled" : ""}>${primaryLabel}</button></div>
    ${feedbackVisible ? feedbackHtml(question, feedback) : ""}`;
  root.querySelectorAll(".choice").forEach((button) => button.addEventListener("click", (event) => {
    if (event.target.closest(".eliminate") || showsFeedback(question) || state.reviewMode) return;
    const number = button.dataset.choice;
    if (eliminatedFor(question).has(number)) return;
    if (selectedFor(question) === number) state.answers.delete(question.id);
    else state.answers.set(question.id, number);
    render();
  }));
  root.querySelectorAll(".eliminate").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (showsFeedback(question) || state.reviewMode) return;
    const number = button.dataset.eliminate;
    const eliminated = eliminatedFor(question);
    eliminated.has(number) ? eliminated.delete(number) : eliminated.add(number);
    if (selectedFor(question) === number) state.answers.delete(question.id);
    render();
  }));
  root.querySelector("#primary-action")?.addEventListener("click", primaryAction);
  root.querySelector("[data-back-to-result]")?.addEventListener("click", (event) => { event.preventDefault(); renderResult(); });
  root.querySelector("[data-main-previous]")?.addEventListener("click", () => goTo(state.index - 1));
  root.querySelectorAll("[data-feedback-tab]").forEach((button) => button.addEventListener("click", () => {
    state.tabs.set(question.id, button.dataset.feedbackTab);
    renderQuestion();
  }));
  root.querySelectorAll("[data-badge-index]").forEach((button) => button.addEventListener("click", () => {
    const index = Number(button.dataset.badgeIndex);
    state.badgeTips.set(question.id, state.badgeTips.get(question.id) === index ? null : index);
    renderQuestion();
  }));
  root.querySelectorAll("[data-lightbox-src]").forEach((figure) => {
    const open = () => openLightbox(figure.dataset.lightboxSrc, figure.dataset.lightboxCaption);
    figure.addEventListener("click", open);
    figure.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
    });
  });
  root.querySelector("[data-toggle-choice-expl]")?.addEventListener("click", () => {
    state.choiceExplOpen.has(question.id) ? state.choiceExplOpen.delete(question.id) : state.choiceExplOpen.add(question.id);
    renderQuestion();
  });
  root.querySelector("[data-toggle-revision]")?.addEventListener("click", () => {
    state.revisionOpen.has(question.id) ? state.revisionOpen.delete(question.id) : state.revisionOpen.add(question.id);
    renderQuestion();
  });
  root.querySelector("[data-open-anki]")?.addEventListener("click", () => {
    state.tabs.set(question.id, "anki");
    renderQuestion();
  });
  root.querySelectorAll("[data-fsrs-rating]").forEach((button) => button.addEventListener("click", () => saveFsrs(Number(button.dataset.fsrsRating), button)));
}

function render() {
  if (!state.items.length) return;
  renderNavigator();
  renderQuestion();
  renderModal();
  updateTop();
}

async function submitQuestion(question, selected, timeMs = null) {
  return api(`/api/student/questions/${encodeURIComponent(question.id)}/answer`, {
    method: "POST",
    body: JSON.stringify({
      event_id: `${sessionId}_${question.id}`,
      session_id: sessionId,
      selected_choices: [String(selected)],
      time_ms: timeMs ?? questionTimeMs(question),
      time_scope: "question",
      mode: state.mode,
      schema_version: 2,
      is_bookmarked: state.bookmarks.has(question.id),
    }),
  });
}

function resultRecord(question, selected, feedback) {
  return {
    questionId: question.id,
    topic: question.topic || question.major || question.subject,
    stem: question.stem,
    selected: String(selected),
    answer: (feedback.answer_keys || []).join(","),
    isCorrect: Boolean(feedback.is_correct),
  };
}

async function primaryAction() {
  if (state.saving) return;
  const question = current();
  const selected = selectedFor(question);
  const feedback = feedbackFor(question);
  if (state.reviewMode) {
    if (state.index === state.items.length - 1) renderResult();
    else goTo(state.index + 1);
    return;
  }
  if (state.mode === "study" && !feedback) {
    if (selected == null) return;
    state.saving = true;
    render();
    try {
      const result = await submitQuestion(question, selected);
      state.feedbacks.set(question.id, result);
      state.results.set(question.id, resultRecord(question, selected, result));
      state.saving = false;
      state.justGraded = question.id;
      render();
      const reduceMotion = prefersReducedMotion();
      const scrollToFeedback = () => {
        if (current().id !== question.id || !showsFeedback(question)) return;   // 그 사이 다른 문항으로 이동했으면 스크롤하지 않는다
        window.scrollTo({top: document.querySelector(".feedback-wrap")?.offsetTop - 80 || 0, behavior: reduceMotion ? "instant" : "smooth"});
      };
      if (reduceMotion) scrollToFeedback();
      else setTimeout(scrollToFeedback, GRADE_SCROLL_DELAY_MS);
    } catch (error) {
      state.saving = false;
      render();
      toast(error.message);
    }
    return;
  }
  if (state.index === state.items.length - 1) {
    if (state.mode === "exam") {
      state.submitConfirmOpen = true;
      renderModal();
    } else {
      renderResult();
    }
    return;
  }
  goTo(state.index + 1);
}

function renderModal() {
  if (!state.submitConfirmOpen) {
    modalRoot.innerHTML = "";
    return;
  }
  const answered = answeredCount();
  const unanswered = state.items.length - answered;
  modalRoot.innerHTML = `<div class="reader-modal-backdrop" data-close-submit-modal></div><section class="reader-modal" role="dialog" aria-modal="true" aria-labelledby="submit-title">
    <span class="eyebrow">Exam Submission</span><h2 id="submit-title">시험을 제출할까요?</h2><p>제출하면 정답과 해설이 공개되고, 현재 답안은 더 이상 바꿀 수 없습니다.</p>
    <dl><div><dt>전체 문항</dt><dd>${state.items.length}</dd></div><div><dt>응답 완료</dt><dd>${answered}</dd></div><div class="${unanswered ? "warning" : ""}"><dt>미응답</dt><dd>${unanswered}</dd></div></dl>
    <div class="reader-modal-actions"><button type="button" class="button secondary" data-close-submit-modal>계속 풀기</button><button type="button" class="button primary" data-confirm-submit ${answered ? "" : "disabled"}>제출하고 결과 보기</button></div>
  </section>`;
  modalRoot.querySelectorAll("[data-close-submit-modal]").forEach((button) => button.addEventListener("click", () => {
    state.submitConfirmOpen = false;
    renderModal();
  }));
  modalRoot.querySelector("[data-confirm-submit]")?.addEventListener("click", submitExam);
}

async function submitExam() {
  state.submitConfirmOpen = false;
  noteDwell();
  // 문항별 시간을 전송 전에 고정한다 — 순차 POST 지연이 현재 문항 시간에 섞이지 않도록
  const times = new Map(state.items.map((question) => [question.id, questionTimeMs(question)]));
  state.finishedAt = state.finishedAt || Date.now();
  state.saving = true;
  render();
  try {
    for (const question of state.items) {
      const selected = state.answers.get(question.id);
      if (!selected) continue;
      const feedback = await submitQuestion(question, selected, times.get(question.id));
      state.feedbacks.set(question.id, feedback);
      state.results.set(question.id, resultRecord(question, selected, feedback));
    }
    state.saving = false;
    renderResult();
  } catch (error) {
    state.saving = false;
    render();
    toast(error.message);
  }
}

function enterReview(index) {
  state.reviewMode = true;
  state.submitConfirmOpen = false;
  layout.classList.remove("result-layout");
  topBookmark.hidden = false;
  navigatorMobile.hidden = false;
  state.enteredAt = Date.now();
  goTo(index);
}

function renderResult() {
  noteDwell();
  state.reviewMode = false;
  state.justGraded = null;
  root.classList.remove("just-graded");
  if (!state.finishedAt) state.finishedAt = Date.now();
  const finishedElapsed = Math.floor((state.finishedAt - state.startedAt) / 1000);
  const total = state.items.length;
  const resultRows = state.items.map((question) => state.results.get(question.id) || {
    questionId: question.id,
    topic: question.topic || question.major || question.subject,
    stem: question.stem,
    selected: "",
    answer: "",
    isCorrect: false,
    unanswered: true,
  });
  const correct = resultRows.filter((item) => item.isCorrect).length;
  const unanswered = resultRows.filter((item) => item.unanswered).length;
  const wrong = resultRows.filter((item) => !item.isCorrect && !item.unanswered);
  const percent = total ? Math.round((correct / total) * 100) : 0;
  const answeredRows = resultRows.filter((item) => !item.unanswered).length;
  const unansweredRows = resultRows.filter((item) => item.unanswered);
  const firstWrongIndex = resultRows.findIndex((item) => !item.unanswered && !item.isCorrect);
  const firstAnsweredIndex = resultRows.findIndex((item) => !item.unanswered);
  document.querySelector("#session-title").textContent = "세션 결과";
  document.querySelector("#session-progress").textContent = `${correct}/${total}`;
  topBookmark.hidden = true;
  navigatorMobile.hidden = true;
  layout.classList.add("result-layout");
  navigatorRoot.innerHTML = "";
  root.innerHTML = `<section class="result-page"><article class="card result-hero"><span class="eyebrow" style="color:#76d7ca">Session Complete</span><h1>${state.mode === "exam" ? "시험을 제출했습니다" : "학습을 완료했습니다"}</h1><p>실제 제출 기록이 리포트와 복습 일정에 반영됩니다.</p><div class="result-score">${percent}%</div></article>
    <div class="result-grid"><article class="card summary-card"><span>정답</span><strong>${correct}/${total}</strong></article><article class="card summary-card"><span>풀이 시간</span><strong>${formatTime(finishedElapsed)}</strong></article><article class="card summary-card"><span>오답 · 미응답</span><strong>${wrong.length} · ${unanswered}</strong></article></div>
    ${answeredRows ? `<div class="result-review-hint"><strong>문항을 누르면 해설·근거·신뢰 배지를 볼 수 있습니다.</strong><span>제출한 답안은 바뀌지 않고, 복습 평가(FSRS)는 여기서도 남길 수 있습니다.</span>${firstWrongIndex >= 0 ? `<button type="button" class="button secondary small" data-review-index="${firstWrongIndex}">틀린 문항부터 복습 →</button>` : `<button type="button" class="button secondary small" data-review-index="${firstAnsweredIndex}">해설 보기 →</button>`}</div>` : ""}
    <section class="result-items">${resultRows.map((item, index) => `<article class="card result-item ${item.unanswered ? "unanswered" : item.isCorrect ? "" : "wrong"} ${item.unanswered ? "" : "clickable"}" ${item.unanswered ? "" : `data-review-index="${index}" role="button" tabindex="0" aria-label="${index + 1}번 문항 해설 보기"`}><span class="mark">${item.unanswered ? "−" : item.isCorrect ? "✓" : "!"}</span><div class="row-main"><h3>${esc(item.topic)}</h3><p>${esc(item.stem)}</p></div><span>${item.unanswered ? "미응답" : `${esc(item.selected)} → ${esc(item.answer)}`}</span></article>`).join("")}</section>
    <div class="result-actions"><a class="button primary" href="/student/#report">리포트 보기 →</a>${wrong.length ? `<a class="button secondary" href="/student/reader.html?ids=${encodeURIComponent(wrong.map((item) => item.questionId).join(","))}&mode=study&count=${wrong.length}">오답 다시 풀기</a>` : ""}${unansweredRows.length ? `<a class="button secondary" href="/student/reader.html?ids=${encodeURIComponent(unansweredRows.map((item) => item.questionId).join(","))}&mode=study&count=${unansweredRows.length}">미응답 ${unansweredRows.length}문항 풀기</a>` : ""}${state.bookmarks.size ? `<a class="button secondary" href="/student/reader.html?ids=${encodeURIComponent([...state.bookmarks].join(","))}&mode=study&count=${state.bookmarks.size}">북마크 학습</a>` : ""}<a class="button secondary" href="/student/#library">서재로 돌아가기</a></div>
  </section>`;
  root.querySelectorAll("[data-review-index]").forEach((el) => {
    const open = () => enterReview(Number(el.dataset.reviewIndex));
    el.addEventListener("click", open);
    el.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
  });
}

async function saveFsrs(rating, button) {
  const question = current();
  if (state.fsrsSaved.has(question.id)) return;
  button.disabled = true;
  try {
    const payload = await api("/api/student/fsrs/reviews", {method: "POST", body: JSON.stringify({event_id: `${sessionId}_${question.id}_fsrs`, question_id: question.id, rating})});
    state.fsrsSaved.add(question.id);
    const due = payload.card?.due ? new Date(payload.card.due).toLocaleString("ko-KR", {month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit"}) : "다음 일정";
    toast(`FSRS 복습 일정 저장 · ${due}`);
    render();
  } catch (error) {
    button.disabled = false;
    toast(error.message);
  }
}

async function toggleBookmark() {
  const question = current();
  const on = !state.bookmarks.has(question.id);
  topBookmark.disabled = true;
  try {
    await api(`/api/student/questions/${encodeURIComponent(question.id)}/bookmark`, {method: "PATCH", body: JSON.stringify({on})});
    on ? state.bookmarks.add(question.id) : state.bookmarks.delete(question.id);
    toast(on ? "북마크했습니다." : "북마크를 해제했습니다.");
    renderNavigator();
    updateTop();
  } catch (error) {
    toast(error.message);
  } finally {
    topBookmark.disabled = false;
  }
}

async function boot() {
  try {
    const [qbank, bookmarks] = await Promise.all([api("/api/student/qbank"), api("/api/student/bookmarks")]);
    let items = (qbank.questions || []).filter((question) => question.practice_ready !== false);
    const ids = (params.get("ids") || "").split(",").filter(Boolean);
    const exam = params.get("exam");
    const courseId = params.get("courseId");
    const count = Math.max(1, Math.min(100, Number(params.get("count")) || 20));
    if (ids.length) {
      const byId = new Map(items.map((question) => [question.id, question]));
      items = ids.map((id) => byId.get(id)).filter(Boolean);
    } else if (exam) {
      items = items.filter((question) => question.exam === exam);
    } else if (courseId) {
      items = items.filter((question) => question.course_id === courseId);
    }
    state.items = items.slice(0, count);
    state.bookmarks = new Set(bookmarks.question_ids || []);
    if (!state.items.length) throw new Error("선택한 범위에 공개된 문항이 없습니다.");
    render();
  } catch (error) {
    layout.classList.add("result-layout");
    navigatorRoot.innerHTML = "";
    root.innerHTML = `<section class="card empty-card" style="margin-top:60px"><strong>문항을 열 수 없습니다</strong><p>${esc(error.message)}</p><a class="button primary" href="/student/#library">서재로 돌아가기</a></section>`;
  }
}

topBookmark.addEventListener("click", toggleBookmark);
navigatorMobile.addEventListener("click", () => {
  state.navigatorOpen = true;
  document.body.classList.add("navigator-open");
  navigatorBackdrop.classList.add("show");
});
navigatorBackdrop.addEventListener("click", closeMobileNavigator);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (state.lightbox) closeLightbox();
    if (state.submitConfirmOpen) {
      state.submitConfirmOpen = false;
      renderModal();
    }
    closeMobileNavigator();
  }
});
setInterval(() => {
  if (state.finishedAt) return;   // 세션 종료 후(결과·복습)에는 타이머를 멈춘다
  state.elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
  const timer = document.querySelector("#timer");
  if (timer) timer.textContent = formatTime(state.elapsed);
}, 1000);
boot();
