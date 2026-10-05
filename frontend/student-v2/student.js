(() => {
  "use strict";

  const KEYS = {
    builder: "paccine.student.builder.v2",
    session: "paccine.student.session.v2",
    result: "paccine.student.result.v2",
  };
  const page = document.body.dataset.studentPage;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const load = (key, fallback = null) => {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  };
  const save = (key, value) => localStorage.setItem(key, JSON.stringify(value));
  const remove = (key) => localStorage.removeItem(key);
  const uid = (prefix) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const formatTime = (milliseconds) => {
    const total = Math.max(0, Math.floor((milliseconds || 0) / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  };
  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: { "content-type": "application/json", ...(options.headers || {}) },
    });
    let payload = {};
    try { payload = await response.json(); } catch { payload = {}; }
    if (!response.ok) throw new Error(payload.detail || "요청을 처리하지 못했습니다.");
    return payload;
  };
  const shuffled = (items) => {
    const copy = [...items];
    for (let index = copy.length - 1; index > 0; index -= 1) {
      const target = Math.floor(Math.random() * (index + 1));
      [copy[index], copy[target]] = [copy[target], copy[index]];
    }
    return copy;
  };
  const selectionFor = (session, question) => session.answers?.[question.question_id] || [];

  function initHome() {
    const session = load(KEYS.session, null);
    const result = load(KEYS.result, null);
    const status = $("#home-status");
    const content = $("#home-content");
    const metrics = $("#home-metrics");

    if (session?.questions?.length) {
      const answered = session.questions.filter((question) => selectionFor(session, question).length).length;
      const percent = Math.round((answered / session.questions.length) * 100);
      $("#home-resume-card").hidden = false;
      $("#home-empty-card").hidden = true;
      $("#home-resume-title").textContent = session.title || [session.subject, session.unit].filter(Boolean).join(" · ") || "진행 중인 학습 세트";
      $("#home-resume-copy").textContent = `${answered}/${session.questions.length}문항 답변 · ${formatTime(session.elapsedMs)} 경과`;
      $("#home-resume-icon").textContent = String(session.subject || session.title || "P").trim().slice(0, 1);
      $("#home-progress-bar").style.width = `${percent}%`;
      $("#home-progress-copy").textContent = `진행 ${percent}%`;
      $("#home-mode-copy").textContent = session.mode === "exam" ? "시험 모드" : "학습 모드";
      $("#home-resume-state").textContent = session.syncStatus === "local_only" ? "기기 저장" : "저장됨";
    } else {
      $("#home-resume-card").hidden = true;
      $("#home-empty-card").hidden = false;
    }

    const resultItems = Array.isArray(result?.items) ? result.items : [];
    const attempted = resultItems.filter((item) => item.attempt);
    const correct = attempted.filter((item) => item.attempt?.is_correct);
    const bookmarks = resultItems.filter((item) => item.bookmarked);
    $("#home-score").textContent = attempted.length ? `${Math.round((correct.length / attempted.length) * 100)}%` : "—";
    $("#home-completed-count").textContent = String(attempted.length);
    $("#home-bookmark-count").textContent = String(bookmarks.length);
    $("#home-time").textContent = formatTime(result?.elapsedMs || session?.elapsedMs || 0);

    content.hidden = false;
    metrics.hidden = false;

    (async () => {
      try {
        const payload = await api("/api/practice/catalog");
        $("#home-available-count").textContent = payload.available_question_count || 0;
        status.hidden = true;
      } catch (error) {
        $("#home-available-count").textContent = "—";
        status.hidden = false;
        status.classList.add("is-error");
        status.textContent = `학습 문항 현황을 불러오지 못했습니다. ${error.message}`;
      }
    })();
  }

  function initLibrary() {
    const state = { catalog: [], query: "", subject: "", media: "" };
    const session = load(KEYS.session, null);
    if (session?.questions?.length) {
      const answered = session.questions.filter((question) => selectionFor(session, question).length).length;
      $("#resume-session-card").hidden = false;
      $("#resume-session-title").textContent = session.title || "진행 중인 학습 세트";
      const storageLabel = session.syncStatus === "local_only" ? " · 기기에 임시 저장" : "";
      $("#resume-session-copy").textContent = `${answered}/${session.questions.length}문항 답변 · ${formatTime(session.elapsedMs)} 경과${storageLabel}`;
    }

    const showStatus = (message, error = false) => {
      const node = $("#library-status");
      node.hidden = !message;
      node.textContent = message || "";
      node.classList.toggle("is-error", error);
    };
    const reset = () => {
      state.query = ""; state.subject = ""; state.media = "";
      $("#library-search").value = ""; $("#library-subject").value = ""; $("#library-media").value = "";
      render();
    };
    const filtered = () => state.catalog.filter((item) => {
      const haystack = [item.title, item.subject, item.unit, item.source_name, item.topic, item.major_category].join(" ").toLocaleLowerCase("ko");
      if (state.query && !haystack.includes(state.query.toLocaleLowerCase("ko"))) return false;
      if (state.subject && item.subject !== state.subject) return false;
      if (state.media === "media" && !item.has_media) return false;
      if (state.media === "text" && item.has_media) return false;
      return true;
    });

    function render() {
      const items = filtered();
      $("#library-result-count").textContent = `${items.length}개 세트`;
      $("#library-grid").hidden = !items.length;
      $("#library-empty").hidden = Boolean(items.length);
      $("#library-grid").innerHTML = items.map((item) => {
        const title = item.title || [item.subject, item.unit].filter(Boolean).join(" · ") || "학습 세트";
        const description = [item.major_category, item.topic, item.source_name].filter(Boolean).join(" · ") || "현재 학습에 사용할 수 있는 문항";
        const icon = (item.subject || title || "P").trim().slice(0, 1);
        const tags = [item.exam_year, item.instructor, item.has_media ? "자료 포함" : "텍스트", item.difficulty].filter(Boolean);
        return `<article class="library-set-card"><div class="library-card-top"><span class="library-card-icon">${escapeHtml(icon)}</span><span>학습 가능</span></div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p><div class="library-card-meta">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div><div class="library-card-footer"><strong>${item.approved_count || 0}문항</strong><a href="/student-v2/builder.html?set=${encodeURIComponent(item.set_id)}">범위 구성 <span>→</span></a></div></article>`;
      }).join("");
    }

    $("#library-search").addEventListener("input", (event) => { state.query = event.target.value.trim(); render(); });
    $("#library-subject").addEventListener("change", (event) => { state.subject = event.target.value; render(); });
    $("#library-media").addEventListener("change", (event) => { state.media = event.target.value; render(); });
    $("#library-reset").addEventListener("click", reset);
    $("#library-empty-reset").addEventListener("click", reset);

    (async () => {
      try {
        const payload = await api("/api/practice/catalog");
        state.catalog = payload.sets || [];
        $("#library-question-count").textContent = payload.available_question_count || 0;
        const subjects = [...new Set(state.catalog.map((item) => String(item.subject || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ko"));
        $("#library-subject").innerHTML = `<option value="">전체 과목</option>${subjects.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("")}`;
        $("#library-content").hidden = false;
        showStatus(state.catalog.length ? "" : "아직 학습 가능한 세트가 없습니다.", !state.catalog.length);
        render();
      } catch (error) {
        showStatus(`서재를 불러오지 못했습니다. ${error.message}`, true);
      }
    })();
  }

  function initBuilder() {
    const saved = load(KEYS.builder, {}) || {};
    const requestedSetId = new URLSearchParams(window.location.search).get("set") || "";
    const state = {
      catalog: [], questions: [], count: Number(saved.count) || 10,
      mode: saved.mode || "learning", construction: saved.construction || "random",
      type: saved.type || "all", difficulty: saved.difficulty || "all",
      mediaOnly: Boolean(saved.mediaOnly),
      setId: requestedSetId || saved.setId || "",
      retryRefs: Array.isArray(saved.retryRefs) ? saved.retryRefs : [],
      filters: { subject: "", year: "", instructor: "", major: "", topic: "", domain: "", ...(saved.filters || {}) },
    };
    const result = load(KEYS.result, null);
    const wrongIds = new Set((result?.items || []).filter((item) => item.attempt && !item.attempt.is_correct).map((item) => item.question.question_id));
    const fieldMap = {
      subject: ["#filter-subject", "전체 과목"], year: ["#filter-year", "전체 연도"],
      instructor: ["#filter-instructor", "전체 교수자"], major: ["#filter-major", "전체"],
      topic: ["#filter-topic", "전체"], domain: ["#filter-domain", "전체 영역"],
    };
    const persist = () => save(KEYS.builder, {
      count: state.count, mode: state.mode, construction: state.construction,
      type: state.type, difficulty: state.difficulty, mediaOnly: state.mediaOnly, filters: state.filters,
      setId: state.setId, retryRefs: state.retryRefs,
    });
    const showStatus = (message, error = false) => {
      const node = $("#builder-status");
      node.hidden = !message;
      node.textContent = message || "";
      node.classList.toggle("is-error", error);
    };
    const valueOf = (value) => String(value || "").trim();
    const unique = (key) => [...new Set(state.questions.map((question) => valueOf(question[key])).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ko"));

    function setOptions(key) {
      const [selector, emptyLabel] = fieldMap[key];
      const select = $(selector);
      const selected = state.filters[key] || "";
      select.innerHTML = `<option value="">${emptyLabel}</option>${unique(key).map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("")}`;
      select.value = unique(key).includes(selected) ? selected : "";
      state.filters[key] = select.value;
    }

    function matches(question) {
      if (state.setId && question.set_id !== state.setId) return false;
      if (state.retryRefs.length && !state.retryRefs.includes(`${question.source_id}|${question.question_id}`)) return false;
      if (Object.entries(state.filters).some(([key, value]) => value && valueOf(question[key]) !== value)) return false;
      if (state.type !== "all" && question.type_group !== state.type) return false;
      if (state.difficulty !== "all" && valueOf(question.difficulty) !== state.difficulty) return false;
      if (state.mediaOnly && !question.has_media) return false;
      return true;
    }

    function candidates() {
      const base = state.questions.filter(matches);
      if (state.construction === "weakness" && wrongIds.size) {
        return [...base].sort((a, b) => Number(wrongIds.has(b.question_id)) - Number(wrongIds.has(a.question_id)));
      }
      if (state.construction === "exam") {
        return [...base].sort((a, b) => `${a.set_id}:${a.question_number}`.localeCompare(`${b.set_id}:${b.question_number}`, "ko", { numeric: true }));
      }
      return base;
    }

    function scopeLabel(list) {
      const bits = [state.filters.subject, state.filters.year, state.filters.major, state.filters.topic].filter(Boolean);
      return bits.join(" · ") || (list[0]?.subject || "전체 학습 문항");
    }

    function render() {
      const list = candidates();
      const max = Math.min(50, list.length);
      state.count = max ? clamp(state.count, 1, max) : 0;
      $("#question-count-range").max = Math.max(1, max);
      $("#question-count-range").value = Math.max(1, state.count);
      $("#question-count-range").disabled = !max;
      $("#question-count").textContent = state.count;
      $("#range-max").textContent = max || 0;
      $("#summary-count").textContent = state.count;
      $("#start-count").textContent = state.count;
      const secondsPerQuestion = state.mediaOnly ? 84 : 72;
      $("#summary-time").textContent = `${Math.max(1, Math.ceil(state.count * secondsPerQuestion / 60))}분`;
      $("#set-title").textContent = state.retryRefs.length ? `다시 풀기 ${state.retryRefs.length}문항` : state.construction === "exam" ? "시험지 순서 세트" : state.construction === "weakness" ? "취약 영역 보강 세트" : "학습 문항 맞춤 세트";
      $("#set-description").textContent = `${scopeLabel(list)} · ${list.length}문항 중 ${state.count}문항 선택`;
      $("#preview-scope").textContent = scopeLabel(list);
      $("#preview-approved").textContent = `사용 가능 ${list.length}`;
      $("#start-label").textContent = state.mode === "learning" ? "문항별 채점과 Reader 학습 패널을 사용합니다." : "세트 종료 후 정답과 해설을 공개합니다.";
      $("#filter-media").checked = state.mediaOnly;
      $$("#construction-tabs button").forEach((button) => button.classList.toggle("is-selected", button.dataset.construction === state.construction));
      $$("#solution-mode button").forEach((button) => button.classList.toggle("is-selected", button.dataset.mode === state.mode));
      $$("#type-chips button").forEach((button) => button.classList.toggle("is-selected", button.dataset.filterValue === state.type));
      $$("#difficulty-chips button").forEach((button) => button.classList.toggle("is-selected", button.dataset.filterValue === state.difficulty));
      const preview = list.slice(0, Math.min(state.count, 8));
      $("#question-preview").innerHTML = preview.length ? preview.map((question, index) => `
        <div class="preview-row"><span>${String(index + 1).padStart(2, "0")}</span><p>${escapeHtml(question.stem)}</p><span>${question.type_group === "multiple" ? "복수" : question.has_media ? "자료" : "단일"}</span></div>`).join("")
        : '<div class="preview-empty"><strong>조건에 맞는 학습 문항이 없습니다.</strong><span>필터를 초기화하거나 범위를 넓혀보세요.</span></div>';
      $("#builder-empty-actions").hidden = Boolean(preview.length);
      $("#disable-media-filter").hidden = !state.mediaOnly;
      $("#start-set").disabled = !state.count;
      persist();
    }

    async function startSet(forceExamOrder = false) {
      let list = candidates();
      if (!list.length) return;
      if (!forceExamOrder && state.construction === "random") list = shuffled(list);
      const questions = list.slice(0, state.count);
      const first = questions[0];
      const startButton = $("#start-set");
      startButton.disabled = true;
      showStatus("학습 문항과 세션을 확인하는 중입니다.");
      try {
        const serverSession = await api("/api/practice/sessions", { method: "POST", body: JSON.stringify({
          title: `${scopeLabel(list)} 학습 세트`, mode: state.mode,
          questions: questions.map((question) => ({ exam_id: question.source_id, question_id: question.question_id })),
        }) });
        const session = {
        schemaVersion: "student_session.v4", sessionId: serverSession.session_id || uid("session"),
        sourceId: first.source_id, setId: first.set_id,
        title: `${scopeLabel(list)} · ${state.construction === "exam" ? "시험지" : state.construction === "weakness" ? "취약 보강" : "맞춤"} 세트`,
        subject: state.filters.subject || first.subject, unit: first.unit, mode: state.mode,
        questions, index: 0, answers: {}, attempts: {}, feedback: {}, bookmarks: [],
        eliminated: {}, notes: {}, questionTimes: {}, elapsedMs: 0, timerHidden: false,
        startedAt: new Date().toISOString(), paused: false,
      };
      save(KEYS.session, session);
      state.retryRefs = []; state.setId = ""; persist();
      window.location.href = "/student-v2/practice.html";
      } catch (error) {
        showStatus(`세트를 시작하지 못했습니다. ${error.message}`, true);
        startButton.disabled = false;
      }
    }

    Object.entries(fieldMap).forEach(([key, [selector]]) => $(selector).addEventListener("change", (event) => { state.filters[key] = event.target.value; render(); }));
    $$("#type-chips button").forEach((button) => button.addEventListener("click", () => { state.type = button.dataset.filterValue; render(); }));
    $$("#difficulty-chips button").forEach((button) => button.addEventListener("click", () => { state.difficulty = button.dataset.filterValue; render(); }));
    $$("#construction-tabs button").forEach((button) => button.addEventListener("click", () => { state.construction = button.dataset.construction; render(); }));
    $$("#solution-mode button").forEach((button) => button.addEventListener("click", () => { state.mode = button.dataset.mode; render(); }));
    $("#filter-media").addEventListener("change", (event) => { state.mediaOnly = event.target.checked; render(); });
    $("#question-count-range").addEventListener("input", (event) => { state.count = Number(event.target.value); render(); });
    $("#reset-filters").addEventListener("click", () => {
      state.filters = { subject: "", year: "", instructor: "", major: "", topic: "", domain: "" };
      state.type = "all"; state.difficulty = "all"; state.mediaOnly = false; state.setId = ""; state.retryRefs = [];
      Object.keys(fieldMap).forEach(setOptions); render();
    });
    $("#reset-empty-filters").addEventListener("click", () => $("#reset-filters").click());
    $("#disable-media-filter").addEventListener("click", () => { state.mediaOnly = false; render(); });
    $("#start-set").addEventListener("click", () => startSet());
    $("#start-original").addEventListener("click", () => { state.construction = "exam"; render(); startSet(true); });
    $("#mobile-filter-toggle").addEventListener("click", () => document.body.classList.add("filters-open"));
    $("#mobile-filter-apply").addEventListener("click", () => document.body.classList.remove("filters-open"));

    (async () => {
      try {
        const payload = await api("/api/practice/catalog");
        state.catalog = payload.sets || [];
        const packets = await Promise.all(state.catalog.map(async (item) => {
          const packet = await api(`/api/practice/sets/${encodeURIComponent(item.set_id)}/questions`);
          return (packet.questions || []).map((question) => ({
            ...question, source_id: item.source_id, set_id: item.set_id,
            subject: item.subject || question.course_name || "미분류", unit: item.unit || question.unit || "",
            year: valueOf(item.exam_year), instructor: valueOf(item.instructor),
            major: valueOf(item.major_category), topic: valueOf(item.topic), domain: valueOf(item.assessment_domain),
            difficulty: valueOf(item.difficulty) || "보통", has_media: Boolean(question.media_refs?.length),
            type_group: question.selection_mode === "multiple" ? "multiple" : question.media_refs?.length ? "media" : "single",
          }));
        }));
        state.questions = packets.flat();
        $("#available-count").textContent = state.questions.length;
        if (!state.questions.length) throw new Error("아직 학습 가능한 교수 승인 문항이 없습니다.");
        Object.keys(fieldMap).forEach(setOptions);
        $("#builder-grid").hidden = false;
        showStatus(""); render();
      } catch (error) {
        showStatus(error.message, true);
      }
    })();
  }

  function initBuilderLegacy() {
    const state = {
      catalog: [],
      selectedId: null,
      preview: [],
      count: 1,
      mode: "learning",
      shuffle: true,
      ...(load(KEYS.builder, {}) || {}),
    };
    let loadingPreview = false;

    const persistBuilder = () => save(KEYS.builder, {
      selectedId: state.selectedId,
      count: state.count,
      mode: state.mode,
      shuffle: state.shuffle,
    });
    const selectedSet = () => state.catalog.find((item) => item.set_id === state.selectedId) || state.catalog[0];
    const renderStatus = (message, error = false) => {
      const node = $("#builder-status");
      node.hidden = !message;
      node.textContent = message || "";
      node.classList.toggle("is-error", error);
    };

    function renderSources() {
      const root = $("#source-list");
      root.innerHTML = state.catalog.map((item) => `
        <button class="source-option ${item.set_id === state.selectedId ? "is-selected" : ""}" type="button" data-set-id="${escapeHtml(item.set_id)}">
          <span class="source-radio" aria-hidden="true"></span>
          <span class="source-copy"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.source_name || "교수 제작 문항")} · ${item.has_media ? "제시자료 포함" : "텍스트 문항"}</small></span>
          <span class="source-count">${item.approved_count}</span>
        </button>`).join("");
      $$(".source-option", root).forEach((button) => button.addEventListener("click", async () => {
        state.selectedId = button.dataset.setId;
        state.count = clamp(state.count, 1, selectedSet().approved_count);
        persistBuilder();
        renderSources();
        await loadPreview();
      }));
    }

    function renderBuilder() {
      const item = selectedSet();
      if (!item) return;
      state.count = clamp(state.count, 1, item.approved_count);
      $("#question-count").textContent = state.count;
      $("#summary-count").textContent = state.count;
      $("#summary-time").textContent = `${Math.max(2, state.count * 2)}분`;
      $("#summary-mode").textContent = state.mode === "learning" ? "학습" : "시험";
      $("#set-title").textContent = item.title;
      $("#set-description").textContent = `${item.source_name || "교수 제작 문항"} · 승인 ${item.approved_count}문항${item.has_media ? " · 제시자료 포함" : ""}`;
      $("#preview-approved").textContent = `승인 ${item.approved_count}`;
      $("#count-minus").disabled = state.count <= 1;
      $("#count-plus").disabled = state.count >= item.approved_count;
      $("#shuffle-questions").checked = state.shuffle;
      $$(".mode-switch button").forEach((button) => button.classList.toggle("is-selected", button.dataset.mode === state.mode));
      $("#start-label").textContent = state.mode === "learning" ? "선택한 조건으로 세트를 만듭니다" : "시험처럼 한 번에 풀고 제출합니다";
      $("#start-sub").textContent = state.mode === "learning" ? "학습 모드 · 문항별 즉시 해설" : "시험 모드 · 세트 종료 후 결과 공개";
      const preview = state.preview.slice(0, state.count);
      $("#question-preview").innerHTML = loadingPreview
        ? '<div class="preview-empty">문항 구성을 불러오는 중입니다.</div>'
        : preview.length
          ? preview.map((question, index) => `<div class="preview-row"><span>${String(index + 1).padStart(2, "0")}</span><p>${escapeHtml(question.stem)}</p><span>${question.selection_mode === "multiple" ? "복수" : "단일"}</span></div>`).join("")
          : '<div class="preview-empty">풀이 가능한 승인 문항이 없습니다.</div>';
      $("#start-set").disabled = loadingPreview || preview.length < state.count;
      persistBuilder();
    }

    async function loadPreview() {
      const item = selectedSet();
      if (!item) return;
      loadingPreview = true;
      renderBuilder();
      try {
        const payload = await api(`/api/practice/sets/${encodeURIComponent(item.set_id)}/questions`);
        state.preview = payload.questions || [];
        renderStatus("");
      } catch (error) {
        state.preview = [];
        renderStatus(error.message, true);
      } finally {
        loadingPreview = false;
        renderBuilder();
      }
    }

    $("#count-minus").addEventListener("click", () => { state.count -= 1; renderBuilder(); });
    $("#count-plus").addEventListener("click", () => { state.count += 1; renderBuilder(); });
    $$(".mode-switch button").forEach((button) => button.addEventListener("click", () => { state.mode = button.dataset.mode; renderBuilder(); }));
    $("#shuffle-questions").addEventListener("change", (event) => { state.shuffle = event.target.checked; persistBuilder(); });
    $("#start-set").addEventListener("click", () => {
      const item = selectedSet();
      const questions = state.shuffle ? shuffled(state.preview).slice(0, state.count) : state.preview.slice(0, state.count);
      const session = {
        schemaVersion: "student_session.v2",
        sessionId: uid("session"),
        sourceId: item.source_id,
        setId: item.set_id,
        title: item.title,
        subject: item.subject,
        unit: item.unit,
        mode: state.mode,
        questions,
        index: 0,
        answers: {},
        attempts: {},
        feedback: {},
        bookmarks: [],
        questionTimes: {},
        elapsedMs: 0,
        paused: false,
        startedAt: new Date().toISOString(),
      };
      save(KEYS.session, session);
      window.location.href = "/student-v2/practice.html";
    });

    (async () => {
      try {
        const payload = await api("/api/practice/catalog");
        state.catalog = payload.sets || [];
        $("#available-count").textContent = payload.available_question_count || 0;
        if (!state.catalog.length) {
          renderStatus("아직 학생에게 공개할 교수 승인 문항이 없습니다. 교수 스튜디오에서 문항을 승인하면 여기에 표시됩니다.", true);
          return;
        }
        if (!state.catalog.some((item) => item.set_id === state.selectedId)) state.selectedId = state.catalog[0].set_id;
        if (!state.count || state.count === 1) state.count = Math.min(10, selectedSet().approved_count);
        $("#builder-grid").hidden = false;
        renderSources();
        await loadPreview();
      } catch (error) {
        renderStatus(`승인 문항을 불러오지 못했습니다. ${error.message}`, true);
      }
    })();
  }

  function initPractice() {
    const session = load(KEYS.session);
    if (!session?.questions?.length) { window.location.replace("/student-v2/builder.html"); return; }
    session.answers ||= {}; session.attempts ||= {}; session.feedback ||= {}; session.bookmarks ||= [];
    session.eliminated ||= {}; session.notes ||= {}; session.reports ||= {}; session.examSaved ||= {};
    session.attemptSequences ||= {};
    session.questionTimes ||= {}; session.elapsedMs ||= 0;
    session.paused = Boolean(session.paused);
    session.index = clamp(session.index || 0, 0, session.questions.length - 1);
    let finishing = false;
    let activeTab = "expl";
    let pendingRange = null;
    let renderedQuestionId = null;
    const marks = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"];
    const currentQuestion = () => session.questions[session.index];
    const persist = () => save(KEYS.session, session);
    const selectedFor = (question) => selectionFor(session, question);
    const attemptFor = (question) => session.attempts[question.question_id];
    const feedbackFor = (question) => session.feedback[question.question_id];
    const completedCount = () => Object.keys(session.attempts).length;
    const answeredCount = () => session.questions.filter((question) => selectedFor(question).length).length;
    const showNotice = (message, error = false) => {
      const node = $("#practice-status"); node.hidden = !message; node.textContent = message || ""; node.classList.toggle("is-error", error);
    };

    function resetQuestionScroll() {
      const pane = $(".reader-question-pane");
      const workspace = $(".reader-workspace");
      if (pane) pane.scrollTop = 0;
      if (workspace) workspace.scrollTop = 0;
    }

    function renderNavigator() {
      $("#reader-question-navigator").innerHTML = session.questions.map((question, index) => {
        const classes = [
          index === session.index ? "is-current" : "",
          selectedFor(question).length ? "is-answered" : "",
          session.bookmarks.includes(question.question_id) ? "is-bookmarked" : "",
        ].filter(Boolean).join(" ");
        return `<button class="${classes}" type="button" data-question-index="${index}" aria-label="${index + 1}번 문항">${index + 1}</button>`;
      }).join("");
      $$("#reader-question-navigator button").forEach((button) => button.addEventListener("click", () => {
        session.index = Number(button.dataset.questionIndex);
        renderedQuestionId = null;
        $("#question-navigator-overlay").hidden = true;
        persist(); renderPractice(); resetQuestionScroll();
      }));
    }

    function setPaused(paused) {
      session.paused = Boolean(paused);
      $("#resume-session").hidden = !session.paused;
      $("#timer-pill").classList.toggle("is-paused", session.paused);
      $("#timer-label").textContent = session.paused ? "일시정지" : "경과";
      persist();
    }

    function renderMeta(question) {
      const values = [question.course_name || question.subject || session.subject, question.unit || session.unit, question.has_media || question.media_refs?.length ? "이미지 판독" : question.selection_mode === "multiple" ? "복수 정답" : "단일 정답"].filter(Boolean);
      $("#question-meta-chips").innerHTML = values.map((value) => `<span>${escapeHtml(value)}</span>`).join("");
    }

    function renderMedia(question) {
      const media = (question.media_refs || []).filter((item) => item.url);
      $("#reader-media-section").hidden = !media.length;
      $("#question-media").innerHTML = media.map((item, index) => `
        <button type="button" data-media-index="${index}"><img src="${escapeHtml(item.url)}" alt="문항 제시자료 ${index + 1}"><span>${escapeHtml(item.caption || `제시자료 ${index + 1}`)}</span><i>⤢</i></button>`).join("");
      $$("#question-media button").forEach((button) => button.addEventListener("click", () => {
        const item = media[Number(button.dataset.mediaIndex)];
        $("#expanded-image").src = item.url; $("#expanded-image-caption").textContent = item.caption || "교수 승인 제시자료";
        $("#image-overlay").hidden = false;
      }));
    }

    function renderChoices(question) {
      const selected = selectedFor(question);
      const attempt = attemptFor(question);
      const feedback = feedbackFor(question);
      const correct = new Set(feedback?.result?.correct_choices || []);
      const eliminated = new Set(session.eliminated[question.question_id] || []);
      $("#choice-list").innerHTML = Object.entries(question.choices || {}).map(([key, value], index) => {
        const classes = ["reader-choice", selected.includes(key) ? "is-selected" : "", eliminated.has(key) ? "is-eliminated" : "", attempt && correct.has(key) ? "is-correct" : "", attempt && selected.includes(key) && !correct.has(key) ? "is-wrong" : ""].filter(Boolean).join(" ");
        const badge = attempt && correct.has(key) ? '<span class="reader-choice-badge">정답</span>' : attempt && selected.includes(key) && !correct.has(key) ? '<span class="reader-choice-badge">내 선택</span>' : "";
        return `<div class="${classes}"><button class="reader-choice-select" type="button" data-choice="${escapeHtml(key)}" ${attempt ? "disabled" : ""}><span>${marks[index] || key}</span><b>${escapeHtml(value)}</b>${badge}</button><button class="reader-choice-cross" type="button" data-cross="${escapeHtml(key)}" ${attempt ? "disabled" : ""} aria-label="${index + 1}번 선지 소거">${eliminated.has(key) ? "↩" : "✕"}</button></div>`;
      }).join("");
      $$(".reader-choice-select").forEach((button) => button.addEventListener("click", () => chooseAnswer(question, button.dataset.choice)));
      $$(".reader-choice-cross").forEach((button) => button.addEventListener("click", () => toggleEliminated(question, button.dataset.cross)));
    }

    function lockedPanel(title = "풀이 후 근거를 확인합니다.") {
      return `<div class="reader-panel-kicker">학습 패널</div><section class="reader-panel-card"><strong>${escapeHtml(title)}</strong><p>정답, 해설, 출제 포인트, 복습 카드 초안을 한 화면에 모읍니다. 답을 선택하고 ‘${session.mode === "exam" ? "선택 저장" : "정답 확인"}’을 누르세요.</p></section>`;
    }

    function renderPanel(question) {
      $$("#reader-tabs button").forEach((button) => button.classList.toggle("is-selected", button.dataset.readerTab === activeTab));
      const attempt = attemptFor(question);
      const feedback = feedbackFor(question);
      const root = $("#reader-panel");
      if (activeTab === "note") {
        root.innerHTML = `<div class="reader-panel-kicker">개념 노트</div><section class="reader-panel-card"><strong>이 문항에서 기억할 내용</strong><p>선지 소거 이유나 다시 볼 개념을 자유롭게 적어두세요.</p><textarea id="reader-note" placeholder="나만의 학습 메모">${escapeHtml(session.notes[question.question_id] || "")}</textarea></section>`;
        $("#reader-note").addEventListener("input", (event) => { session.notes[question.question_id] = event.target.value; persist(); });
        return;
      }
      if (session.mode === "exam" || !attempt || !feedback) { root.innerHTML = lockedPanel(session.mode === "exam" ? "시험 모드 · 해설 잠금" : undefined); return; }
      const correctKeys = feedback.result?.correct_choices || [];
      const correctText = correctKeys.map((key) => `${key}. ${question.choices?.[key] || ""}`).join(" / ");
      if (activeTab === "expl") {
        root.innerHTML = `<div class="reader-panel-kicker">정답 해설</div><div class="panel-result ${attempt.is_correct ? "is-correct" : "is-wrong"}">${attempt.is_correct ? "정답입니다" : `정답 ${escapeHtml(correctText)}`}</div><section class="reader-panel-card"><strong>교수 승인 해설</strong><p>${escapeHtml(feedback.explanation || feedback.safe_message || "검토된 해설이 준비되지 않았습니다.")}</p></section>`;
      } else if (activeTab === "point") {
        root.innerHTML = `<div class="reader-panel-kicker">출제 포인트</div><section class="reader-panel-card"><strong>${escapeHtml(question.course_name || session.subject || "이번 영역")} · ${escapeHtml(question.unit || session.unit || "핵심 판단")}</strong><ol><li>질문이 묻는 평가 항목을 먼저 확인합니다.</li><li>병력·검사·제시자료에서 결정 단서를 찾습니다.</li><li>각 선지가 기준에 맞는지 대조합니다.</li></ol></section>`;
      } else if (activeTab === "media") {
        const labs = Array.isArray(question.lab_values) ? question.lab_values : [];
        root.innerHTML = `<div class="reader-panel-kicker">검사 · 자료</div><section class="reader-panel-card"><strong>제시자료 ${question.media_refs?.length || 0}개 · 참고치 ${labs.length}개</strong><p>${labs.length ? labs.map((item) => typeof item === "string" ? item : `${item.label || item.name || "검사"} ${item.value || ""}`).map(escapeHtml).join("<br>") : "이 문항에 별도로 구조화된 검사 참고치는 없습니다."}</p></section>`;
      } else if (activeTab === "anki") {
        root.innerHTML = `<div class="reader-panel-kicker">ANKI</div><section class="reader-panel-card"><strong>이 문항을 복습 카드로 저장</strong><p>실제로 제출한 승인 문항의 정답·해설만 카드에 포함합니다.</p><button id="export-current-anki" class="primary-button" type="button">현재 문항 Anki 내보내기</button><small id="anki-panel-status"></small></section>`;
        $("#export-current-anki").addEventListener("click", async () => {
          const button = $("#export-current-anki"); button.disabled = true; $("#anki-panel-status").textContent = "카드를 만드는 중입니다.";
          try {
            const payload = await api("/api/practice/anki-export", { method: "POST", body: JSON.stringify({ session_id: session.sessionId, items: [{ exam_id: question.source_id || session.sourceId, question_id: question.question_id }] }) });
            $("#anki-panel-status").textContent = `${payload.card_count}장 생성 완료`;
            window.location.href = payload.download_url;
          } catch (error) { $("#anki-panel-status").textContent = error.message; button.disabled = false; }
        });
      }
    }

    function renderPractice() {
      const question = currentQuestion();
      const attempt = attemptFor(question);
      const selected = selectedFor(question);
      const multiple = question.selection_mode === "multiple";
      $("#reader-progress").textContent = `${session.index + 1} / ${session.questions.length}`;
      $("#practice-mode-badge").textContent = session.mode === "exam" ? "시험 모드" : "학습 모드";
      $("#timer-label").textContent = session.mode === "exam" ? "경과" : "경과";
      $("#reported-badge").hidden = !session.reports[question.question_id];
      if (renderedQuestionId !== question.question_id) {
        renderedQuestionId = question.question_id;
        renderMeta(question); renderMedia(question);
        $("#question-stem").textContent = question.stem;
        const stimulus = $("#question-stimulus"); stimulus.hidden = !question.stimulus; stimulus.textContent = question.stimulus || "";
      }
      renderChoices(question); renderPanel(question);
      renderNavigator();
      $("#selection-hint").textContent = attempt ? "제출이 완료되어 Reader 학습 패널이 열렸습니다." : multiple ? `${selected.length} / ${question.required_selection_count || 2} 선택됨 · 복수 정답 문항입니다.` : selected.length ? "선택을 확인한 뒤 정답을 제출하세요." : "선지를 선택하거나 ✕ 버튼으로 소거할 수 있습니다.";
      const submit = $("#submit-answer");
      submit.textContent = session.mode === "exam" ? (session.examSaved[question.question_id] ? "선택 저장됨 · 변경 가능" : "선택 저장") : "정답 확인";
      submit.hidden = Boolean(attempt);
      submit.disabled = !selected.length || (multiple && selected.length !== (question.required_selection_count || 2));
      const banner = $("#result-banner");
      banner.hidden = !attempt;
      if (attempt) { banner.className = `reader-result-banner ${attempt.is_correct ? "is-correct" : "is-wrong"}`; banner.textContent = attempt.is_correct ? "정답입니다 · 우측 학습 패널에서 근거를 확인하세요." : "오답입니다 · 우측 학습 패널에서 정답과 근거를 확인하세요."; }
      $("#retry-current-question").hidden = !attempt || session.mode === "exam";
      $("#previous-question").disabled = session.index === 0;
      $("#next-question").textContent = session.index === session.questions.length - 1 ? (session.mode === "exam" ? "시험 제출 →" : "세트 결과 보기 →") : "다음 문항 →";
      $("#next-question").disabled = session.mode === "learning" && !attempt;
      const bookmarked = session.bookmarks.includes(question.question_id);
      $("#bookmark-question").classList.toggle("is-active", bookmarked);
      $("#bookmark-question").querySelector("strong").textContent = bookmarked ? "★" : "☆";
      document.body.classList.toggle("timer-hidden", Boolean(session.timerHidden));
      setPaused(session.paused);
      persist();
    }

    function chooseAnswer(question, choice) {
      if (attemptFor(question) || finishing) return;
      const selected = selectedFor(question);
      if (question.selection_mode === "multiple") {
        const next = selected.includes(choice) ? selected.filter((item) => item !== choice) : [...selected, choice];
        session.answers[question.question_id] = next.slice(0, question.required_selection_count || 2);
      } else session.answers[question.question_id] = [choice];
      delete session.examSaved[question.question_id];
      persist(); renderPractice();
    }

    function toggleEliminated(question, choice) {
      if (attemptFor(question)) return;
      const values = session.eliminated[question.question_id] || [];
      session.eliminated[question.question_id] = values.includes(choice) ? values.filter((item) => item !== choice) : [...values, choice];
      persist(); renderChoices(question);
    }

    async function submitQuestion(question, duringFinish = false) {
      if (attemptFor(question) || (finishing && !duringFinish)) return attemptFor(question);
      const selected = selectedFor(question);
      if (!selected.length) return null;
      showNotice("답안을 안전하게 채점하는 중입니다.");
      try {
        const payload = await api("/api/practice/attempts", { method: "POST", body: JSON.stringify({
          event_id: `${session.sessionId}_${question.source_id || session.sourceId}_${question.question_id}_${session.attemptSequences[question.question_id] || 0}`,
          session_id: session.sessionId, exam_id: question.source_id || session.sourceId,
          question_id: question.question_id, selected_choices: selected,
          time_ms: session.questionTimes[question.question_id] || 0,
          is_bookmarked: session.bookmarks.includes(question.question_id),
        }) });
        session.attempts[question.question_id] = payload.attempt; session.feedback[question.question_id] = payload.feedback;
        showNotice(""); persist(); renderPractice(); return payload.attempt;
      } catch (error) { showNotice(`답안을 저장하지 못했습니다. ${error.message}`, true); return null; }
    }

    async function finishSession(force = false) {
      if (finishing) return;
      const unanswered = session.questions.filter((question) => !selectedFor(question).length);
      if (!force && unanswered.length && !window.confirm(`답하지 않은 문항이 ${unanswered.length}개 있습니다. 지금 세트를 종료할까요?`)) return;
      finishing = true; showNotice("세션 결과를 정리하는 중입니다.");
      if (session.mode === "exam") for (const question of session.questions) if (selectedFor(question).length && !attemptFor(question)) await submitQuestion(question, true);
      const items = session.questions.map((question, index) => ({ index, question, selected: selectedFor(question), attempt: attemptFor(question) || null, feedback: feedbackFor(question) || null, bookmarked: session.bookmarks.includes(question.question_id), timeMs: session.questionTimes[question.question_id] || 0 }));
      let syncStatus = "saved";
      try {
        await api(`/api/practice/sessions/${encodeURIComponent(session.sessionId)}/finalize`, { method: "POST", body: JSON.stringify({
          answered_count: items.filter((item) => item.attempt).length,
          correct_count: items.filter((item) => item.attempt?.is_correct).length,
          elapsed_ms: session.elapsedMs,
        }) });
      } catch { syncStatus = "local_only"; }
      save(KEYS.result, { schemaVersion: "student_result.v4", sessionId: session.sessionId, sourceId: session.sourceId, setId: session.setId, title: session.title, subject: session.subject, unit: session.unit, mode: session.mode, elapsedMs: session.elapsedMs, startedAt: session.startedAt, completedAt: new Date().toISOString(), syncStatus, items });
      remove(KEYS.session); window.location.href = "/student-v2/result.html";
    }

    $$("#reader-tabs button").forEach((button) => button.addEventListener("click", () => { activeTab = button.dataset.readerTab; renderPanel(currentQuestion()); }));
    $("#submit-answer").addEventListener("click", () => {
      const question = currentQuestion();
      if (session.mode === "exam") { session.examSaved[question.question_id] = true; persist(); renderPractice(); }
      else submitQuestion(question);
    });
    $("#previous-question").addEventListener("click", () => { if (session.index > 0) { session.index -= 1; renderedQuestionId = null; renderPractice(); resetQuestionScroll(); } });
    $("#next-question").addEventListener("click", async () => { if (session.index === session.questions.length - 1) await finishSession(); else { session.index += 1; renderedQuestionId = null; renderPractice(); resetQuestionScroll(); } });
    $("#retry-current-question").addEventListener("click", () => {
      const id = currentQuestion().question_id;
      session.attemptSequences[id] = (session.attemptSequences[id] || 0) + 1;
      delete session.answers[id]; delete session.attempts[id]; delete session.feedback[id]; delete session.examSaved[id];
      activeTab = "expl"; persist(); renderPractice(); resetQuestionScroll();
    });
    $("#finish-set-rail").addEventListener("click", () => { $("#reader-menu-overlay").hidden = true; finishSession(); });
    $("#open-reference").addEventListener("click", () => {
      const labs = currentQuestion().lab_values || [];
      const defaults = ["혈색소 12–16 g/dL", "백혈구 4,000–10,000 /μL", "혈소판 150,000–400,000 /μL", "Na 135–145 mmol/L", "K 3.5–5.0 mmol/L"];
      $("#reference-values").innerHTML = (labs.length ? labs : defaults).map((item) => typeof item === "string" ? `<div><span>${escapeHtml(item)}</span></div>` : `<div><span>${escapeHtml(item.label || item.name || "검사")}</span><strong>${escapeHtml(item.value || "")}</strong></div>`).join("");
      $("#reference-overlay").hidden = false;
    });
    $("#close-reference").addEventListener("click", () => { $("#reference-overlay").hidden = true; });
    $("#open-reader-menu").addEventListener("click", () => { $("#reader-menu-overlay").hidden = false; });
    $("#close-reader-menu").addEventListener("click", () => { $("#reader-menu-overlay").hidden = true; });
    $("#toggle-timer").addEventListener("click", () => { session.timerHidden = !session.timerHidden; persist(); renderPractice(); });
    $("#timer-pill").addEventListener("click", () => setPaused(!session.paused));
    $("#resume-session").addEventListener("click", () => setPaused(false));
    $("#toggle-question-navigator").addEventListener("click", () => { renderNavigator(); $("#question-navigator-overlay").hidden = false; });
    $("#close-question-navigator").addEventListener("click", () => { $("#question-navigator-overlay").hidden = true; });
    $("#bookmark-question").addEventListener("click", async () => {
      const question = currentQuestion();
      const id = question.question_id;
      const wasOn = session.bookmarks.includes(id);
      session.bookmarks = wasOn ? session.bookmarks.filter((item) => item !== id) : [...session.bookmarks, id];
      persist(); renderPractice();
      try {
        await api(`/api/questions/${encodeURIComponent(id)}/bookmark`, {
          method: "PATCH",
          body: JSON.stringify({
            session_id: session.sessionId,
            exam_id: question.source_id || session.sourceId,
            on: !wasOn,
          }),
        });
      } catch (error) {
        session.bookmarks = wasOn ? [...new Set([...session.bookmarks, id])] : session.bookmarks.filter((item) => item !== id);
        persist(); renderPractice(); showNotice(`북마크를 저장하지 못했습니다. ${error.message}`, true);
      }
    });
    $("#report-question").addEventListener("click", async () => {
      const reason = window.prompt("신고 사유를 간단히 적어주세요. (오답·오타·이미지 오류 등)", "문항 내용 검토 요청");
      if (!reason) return;
      const question = currentQuestion();
      try {
        const payload = await api("/api/practice/reports", { method: "POST", body: JSON.stringify({ session_id: session.sessionId, exam_id: question.source_id || session.sourceId, question_id: question.question_id, reason }) });
        session.reports[question.question_id] = { reportId: payload.report_id, reason, createdAt: new Date().toISOString() };
        persist(); $("#reader-menu-overlay").hidden = true; renderPractice(); showNotice("문항 신고가 접수되었습니다.");
      } catch (error) { showNotice(`문항 신고를 저장하지 못했습니다. ${error.message}`, true); }
    });
    $("#exit-session").addEventListener("click", () => { $("#exit-summary").textContent = `진행 ${answeredCount()}/${session.questions.length} · 채점 완료 ${completedCount()} · 경과 ${formatTime(session.elapsedMs)}. 저장하면 다음에 이어 풀 수 있어요.`; $("#exit-overlay").hidden = false; });
    $("#continue-session").addEventListener("click", () => { $("#exit-overlay").hidden = true; });
    $("#save-and-exit").addEventListener("click", async () => {
      const button = $("#save-and-exit");
      button.disabled = true;
      session.syncStatus = "saving"; persist();
      try {
        await api(`/api/practice/sessions/${encodeURIComponent(session.sessionId)}/snapshot`, {
          method: "PUT",
          body: JSON.stringify({
            index: session.index,
            answers: session.answers,
            elapsed_ms: session.elapsedMs,
            flags: { bookmarks: session.bookmarks, eliminated: session.eliminated, notes: session.notes },
          }),
        });
        session.syncStatus = "saved";
      } catch {
        session.syncStatus = "local_only";
      }
      persist(); window.location.href = "/student-v2/";
    });
    $("#discard-session").addEventListener("click", () => { remove(KEYS.session); window.location.href = "/student-v2/"; });
    $("#close-image-overlay").addEventListener("click", () => { $("#image-overlay").hidden = true; });
    $("#image-overlay").addEventListener("click", (event) => { if (event.target === $("#image-overlay")) $("#image-overlay").hidden = true; });
    $("#question-stem").addEventListener("mouseup", () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !$("#question-stem").contains(selection.anchorNode)) return;
      pendingRange = selection.getRangeAt(0).cloneRange();
      const rangeBox = pendingRange.getBoundingClientRect(); const stemBox = $("#question-stem").getBoundingClientRect();
      const pop = $("#apply-highlight"); pop.style.left = `${clamp(rangeBox.left - stemBox.left, 0, stemBox.width - 110)}px`; pop.style.top = `${Math.max(0, rangeBox.top - stemBox.top - 36)}px`; pop.hidden = false;
    });
    $("#apply-highlight").addEventListener("click", () => {
      if (!pendingRange) return;
      const mark = document.createElement("mark"); mark.className = "reader-highlight";
      try { mark.appendChild(pendingRange.extractContents()); pendingRange.insertNode(mark); } catch { /* selection spans incompatible nodes */ }
      window.getSelection()?.removeAllRanges(); pendingRange = null; $("#apply-highlight").hidden = true;
    });
    document.addEventListener("keydown", (event) => {
      const tag = String(event.target?.tagName || "").toLowerCase();
      if (["input", "textarea", "select"].includes(tag)) return;
      if (event.key === "Escape") {
        ["#reference-overlay", "#reader-menu-overlay", "#question-navigator-overlay", "#exit-overlay", "#image-overlay"].forEach((selector) => { const node = $(selector); if (node) node.hidden = true; });
        return;
      }
      if (event.code === "Space") { event.preventDefault(); setPaused(!session.paused); return; }
      if (session.paused) return;
      if (/^[1-5]$/.test(event.key)) {
        const question = currentQuestion();
        const key = Object.keys(question.choices || {})[Number(event.key) - 1];
        if (key) chooseAnswer(question, key);
        return;
      }
      if (event.key === "ArrowLeft" && session.index > 0) { event.preventDefault(); $("#previous-question").click(); }
      if (event.key === "ArrowRight" && !$("#next-question").disabled) { event.preventDefault(); $("#next-question").click(); }
    });
    const timerId = window.setInterval(() => {
      if (session.paused) return;
      session.elapsedMs += 1000; const id = currentQuestion().question_id; session.questionTimes[id] = (session.questionTimes[id] || 0) + 1000;
      if (!session.timerHidden) $("#session-timer").textContent = formatTime(session.elapsedMs);
      if (session.elapsedMs % 5000 === 0) persist();
    }, 1000);
    window.addEventListener("beforeunload", () => { window.clearInterval(timerId); persist(); });
    $("#session-timer").textContent = formatTime(session.elapsedMs); renderPractice();
  }

  function initPracticeLegacy() {
    const session = load(KEYS.session);
    if (!session?.questions?.length) {
      window.location.replace("/student-v2/builder.html");
      return;
    }
    session.answers ||= {};
    session.attempts ||= {};
    session.feedback ||= {};
    session.bookmarks ||= [];
    session.questionTimes ||= {};
    session.elapsedMs ||= 0;
    session.index = clamp(session.index || 0, 0, session.questions.length - 1);
    let timerId;
    let finishing = false;

    const currentQuestion = () => session.questions[session.index];
    const persist = () => save(KEYS.session, session);
    const answeredCount = () => session.questions.filter((question) => selectionFor(session, question).length).length;
    const completedCount = () => Object.keys(session.attempts).length;
    const showPracticeNotice = (message, error = false) => {
      const node = $("#practice-status");
      node.hidden = !message;
      node.textContent = message || "";
      node.classList.toggle("is-error", error);
    };

    function renderNavigator() {
      $("#question-navigator").innerHTML = session.questions.map((question, index) => {
        const attempt = session.attempts[question.question_id];
        const classes = [
          index === session.index ? "is-current" : "",
          selectionFor(session, question).length ? "is-answered" : "",
          attempt ? (attempt.is_correct ? "is-correct" : "is-wrong") : "",
          session.bookmarks.includes(question.question_id) ? "is-bookmarked" : "",
        ].filter(Boolean).join(" ");
        return `<button class="${classes}" type="button" data-index="${index}" aria-label="${index + 1}번 문항">${index + 1}</button>`;
      }).join("");
      $$("button", $("#question-navigator")).forEach((button) => button.addEventListener("click", () => {
        session.index = Number(button.dataset.index);
        document.body.classList.remove("nav-open");
        persist();
        renderPractice();
      }));
    }

    function renderMedia(question) {
      const mediaRoot = $("#question-media");
      const media = (question.media_refs || []).filter((item) => item.url);
      mediaRoot.hidden = !media.length;
      mediaRoot.innerHTML = media.map((item, index) => `<figure><img src="${escapeHtml(item.url)}" alt="문항 제시자료 ${index + 1}"><figcaption>교수 승인 제시자료</figcaption></figure>`).join("");
      const labs = Array.isArray(question.lab_values) ? question.lab_values : [];
      const labRoot = $("#lab-values");
      labRoot.hidden = !labs.length;
      labRoot.innerHTML = labs.map((item) => {
        if (typeof item === "string") return `<div class="lab-item"><span>${escapeHtml(item)}</span></div>`;
        return `<div class="lab-item"><span>${escapeHtml(item.label || item.name || "검사")}</span><b>${escapeHtml(item.value || "")}</b></div>`;
      }).join("");
    }

    function renderChoices(question) {
      const selected = selectionFor(session, question);
      const feedback = session.feedback[question.question_id];
      const submitted = Boolean(session.attempts[question.question_id]);
      const correct = new Set(feedback?.result?.correct_choices || []);
      $("#choice-list").innerHTML = Object.entries(question.choices || {}).map(([key, value]) => {
        const isSelected = selected.includes(key);
        const isCorrect = submitted && correct.has(key);
        const isWrong = submitted && isSelected && !correct.has(key);
        const classes = ["choice", isSelected ? "is-selected" : "", isCorrect ? "is-correct" : "", isWrong ? "is-wrong" : ""].filter(Boolean).join(" ");
        const tag = isCorrect ? '<span class="choice-tag">정답</span>' : isWrong ? '<span class="choice-tag">내 선택</span>' : "";
        return `<button class="${classes}" type="button" data-choice="${escapeHtml(key)}" ${submitted ? "disabled" : ""}><span class="choice-letter">${escapeHtml(key)}</span><span class="choice-text">${escapeHtml(value)}</span>${tag}</button>`;
      }).join("");
      $$(".choice", $("#choice-list")).forEach((button) => button.addEventListener("click", () => chooseAnswer(question, button.dataset.choice)));
    }

    function renderFeedback(question) {
      const attempt = session.attempts[question.question_id];
      const feedback = session.feedback[question.question_id];
      const root = $("#feedback-panel");
      root.hidden = !attempt || !feedback;
      if (!attempt || !feedback) { root.innerHTML = ""; return; }
      const correctKeys = feedback.result?.correct_choices || [];
      const correctLabel = correctKeys.map((key) => `${key}번`).join(", ");
      root.innerHTML = `
        <div class="feedback-result ${attempt.is_correct ? "is-correct" : "is-wrong"}"><strong>${attempt.is_correct ? "정답이에요" : "다시 볼까요"}</strong><span>정답 ${escapeHtml(correctLabel)}</span></div>
        <div class="feedback-copy"><h3>교수 승인 해설</h3><p>${escapeHtml(feedback.explanation || feedback.safe_message || "검토된 해설이 준비되지 않았습니다.")}</p></div>`;
    }

    function renderPractice() {
      const question = currentQuestion();
      const selected = selectionFor(session, question);
      const submitted = Boolean(session.attempts[question.question_id]);
      const isMultiple = question.selection_mode === "multiple";
      $("#practice-mode-badge").textContent = session.mode === "learning" ? "학습 모드" : "시험 모드";
      $("#practice-subject").textContent = session.title || question.course_name || "승인 문항";
      $("#rail-progress").textContent = `${session.index + 1} / ${session.questions.length}`;
      $("#progress-fill").style.width = `${((session.index + 1) / session.questions.length) * 100}%`;
      $("#question-number").textContent = `QUESTION ${String(session.index + 1).padStart(2, "0")}`;
      $("#question-type").textContent = isMultiple ? `복수 정답 · ${question.required_selection_count}개` : "단일 정답";
      $("#question-course").textContent = question.course_name || session.subject || "승인 문항";
      $("#question-stem").textContent = question.stem;
      const stimulus = $("#question-stimulus");
      stimulus.hidden = !question.stimulus;
      stimulus.textContent = question.stimulus || "";
      renderMedia(question);
      renderChoices(question);
      renderFeedback(question);
      renderNavigator();
      const bookmarked = session.bookmarks.includes(question.question_id);
      $("#bookmark-question").textContent = bookmarked ? "★" : "☆";
      $("#bookmark-question").classList.toggle("is-active", bookmarked);
      $("#previous-question").disabled = session.index === 0;
      const submitButton = $("#submit-answer");
      const required = question.required_selection_count || 1;
      submitButton.hidden = session.mode !== "learning" || !isMultiple || submitted;
      submitButton.disabled = selected.length !== required;
      const nextButton = $("#next-question");
      const isLast = session.index === session.questions.length - 1;
      nextButton.textContent = isLast ? (session.mode === "exam" ? "시험 제출" : "세트 결과 보기") : "다음 →";
      nextButton.disabled = session.mode === "learning" && !submitted;
      $("#selection-hint").textContent = submitted
        ? "제출이 완료되어 정답과 교수 승인 해설이 공개되었습니다."
        : isMultiple
          ? `${selected.length} / ${required} 선택됨 · 복수 정답 문항입니다.`
          : session.mode === "learning" ? "선지를 고르면 바로 채점합니다." : "답안을 선택한 뒤 다음 문항으로 이동하세요.";
      persist();
    }

    function chooseAnswer(question, choice) {
      if (session.attempts[question.question_id] || finishing) return;
      const selected = selectionFor(session, question);
      if (question.selection_mode === "multiple") {
        const next = selected.includes(choice) ? selected.filter((item) => item !== choice) : [...selected, choice];
        session.answers[question.question_id] = next.slice(0, question.required_selection_count || 2);
      } else {
        session.answers[question.question_id] = [choice];
      }
      persist();
      renderPractice();
      if (session.mode === "learning" && question.selection_mode !== "multiple") {
        window.setTimeout(() => submitQuestion(question), 180);
      }
    }

    async function submitQuestion(question, duringFinish = false) {
      if (session.attempts[question.question_id] || (finishing && !duringFinish)) return session.attempts[question.question_id];
      const selected = selectionFor(session, question);
      if (!selected.length) return null;
      const required = question.required_selection_count || 1;
      if (question.selection_mode === "multiple" && selected.length !== required) return null;
      showPracticeNotice("답안을 안전하게 채점하는 중입니다.");
      try {
        const payload = await api("/api/practice/attempts", {
          method: "POST",
          body: JSON.stringify({
            event_id: `${session.sessionId}_${question.question_id}`,
            session_id: session.sessionId,
            exam_id: session.sourceId,
            question_id: question.question_id,
            selected_choices: selected,
            time_ms: session.questionTimes[question.question_id] || 0,
            is_bookmarked: session.bookmarks.includes(question.question_id),
          }),
        });
        session.attempts[question.question_id] = payload.attempt;
        session.feedback[question.question_id] = payload.feedback;
        showPracticeNotice("");
        persist();
        renderPractice();
        return payload.attempt;
      } catch (error) {
        showPracticeNotice(`답안을 저장하지 못했습니다. ${error.message}`, true);
        return null;
      }
    }

    async function finishSession(force = false) {
      if (finishing) return;
      const unanswered = session.questions.filter((question) => !selectionFor(session, question).length);
      if (!force && unanswered.length && !window.confirm(`답하지 않은 문항이 ${unanswered.length}개 있습니다. 지금 세트를 종료할까요?`)) return;
      finishing = true;
      showPracticeNotice("세션 결과를 정리하는 중입니다.");
      if (session.mode === "exam") {
        for (const question of session.questions) {
          if (selectionFor(session, question).length && !session.attempts[question.question_id]) await submitQuestion(question, true);
        }
      }
      const items = session.questions.map((question, index) => ({
        index,
        question,
        selected: selectionFor(session, question),
        attempt: session.attempts[question.question_id] || null,
        feedback: session.feedback[question.question_id] || null,
        bookmarked: session.bookmarks.includes(question.question_id),
        timeMs: session.questionTimes[question.question_id] || 0,
      }));
      const result = {
        schemaVersion: "student_result.v2",
        sessionId: session.sessionId,
        sourceId: session.sourceId,
        setId: session.setId,
        title: session.title,
        subject: session.subject,
        unit: session.unit,
        mode: session.mode,
        elapsedMs: session.elapsedMs,
        startedAt: session.startedAt,
        completedAt: new Date().toISOString(),
        items,
      };
      save(KEYS.result, result);
      remove(KEYS.session);
      window.location.href = "/student-v2/result.html";
    }

    $("#bookmark-question").addEventListener("click", () => {
      const id = currentQuestion().question_id;
      session.bookmarks = session.bookmarks.includes(id) ? session.bookmarks.filter((item) => item !== id) : [...session.bookmarks, id];
      persist(); renderPractice();
    });
    $("#previous-question").addEventListener("click", () => { if (session.index > 0) { session.index -= 1; renderPractice(); } });
    $("#next-question").addEventListener("click", async () => {
      if (session.index === session.questions.length - 1) await finishSession();
      else { session.index += 1; renderPractice(); }
    });
    $("#submit-answer").addEventListener("click", () => submitQuestion(currentQuestion()));
    $("#finish-set-rail").addEventListener("click", () => finishSession());
    $("#mobile-nav-toggle").addEventListener("click", () => document.body.classList.toggle("nav-open"));
    $("#pause-session").addEventListener("click", () => { session.paused = true; persist(); $("#pause-overlay").hidden = false; });
    $("#resume-session").addEventListener("click", () => { session.paused = false; persist(); $("#pause-overlay").hidden = true; });
    $("#exit-session").addEventListener("click", () => {
      $("#exit-summary").textContent = `진행 ${answeredCount()}/${session.questions.length} · 채점 완료 ${completedCount()} · 경과 ${formatTime(session.elapsedMs)}. 저장하면 다음에 이어 풀 수 있어요.`;
      $("#exit-overlay").hidden = false;
    });
    $("#continue-session").addEventListener("click", () => { $("#exit-overlay").hidden = true; });
    $("#save-and-exit").addEventListener("click", () => { persist(); window.location.href = "/student-v2/"; });
    $("#discard-session").addEventListener("click", () => { remove(KEYS.session); window.location.href = "/student-v2/"; });
    timerId = window.setInterval(() => {
      if (!session.paused && !document.hidden) {
        session.elapsedMs += 1000;
        const id = currentQuestion().question_id;
        session.questionTimes[id] = (session.questionTimes[id] || 0) + 1000;
        $("#session-timer").textContent = formatTime(session.elapsedMs);
        if (session.elapsedMs % 5000 === 0) persist();
      }
    }, 1000);
    window.addEventListener("beforeunload", () => { window.clearInterval(timerId); persist(); });
    $("#session-timer").textContent = formatTime(session.elapsedMs);
    renderPractice();
  }

  function initResult() {
    const result = load(KEYS.result);
    if (!result?.items?.length) {
      $("#result-empty").hidden = false;
      return;
    }
    $("#result-content").hidden = false;
    let filter = "all";
    let expanded = null;
    const selectedIds = new Set();
    const correctItems = result.items.filter((item) => item.attempt?.is_correct);
    const wrongItems = result.items.filter((item) => item.attempt && !item.attempt.is_correct);
    const answeredItems = result.items.filter((item) => item.attempt);
    const bookmarkedItems = result.items.filter((item) => item.bookmarked);
    const rate = result.items.length ? Math.round((correctItems.length / result.items.length) * 100) : 0;
    if (result.syncStatus === "local_only") {
      $("#result-save-status").classList.add("is-error");
      $("#result-save-copy").textContent = "기기에 저장됨 · 서버 반영이 필요합니다.";
      $("#retry-result-save").hidden = false;
    }
    $("#result-score").textContent = rate;
    $("#correct-rate").textContent = `${rate}%`;
    $("#wrong-count").textContent = `오답 ${wrongItems.length}문항 · 미응답 ${result.items.length - answeredItems.length}문항`;
    $("#result-time").textContent = formatTime(result.elapsedMs);
    $("#average-time").textContent = `평균 ${Math.round((result.elapsedMs || 0) / Math.max(1, result.items.length) / 1000)}초`;
    $("#answered-count").textContent = `${answeredItems.length} / ${result.items.length}`;
    $("#bookmark-count").textContent = `북마크 ${bookmarkedItems.length}문항`;
    $("#result-title").textContent = `${result.title || "학습 문항 세트"} · ${result.mode === "exam" ? "시험 모드" : "학습 모드"}`;
    $("#result-eyebrow").textContent = `SESSION COMPLETE · ${result.subject || "P:ACCINE"}`;
    $("#retry-wrong .retry-count").textContent = wrongItems.length;
    $("#retry-bookmark-label").textContent = `표시한 ${bookmarkedItems.length}문항`;
    $("#retry-wrong").disabled = !wrongItems.length;
    $("#retry-bookmarks").disabled = !bookmarkedItems.length;

    const weakRate = wrongItems.length + (result.items.length - answeredItems.length);
    $("#weak-area").innerHTML = `<div class="weak-area-row"><div class="weak-area-label"><span>${escapeHtml([result.subject, result.unit].filter(Boolean).join(" · ") || "이번 학습 영역")}</span><strong>${rate}%</strong></div><div class="weak-area-track"><i style="width:${Math.max(8, 100 - rate)}%"></i></div></div>${weakRate ? '<p style="margin:12px 0 0;color:#6f7c78;font-size:10.5px;line-height:1.5">오답과 미응답 문항을 다시 풀면 이 영역의 학습 기록을 보완할 수 있습니다.</p>' : '<p style="margin:12px 0 0;color:#0f8f72;font-size:10.5px">모든 문항을 정확히 해결했습니다.</p>'}`;

    function visibleItems() {
      if (filter === "wrong") return wrongItems;
      if (filter === "bookmark") return bookmarkedItems;
      return result.items;
    }

    function updateSelectionStatus() {
      const visibleAnsweredIds = visibleItems().filter((item) => item.attempt).map((item) => item.question.question_id);
      const selectedAnswered = answeredItems.filter((item) => selectedIds.has(item.question.question_id));
      $("#result-selected-count").textContent = `${selectedAnswered.length}문항 선택`;
      $("#result-select-all").checked = Boolean(visibleAnsweredIds.length) && visibleAnsweredIds.every((id) => selectedIds.has(id));
      $("#export-anki").disabled = !selectedAnswered.length;
      $("#export-anki").innerHTML = `${selectedAnswered.length || "선택"}문항 Anki 만들기 <span>→</span>`;
    }

    function renderResults() {
      const items = visibleItems();
      $("#result-list").innerHTML = items.length ? items.map((item) => {
        const status = !item.attempt ? "unanswered" : item.attempt.is_correct ? "correct" : "wrong";
        const label = status === "correct" ? "정답" : status === "wrong" ? "오답" : "미응답";
        const symbol = status === "correct" ? "✓" : status === "wrong" ? "×" : "–";
        const answerKeys = item.feedback?.result?.correct_choices || [];
        const answerText = answerKeys.map((key) => `${key}. ${item.question.choices?.[key] || ""}`).join(" / ");
        const detail = expanded === item.question.question_id && item.feedback ? `<div class="result-answer"><b>정답 ${escapeHtml(answerText)}</b>\n${escapeHtml(item.feedback.explanation || item.feedback.safe_message || "")}</div>` : "";
        const checked = selectedIds.has(item.question.question_id) ? "checked" : "";
        const disabled = item.attempt ? "" : "disabled";
        return `<div class="result-row has-selection is-${status}" role="button" tabindex="0" data-question-id="${escapeHtml(item.question.question_id)}"><label class="result-row-select" aria-label="Anki 내보내기 선택"><input type="checkbox" data-result-select="${escapeHtml(item.question.question_id)}" ${checked} ${disabled}></label><span class="result-state">${symbol}</span><div class="result-main"><p>${escapeHtml(item.question.stem)}</p><div class="result-meta"><span>${formatTime(item.timeMs)}</span><span>${escapeHtml(item.question.course_name || result.subject || "학습 문항")}</span>${item.bookmarked ? '<span class="bookmarked">★ 북마크</span>' : ""}</div></div><span class="result-label">${label}</span>${detail}</div>`;
      }).join("") : '<div class="result-empty-row">이 조건에 해당하는 문항이 없습니다.</div>';
      $$(".result-row", $("#result-list")).forEach((row) => {
        const toggle = () => { expanded = expanded === row.dataset.questionId ? null : row.dataset.questionId; renderResults(); };
        row.addEventListener("click", (event) => { if (!event.target.closest(".result-row-select")) toggle(); });
        row.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); } });
      });
      $$('[data-result-select]', $("#result-list")).forEach((input) => input.addEventListener("change", () => {
        if (input.checked) selectedIds.add(input.dataset.resultSelect); else selectedIds.delete(input.dataset.resultSelect);
        updateSelectionStatus();
      }));
      updateSelectionStatus();
    }

    function retry(items) {
      if (!items.length) return;
      save(KEYS.builder, {
        count: items.length, mode: "learning", construction: "weakness", type: "all", difficulty: "all", mediaOnly: false,
        filters: { subject: "", year: "", instructor: "", major: "", topic: "", domain: "" },
        retryRefs: items.map((item) => `${item.question.source_id || result.sourceId}|${item.question.question_id}`),
      });
      window.location.href = "/student-v2/builder.html";
    }

    $$("#result-filters button").forEach((button) => button.addEventListener("click", () => {
      filter = button.dataset.filter;
      $$("#result-filters button").forEach((item) => item.classList.toggle("is-selected", item === button));
      expanded = null;
      renderResults();
    }));
    $("#result-select-all").addEventListener("change", (event) => {
      visibleItems().filter((item) => item.attempt).forEach((item) => {
        if (event.target.checked) selectedIds.add(item.question.question_id); else selectedIds.delete(item.question.question_id);
      });
      renderResults();
    });
    $("#retry-wrong").addEventListener("click", () => retry(wrongItems));
    $("#retry-bookmarks").addEventListener("click", () => retry(bookmarkedItems));
    $("#retry-result-save").addEventListener("click", async () => {
      const button = $("#retry-result-save"); button.disabled = true;
      try {
        await api(`/api/practice/sessions/${encodeURIComponent(result.sessionId)}/finalize`, { method: "POST", body: JSON.stringify({ answered_count: answeredItems.length, correct_count: correctItems.length, elapsed_ms: result.elapsedMs }) });
        result.syncStatus = "saved"; save(KEYS.result, result);
        $("#result-save-status").classList.remove("is-error"); $("#result-save-copy").textContent = "학습 기록이 저장되었습니다."; button.hidden = true;
      } catch (error) { $("#result-save-copy").textContent = `서버 반영 실패 · ${error.message}`; button.disabled = false; }
    });
    $("#export-anki").addEventListener("click", async () => {
      const button = $("#export-anki");
      const status = $("#anki-status");
      button.disabled = true;
      const selectedItems = answeredItems.filter((item) => selectedIds.has(item.question.question_id));
      if (!selectedItems.length) return;
      status.textContent = "선택한 학습 문항으로 카드를 만드는 중입니다.";
      try {
        const payload = await api("/api/practice/anki-export", {
          method: "POST",
          body: JSON.stringify({
            session_id: result.sessionId,
            items: selectedItems.map((item) => ({ exam_id: item.question.source_id || result.sourceId, question_id: item.question.question_id })),
          }),
        });
        status.textContent = `${payload.question_count}문항 · ${payload.card_count}장 생성 완료`;
        window.location.href = payload.download_url;
      } catch (error) {
        status.textContent = `내보내지 못했습니다. ${error.message}`;
        button.disabled = false;
      }
    });
    renderResults();
  }

  if (page === "home") initHome();
  if (page === "library") initLibrary();
  if (page === "builder") initBuilder();
  if (page === "practice") initPractice();
  if (page === "result") initResult();
})();
