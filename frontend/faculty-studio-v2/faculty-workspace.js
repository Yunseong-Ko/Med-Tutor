/* P:accine Faculty Studio V2 — import, review, evidence/media, archive workspaces.
   Uses only existing server contracts and never renders local file_path values. */
(() => {
  "use strict";

  const page = document.body.dataset.workspace || "";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
  const attr = esc;
  const fmtDate = (value) => {
    if (!value) return "시간 기록 없음";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(date);
  };
  const safeUrl = (value) => {
    const url = String(value || "").trim();
    if (!url) return "";
    if (url.startsWith("/") || url.startsWith("./") || url.startsWith("#")) return url;
    try {
      const parsed = new URL(url, window.location.origin);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
    } catch { return ""; }
  };

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    let payload = {};
    try { payload = await response.json(); }
    catch { payload = {}; }
    if (!response.ok) throw new Error(payload.detail || payload.message || `요청 실패 (${response.status})`);
    return payload;
  }

  let toastTimer = null;
  function toast(message) {
    const node = $("#fsw-toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { node.hidden = true; }, 3200);
  }

  function wireNavigation() {
    const menu = $(".fsw-menu-button");
    const nav = $("#fsw-topnav");
    menu?.addEventListener("click", () => {
      const open = !nav?.classList.contains("is-open");
      nav?.classList.toggle("is-open", open);
      menu.setAttribute("aria-expanded", String(open));
    });
  }

  async function loadReviewBadge() {
    try {
      const payload = await api("/api/question-sets?limit=80");
      const count = (payload.sets || []).reduce((sum, set) => sum + Number(set.needs_review_count || 0), 0);
      $$('[data-review-count]').forEach((node) => {
        node.hidden = count < 1;
        node.textContent = String(count);
      });
    } catch {
      $$('[data-review-count]').forEach((node) => { node.hidden = true; });
    }
  }

  function statusInfo(question) {
    const status = String(question?.review_status || "draft");
    if (status === "approved") return { key: "approved", label: "승인", cls: "is-approved" };
    if (status === "rejected") return { key: "rejected", label: "반려", cls: "is-rejected" };
    if (status === "needs_revision") return { key: "needs_revision", label: "수정요청", cls: "is-needs" };
    return { key: "pending", label: "검토대기", cls: "is-draft" };
  }

  function setStatusInfo(set) {
    const raw = String(set?.review_status || "draft");
    if (raw === "approved") return { key: "approved", label: "승인", cls: "is-approved" };
    return { key: "pending", label: "검토대기", cls: "is-needs" };
  }

  // ---------- Import ----------
  function initImport() {
    const examFile = $("#fsw-exam-file");
    const answerFile = $("#fsw-answer-file");
    const examSubmit = $("#fsw-exam-submit");
    const examHint = $("#fsw-exam-hint");
    const syncExamFile = () => {
      const file = examFile?.files?.[0];
      $("#fsw-exam-file-label").textContent = file?.name || "시험지를 선택하거나 드래그하세요";
      examSubmit.disabled = !file;
      examHint.textContent = file ? "구조화 준비 완료 · 정답지는 선택 사항입니다." : "다음: 시험지 파일 선택";
    };
    examFile?.addEventListener("change", syncExamFile);
    answerFile?.addEventListener("change", () => {
      $("#fsw-answer-file-label").textContent = answerFile.files?.[0]?.name || "정답지를 선택하세요";
    });

    $("#fsw-exam-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const result = $("#fsw-exam-result");
      if (!examFile.files?.length) { syncExamFile(); return; }
      examSubmit.disabled = true;
      examSubmit.textContent = "구조화 중";
      result.hidden = false;
      result.className = "fsw-result";
      result.innerHTML = '<div class="fsw-loading-state"><span class="fsw-spinner"></span>업로드한 시험지를 분석하고 문항·정답·이미지를 연결하는 중입니다.</div>';
      try {
        const payload = await api("/api/course-exams/import", { method: "POST", body: new FormData(event.currentTarget) });
        const summary = payload.summary || {};
        const warnings = [...(summary.extraction_warnings || [])];
        if (payload.answer_key?.missing_question_numbers?.length) warnings.push(`정답 누락 문항: ${payload.answer_key.missing_question_numbers.join(", ")}`);
        result.className = `fsw-result${warnings.length ? " is-warning" : ""}`;
        result.innerHTML = `
          <h2>${warnings.length ? "구조화 완료 · 확인이 필요합니다" : "시험지 구조화가 완료되었습니다"}</h2>
          <p>가져온 문항은 검토 전 상태이며 학생에게 공개되지 않습니다.</p>
          <dl>
            <div><dt>문항</dt><dd>${esc(summary.question_count || 0)}</dd></div>
            <div><dt>정답 연결</dt><dd>${esc(summary.with_answer_count || 0)}</dd></div>
            <div><dt>제시자료</dt><dd>${esc(summary.with_stimulus_count || 0)}</dd></div>
            <div><dt>해설</dt><dd>${esc(summary.with_explanation_count || 0)}</dd></div>
            <div><dt>이미지</dt><dd>${esc(summary.media_asset_count || 0)}</dd></div>
            <div><dt>확인 필요</dt><dd>${esc(summary.needs_review_count || 0)}</dd></div>
          </dl>
          ${warnings.length ? `<p><strong>확인 항목:</strong> ${esc(warnings.join(" · "))}</p>` : ""}
          <div class="fsw-result-actions">
            ${safeUrl(payload.preview_url) ? `<a class="fsw-secondary-button" href="${attr(safeUrl(payload.preview_url))}" target="_blank" rel="noopener">파싱 미리보기 열기</a>` : ""}
            ${payload.set_id ? `<a class="fsw-primary-button" href="./review.html?set=${encodeURIComponent(payload.set_id)}">가져온 문항 검토·승인</a>` : ""}
          </div>`;
        toast("시험지 구조화가 완료되었습니다.");
      } catch (error) {
        result.className = "fsw-result is-error";
        result.innerHTML = `<h2>시험지 구조화에 실패했습니다</h2><p>${esc(error.message)}</p><div class="fsw-result-actions"><button class="fsw-secondary-button" type="button" data-exam-retry>동일 파일로 다시 시도</button></div>`;
        result.querySelector("[data-exam-retry]")?.addEventListener("click", () => event.currentTarget.requestSubmit());
      } finally {
        examSubmit.disabled = false;
        examSubmit.textContent = "문항 구조화";
      }
    });

  }

  // ---------- Native source hub ----------
  const sources = { items: [], selectedId: "", filter: "all", query: "", subject: "all", duplicateId: "" };

  function fileNameOnly(value) {
    const parts = String(value || "").split(/[\\/]/);
    return parts[parts.length - 1] || "이름 없는 시험지";
  }

  function sourceUnit(item) {
    return [item.round_label, item.period_label].filter(Boolean).join(" · ") || "단원 미분류";
  }

  function sourceStatus(item) {
    const explicit = String(item.processing_status || item.import_status || "").toLowerCase();
    if (["waiting", "queued"].includes(explicit)) return { key: "waiting", label: "대기" };
    if (["processing", "analyzing"].includes(explicit)) return { key: "processing", label: "분석 중" };
    if (["failed", "error"].includes(explicit)) return { key: "failed", label: "실패" };
    if (Number(item.question_count || 0) < 1) return { key: "failed", label: "확인 필요" };
    if (Number(item.needs_review_count || 0) > 0 || Number(item.with_answer_count || 0) < Number(item.question_count || 0)) {
      return { key: "partial", label: "부분 확인 필요" };
    }
    return { key: "done", label: "완료" };
  }

  function sourceFileType(item) {
    const name = fileNameOnly(item.source_file || item.source_exam || item.exam_id).toLowerCase();
    return name.endsWith(".pdf") ? "PDF" : "HWP";
  }

  function sourceMatches(item) {
    const status = sourceStatus(item).key;
    if (sources.filter !== "all" && status !== sources.filter) return false;
    if (sources.subject !== "all" && String(item.course_name || "미분류") !== sources.subject) return false;
    if (!sources.query) return true;
    const haystack = [item.source_file, item.source_exam, item.course_name, sourceUnit(item)].join(" ").toLowerCase();
    return haystack.includes(sources.query.toLowerCase());
  }

  function sourceCounts() {
    const counts = { all: sources.items.length, waiting: 0, processing: 0, partial: 0, done: 0, failed: 0 };
    sources.items.forEach((item) => { counts[sourceStatus(item).key] += 1; });
    return counts;
  }

  function renderSourceFilters() {
    const counts = sourceCounts();
    Object.entries(counts).forEach(([key, value]) => {
      const node = $(`[data-source-count-key="${key}"]`);
      if (node) node.textContent = String(value);
    });
    $$('[data-source-count]').forEach((node) => {
      node.hidden = counts.all < 1;
      node.textContent = String(counts.all);
    });
  }

  function sourceEmptyMarkup(filtered) {
    if (!sources.items.length) return `<div class="fsw-empty-state"><strong>보관된 자료가 없습니다</strong><p>첫 시험지를 올리면 P:accine이 문항을 구조화하고, 처리 이력이 여기에 쌓입니다.</p><button class="fsw-primary-button" type="button" data-open-source-upload>＋ 새 시험지 가져오기</button></div>`;
    if (!filtered.length) return `<div class="fsw-empty-state"><strong>검색·필터에 맞는 자료가 없습니다</strong><p>검색어 또는 처리 상태를 바꿔 보세요.</p><button class="fsw-secondary-button" type="button" data-source-clear>검색·필터 초기화</button></div>`;
    return "";
  }

  function renderSourceList() {
    renderSourceFilters();
    const list = $("#fsw-source-list");
    if (!list) return;
    const filtered = sources.items.filter(sourceMatches);
    const empty = sourceEmptyMarkup(filtered);
    if (empty) { list.innerHTML = empty; wireSourceTransientActions(); return; }
    list.innerHTML = filtered.map((item) => {
      const status = sourceStatus(item);
      const type = sourceFileType(item);
      const filename = fileNameOnly(item.source_file || item.source_exam || item.exam_id);
      const meta = [item.course_name || "과목 미분류", sourceUnit(item), fmtDate(item.updated_at)].join(" · ");
      return `<button class="fsw-source-row${String(item.exam_id) === sources.selectedId ? " is-active" : ""}" type="button" data-source-id="${attr(item.exam_id)}" aria-pressed="${String(item.exam_id) === sources.selectedId}">
        <span class="fsw-source-file-icon${type === "PDF" ? " is-pdf" : ""}">${type}</span>
        <span class="fsw-source-row-copy"><strong>${esc(filename)}</strong><small>${esc(meta)}</small></span>
        <span class="fsw-source-row-state"><span class="fsw-source-status is-${status.key}">${esc(status.label)}</span><small>${esc(item.question_count || 0)}문항</small></span>
      </button>`;
    }).join("");
  }

  function sourceSteps(item) {
    const status = sourceStatus(item).key;
    const partial = status === "partial";
    return [
      { label: "업로드", state: "done" },
      { label: "원문 분석", state: status === "failed" ? "partial" : "done" },
      { label: "문항 분리", state: status === "failed" ? "waiting" : "done" },
      { label: "정답·이미지 연결", state: partial ? "partial" : status === "failed" ? "waiting" : "done" },
      { label: "검토 세트 저장", state: status === "failed" ? "waiting" : "done" },
    ];
  }

  function renderSourceDetail(item) {
    const detail = $("#fsw-source-detail");
    if (!detail || !item) return;
    const status = sourceStatus(item);
    const type = sourceFileType(item);
    const filename = fileNameOnly(item.source_file || item.source_exam || item.exam_id);
    const needs = Number(item.needs_review_count || 0);
    const previewUrl = safeUrl(item.preview_url);
    const steps = sourceSteps(item).map((step) => `<div class="fsw-source-step is-${step.state}"><span class="fsw-source-step-dot">${step.state === "done" ? "✓" : step.state === "partial" ? "!" : ""}</span><span>${esc(step.label)}</span><small>${step.state === "done" ? "완료" : step.state === "partial" ? "확인 필요" : "대기"}</small></div>`).join("");
    detail.innerHTML = `<div class="fsw-source-detail-card">
      <button class="fsw-source-mobile-back" type="button" data-source-back>← 자료 보관함</button>
      <div class="fsw-source-detail-header">
        <span class="fsw-source-file-icon${type === "PDF" ? " is-pdf" : ""}">${type}</span>
        <div><h2>${esc(filename)}</h2><p>${esc(item.course_name || "과목 미분류")} · ${esc(sourceUnit(item))}</p></div>
        <span class="fsw-source-status is-${status.key}">${esc(status.label)}</span>
      </div>
      <div class="fsw-source-original"><span>원문 파일</span><div><span>유형 <b>${type} 시험지</b></span><span>정답지 <b>${item.answer_key_source ? "XLSX 연결됨" : "연결 없음"}</b></span><span>업로드 <b>${esc(fmtDate(item.updated_at))}</b></span></div></div>
      <div><div class="fsw-source-steps-label"><span>처리 단계</span><span>진행률 대신 완료·확인 필요 상태를 표시합니다</span></div><div class="fsw-source-steps">${steps}</div></div>
      <div class="fsw-source-counts">
        <div><b>${esc(item.question_count || 0)}</b><small>문항</small></div>
        <div><b>${esc(item.with_answer_count || 0)}</b><small>정답 연결</small></div>
        <div><b>${esc(item.media_linked_question_count || item.media_asset_count || 0)}</b><small>제시자료</small></div>
        <div class="${needs ? "is-warning" : ""}"><b>${needs}</b><small>확인 필요</small></div>
      </div>
      ${status.key === "partial" ? `<div class="fsw-source-warning"><strong>! 부분 확인 필요</strong><p>${esc(item.question_count || 0)}문항 중 <b>${needs}문항</b>이 정답 또는 이미지 매칭을 확인해야 합니다. 나머지는 검토 세트로 준비할 수 있습니다.</p><div><button class="fsw-primary-button" type="button" data-source-review>검토 화면으로 이동</button><button class="fsw-secondary-button" type="button" disabled title="부분 재처리 서버 계약 준비 중">확인 필요 항목만 다시 처리</button></div></div>` : ""}
      <div class="fsw-source-actions">
        <button class="fsw-secondary-button" type="button" disabled title="원문 파일 보안 제공 계약 준비 중">원문 미리보기</button>
        ${previewUrl ? `<a class="fsw-secondary-button" href="${attr(previewUrl)}" target="_blank" rel="noopener">구조화 결과 미리보기</a>` : `<button class="fsw-secondary-button" type="button" disabled>구조화 결과 미리보기</button>`}
        ${status.key !== "failed" ? `<button class="fsw-primary-button fsw-source-review-link" type="button" data-source-review>검토·승인으로 이동 →</button>` : ""}
      </div>
      <div class="fsw-source-policy"><span>구조화 결과는 검토·승인 전 · 학생 공개 아님</span><button class="fsw-quiet-button" type="button" disabled title="연결 문항 보호 정책 확정 후 제공">자료 삭제 · 준비 중</button></div>
      <div class="fsw-source-retention"><strong>보존·권한 <span>P1 서버 계약 필요</span></strong>원본 보존·저작권·비식별 정책은 운영 환경에 맞춰 확정됩니다. 연결 문항이 있는 자료는 현재 삭제할 수 없습니다.</div>
    </div>`;
    detail.querySelector("[data-source-back]")?.addEventListener("click", () => detail.classList.remove("is-mobile-open"));
    detail.querySelectorAll("[data-source-review]").forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      const label = button.textContent;
      button.textContent = item.review_set_exists ? "검토 화면 여는 중" : "검토 세트 준비 중";
      try {
        const payload = await api(`/api/course-exams/${encodeURIComponent(item.exam_id)}/review-set`, { method: "POST" });
        window.location.href = `./review.html?set=${encodeURIComponent(payload.set_id)}`;
      } catch (error) {
        button.disabled = false;
        button.textContent = label;
        toast(`검토 세트를 준비하지 못했습니다. ${error.message}`);
      }
    }));
  }

  function selectSource(id, { openMobile = true } = {}) {
    const item = sources.items.find((source) => String(source.exam_id) === String(id));
    if (!item) return;
    sources.selectedId = String(id);
    renderSourceList();
    renderSourceDetail(item);
    if (openMobile && window.matchMedia("(max-width: 767px)").matches) $("#fsw-source-detail")?.classList.add("is-mobile-open");
  }

  function populateSourceSubjects() {
    const select = $("#fsw-source-subject");
    if (!select) return;
    const values = [...new Set(sources.items.map((item) => String(item.course_name || "미분류")))].sort((a, b) => a.localeCompare(b, "ko"));
    select.innerHTML = `<option value="all">전체 과목</option>${values.map((value) => `<option value="${attr(value)}">${esc(value)}</option>`).join("")}`;
    select.value = values.includes(sources.subject) ? sources.subject : "all";
  }

  async function loadSources(preferredId = "") {
    const list = $("#fsw-source-list");
    try {
      const payload = await api("/api/course-exams?limit=100");
      sources.items = payload.exams || [];
      populateSourceSubjects();
      const nextId = preferredId && sources.items.some((item) => String(item.exam_id) === String(preferredId)) ? preferredId : sources.selectedId;
      if (nextId && sources.items.some((item) => String(item.exam_id) === String(nextId))) sources.selectedId = String(nextId);
      else if (sources.items.length && !window.matchMedia("(max-width: 767px)").matches) sources.selectedId = String(sources.items[0].exam_id);
      renderSourceList();
      const selected = sources.items.find((item) => String(item.exam_id) === sources.selectedId);
      if (selected) renderSourceDetail(selected);
    } catch (error) {
      if (list) list.innerHTML = `<div class="fsw-empty-state"><strong>보관함을 불러오지 못했습니다</strong><p>${esc(error.message)}</p><button class="fsw-secondary-button" type="button" data-source-retry>↻ 다시 시도</button></div>`;
      list?.querySelector("[data-source-retry]")?.addEventListener("click", () => loadSources());
    }
  }

  function openSourceUpload() {
    const overlay = $("#fsw-source-upload-overlay");
    if (!overlay) return;
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => $("#fsw-source-exam-file")?.focus(), 0);
  }

  function closeSourceUpload() {
    const overlay = $("#fsw-source-upload-overlay");
    if (overlay) overlay.hidden = true;
    document.body.style.overflow = "";
  }

  function wireSourceTransientActions() {
    $$('[data-open-source-upload]').forEach((button) => { button.onclick = openSourceUpload; });
    $("[data-source-clear]")?.addEventListener("click", () => {
      sources.filter = "all"; sources.query = ""; sources.subject = "all";
      $("#fsw-source-search").value = ""; $("#fsw-source-subject").value = "all";
      $$('[data-source-filter]').forEach((button) => button.classList.toggle("is-active", button.dataset.sourceFilter === "all"));
      renderSourceList();
    });
  }

  function initSources() {
    wireSourceTransientActions();
    $$('[data-close-source-upload]').forEach((button) => button.addEventListener("click", closeSourceUpload));
    $$('[data-close-source-duplicate]').forEach((button) => button.addEventListener("click", () => { $("#fsw-source-duplicate-overlay").hidden = true; document.body.style.overflow = ""; }));
    $("#fsw-source-list")?.addEventListener("click", (event) => {
      const row = event.target.closest("[data-source-id]");
      if (row) selectSource(row.dataset.sourceId);
    });
    $("#fsw-source-search")?.addEventListener("input", (event) => { sources.query = event.target.value.trim(); renderSourceList(); });
    $("#fsw-source-subject")?.addEventListener("change", (event) => { sources.subject = event.target.value; renderSourceList(); });
    $("#fsw-source-filters")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-source-filter]");
      if (!button) return;
      sources.filter = button.dataset.sourceFilter;
      $$('[data-source-filter]').forEach((item) => item.classList.toggle("is-active", item === button));
      renderSourceList();
    });
    const examFile = $("#fsw-source-exam-file");
    const answerFile = $("#fsw-source-answer-file");
    const submit = $("#fsw-source-upload-submit");
    examFile?.addEventListener("change", () => {
      const file = examFile.files?.[0];
      $("#fsw-source-exam-label").textContent = file?.name || "HWP · PDF 파일을 선택하거나 드래그";
      submit.disabled = !file;
    });
    answerFile?.addEventListener("change", () => { $("#fsw-source-answer-label").textContent = answerFile.files?.[0]?.name || "정답지 XLSX 선택"; });
    $("#fsw-source-open-existing")?.addEventListener("click", () => {
      const id = sources.duplicateId;
      $("#fsw-source-duplicate-overlay").hidden = true;
      closeSourceUpload();
      selectSource(id);
    });
    $("#fsw-source-upload-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const file = examFile?.files?.[0];
      const state = $("#fsw-source-upload-state");
      if (!file) return;
      if (file.size > 50 * 1024 * 1024) { state.hidden = false; state.className = "fsw-source-upload-state is-error"; state.textContent = "시험지 파일은 50MB 이하만 업로드할 수 있습니다."; return; }
      const duplicate = sources.items.find((item) => fileNameOnly(item.source_file || item.source_exam).toLowerCase() === file.name.toLowerCase());
      if (duplicate) {
        sources.duplicateId = String(duplicate.exam_id);
        $("#fsw-source-duplicate-copy").textContent = `${file.name} · ${fmtDate(duplicate.updated_at)} 업로드`;
        $("#fsw-source-duplicate-overlay").hidden = false;
        return;
      }
      submit.disabled = true;
      submit.textContent = "구조화 중";
      state.hidden = false;
      state.className = "fsw-source-upload-state";
      state.innerHTML = '<span class="fsw-spinner"></span> 업로드 → 원문 분석 → 문항 분리 → 정답·이미지 연결을 진행하고 있습니다.';
      try {
        const payload = await api("/api/course-exams/import", { method: "POST", body: new FormData(event.currentTarget) });
        toast("시험지 구조화가 완료되었습니다.");
        closeSourceUpload();
        event.currentTarget.reset();
        $("#fsw-source-exam-label").textContent = "HWP · PDF 파일을 선택하거나 드래그";
        $("#fsw-source-answer-label").textContent = "정답지 XLSX 선택";
        state.hidden = true;
        await loadSources(payload.exam_id || payload.summary?.exam_id || "");
        if (payload.exam_id) selectSource(payload.exam_id);
      } catch (error) {
        state.className = "fsw-source-upload-state is-error";
        state.textContent = `구조화에 실패했습니다. ${error.message}`;
      } finally {
        submit.disabled = !examFile?.files?.length;
        submit.textContent = "가져오기 시작";
      }
    });
    loadSources();
  }

  // ---------- Review ----------
  const review = { sets: [], packet: null, filter: "all", selectedId: "", dirty: false };
  const reviewFeedbackOptions = [
    ["too_easy", "너무 쉬움"],
    ["too_difficult", "너무 어려움"],
    ["excessive_clues", "단서 과다"],
    ["insufficient_clues", "단서 부족"],
    ["ambiguous_answer", "정답 모호"],
    ["inappropriate_options", "선지 부적절"],
    ["faculty_intent_mismatch", "출제 의도 불일치"],
    ["department_level_mismatch", "과 수준 부적합"],
  ];
  const reviewFeedbackIds = new Set(reviewFeedbackOptions.map(([value]) => value));
  const reviewReasonLabels = new Map([
    ["automated_generation_requires_human_review", "자동 생성 문항 · 교수 검토 필요"],
    ["distractor_outside_registry_scope", "일부 오답 선지가 Ontology 범위 밖"],
    ["evidence_disclosure_plan_blocked", "근거 제시 설계 보완 필요"],
    ["item_quality_flaws", "문항 품질 점검 항목 있음"],
    ["model_marked_needs_review", "생성 모델이 추가 검토를 요청함"],
    ["nbme_hard_rule_failures", "문항 작성 규칙 보완 필요"],
    ["question_blueprint_distractor_source_missing", "오답 선지 근거 연결 누락"],
    ["question_blueprint_blocked", "문항 설계도 보완 필요"],
    ["missing_source_anchor", "직접 근거 연결 누락"],
    ["invalid_answer", "정답 매핑 확인 필요"],
    ["choice_count_lt_5", "선지 수 보완 필요"],
    ...reviewFeedbackOptions,
  ]);
  const reviewReasonLabel = (reason) => reviewReasonLabels.get(String(reason || "")) || String(reason || "").replaceAll("_", " ");

  function reviewQuestions() { return review.packet?.questions || []; }
  function selectedQuestion() { return reviewQuestions().find((item) => String(item.question_id) === String(review.selectedId)); }
  function matchesReviewFilter(item) {
    if (review.filter === "all") return true;
    return statusInfo(item).key === review.filter;
  }
  function issueText(item) {
    const reasons = Array.isArray(item.review_reasons) ? item.review_reasons : [];
    if (reasons.length) return reasons.map(reviewReasonLabel).join(" · ");
    if ((item.question_type === "image_based") && !(item.image_refs || []).length) return "이미지 누락";
    if (item.question_blueprint?.status === "blocked") return "문항 설계 차단";
    return item.needs_review ? "교수 검토 필요" : "";
  }

  function setSaveState(label, cls = "") {
    const node = $("#fsw-save-state");
    if (!node) return;
    node.textContent = label;
    node.className = `fsw-save-pill${cls ? ` ${cls}` : ""}`;
  }

  function syncReviewCounts() {
    const items = reviewQuestions();
    const counts = { all: items.length, pending: 0, needs_revision: 0, approved: 0, rejected: 0 };
    items.forEach((item) => { counts[statusInfo(item).key] += 1; });
    Object.entries(counts).forEach(([key, value]) => {
      const node = $(`[data-filter-count="${key}"]`);
      if (node) node.textContent = String(value);
    });
  }

  function renderQuestionQueue() {
    syncReviewCounts();
    const queue = $("#fsw-question-queue");
    const visible = reviewQuestions().filter(matchesReviewFilter);
    if (!visible.length) {
      queue.innerHTML = '<p class="fsw-empty-inline">이 상태에 해당하는 문항이 없습니다.</p>';
      review.selectedId = "";
      renderReviewEditor();
      return;
    }
    if (!visible.some((item) => String(item.question_id) === String(review.selectedId))) review.selectedId = String(visible[0].question_id);
    queue.innerHTML = visible.map((item, index) => {
      const info = statusInfo(item);
      const issue = issueText(item);
      const title = String(item.problem || item.stem || `문항 ${index + 1}`).trim();
      return `<button type="button" class="fsw-question-row${String(item.question_id) === String(review.selectedId) ? " is-active" : ""}" data-question-id="${attr(item.question_id)}">
        <span class="fsw-question-index">${String(index + 1).padStart(2, "0")}</span><span><strong>${esc(title)}</strong><small class="${issue ? "is-warning" : ""}">${esc(info.label)}${issue ? ` · ▲ ${esc(issue)}` : " · 검수 상태 확인"}</small></span></button>`;
    }).join("");
    renderReviewEditor();
  }

  function warningForQuestion(item) {
    const warnings = [];
    if (!Number(item.answer)) warnings.push("정답 매핑 누락 — 단일 정답을 지정해야 승인할 수 있습니다.");
    if ((item.question_type === "image_based") && !(item.image_refs || []).length) warnings.push("이미지/자료해석 문항인데 연결된 이미지가 없습니다.");
    if (item.question_blueprint?.status === "blocked") warnings.push(`문항 설계도 차단 — ${(item.question_blueprint.block_reasons || []).join(", ") || "설계도 확인 필요"}`);
    if (Number(item.image_match_confidence) > 0 && Number(item.image_match_confidence) < .7) warnings.push(`이미지 매칭 신뢰도가 낮습니다 (${Math.round(Number(item.image_match_confidence) * 100)}%).`);
    (item.review_reasons || []).forEach((reason) => {
      const label = reviewReasonLabel(reason);
      if (label && !warnings.includes(label)) warnings.push(label);
    });
    return warnings;
  }

  function renderReferences(item) {
    const image = (item.image_refs || [])[0];
    const ref = (item.reference_notes || [])[0];
    const imageText = image ? (image.caption || image.original_name || image.modality || image.asset_id || image) : "연결 이미지 없음";
    const confidence = Number(item.image_match_confidence || image?.image_match_confidence || 0);
    return `<div class="fsw-media-reference-row">
      <div class="fsw-reference-box"><strong>${image ? `연결 이미지 · ${esc(image.modality || "MEDIA")}` : "연결 이미지"}</strong>${esc(imageText)}${confidence ? `<br>매칭 신뢰도 ${Math.round(confidence * 100)}%` : ""}</div>
      <div class="fsw-reference-box"><strong>참고 메모 (reference notes)</strong>${ref ? `${esc(ref.source || "근거")}${ref.basis ? ` · ${esc(ref.basis)}` : ""}` : "참고 메모 없음"}</div>
    </div>`;
  }

  function renderReviewEditor() {
    const editor = $("#fsw-review-editor");
    const item = selectedQuestion();
    if (!item) {
      editor.innerHTML = '<div class="fsw-empty-state"><strong>검토할 문항을 선택하세요</strong><p>왼쪽 목록에서 문항을 선택하면 편집 화면이 열립니다.</p></div>';
      return;
    }
    const info = statusInfo(item);
    const warnings = warningForQuestion(item);
    const choices = Array.from({ length: 5 }, (_, index) => item.options?.[index] || "");
    const allReasons = Array.isArray(item.review_reasons) ? item.review_reasons : String(item.review_reasons || "").split(/[,;\n]+/).map((value) => value.trim()).filter(Boolean);
    const reasons = allReasons.filter((reason) => !reviewFeedbackIds.has(reason)).join(", ");
    const facultyIntent = item.faculty_question_intent && typeof item.faculty_question_intent === "object" ? item.faculty_question_intent : {};
    const assessmentClaim = facultyIntent.assessment_claim && typeof facultyIntent.assessment_claim === "object" ? facultyIntent.assessment_claim : {};
    const intentTitle = assessmentClaim.faculty_claim || assessmentClaim.task_label || assessmentClaim.task || "";
    editor.innerHTML = `
      ${warnings.length ? `<div class="fsw-warning-banner"><strong>!</strong><span>${warnings.map((warning) => esc(warning)).join("<br>")}</span></div>` : ""}
      <div class="fsw-editor-head"><div class="fsw-editor-kicker"><span class="fsw-status-badge ${info.cls}">${esc(info.label)}</span><small>${esc(item.question_id)} · Ontology 근거: 검토용 · 의학승인 전</small></div></div>
      <form class="fsw-editor-form" id="fsw-review-form">
        ${(item.faculty_intent_id || intentTitle) ? `<section class="fsw-intent-trace"><small>선택한 출제 의도</small><strong>${esc(intentTitle || "출제 의도 확인 필요")}</strong><span>${esc(item.faculty_intent_id || "intent id 없음")}</span></section>` : ""}
        <label class="fsw-field"><span>문제 본문</span><textarea data-review-field="problem" rows="4">${esc(item.problem || "")}</textarea></label>
        ${renderReferences(item)}
        <div><label class="fsw-field"><span>선지 · 단일 정답 1개</span></label><div class="fsw-choice-list">${choices.map((choice, index) => `<label class="fsw-choice-row"><input type="radio" name="answer" value="${index + 1}" ${Number(item.answer) === index + 1 ? "checked" : ""} aria-label="${index + 1}번을 정답으로 지정" /><span>${index + 1}</span><input type="text" value="${attr(choice)}" data-review-choice="${index}" aria-label="${index + 1}번 선지" /></label>`).join("")}</div></div>
        <label class="fsw-field"><span>해설</span><textarea data-review-field="explanation" rows="5">${esc(item.explanation || "")}</textarea></label>
        <fieldset class="fsw-field fsw-quick-feedback"><span>빠른 피드백</span><p>선택한 항목은 review_reasons에 저장되며 자동 재생성·자동 승인·학생 공개를 실행하지 않습니다.</p><div>${reviewFeedbackOptions.map(([value, label]) => `<label><input type="checkbox" data-review-feedback value="${attr(value)}" ${allReasons.includes(value) ? "checked" : ""} /><span>${esc(label)}</span></label>`).join("")}</div><label class="fsw-field"><span>자유 메모</span><textarea data-review-comment rows="2" placeholder="수정 방향을 구체적으로 남겨 주세요. 변경 이력의 comment로 저장됩니다."></textarea></label></fieldset>
        <div class="fsw-review-meta-grid">
          <fieldset class="fsw-field"><span>검토 상태</span><div class="fsw-review-status-buttons">${[
            ["draft", "초안"], ["needs_revision", "수정요청"], ["approved", "승인"], ["rejected", "반려"],
          ].map(([value, label]) => `<label><input type="radio" name="review_status" value="${value}" ${String(item.review_status || "draft") === value ? "checked" : ""} /><span>${label}</span></label>`).join("")}</div></fieldset>
          <label class="fsw-field"><span>검토 사유 (review reason)</span><input data-review-field="review_reasons" type="text" value="${attr(reasons)}" placeholder="반려·수정요청 시 사유를 남기세요" /></label>
        </div>
        <div class="fsw-review-actions"><button class="fsw-secondary-button" type="button" data-review-action="save">수정 저장</button><button class="fsw-quiet-button" type="button" data-open-history>변경 이력</button><span class="fsw-action-spacer"></span><button class="fsw-primary-button" type="button" data-review-action="approve">승인</button><button class="fsw-danger-button" type="button" data-review-action="reject">반려</button></div>
      </form>
      <p class="fsw-help">승인 = 검수 완료 · 내보내기는 별도 메뉴 · 학생 공개 CTA 없음</p>`;
    review.dirty = false;
    setSaveState("변경 없음");
    $("#fsw-review-form")?.addEventListener("input", (event) => {
      review.dirty = true;
      if (event.target.matches("[data-review-feedback], [data-review-comment]")) {
        const status = $('input[name="review_status"][value="needs_revision"]', $("#fsw-review-form"));
        if (status) status.checked = true;
      }
      setSaveState("저장 필요", "is-saving");
    });
    $("#fsw-review-form")?.addEventListener("change", () => { review.dirty = true; setSaveState("저장 필요", "is-saving"); });
  }

  function collectReviewUpdates() {
    const form = $("#fsw-review-form");
    const choices = $$('[data-review-choice]', form).sort((a, b) => Number(a.dataset.reviewChoice) - Number(b.dataset.reviewChoice)).map((node) => node.value.trim());
    const status = $('input[name="review_status"]:checked', form)?.value || "draft";
    const answer = $('input[name="answer"]:checked', form)?.value;
    const quickReasons = $$('[data-review-feedback]:checked', form).map((node) => node.value);
    const manualReasons = ($('[data-review-field="review_reasons"]', form)?.value || "").split(/[,;\n]+/).map((value) => value.trim()).filter(Boolean);
    const feedbackComment = $('[data-review-comment]', form)?.value.trim() || "";
    const feedbackRequested = quickReasons.length > 0 || Boolean(feedbackComment);
    const updates = {
      problem: $('[data-review-field="problem"]', form)?.value.trim() || "",
      options: choices,
      explanation: $('[data-review-field="explanation"]', form)?.value.trim() || "",
      review_status: feedbackRequested ? "needs_revision" : status,
      needs_review: feedbackRequested || status === "needs_revision" || status === "rejected",
      review_reasons: [...new Set([...manualReasons, ...quickReasons])],
    };
    updates.feedback_comment = feedbackComment;
    if (answer) updates.answer = Number(answer);
    return updates;
  }

  async function submitReview(action) {
    const item = selectedQuestion();
    if (!item || !review.packet?.set_id) return;
    const updates = collectReviewUpdates();
    const feedbackComment = String(updates.feedback_comment || "");
    delete updates.feedback_comment;
    if (action === "approve" && (!updates.problem || updates.options.some((choice) => !choice) || !updates.answer || !updates.explanation)) {
      toast("승인 전 문제·선지 5개·단일 정답·해설을 모두 확인해주세요.");
      return;
    }
    if (action === "reject" && !String(updates.review_reasons).trim()) {
      toast("반려 사유를 먼저 입력해주세요.");
      $('[data-review-field="review_reasons"]')?.focus();
      return;
    }
    const endpoint = action === "save"
      ? `/api/question-sets/${encodeURIComponent(review.packet.set_id)}/questions/${encodeURIComponent(item.question_id)}`
      : `/api/question-sets/${encodeURIComponent(review.packet.set_id)}/questions/${encodeURIComponent(item.question_id)}/${action}`;
    const buttons = $$('[data-review-action]');
    buttons.forEach((button) => { button.disabled = true; });
    setSaveState(action === "approve" ? "승인 저장 중…" : action === "reject" ? "반려 저장 중…" : "저장 중…", "is-saving");
    try {
      const payload = await api(endpoint, {
        method: action === "save" ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates, actor_id: "local_faculty", comment: action === "approve" ? "문항 승인" : action === "reject" ? String(updates.review_reasons) : feedbackComment || (updates.review_status === "needs_revision" ? "빠른 피드백으로 수정 요청" : "문항 수정") }),
      });
      review.packet = payload.set || await api(`/api/question-sets/${encodeURIComponent(review.packet.set_id)}`);
      review.dirty = false;
      renderQuestionQueue();
      setSaveState(action === "approve" ? "승인됨 ✓" : action === "reject" ? "반려됨 ✓" : "저장됨 ✓", "is-saved");
      loadReviewBadge();
      toast(action === "approve" ? "문항 검수를 승인했습니다. 학생 공개는 아닙니다." : action === "reject" ? "문항을 반려했습니다." : "문항 수정 내용을 저장했습니다.");
    } catch (error) {
      setSaveState("저장 실패", "is-error");
      toast(`저장 실패 · ${error.message}`);
    } finally { buttons.forEach((button) => { button.disabled = false; }); }
  }

  function openHistory() {
    const overlay = $("#fsw-history-overlay");
    const list = $("#fsw-history-list");
    const events = (review.packet?.review_events || []).filter((event) => String(event.question_id) === String(review.selectedId)).slice().reverse();
    list.innerHTML = events.length ? events.map((event) => `<article class="fsw-history-item"><strong>${esc({ approved: "승인", rejected: "반려", edited: "수정", imported: "가져오기" }[event.event_type] || event.event_type || "변경")}</strong><p>${esc(event.comment || "상태 또는 문항 내용이 변경되었습니다.")}</p><small>${esc(event.actor_id || "local_faculty")} · ${esc(fmtDate(event.created_at))}</small></article>`).join("") : '<div class="fsw-empty-state"><strong>아직 변경 이력이 없습니다</strong><p>저장·승인·반려 기록이 이곳에 표시됩니다.</p></div>';
    overlay.hidden = false;
    $(".fsw-history-drawer header button", overlay)?.focus();
  }
  function closeHistory() { $("#fsw-history-overlay").hidden = true; }

  async function loadReviewSet(setId) {
    const queue = $("#fsw-question-queue");
    queue.innerHTML = '<div class="fsw-loading-state"><span class="fsw-spinner"></span>문항을 불러오는 중입니다.</div>';
    try {
      review.packet = await api(`/api/question-sets/${encodeURIComponent(setId)}`);
      review.selectedId = "";
      review.dirty = false;
      renderQuestionQueue();
      const url = new URL(window.location.href);
      url.searchParams.set("set", setId);
      window.history.replaceState({}, "", url);
    } catch (error) {
      queue.innerHTML = `<p class="fsw-empty-inline">문항 세트를 불러오지 못했습니다. ${esc(error.message)}</p>`;
      $("#fsw-review-editor").innerHTML = '<div class="fsw-empty-state"><strong>불러오기 실패</strong><p>잠시 후 다시 시도해주세요.</p></div>';
    }
  }

  async function initReview() {
    const select = $("#fsw-set-select");
    try {
      const payload = await api("/api/question-sets?limit=80");
      review.sets = payload.sets || [];
      if (!review.sets.length) {
        select.innerHTML = '<option value="">저장된 세트 없음</option>';
        $("#fsw-question-queue").innerHTML = '<p class="fsw-empty-inline">아직 생성되거나 가져온 문항 세트가 없습니다.</p>';
        $("#fsw-review-editor").innerHTML = '<div class="fsw-empty-state"><strong>검토할 세트가 없습니다</strong><p>새 문항을 만들거나 기존 문항을 가져오면 이곳에서 검토할 수 있습니다.</p><a class="fsw-primary-button" href="./">새 문항 만들기</a></div>';
        return;
      }
      select.innerHTML = review.sets.map((set) => `<option value="${attr(set.set_id)}">${esc(set.set_name || set.source_name || set.set_id)} (${esc(set.question_count || 0)}문항)</option>`).join("");
      const requested = new URLSearchParams(window.location.search).get("set");
      const initial = review.sets.some((set) => set.set_id === requested) ? requested : review.sets[0].set_id;
      select.value = initial;
      await loadReviewSet(initial);
    } catch (error) {
      select.innerHTML = '<option value="">세트 로드 실패</option>';
      toast(`문항 세트 로드 실패 · ${error.message}`);
    }

    select.addEventListener("change", async () => {
      if (review.dirty && !window.confirm("저장하지 않은 변경이 있습니다. 다른 세트로 이동할까요?")) { select.value = review.packet?.set_id || ""; return; }
      await loadReviewSet(select.value);
    });
    $("#fsw-review-filters")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-review-filter]");
      if (!button) return;
      if (review.dirty && !window.confirm("저장하지 않은 변경이 있습니다. 상태 필터를 바꿀까요?")) return;
      review.filter = button.dataset.reviewFilter;
      $$('[data-review-filter]').forEach((item) => item.classList.toggle("is-active", item === button));
      review.selectedId = "";
      renderQuestionQueue();
    });
    $("#fsw-question-queue")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-question-id]");
      if (!button || String(button.dataset.questionId) === String(review.selectedId)) return;
      if (review.dirty && !window.confirm("저장하지 않은 변경이 있습니다. 다른 문항으로 이동할까요?")) return;
      review.selectedId = button.dataset.questionId;
      renderQuestionQueue();
    });
    $("#fsw-review-editor")?.addEventListener("click", (event) => {
      const action = event.target.closest("[data-review-action]")?.dataset.reviewAction;
      if (action) submitReview(action);
      if (event.target.closest("[data-open-history]")) openHistory();
    });
    $$('[data-close-history]').forEach((button) => button.addEventListener("click", closeHistory));
    window.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("#fsw-history-overlay").hidden) closeHistory(); });
    window.addEventListener("beforeunload", (event) => { if (review.dirty) { event.preventDefault(); event.returnValue = ""; } });
  }

  // ---------- Evidence / media ----------
  const resources = { tab: "evidence", evidenceStatus: "draft", media: [], mediaFilter: "all", pendingDelete: "" };

  async function loadEvidence() {
    const list = $("#fsw-evidence-list");
    list.innerHTML = '<div class="fsw-loading-state"><span class="fsw-spinner"></span>근거 목록을 불러오는 중입니다.</div>';
    try {
      const payload = await api(`/api/evidence/review?status=${encodeURIComponent(resources.evidenceStatus)}&limit=80`);
      Object.entries(payload.counts || {}).forEach(([key, value]) => {
        const node = $(`[data-evidence-count="${key}"]`);
        if (node) node.textContent = String(value);
      });
      const items = payload.items || [];
      if (!items.length) {
        list.innerHTML = `<div class="fsw-empty-state"><strong>${resources.evidenceStatus === "draft" ? "검토 대기 근거가 없습니다" : "이 상태의 근거가 없습니다"}</strong><p>다른 상태 탭을 선택하거나 새로고침해주세요.</p></div>`;
        return;
      }
      list.innerHTML = items.map((item) => {
        const evidence = (item.evidence || [])[0];
        const sourceUrl = safeUrl(evidence?.url);
        return `<article class="fsw-evidence-card" data-evidence-row="${attr(item.question_id)}">
          <div class="fsw-evidence-card-head"><div><span class="fsw-evidence-type">${esc(evidence?.type || "근거")}</span><h2>${esc(evidence?.title || "자동 매칭된 근거 없음")}</h2><p class="fsw-evidence-meta">${esc([evidence?.journal, evidence?.year].filter(Boolean).join(" · ") || item.source_name || item.exam_id)}</p></div><span class="fsw-status-badge ${resources.evidenceStatus === "verified" ? "is-approved" : resources.evidenceStatus === "rejected" ? "is-rejected" : "is-needs"}">${esc(item.evidence_status)}</span></div>
          <p class="fsw-evidence-stem">연결 문항 · ${esc(item.question_number || item.question_id)}번<br>${esc(item.stem || "문항 요약 없음")}</p>
          ${evidence ? `${sourceUrl ? `<a class="fsw-evidence-source" href="${attr(sourceUrl)}" target="_blank" rel="noopener"><strong>${esc(evidence.title || "원문 근거")}</strong>${esc(evidence.matched_concept ? `검색 개념 · ${evidence.matched_concept}` : "원문 링크 열기")} ↗</a>` : `<div class="fsw-evidence-source"><strong>${esc(evidence.title || "근거 메타데이터")}</strong>${esc(evidence.matched_concept ? `검색 개념 · ${evidence.matched_concept}` : "원문 링크 없음")}</div>`}` : `<div class="fsw-evidence-source"><strong>자동 매칭 실패</strong>${esc(item.evidence_note || "근거를 찾지 못했습니다.")}</div>`}
          <div class="fsw-evidence-actions">${evidence ? `<button class="fsw-primary-button" type="button" data-evidence-action="approve" data-exam-id="${attr(item.exam_id)}" data-question-id="${attr(item.question_id)}">승인</button>` : ""}<button class="fsw-danger-button" type="button" data-evidence-action="reject" data-exam-id="${attr(item.exam_id)}" data-question-id="${attr(item.question_id)}">반려</button><button class="fsw-secondary-button" type="button" data-evidence-action="flag" data-exam-id="${attr(item.exam_id)}" data-question-id="${attr(item.question_id)}">검토 필요 표시</button></div>
        </article>`;
      }).join("");
    } catch (error) {
      list.innerHTML = `<div class="fsw-empty-state"><strong>근거 목록을 불러오지 못했습니다</strong><p>${esc(error.message)}</p><button class="fsw-secondary-button" type="button" data-evidence-retry>다시 시도</button></div>`;
      list.querySelector("[data-evidence-retry]")?.addEventListener("click", loadEvidence);
    }
  }

  async function updateEvidence(button) {
    const action = button.dataset.evidenceAction;
    if (action === "reject" && !window.confirm("이 문항의 연결 근거를 반려하고 제거할까요?")) return;
    button.disabled = true;
    try {
      await api("/api/evidence/review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ exam_id: button.dataset.examId, question_id: button.dataset.questionId, action }) });
      toast(action === "approve" ? "근거를 승인했습니다." : action === "flag" ? "검토 필요로 표시했습니다." : "근거를 반려했습니다.");
      await loadEvidence();
    } catch (error) { toast(`근거 처리 실패 · ${error.message}`); button.disabled = false; }
  }

  function mediaText(asset) {
    return [asset.original_name, asset.asset_type, asset.modality, asset.subject, asset.unit, asset.diagnosis, asset.caption, asset.faculty_note, ...(asset.key_findings || [])].filter(Boolean).join(" ").toLowerCase();
  }
  function renderMedia() {
    const grid = $("#fsw-media-grid");
    const query = $("#fsw-media-search")?.value.trim().toLowerCase() || "";
    const visible = resources.media.filter((asset) => (!query || mediaText(asset).includes(query)) && (resources.mediaFilter === "all" || String(asset.modality || asset.asset_type || "기타") === resources.mediaFilter));
    if (!visible.length) {
      grid.innerHTML = `<div class="fsw-empty-state"><strong>${resources.media.length ? "검색 결과가 없습니다" : "저장된 제시자료가 없습니다"}</strong><p>${resources.media.length ? "검색어나 modality 필터를 조정해주세요." : "왼쪽 업로드 양식에서 새 자료를 추가할 수 있습니다."}</p></div>`;
      return;
    }
    grid.innerHTML = visible.map((asset) => `<article class="fsw-media-card"><img src="${attr(safeUrl(asset.url))}" alt="${attr(asset.caption || asset.original_name || "제시자료")}" loading="lazy" /><div class="fsw-media-card-body"><strong>${esc(asset.caption || asset.diagnosis || asset.original_name || "제시자료")}</strong><p>${esc([asset.modality || asset.asset_type, asset.subject, asset.unit].filter(Boolean).join(" · "))}</p><div class="fsw-media-tags"><span class="${asset.deidentified ? "is-approved" : "is-review"}">${asset.deidentified ? "비식별화" : "비식별 확인 필요"}</span><span class="${asset.approved_for_question_use ? "is-approved" : "is-review"}">${asset.approved_for_question_use ? "사용 승인" : "승인 필요"}</span></div><div class="fsw-media-card-footer"><small>${esc(asset.asset_id)}</small><button type="button" data-delete-media="${attr(asset.asset_id)}">삭제</button></div></div></article>`).join("");
  }
  async function loadMedia() {
    const grid = $("#fsw-media-grid");
    grid.innerHTML = '<div class="fsw-loading-state"><span class="fsw-spinner"></span>미디어를 불러오는 중입니다.</div>';
    try {
      const payload = await api("/api/media");
      resources.media = payload.assets || [];
      const filter = $("#fsw-media-filter");
      const current = filter.value;
      const values = [...new Set(resources.media.map((asset) => String(asset.modality || asset.asset_type || "기타")).filter(Boolean))].sort();
      filter.innerHTML = '<option value="all">전체 자료</option>' + values.map((value) => `<option value="${attr(value)}">${esc(value)}</option>`).join("");
      filter.value = values.includes(current) ? current : "all";
      resources.mediaFilter = filter.value;
      renderMedia();
    } catch (error) {
      grid.innerHTML = `<div class="fsw-empty-state"><strong>미디어를 불러오지 못했습니다</strong><p>${esc(error.message)}</p><button class="fsw-secondary-button" type="button" data-media-retry>다시 시도</button></div>`;
      grid.querySelector("[data-media-retry]")?.addEventListener("click", loadMedia);
    }
  }

  function initResources() {
    $$('[data-resource-tab]').forEach((tab) => tab.addEventListener("click", () => {
      resources.tab = tab.dataset.resourceTab;
      $$('[data-resource-tab]').forEach((item) => { const active = item === tab; item.classList.toggle("is-active", active); item.setAttribute("aria-selected", String(active)); });
      $$('[data-resource-panel]').forEach((panel) => { panel.hidden = panel.dataset.resourcePanel !== resources.tab; });
      if (resources.tab === "media" && !resources.media.length) loadMedia();
    }));
    $("#fsw-evidence-filters")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-evidence-status]");
      if (!button) return;
      resources.evidenceStatus = button.dataset.evidenceStatus;
      $$('[data-evidence-status]').forEach((item) => item.classList.toggle("is-active", item === button));
      loadEvidence();
    });
    $("#fsw-evidence-reload")?.addEventListener("click", loadEvidence);
    $("#fsw-evidence-list")?.addEventListener("click", (event) => { const button = event.target.closest("[data-evidence-action]"); if (button) updateEvidence(button); });
    const mediaFile = $("#fsw-media-file");
    mediaFile?.addEventListener("change", () => { $("#fsw-media-file-label").textContent = mediaFile.files?.[0]?.name || "이미지 또는 DICOM 파일 선택"; });
    $("#fsw-media-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!mediaFile.files?.length) { toast("업로드할 미디어 파일을 선택해주세요."); return; }
      const submit = $("#fsw-media-submit");
      submit.disabled = true; submit.textContent = "업로드 중";
      try {
        await api("/api/media", { method: "POST", body: new FormData(event.currentTarget) });
        event.currentTarget.reset();
        $("#fsw-media-file-label").textContent = "이미지 또는 DICOM 파일 선택";
        toast("제시자료를 업로드했습니다.");
        await loadMedia();
      } catch (error) { toast(`미디어 업로드 실패 · ${error.message}`); }
      finally { submit.disabled = false; submit.textContent = "미디어 업로드"; }
    });
    $("#fsw-media-search")?.addEventListener("input", renderMedia);
    $("#fsw-media-filter")?.addEventListener("change", (event) => { resources.mediaFilter = event.target.value; renderMedia(); });
    $("#fsw-media-grid")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-delete-media]");
      if (!button) return;
      resources.pendingDelete = button.dataset.deleteMedia;
      $("#fsw-delete-overlay").hidden = false;
      $("#fsw-delete-confirm").focus();
    });
    $$('[data-delete-cancel]').forEach((button) => button.addEventListener("click", () => { resources.pendingDelete = ""; $("#fsw-delete-overlay").hidden = true; }));
    $("#fsw-delete-confirm")?.addEventListener("click", async () => {
      const id = resources.pendingDelete;
      if (!id) return;
      const button = $("#fsw-delete-confirm");
      button.disabled = true; button.textContent = "삭제 중";
      try {
        await api(`/api/media/${encodeURIComponent(id)}`, { method: "DELETE" });
        resources.pendingDelete = "";
        $("#fsw-delete-overlay").hidden = true;
        toast("제시자료를 삭제했습니다.");
        await loadMedia();
      } catch (error) { toast(`삭제 실패 · ${error.message}`); }
      finally { button.disabled = false; button.textContent = "삭제"; }
    });
    window.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("#fsw-delete-overlay").hidden) { resources.pendingDelete = ""; $("#fsw-delete-overlay").hidden = true; } });
    loadEvidence();
  }

  // ---------- Archive ----------
  const archive = { sets: [], filter: "all", selectedId: "" };
  function archiveVisible() {
    const query = $("#fsw-archive-search")?.value.trim().toLowerCase() || "";
    return archive.sets.filter((set) => {
      const status = setStatusInfo(set).key;
      const text = [set.set_name, set.source_name, set.subject, set.unit, set.set_id].filter(Boolean).join(" ").toLowerCase();
      return (archive.filter === "all" || archive.filter === status) && (!query || text.includes(query));
    });
  }
  function syncArchiveCounts() {
    const counts = { all: archive.sets.length, approved: 0, pending: 0 };
    archive.sets.forEach((set) => { counts[setStatusInfo(set).key] += 1; });
    Object.entries(counts).forEach(([key, value]) => { const node = $(`[data-archive-count="${key}"]`); if (node) node.textContent = String(value); });
  }
  function renderArchive() {
    syncArchiveCounts();
    const list = $("#fsw-archive-list");
    const visible = archiveVisible();
    if (!archive.sets.length) {
      list.innerHTML = '<div class="fsw-empty-state"><strong>저장된 문항 세트가 없습니다</strong><p>새 문항을 만들거나 기존 문항을 가져온 뒤 내보낼 수 있습니다.</p><a class="fsw-primary-button" href="./">새 문항 만들기</a></div>';
      return;
    }
    if (!visible.length) { list.innerHTML = '<div class="fsw-empty-state"><strong>조건에 맞는 세트가 없습니다</strong><p>검색어나 상태 필터를 조정해주세요.</p></div>'; return; }
    list.innerHTML = visible.map((set) => {
      const info = setStatusInfo(set);
      return `<button class="fsw-archive-row${archive.selectedId === set.set_id ? " is-active" : ""}" type="button" data-archive-set="${attr(set.set_id)}"><span class="fsw-select-mark">✓</span><span><strong>${esc(set.set_name || set.source_name || set.set_id)}</strong><small>${esc([set.subject, set.unit].filter(Boolean).join(" · ") || set.set_id)} · <span class="fsw-status-badge ${info.cls}">${esc(info.label)}</span></small></span><span class="fsw-archive-stats"><span>문항<b>${esc(set.question_count || 0)}</b></span><span>이미지<b>${esc(set.image_question_count || 0)}</b></span><span>확인 필요<b>${esc(set.needs_review_count || 0)}</b></span><span>승인<b>${esc(set.approved_count || 0)}</b></span></span></button>`;
    }).join("");
  }
  function selectArchiveSet(setId) {
    archive.selectedId = setId;
    renderArchive();
    const set = archive.sets.find((item) => item.set_id === setId);
    if (!set) return;
    $("#fsw-export-title").textContent = set.set_name || set.source_name || set.set_id;
    $("#fsw-export-summary").textContent = `${set.subject || "미분류"} · ${set.unit || "미분류"} · 승인 ${set.approved_count || 0}/${set.question_count || 0}문항`;
    const button = $("#fsw-export-submit");
    button.disabled = Number(set.approved_count || 0) < 1;
    button.textContent = button.disabled ? "승인 문항이 없어 내보낼 수 없습니다" : `${set.approved_count}개 승인 문항 내보내기`;
    $("#fsw-export-result").hidden = true;
  }
  async function runExport() {
    const set = archive.sets.find((item) => item.set_id === archive.selectedId);
    if (!set || Number(set.approved_count || 0) < 1) return;
    const format = $('input[name="export_format"]:checked')?.value || "cbt-docx";
    const button = $("#fsw-export-submit");
    const result = $("#fsw-export-result");
    button.disabled = true; button.textContent = "파일 생성 중";
    result.hidden = false; result.className = "fsw-export-result"; result.innerHTML = '<span class="fsw-spinner"></span> 승인 문항을 준비하고 파일을 생성하는 중입니다.';
    const payloadByFormat = {
      "cbt-docx": { include_unapproved: false, include_explanations: true },
      "cbt-hwp": { include_unapproved: false, include_answers: true, include_explanations: true, include_references: true },
      anki: { include_unapproved: false },
    };
    try {
      const payload = await api(`/api/question-sets/${encodeURIComponent(set.set_id)}/export/${format}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payloadByFormat[format]) });
      const url = safeUrl(payload.download_url);
      result.innerHTML = `<strong>내보내기 파일이 준비되었습니다.</strong><br>${esc(set.set_name || set.source_name || set.set_id)} · 승인 ${esc(set.approved_count)}문항${url ? `<br><a href="${attr(url)}" download>파일 다운로드</a>` : ""}`;
      toast("내보내기 파일 생성을 완료했습니다.");
    } catch (error) {
      result.className = "fsw-export-result is-error";
      result.innerHTML = `<strong>파일 생성에 실패했습니다.</strong><br>${esc(error.message)}<br><button class="fsw-secondary-button" type="button" data-export-retry>다시 시도</button>`;
      result.querySelector("[data-export-retry]")?.addEventListener("click", runExport);
    } finally {
      button.disabled = false;
      button.textContent = `${set.approved_count}개 승인 문항 내보내기`;
    }
  }
  async function initArchive() {
    try {
      const payload = await api("/api/question-sets?limit=80");
      archive.sets = payload.sets || [];
      renderArchive();
    } catch (error) {
      $("#fsw-archive-list").innerHTML = `<div class="fsw-empty-state"><strong>문항 세트를 불러오지 못했습니다</strong><p>${esc(error.message)}</p></div>`;
    }
    $("#fsw-archive-search")?.addEventListener("input", renderArchive);
    $("#fsw-archive-filters")?.addEventListener("click", (event) => { const button = event.target.closest("[data-archive-filter]"); if (!button) return; archive.filter = button.dataset.archiveFilter; $$('[data-archive-filter]').forEach((item) => item.classList.toggle("is-active", item === button)); renderArchive(); });
    $("#fsw-archive-list")?.addEventListener("click", (event) => { const button = event.target.closest("[data-archive-set]"); if (button) selectArchiveSet(button.dataset.archiveSet); });
    $("#fsw-export-submit")?.addEventListener("click", runExport);
  }

  wireNavigation();
  loadReviewBadge();
  if (page === "import") initImport();
  if (page === "sources") initSources();
  if (page === "review") initReview();
  if (page === "evidence-media") initResources();
  if (page === "archive") initArchive();
})();
