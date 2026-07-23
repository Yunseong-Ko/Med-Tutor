(() => {
  "use strict";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const state = { tasks: [], selectedTask: null, drafts: [], selectedClaim: null };
  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));

  async function api(url, options = {}) {
    const response = await fetch(url, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `요청 실패 (${response.status})`);
    return payload;
  }

  function toast(message, error = false) {
    const node = $("#claim-toast");
    node.textContent = message;
    node.classList.toggle("is-error", error);
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
  }

  function readinessLabel(value) {
    if (value === "ready_for_candidate_extraction") return ["추출 가능", "is-ready"];
    if (value === "source_file_unavailable") return ["원문 없음", "is-warning"];
    return ["최신성 확인 필요", "is-warning"];
  }

  function renderMetrics(summary = {}) {
    $("#metric-tasks").textContent = summary.tasks ?? 0;
    $("#metric-matches").textContent = summary.matching_tasks ?? 0;
    $("#metric-drafts").textContent = summary.claim_drafts ?? 0;
    $("#metric-released").textContent = summary.released_claims ?? 0;
  }

  function renderTasks() {
    const box = $("#task-list");
    $("#task-total").textContent = `${state.tasks.length}개 표시`;
    if (!state.tasks.length) {
      box.innerHTML = '<div class="claim-empty"><b>조건에 맞는 작업이 없습니다.</b><span>필터를 바꾸거나 원문 준비 상태를 확인하세요.</span></div>';
      return;
    }
    box.innerHTML = state.tasks.map((task) => {
      const [label, cls] = readinessLabel(task.readiness);
      const active = state.selectedTask?.task_id === task.task_id ? " is-active" : "";
      return `<button class="claim-task${active}" type="button" data-task-id="${esc(task.task_id)}"><span class="claim-task-top"><span class="claim-badge ${cls}">${esc(label)}</span><span class="claim-badge">${esc(task.priority)}</span></span><strong>${esc(task.source_title)}</strong><small>${esc((task.concept_candidates || []).join(" · ") || "concept 후보 없음")}</small><span class="claim-task-meta"><span>${esc(task.clinical_axis)}</span><span>초안 ${esc(task.draft_count)} · release ${esc(task.released_count)}</span></span></button>`;
    }).join("");
    $$("[data-task-id]", box).forEach((button) => button.addEventListener("click", () => selectTask(button.dataset.taskId)));
  }

  async function loadTasks(keepSelection = true) {
    const params = new URLSearchParams();
    const values = { query: $("#task-query").value.trim(), priority: $("#task-priority").value, readiness: $("#task-readiness").value, clinical_axis: $("#task-axis").value };
    Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); });
    try {
      const payload = await api(`/api/faculty/guideline-claims/tasks?${params}`);
      state.tasks = payload.items || [];
      renderMetrics(payload.summary);
      if (keepSelection && state.selectedTask) state.selectedTask = state.tasks.find((task) => task.task_id === state.selectedTask.task_id) || state.selectedTask;
      renderTasks();
    } catch (error) {
      $("#task-list").innerHTML = `<div class="claim-error">${esc(error.message)}</div>`;
      toast(error.message, true);
    }
  }

  function sourceUrl(task, doc) {
    return `/api/faculty/guideline-claims/tasks/${encodeURIComponent(task.task_id)}/source/${encodeURIComponent(doc.attachment_id)}`;
  }

  function defaultDue() {
    const date = new Date(Date.now() + 180 * 86400000);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
  }

  function renderEditor() {
    const task = state.selectedTask;
    const box = $("#claim-editor");
    if (!task) return;
    const docs = task.source_documents || [];
    const candidates = task.concept_candidates || [];
    const [readyLabel] = readinessLabel(task.readiness);
    box.innerHTML = `<header class="claim-editor-head"><div><span class="claim-badge">${esc(task.priority)} · ${esc(task.clinical_axis)}</span><h2>${esc(task.source_title)}</h2><p>${esc(task.source_id)} · ${esc(readyLabel)}</p></div><div class="claim-source-actions">${docs.map((doc) => `<a href="${esc(sourceUrl(task, doc))}" target="_blank" rel="noopener">원문 열기 · ${esc(doc.role || "PDF")} ${esc(doc.page_count || "?")}p ↗</a>`).join("") || "<span>연결된 원문 없음</span>"}</div></header><div class="claim-warning"><b>! 원자 단위만 기록</b><span>한 claim에는 한 대상군·한 관계·한 권고만 적습니다. 문장 자동 추출이나 자동 의학 승인은 수행하지 않습니다.</span></div><form id="claim-form" class="claim-form"><div class="claim-form-grid three"><label class="fsw-field"><span>원문 파일 <b>*</b></span><select name="attachment_id" required>${docs.map((doc) => `<option value="${esc(doc.attachment_id)}">${esc(doc.role || doc.attachment_id)}</option>`).join("")}</select></label><label class="fsw-field"><span>페이지 <b>*</b></span><input name="page" type="number" min="1" required /></label><label class="fsw-field"><span>적용 버전 <b>*</b></span><input name="effective_version" placeholder="예: 2026 · 4th edition" required /></label></div><div class="claim-form-grid"><label class="fsw-field"><span>Ontology concept ID <b>*</b></span><input name="subject_concept_id" list="concept-candidates" value="${esc(candidates[0] || "")}" required /><datalist id="concept-candidates">${candidates.map((id) => `<option value="${esc(id)}"></option>`).join("")}</datalist></label><label class="fsw-field"><span>후보 외 concept 사용 사유</span><input name="concept_override_reason" placeholder="후보 밖 ID일 때 필수" /></label></div><div class="claim-form-grid three"><label class="fsw-field"><span>관계 <b>*</b></span><select name="relation"><option>recommends</option><option>suggests</option><option>requires</option><option>permits</option><option>contraindicates</option><option>does_not_recommend</option><option>defines</option></select></label><label class="fsw-field"><span>권고 강도</span><input name="recommendation_strength" placeholder="예: strong · 조건부" /></label><label class="fsw-field"><span>근거 수준</span><input name="evidence_grade" placeholder="예: A · low" /></label></div><label class="fsw-field"><span>승인 후보 문장 <b>*</b></span><textarea name="object_text" rows="4" minlength="20" placeholder="원문 의미를 벗어나지 않는 하나의 주장" required></textarea></label><label class="fsw-field"><span>적용 대상군 <b>*</b></span><textarea name="population" rows="2" placeholder="연령·상태·제외 조건을 포함해 구체적으로" required></textarea></label><label class="fsw-field"><span>원문 위치 메모 <b>*</b></span><input name="locator_note" placeholder="예: 권고문 3, 표 2 아래 첫 문단" required /></label><div class="claim-form-grid"><label class="fsw-field"><span>작성자</span><input name="created_by" autocomplete="name" placeholder="검토자 식별값" /></label><label class="fsw-field"><span>검토 메모</span><input name="review_notes" placeholder="예외·해석 주의사항" /></label></div><div class="claim-form-foot"><span>저장 시 draft·needs_review 상태가 됩니다. 학생, 챗봇, FSRS에는 아직 연결되지 않습니다.</span><button class="fsw-primary-button" type="submit">Claim 초안 저장</button></div></form>`;
    $("#claim-form").addEventListener("submit", createDraft);
  }

  async function createDraft(event) {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    payload.task_id = state.selectedTask.task_id;
    payload.page = Number(payload.page);
    try {
      await api("/api/faculty/guideline-claims/drafts", { method: "POST", body: JSON.stringify(payload) });
      event.currentTarget.reset();
      toast("Claim 초안을 저장했습니다. 아직 의학 승인 상태가 아닙니다.");
      await Promise.all([loadDrafts(), loadTasks(true)]);
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; }
  }

  function renderDrafts() {
    const box = $("#claim-draft-list");
    if (!state.drafts.length) {
      box.innerHTML = '<div class="claim-empty"><b>저장된 claim이 없습니다.</b><span>원문을 확인한 뒤 가운데에서 초안을 기록하세요.</span></div>';
      $("#decision-form").hidden = true;
      return;
    }
    box.innerHTML = state.drafts.map((claim) => `<button class="claim-draft${state.selectedClaim?.claim_id === claim.claim_id ? " is-active" : ""}" type="button" data-claim-id="${esc(claim.claim_id)}"><span class="claim-draft-head"><span class="claim-badge">${esc(claim.status)}</span><span class="claim-badge">p.${esc(claim.page)}</span></span><strong>${esc(claim.object_text)}</strong><small>${esc(claim.subject_concept_id)} · ${esc(claim.relation)} · ${esc(claim.population)}</small></button>`).join("");
    $$("[data-claim-id]", box).forEach((button) => button.addEventListener("click", () => selectClaim(button.dataset.claimId)));
  }

  async function loadDrafts() {
    if (!state.selectedTask) return;
    try {
      const payload = await api(`/api/faculty/guideline-claims/drafts?task_id=${encodeURIComponent(state.selectedTask.task_id)}`);
      state.drafts = payload.items || [];
      if (state.selectedClaim) state.selectedClaim = state.drafts.find((claim) => claim.claim_id === state.selectedClaim.claim_id) || null;
      renderDrafts();
      renderDecision();
    } catch (error) { toast(error.message, true); }
  }

  function selectClaim(claimId) {
    state.selectedClaim = state.drafts.find((claim) => claim.claim_id === claimId) || null;
    renderDrafts();
    renderDecision();
  }

  function renderDecision() {
    const form = $("#decision-form");
    const claim = state.selectedClaim;
    form.hidden = !claim;
    if (!claim) return;
    $("#decision-summary").innerHTML = `<b>${esc(claim.subject_concept_id)} · ${esc(claim.clinical_axis)}</b>${esc(claim.object_text)}<br><small>${esc(claim.claim_id)}</small>`;
    if (!$("#decision-due").value) $("#decision-due").value = defaultDue();
    $$('[data-decision="release"]', form).forEach((button) => { button.disabled = claim.status === "released"; });
    $$('[data-decision="revoke"]', form).forEach((button) => { button.disabled = claim.status !== "released"; });
  }

  async function decide(action, button) {
    const claim = state.selectedClaim;
    if (!claim) return;
    const reviewer = $("#decision-reviewer").value.trim();
    const attestation = $("#decision-attestation").checked;
    const reason = $("#decision-reason").value.trim();
    const payload = { action, reviewer, attestation, reason };
    if (action === "release") {
      payload.surfaces = $$(".claim-surfaces input:checked").map((input) => input.value);
      const due = $("#decision-due").value;
      payload.review_due_at = due ? new Date(due).toISOString() : "";
    }
    button.disabled = true;
    try {
      await api(`/api/faculty/guideline-claims/${encodeURIComponent(claim.claim_id)}/decision`, { method: "POST", body: JSON.stringify(payload) });
      toast(action === "release" ? "검토 기록과 사용 화면을 저장했습니다." : action === "reject" ? "Claim을 반려했습니다." : "Claim release를 철회했습니다.");
      $("#decision-attestation").checked = false;
      $("#decision-reason").value = "";
      await Promise.all([loadDrafts(), loadTasks(true)]);
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; renderDecision(); }
  }

  async function selectTask(taskId) {
    state.selectedTask = state.tasks.find((task) => task.task_id === taskId) || null;
    state.selectedClaim = null;
    state.drafts = [];
    renderTasks();
    renderEditor();
    await loadDrafts();
  }

  function bind() {
    $("#task-search").addEventListener("click", () => loadTasks(false));
    $("#task-refresh").addEventListener("click", () => loadTasks(true));
    $("#task-query").addEventListener("keydown", (event) => { if (event.key === "Enter") loadTasks(false); });
    $$("[data-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decision, button)));
    $("#claim-menu").addEventListener("click", () => {
      const nav = $("#claim-topnav");
      const open = !nav.classList.contains("is-open");
      nav.classList.toggle("is-open", open);
      $("#claim-menu").setAttribute("aria-expanded", String(open));
    });
  }

  bind();
  loadTasks(false);
})();
