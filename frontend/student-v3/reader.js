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
};
const sessionId = `student_v3_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
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
  if (state.mode === "study" && feedback) return feedback.is_correct ? "correct" : "wrong";
  if (state.answers.has(question.id)) return "answered";
  return "unanswered";
}

function closeMobileNavigator() {
  state.navigatorOpen = false;
  document.body.classList.remove("navigator-open");
  navigatorBackdrop.classList.remove("show");
}

function goTo(index) {
  if (index < 0 || index >= state.items.length || state.saving) return;
  state.index = index;
  closeMobileNavigator();
  render();
  window.scrollTo({top: 0, behavior: "smooth"});
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
      <div class="navigator-legend"><span><i class="answered"></i>응답</span>${state.mode === "study" ? `<span><i class="correct"></i>정답</span><span><i class="wrong"></i>오답</span>` : ""}<span><i class="bookmarked"></i>북마크</span></div>
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
    const evidence = feedback.evidence || [];
    const detail = feedback.structured_explanation || {};
    const keyPoints = detail.key_points || feedback.points || [];
    const reasoning = detail.clinical_reasoning || [];
    const reasoningHtml = (reasoning.length ? reasoning : [detail.summary || feedback.explanation || "등록된 해설이 없습니다."])
      .map((paragraph) => `<p>${esc(paragraph)}</p>`).join("");
    const axisMessage = safeAxisMessage(feedback);
    return `<div class="explanation-hero"><span>핵심 결론</span><strong>${esc(detail.conclusion || detail.summary || feedback.explanation || "등록된 해설이 없습니다.")}</strong>${detail.correct_answer ? `<small>정답 · ${esc(detail.correct_answer)}</small>` : ""}</div>
      <h3 class="feedback-subtitle first">임상 추론</h3><div class="clinical-reasoning">${reasoningHtml}</div>
      ${detail.correct_answer_rationale ? `<div class="answer-rationale"><span>정답 근거</span><p>${esc(detail.correct_answer_rationale)}</p></div>` : ""}
      ${axisMessage ? `<div class="axis-focus"><span>10-Axis</span><strong>${esc(axisMessage)}</strong></div>` : ""}
      ${keyPoints.length ? `<h3 class="feedback-subtitle">핵심 학습 포인트</h3><ul class="key-point-list">${keyPoints.map((point) => `<li>${esc(point)}</li>`).join("")}</ul>` : ""}
      <h3 class="feedback-subtitle">선지별 분석</h3><div class="choice-explanations">${question.choices.map((choice) => `<div class="choice-expl"><b>${esc(choice.n)}</b><span>${esc(feedback.choice_explanations?.[String(choice.n)] || "선택지별 해설이 없습니다.")}</span></div>`).join("")}</div>
      <h3 class="feedback-subtitle">근거·출처</h3>${evidence.length ? `<div class="evidence-list">${evidence.map((item) => `<article class="evidence-item"><span>${esc(item.source_id || "근거")}</span><div><strong>${esc(item.locator || item.title || "학습 근거")}</strong><small>${esc(item.support_scope === "chapter_pointer_not_claim_entailment" ? "Harrison 위치 안내" : item.source_type === "answer_key_aligned_learning_explanation" ? "정답키와 대조된 학습 해설" : "공개 가능한 근거 위치")}</small></div></article>`).join("")}</div>` : `<div class="context-state">연결된 공개 근거 위치가 없습니다.</div>`}`;
  }
  if (activeTab === "points") {
    return `<h3>출제 포인트</h3>${(feedback.points || []).length ? `<ul>${feedback.points.map((point) => `<li>${esc(point)}</li>`).join("")}</ul>` : `<div class="context-state">등록된 출제 포인트가 없습니다.</div>`}`;
  }
  if (activeTab === "media") {
    const media = feedback.connected_media || question.imgs || [];
    return `<h3>검사·자료</h3>${media.length ? `<div class="question-media feedback-media">${media.map((image) => `<figure><img src="${esc(imageUrl(image))}" alt="${esc(imageCaption(image))}"><figcaption>${esc(imageCaption(image))}</figcaption></figure>`).join("")}</div>` : feedback.media_requirement_satisfied_by_text ? `<div class="context-state ready">필요한 영상 소견이 문제 본문에 문장으로 제시되어 있습니다.</div>` : `<div class="context-state">이 문항에는 연결된 검사·이미지 자료가 없습니다.</div>`}`;
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
  const feedbackVisible = state.mode === "study" && feedback;
  const primaryDisabled = state.saving || (state.mode === "study" && !feedback && selected == null);
  const primaryLabel = state.saving
    ? "저장 중…"
    : state.mode === "study" && !feedback
      ? "정답 확인"
      : state.index === state.items.length - 1
        ? state.mode === "exam" ? "시험 제출" : "세션 완료"
        : "다음 문항 →";
  root.innerHTML = `
    <div class="reader-meta"><div><span class="mode-chip">${state.mode === "study" ? "학습 모드" : "시험 모드"}</span><span>${esc(question.course_name || question.course || question.subject)}</span><span>·</span><span>${esc(question.topic || question.major || "미분류")}</span></div><span>문항 ID · ${esc(question.id)}</span></div>
    <article class="question-card">
      <div class="question-stem">${question.stimulus ? `<span class="stimulus">${esc(question.stimulus)}</span>\n\n` : ""}${esc(question.stem)}</div>
      ${(question.imgs || []).length ? `<div class="question-media">${question.imgs.map((image) => `<figure><img src="${esc(imageUrl(image))}" alt="${esc(imageCaption(image))}"><figcaption>${esc(imageCaption(image))}</figcaption></figure>`).join("")}</div>` : ""}
      <div class="choices">${question.choices.map((choice) => choiceHtml(choice, feedbackVisible ? feedback : null)).join("")}</div>
    </article>
    ${state.mode === "exam" ? `<div class="exam-note">시험 모드에서는 세션 제출 전까지 정답·해설·개념 연결을 공개하지 않습니다. 문항 목록에서 자유롭게 이동하고 답을 바꿀 수 있습니다.</div>` : ""}
    <div class="reader-actionbar"><button type="button" class="button secondary reader-previous" data-main-previous ${state.index === 0 ? "disabled" : ""}>← 이전</button><p>${state.mode === "study" ? (feedback ? "아래 학습 피드백을 확인한 뒤 다음 문항으로 이동하세요." : "답안을 선택하면 서버에서 정답을 확인합니다.") : `${answeredCount()}/${state.items.length}문항 응답 · 마지막에 한 번에 제출합니다.`}</p><button id="primary-action" class="button primary" ${primaryDisabled ? "disabled" : ""}>${primaryLabel}</button></div>
    ${feedbackVisible ? feedbackHtml(question, feedback) : ""}`;
  root.querySelectorAll(".choice").forEach((button) => button.addEventListener("click", (event) => {
    if (event.target.closest(".eliminate") || (state.mode === "study" && feedbackFor(question))) return;
    const number = button.dataset.choice;
    if (eliminatedFor(question).has(number)) return;
    if (selectedFor(question) === number) state.answers.delete(question.id);
    else state.answers.set(question.id, number);
    render();
  }));
  root.querySelectorAll(".eliminate").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (state.mode === "study" && feedbackFor(question)) return;
    const number = button.dataset.eliminate;
    const eliminated = eliminatedFor(question);
    eliminated.has(number) ? eliminated.delete(number) : eliminated.add(number);
    if (selectedFor(question) === number) state.answers.delete(question.id);
    render();
  }));
  root.querySelector("#primary-action")?.addEventListener("click", primaryAction);
  root.querySelector("[data-main-previous]")?.addEventListener("click", () => goTo(state.index - 1));
  root.querySelectorAll("[data-feedback-tab]").forEach((button) => button.addEventListener("click", () => {
    state.tabs.set(question.id, button.dataset.feedbackTab);
    renderQuestion();
  }));
  root.querySelectorAll("[data-fsrs-rating]").forEach((button) => button.addEventListener("click", () => saveFsrs(Number(button.dataset.fsrsRating), button)));
}

function render() {
  if (!state.items.length) return;
  renderNavigator();
  renderQuestion();
  renderModal();
  updateTop();
}

async function submitQuestion(question, selected) {
  return api(`/api/student/questions/${encodeURIComponent(question.id)}/answer`, {
    method: "POST",
    body: JSON.stringify({
      event_id: `${sessionId}_${question.id}`,
      session_id: sessionId,
      selected_choices: [String(selected)],
      time_ms: Math.max(1000, state.elapsed * 1000),
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
  if (state.mode === "study" && !feedback) {
    if (selected == null) return;
    state.saving = true;
    render();
    try {
      const result = await submitQuestion(question, selected);
      state.feedbacks.set(question.id, result);
      state.results.set(question.id, resultRecord(question, selected, result));
      state.saving = false;
      render();
      window.scrollTo({top: document.querySelector(".feedback-wrap")?.offsetTop - 80 || 0, behavior: "smooth"});
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
  state.saving = true;
  render();
  try {
    for (const question of state.items) {
      const selected = state.answers.get(question.id);
      if (!selected) continue;
      const feedback = await submitQuestion(question, selected);
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

function renderResult() {
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
  document.querySelector("#session-title").textContent = "세션 결과";
  document.querySelector("#session-progress").textContent = `${correct}/${total}`;
  topBookmark.hidden = true;
  navigatorMobile.hidden = true;
  layout.classList.add("result-layout");
  navigatorRoot.innerHTML = "";
  root.innerHTML = `<section class="result-page"><article class="card result-hero"><span class="eyebrow" style="color:#76d7ca">Session Complete</span><h1>${state.mode === "exam" ? "시험을 제출했습니다" : "학습을 완료했습니다"}</h1><p>실제 제출 기록이 리포트와 복습 일정에 반영됩니다.</p><div class="result-score">${percent}%</div></article>
    <div class="result-grid"><article class="card summary-card"><span>정답</span><strong>${correct}/${total}</strong></article><article class="card summary-card"><span>풀이 시간</span><strong>${formatTime(state.elapsed)}</strong></article><article class="card summary-card"><span>오답 · 미응답</span><strong>${wrong.length} · ${unanswered}</strong></article></div>
    <section class="result-items">${resultRows.map((item) => `<article class="card result-item ${item.unanswered ? "unanswered" : item.isCorrect ? "" : "wrong"}"><span class="mark">${item.unanswered ? "−" : item.isCorrect ? "✓" : "!"}</span><div class="row-main"><h3>${esc(item.topic)}</h3><p>${esc(item.stem)}</p></div><span>${item.unanswered ? "미응답" : `${esc(item.selected)} → ${esc(item.answer)}`}</span></article>`).join("")}</section>
    <div class="result-actions"><a class="button primary" href="/student/#report">리포트 보기 →</a>${wrong.length ? `<a class="button secondary" href="/student/reader.html?ids=${encodeURIComponent(wrong.map((item) => item.questionId).join(","))}&mode=study&count=${wrong.length}">오답 다시 풀기</a>` : ""}${state.bookmarks.size ? `<a class="button secondary" href="/student/reader.html?ids=${encodeURIComponent([...state.bookmarks].join(","))}&mode=study&count=${state.bookmarks.size}">북마크 학습</a>` : ""}<a class="button secondary" href="/student/#library">서재로 돌아가기</a></div>
  </section>`;
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
    if (state.submitConfirmOpen) {
      state.submitConfirmOpen = false;
      renderModal();
    }
    closeMobileNavigator();
  }
});
setInterval(() => {
  state.elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
  const timer = document.querySelector("#timer");
  if (timer) timer.textContent = formatTime(state.elapsed);
}, 1000);
boot();
