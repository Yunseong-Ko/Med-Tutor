(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char]);
  const generationJobStorageKey = "paccine.faculty_generation_job.v1";
  const intentGenerationJobStorageKey = "paccine.faculty_intent_generation_job.v1";
  const workflowDraftStorageKey = "paccine.faculty_item_workflow_draft.v1";
  let pendingLeaveAction = null;
  let bypassLeaveGuard = false;
  const steps = ["출제 범위", "대상 개념", "평가 의도", "근거 준비", "문항 설계도", "생성·자동 점검", "검토로 보내기"];
  const tasks = [
    { group: "A · 왜 생겼나요?", items: [
      ["etiology", "직접 원인은 무엇인가?", "etiology"], ["risk_harm", "위험을 높이는 것은?", "risk_factor"], ["mechanism", "어떤 기전으로 발생하는가?", "pathophysiology"], ["epidemiology", "누구에게 흔한가?", "epidemiology"],
    ]},
    { group: "B · 무엇이며 얼마나 심한가요?", items: [
      ["most_likely_diagnosis", "가장 가능성 높은 진단은?", "diagnosis"], ["differential_diagnosis", "무엇과 감별해야 하는가?", "diagnosis"], ["test_selection", "어떤 검사를 먼저 해야 하는가?", "diagnosis"], ["test_interpretation", "검사를 어떻게 해석하는가?", "diagnosis"], ["severity_staging", "중증도·병기는 어떻게 판단하는가?", "diagnosis"],
    ]},
    { group: "C · 무엇을 해야 하나요?", items: [
      ["immediate_management", "지금 가장 먼저 할 처치는?", "treatment"], ["first_line_treatment", "1차 또는 최선의 치료는?", "treatment"], ["pharmacotherapy", "어떤 약물을 선택하는가?", "treatment"], ["clinical_intervention", "어떤 시술·수술을 선택하는가?", "treatment"], ["indication", "언제 시행해야 하는가?", "indication"], ["contraindication", "언제 피하거나 중단해야 하는가?", "contraindication"], ["monitoring", "치료 반응을 무엇으로 확인하는가?", "treatment", true], ["prevention", "무엇으로 예방하는가?", "treatment", true],
    ]},
    { group: "D · 앞으로 어떻게 되나요?", items: [
      ["natural_history", "자연경과는 어떠한가?", "prognosis"], ["prognostic_factor", "예후를 좌우하는 것은?", "prognosis"], ["complication", "어떤 합병증이 생길 수 있는가?", "prognosis", true], ["follow_up_recurrence", "재발·추적관리는 어떻게 하는가?", "prognosis", true],
    ]},
  ];
  const taskById = new Map(tasks.flatMap((group) => group.items).map((item) => [item[0], { id: item[0], label: item[1], axis: item[2], scarce: Boolean(item[3]) }]));

  const state = {
    step: 1,
    courses: [],
    courseId: "gi",
    courseName: "소화기및영양학",
    setName: "새 Ontology 문항 세트",
    count: 2,
    difficulty: "국가고시형",
    facultyRequest: "",
    targetType: "condition",
    conceptQuery: "",
    searchResults: [],
    concept: null,
    context: null,
    selectedAxisIds: [],
    selectedTasks: [],
    questionType: "clinical_case",
    reasoningHops: 2,
    carePhase: "initial",
    optionDomain: "",
    teachingPoints: "",
    textbookReference: "",
    lectureFile: null,
    media: [],
    selectedMediaIds: new Set(),
    drawerMediaIds: new Set(),
    preflight: { checked: false, policyBlocked: false, softBlocked: false, reasons: [], payload: null },
    generating: false,
    generation: null,
    generationJob: null,
    generationPollTimer: null,
    proposal: null,
    intentMode: "recommended",
    departmentState: "loading",
    departmentError: "",
    departments: [],
    departmentDefaults: { requested_item_count: 3, candidate_count: 6, allowed_item_count: [2, 3] },
    selectedDepartment: null,
    intentSetName: "임상의학종합평가 문항 세트",
    intentCount: 3,
    recommendationState: "idle",
    recommendationError: "",
    intentCandidates: [],
    selectedIntentIds: new Set(),
    intentTaskOverrides: new Map(),
    intentPreflight: { checked: false, blockedIntentIds: [], reasons: [] },
    intentGeneration: null,
    intentGenerationJob: null,
    intentGenerating: false,
    intentGenerationPollTimer: null,
    workflowComplete: false,
    restoredDraft: false,
    savedLectureFileName: "",
  };

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.message || `요청 실패 (${response.status})`);
    return payload;
  }

  function toast(message) {
    const node = $("#toast");
    node.textContent = message;
    node.classList.add("show");
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => node.classList.remove("show"), 2200);
  }

  function hasUnfinishedWorkflow() {
    if (state.workflowComplete) return false;
    const recommendedStarted = Boolean(
      state.selectedDepartment
      || state.selectedIntentIds.size
      || state.intentTaskOverrides.size
      || state.intentPreflight.checked
      || state.intentGeneration
      || state.intentGenerationJob
      || state.intentGenerating
    );
    const manualStarted = Boolean(
      state.intentMode === "manual"
      && (
        state.facultyRequest.trim()
        || state.conceptQuery.trim()
        || state.concept
        || state.selectedTasks.length
        || state.teachingPoints.trim()
        || state.textbookReference.trim()
        || state.lectureFile
        || state.selectedMediaIds.size
        || state.preflight.checked
        || state.generation
        || state.generationJob
        || state.generating
      )
    );
    return state.step > 1 || recommendedStarted || manualStarted || Boolean(currentGeneration()) || Boolean(currentGenerationJob()) || currentGenerating();
  }

  function workflowDraftSnapshot() {
    return {
      schema_version: "paccine.faculty_item_workflow_draft.v1",
      saved_at: new Date().toISOString(),
      step: state.step,
      intentMode: state.intentMode,
      selectedDepartmentId: state.selectedDepartment?.id || "",
      intentSetName: state.intentSetName,
      intentCount: state.intentCount,
      recommendationState: state.recommendationState,
      intentCandidates: state.intentCandidates,
      selectedIntentIds: [...state.selectedIntentIds],
      intentTaskOverrides: [...state.intentTaskOverrides.entries()],
      intentPreflight: state.intentPreflight,
      intentGeneration: state.intentGeneration,
      intentGenerationJob: state.intentGenerationJob,
      courseId: state.courseId,
      courseName: state.courseName,
      setName: state.setName,
      count: state.count,
      difficulty: state.difficulty,
      facultyRequest: state.facultyRequest,
      targetType: state.targetType,
      conceptQuery: state.conceptQuery,
      searchResults: state.searchResults,
      concept: state.concept,
      context: state.context,
      selectedAxisIds: state.selectedAxisIds,
      selectedTasks: state.selectedTasks,
      questionType: state.questionType,
      reasoningHops: state.reasoningHops,
      carePhase: state.carePhase,
      optionDomain: state.optionDomain,
      teachingPoints: state.teachingPoints,
      textbookReference: state.textbookReference,
      selectedMediaIds: [...state.selectedMediaIds],
      preflight: state.preflight,
      generation: state.generation,
      generationJob: state.generationJob,
      lectureFileName: state.lectureFile?.name || state.savedLectureFileName || "",
    };
  }

  function saveWorkflowDraft() {
    try {
      window.localStorage.setItem(workflowDraftStorageKey, JSON.stringify(workflowDraftSnapshot()));
      const saveState = $("#save-state");
      if (saveState) saveState.textContent = "임시저장 완료";
      return true;
    } catch {
      toast("브라우저 임시저장 공간이 부족합니다. 작성 화면을 유지해 주세요.");
      return false;
    }
  }

  function clearWorkflowDraft() {
    window.localStorage.removeItem(workflowDraftStorageKey);
  }

  function restoreWorkflowDraft() {
    const raw = window.localStorage.getItem(workflowDraftStorageKey);
    if (!raw) return false;
    try {
      const saved = JSON.parse(raw);
      if (saved?.schema_version !== "paccine.faculty_item_workflow_draft.v1") return false;
      state.step = Math.max(1, Math.min(7, Number(saved.step || 1)));
      state.intentMode = saved.intentMode === "manual" ? "manual" : "recommended";
      state.selectedDepartment = state.departments.find((item) => item.id === saved.selectedDepartmentId) || null;
      state.intentSetName = String(saved.intentSetName || state.intentSetName);
      state.intentCount = [2, 3].includes(Number(saved.intentCount)) ? Number(saved.intentCount) : state.intentCount;
      state.intentCandidates = Array.isArray(saved.intentCandidates) ? saved.intentCandidates : [];
      state.recommendationState = state.intentCandidates.length ? "success" : state.selectedDepartment ? "idle" : "idle";
      const candidateIds = new Set(state.intentCandidates.map((item) => item?.intent_id).filter(Boolean));
      state.selectedIntentIds = new Set((saved.selectedIntentIds || []).filter((id) => candidateIds.has(id)));
      state.intentTaskOverrides = new Map(Array.isArray(saved.intentTaskOverrides) ? saved.intentTaskOverrides : []);
      state.intentPreflight = saved.intentPreflight || state.intentPreflight;
      state.intentGeneration = saved.intentGeneration || null;
      state.intentGenerationJob = saved.intentGenerationJob || null;
      state.courseId = String(saved.courseId || state.courseId);
      state.courseName = String(saved.courseName || state.courseName);
      state.setName = String(saved.setName || state.setName);
      state.count = Math.max(1, Math.min(30, Number(saved.count || state.count)));
      state.difficulty = String(saved.difficulty || state.difficulty);
      state.facultyRequest = String(saved.facultyRequest || "");
      state.targetType = String(saved.targetType || state.targetType);
      state.conceptQuery = String(saved.conceptQuery || "");
      state.searchResults = Array.isArray(saved.searchResults) ? saved.searchResults : [];
      state.concept = saved.concept || null;
      state.context = saved.context || null;
      state.selectedAxisIds = Array.isArray(saved.selectedAxisIds) ? saved.selectedAxisIds : [];
      state.selectedTasks = Array.isArray(saved.selectedTasks) ? saved.selectedTasks : [];
      state.questionType = String(saved.questionType || state.questionType);
      state.reasoningHops = Math.max(1, Math.min(3, Number(saved.reasoningHops || state.reasoningHops)));
      state.carePhase = String(saved.carePhase || state.carePhase);
      state.optionDomain = String(saved.optionDomain || "");
      state.teachingPoints = String(saved.teachingPoints || "");
      state.textbookReference = String(saved.textbookReference || "");
      state.selectedMediaIds = new Set(saved.selectedMediaIds || []);
      state.drawerMediaIds = new Set(state.selectedMediaIds);
      state.preflight = saved.preflight || state.preflight;
      state.generation = saved.generation || null;
      state.generationJob = saved.generationJob || null;
      state.savedLectureFileName = String(saved.lectureFileName || "");
      state.restoredDraft = true;
      return true;
    } catch {
      clearWorkflowDraft();
      return false;
    }
  }

  function syncRestoredDraftControls() {
    $("#intent-set-name").value = state.intentSetName;
    $("#set-name").value = state.setName;
    $("#faculty-request").value = state.facultyRequest;
    $("#concept-query").value = state.conceptQuery;
    $("#question-count").textContent = String(state.count);
    $("#course-select").value = state.courseId;
    $("#reasoning-hops").value = String(state.reasoningHops);
    $("#care-phase").value = state.carePhase;
    $("#option-domain").value = state.optionDomain;
    $("#teaching-points").value = state.teachingPoints;
    $("#textbook-reference").value = state.textbookReference;
    $("#media-count").textContent = String(state.selectedMediaIds.size);
    $$("[data-intent-count]").forEach((button) => button.classList.toggle("selected", Number(button.dataset.intentCount) === state.intentCount));
    $$("#difficulty-options button").forEach((button) => button.classList.toggle("selected", button.dataset.value === state.difficulty));
    $$("#target-types button").forEach((button) => button.classList.toggle("selected", button.dataset.value === state.targetType));
    $$("#format-options button").forEach((button) => button.classList.toggle("selected", button.dataset.value === state.questionType));
    renderTaskGroups();
    if (state.concept) {
      const selected = $("#selected-concept");
      selected.hidden = false;
      selected.innerHTML = `<span><b>${escapeHtml(state.concept.label)}</b><span>${escapeHtml(state.concept.disease_concept_id)} · 임시저장에서 복구됨</span></span>`;
    }
  }

  function closeLeaveGuard() {
    pendingLeaveAction = null;
    $("#leave-guard").hidden = true;
  }

  function requestLeave(action) {
    if (!hasUnfinishedWorkflow() || bypassLeaveGuard) {
      action();
      return;
    }
    pendingLeaveAction = action;
    $("#leave-guard").hidden = false;
    $("#leave-guard-stay").focus();
  }

  async function resolveLeave({ save }) {
    const action = pendingLeaveAction;
    if (!action) return;
    if (save && !saveWorkflowDraft()) return;
    if (!save) clearWorkflowDraft();
    pendingLeaveAction = null;
    $("#leave-guard").hidden = true;
    bypassLeaveGuard = true;
    try {
      await action();
    } catch (error) {
      bypassLeaveGuard = false;
      toast(error.message || "화면을 이동하지 못했습니다.");
    }
  }

  function isIntentMode() {
    return state.intentMode === "recommended";
  }

  function selectedIntentCandidates() {
    return [...state.selectedIntentIds]
      .map((intentId) => state.intentCandidates.find((item) => item.intent_id === intentId))
      .filter(Boolean);
  }

  function effectiveIntent(candidate) {
    const override = state.intentTaskOverrides.get(candidate.intent_id);
    const target = { ...(candidate.target || {}) };
    const taskModel = { ...(candidate.task_model || {}) };
    const evidenceContract = {
      ...(candidate.evidence_contract || {}),
      selected_media_ids: [...state.selectedMediaIds],
      reference_note: state.textbookReference || null,
      requires_faculty_review: true,
    };
    const assessmentClaim = override ? {
      ...(candidate.assessment_claim || {}),
      task: override.task,
      task_label: override.task_label,
      task_family: override.task_family,
      faculty_claim: `학생이 ${target.label || "선택한 질환"} 관련 임상상황에서 ${override.task_label}을 수행할 수 있는지 평가한다.`,
    } : { ...(candidate.assessment_claim || {}) };
    const selectionContract = {
      ...(candidate.selection_contract || {}),
      department: { ...(candidate.department || candidate.selection_contract?.department || {}) },
      target: { type: target.type || "condition", id: target.concept_id || target.id, concept_id: target.concept_id || target.id, label: target.label },
      assessment_claim: { ...assessmentClaim },
      task_model: { ...taskModel },
      evidence_contract: { ...evidenceContract },
    };
    return {
      ...candidate,
      title: override ? `${target.label || "선택한 질환"} · ${override.task_label}` : candidate.title,
      target,
      assessment_claim: assessmentClaim,
      task_model: taskModel,
      target_axis_type: override ? override.target_axis_type : candidate.target_axis_type,
      evidence_contract: evidenceContract,
      selection_contract: selectionContract,
    };
  }

  function selectedEffectiveIntents() {
    return selectedIntentCandidates().map(effectiveIntent);
  }

  function invalidateIntentPreflight() {
    state.intentPreflight = { checked: false, blockedIntentIds: [], reasons: [] };
    if (!state.intentGenerating) {
      state.intentGeneration = null;
      state.intentGenerationJob = null;
      window.localStorage.removeItem(intentGenerationJobStorageKey);
    }
  }

  function currentGenerationJob() {
    return isIntentMode() ? state.intentGenerationJob : state.generationJob;
  }

  function currentGeneration() {
    return isIntentMode() ? state.intentGeneration : state.generation;
  }

  function currentGenerating() {
    return isIntentMode() ? state.intentGenerating : state.generating;
  }

  function setCurrentGenerationJob(job) {
    if (isIntentMode()) {
      state.intentGenerationJob = job;
      if (job?.job_id) window.localStorage.setItem(intentGenerationJobStorageKey, job.job_id);
    } else {
      state.generationJob = job;
      if (job?.job_id) window.localStorage.setItem(generationJobStorageKey, job.job_id);
    }
  }

  function setCurrentGeneration(value) {
    if (isIntentMode()) state.intentGeneration = value;
    else state.generation = value;
  }

  function setCurrentGenerating(value) {
    if (isIntentMode()) state.intentGenerating = value;
    else state.generating = value;
  }

  function activeStorageKey() {
    return isIntentMode() ? intentGenerationJobStorageKey : generationJobStorageKey;
  }

  function clearCurrentGenerationPoll() {
    if (isIntentMode()) {
      window.clearTimeout(state.intentGenerationPollTimer);
      state.intentGenerationPollTimer = null;
    } else {
      window.clearTimeout(state.generationPollTimer);
      state.generationPollTimer = null;
    }
  }

  function scheduleCurrentGenerationPoll() {
    if (isIntentMode()) state.intentGenerationPollTimer = window.setTimeout(pollGenerationJob, 1600);
    else state.generationPollTimer = window.setTimeout(pollGenerationJob, 1600);
  }

  function invalidatePreflight() {
    if (isIntentMode()) {
      invalidateIntentPreflight();
      return;
    }
    state.preflight = { checked: false, policyBlocked: false, softBlocked: false, reasons: [], payload: null };
    if (!state.generating) {
      state.generation = null;
      state.generationJob = null;
      window.localStorage.removeItem(generationJobStorageKey);
    }
  }

  function selectedTaskObjects() {
    return state.selectedTasks.map((id) => taskById.get(id)).filter(Boolean);
  }

  function primaryAxis() {
    return selectedTaskObjects()[0]?.axis || "";
  }

  function supportingAxes() {
    return [...new Set(selectedTaskObjects().slice(1).map((item) => item.axis).filter((axis) => axis && axis !== primaryAxis()))];
  }

  function targetAxisIds() {
    return [...state.selectedAxisIds];
  }

  function coverage() {
    if (!state.concept || state.context?.status !== "matched") return { status: "unsupported", label: "Ontology 미연결", message: "주제 기반 초안은 가능하지만 Ontology 상속 근거가 없습니다." };
    const hasEvidence = Boolean(state.context?.evidence?.harrison || state.context?.evidence?.ncbi);
    const directSource = Boolean(state.lectureFile || state.teachingPoints.trim() || state.textbookReference.trim());
    if (hasEvidence || directSource) return { status: "partial", label: "검토 필요", message: "연결 근거가 모두 의학검토 전입니다. 교수 검수가 반드시 필요합니다." };
    return { status: "unsupported", label: "근거 추가 필요", message: "대상은 연결됐지만 직접 근거 슬롯이 비어 있습니다." };
  }

  function generationRequirements() {
    if (isIntentMode()) {
      const selected = selectedEffectiveIntents();
      const blocked = selected.filter((item) => item.evidence_contract?.coverage_status === "unsupported");
      return [
        [Boolean(state.selectedDepartment), "출제 과"],
        [selected.length === state.intentCount, `출제 후보 ${state.intentCount}개`],
        [new Set(selected.map((item) => item.intent_id)).size === selected.length, "중복 없는 출제 의도"],
        [blocked.length === 0, "unsupported 후보 없음"],
        [state.intentPreflight.checked, "후보 사전 점검"],
      ];
    }
    const topic = state.concept?.disease_concept_id || state.conceptQuery.trim() || state.facultyRequest.trim();
    return [
      [Boolean(state.courseName), "출제 과목"],
      [Boolean(topic), "대상 개념 또는 주제"],
      [state.selectedTasks.length > 0, "평가 과업"],
      [Boolean(state.questionType), "문항 형식"],
      [state.preflight.checked, "설계도 사전 점검"],
      [!state.preflight.policyBlocked, "정책 차단 없음"],
    ];
  }

  function canGenerate() {
    return !currentGenerating() && generationRequirements().every(([ok]) => ok);
  }

  function renderStepRail() {
    $("#step-list").innerHTML = steps.map((label, index) => {
      const number = index + 1;
      const generation = currentGeneration();
      const done = number < state.step || (number === 6 && Boolean(generation && !generation.error));
      return `<button type="button" class="step-button ${number === state.step ? "current" : ""} ${done ? "done" : ""}" data-step="${number}"><span>${done ? "✓" : number}</span>${escapeHtml(label)}</button>`;
    }).join("");
    $$("[data-step]").forEach((button) => button.addEventListener("click", () => goStep(Number(button.dataset.step))));
  }

  function goStep(step) {
    state.step = Math.max(1, Math.min(7, step));
    $$('[data-panel]').forEach((panel) => { panel.hidden = Number(panel.dataset.panel) !== state.step; });
    $("#step-indicator").textContent = `${state.step} / 7 · ${steps[state.step - 1]}`;
    $("#previous-step").disabled = state.step === 1;
    $("#next-step").disabled = state.step === 7;
    renderStepRail();
    renderDynamicPanel();
    if (state.step === 2 && isIntentMode() && state.selectedDepartment && state.recommendationState === "idle") loadIntentRecommendations();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderDynamicPanel() {
    renderIntentMode();
    if (state.step === 1 && isIntentMode()) renderDepartments();
    if (state.step === 2 && isIntentMode()) renderIntentCandidates();
    if (state.step === 3 && isIntentMode()) renderIntentTasks();
    if (state.step === 4) isIntentMode() ? renderIntentEvidence() : renderCoverage();
    if (state.step === 5) isIntentMode() ? renderIntentBlueprint() : renderBlueprint();
    if (state.step === 6) renderGeneration();
    if (state.step === 7) renderReviewHandoff();
    renderSummary();
  }

  function renderIntentMode() {
    const recommended = isIntentMode();
    [1, 2, 3, 4, 5].forEach((step) => {
      const intent = $(`#intent-step-${step}`);
      const manual = $(`#manual-step-${step}`);
      if (intent) intent.hidden = !recommended;
      if (manual) manual.hidden = recommended;
    });
    $$('[data-intent-mode]').forEach((button) => button.classList.toggle("selected", button.dataset.intentMode === state.intentMode));
    const endpoint = $("#generation-endpoint");
    if (endpoint) endpoint.textContent = recommended ? "POST /api/faculty/item-intents/generation-jobs" : "POST /api/generation-jobs";
  }

  function setIntentMode(mode) {
    if (!['recommended', 'manual'].includes(mode) || state.intentMode === mode) return;
    if (state.intentGenerating || state.generating) {
      toast("생성 작업이 진행 중일 때는 출제 모드를 바꿀 수 없습니다.");
      return;
    }
    clearCurrentGenerationPoll();
    state.intentMode = mode;
    renderIntentMode();
    renderDynamicPanel();
    if (mode === "recommended" && state.step === 2 && state.selectedDepartment && state.recommendationState === "idle") loadIntentRecommendations();
    toast(mode === "recommended" ? "AI 추천 흐름으로 전환했습니다." : "기존 직접 설정 흐름으로 전환했습니다.");
  }

  async function loadDepartments() {
    state.departmentState = "loading";
    state.departmentError = "";
    renderDepartments();
    try {
      const payload = await api("/api/faculty/item-intents/departments");
      state.departments = Array.isArray(payload.departments) ? payload.departments : [];
      state.departmentDefaults = { ...state.departmentDefaults, ...(payload.defaults || {}) };
      const allowed = Array.isArray(state.departmentDefaults.allowed_item_count) ? state.departmentDefaults.allowed_item_count.map(Number) : [2, 3];
      if (!allowed.includes(state.intentCount)) state.intentCount = Number(state.departmentDefaults.requested_item_count || allowed[0] || 3);
      state.departmentState = "success";
    } catch (error) {
      state.departmentState = "error";
      state.departmentError = error.message;
    }
    renderDepartments();
    renderSummary();
  }

  function renderDepartments() {
    const stateNode = $("#intent-department-state");
    const list = $("#intent-department-list");
    if (!stateNode || !list) return;
    if (state.departmentState === "loading") {
      stateNode.className = "fs3-intent-state";
      stateNode.innerHTML = "<b>과 목록을 불러오는 중입니다.</b><span>현재 Ontology의 과별 후보 가용성을 확인합니다.</span>";
      list.innerHTML = Array.from({ length: 6 }, () => '<div class="fs3-intent-skeleton" aria-hidden="true"></div>').join("");
      return;
    }
    if (state.departmentState === "error") {
      stateNode.className = "fs3-intent-state is-danger";
      stateNode.innerHTML = `<b>과 목록을 불러오지 못했습니다.</b><span>${escapeHtml(state.departmentError)}</span><div><button type="button" id="intent-department-retry" class="secondary-action">다시 시도</button><button type="button" id="intent-department-manual" class="text-action">직접 설정으로 진행</button></div>`;
      list.innerHTML = "";
      $("#intent-department-retry")?.addEventListener("click", loadDepartments);
      $("#intent-department-manual")?.addEventListener("click", () => { setIntentMode("manual"); goStep(2); });
      return;
    }
    stateNode.className = "fs3-intent-state is-quiet";
    stateNode.innerHTML = state.selectedDepartment
      ? `<b>${escapeHtml(state.selectedDepartment.label)} 선택</b><span>후보 구성 가능 ${escapeHtml(state.selectedDepartment.candidate_ready_count || 0)}개 · 배정 ${escapeHtml(state.intentCount)}문항</span>`
      : "<b>출제할 과를 선택하세요.</b><span>추천 후보가 적거나 아직 연결되지 않은 과는 상태를 함께 표시합니다.</span>";
    list.innerHTML = state.departments.map((department) => {
      const unavailable = department.availability === "unavailable";
      const selected = state.selectedDepartment?.id === department.id;
      const status = department.availability === "limited" ? '<small class="is-warning">추천 후보가 적습니다</small>' : unavailable ? '<small>개념 미연결 · 직접 설정 이용</small>' : "";
      return `<button type="button" class="fs3-intent-department${selected ? " is-selected" : ""}${unavailable ? " is-unavailable" : ""}" data-department-id="${escapeHtml(department.id)}" aria-pressed="${selected}" ${unavailable ? "disabled" : ""}><span><b>${escapeHtml(department.label)}</b>${selected ? "<i>✓</i>" : ""}</span><small>개념 ${escapeHtml(department.concept_count || 0)} · 후보 구성 가능 ${escapeHtml(department.candidate_ready_count || 0)}</small>${status}</button>`;
    }).join("");
    $$('[data-department-id]').forEach((button) => button.addEventListener("click", () => selectDepartment(button.dataset.departmentId)));
    const allowed = Array.isArray(state.departmentDefaults.allowed_item_count) ? state.departmentDefaults.allowed_item_count.map(Number) : [2, 3];
    $$('[data-intent-count]').forEach((button) => {
      const count = Number(button.dataset.intentCount);
      button.hidden = !allowed.includes(count);
      button.classList.toggle("selected", count === state.intentCount);
    });
    const nameInput = $("#intent-set-name");
    if (nameInput && document.activeElement !== nameInput) nameInput.value = state.intentSetName;
  }

  function selectDepartment(departmentId) {
    const selected = state.departments.find((item) => item.id === departmentId && item.availability !== "unavailable");
    if (!selected) return;
    const changed = state.selectedDepartment?.id !== selected.id;
    state.selectedDepartment = selected;
    state.intentSetName = `${selected.label} 임상의학종합평가 출제`;
    if (changed) {
      state.recommendationState = "idle";
      state.intentCandidates = [];
      state.selectedIntentIds.clear();
      state.intentTaskOverrides.clear();
      invalidateIntentPreflight();
    }
    renderDepartments();
    renderSummary();
  }

  async function loadIntentRecommendations({ refresh = false } = {}) {
    if (!state.selectedDepartment) {
      state.recommendationState = "error";
      state.recommendationError = "먼저 출제 과를 선택하세요.";
      renderIntentCandidates();
      return;
    }
    state.recommendationState = "loading";
    state.recommendationError = "";
    renderIntentCandidates();
    const selected = selectedEffectiveIntents();
    const exclude = refresh ? selected.map((item) => item.target?.concept_id || item.target?.id).filter(Boolean) : [];
    try {
      const payload = await api("/api/faculty/item-intents/recommendations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          department: state.selectedDepartment.id,
          requested_item_count: state.intentCount,
          candidate_count: Number(state.departmentDefaults.candidate_count || 6),
          exclude_concept_ids: exclude,
        }),
      });
      const incoming = Array.isArray(payload.candidates) ? payload.candidates : [];
      const preserved = refresh ? selectedIntentCandidates() : [];
      const merged = [...preserved, ...incoming].filter((item, index, rows) => item?.intent_id && rows.findIndex((row) => row?.intent_id === item.intent_id) === index);
      state.intentCandidates = merged;
      state.recommendationState = "success";
      invalidateIntentPreflight();
    } catch (error) {
      state.recommendationState = "error";
      state.recommendationError = error.message;
    }
    renderIntentCandidates();
    renderSummary();
  }

  function renderIntentCandidates() {
    const stateNode = $("#intent-recommendation-state");
    const list = $("#intent-candidate-list");
    const counter = $("#intent-selection-count");
    if (!stateNode || !list || !counter) return;
    counter.textContent = `${state.selectedIntentIds.size} / ${state.intentCount} 선택`;
    if (!state.selectedDepartment) {
      stateNode.className = "fs3-intent-state is-warning";
      stateNode.innerHTML = '<b>출제 과를 먼저 선택하세요.</b><span>1단계에서 과를 선택하면 후보를 불러옵니다.</span><button id="intent-go-department" type="button" class="secondary-action">1단계로 이동</button>';
      list.innerHTML = "";
      $("#intent-go-department")?.addEventListener("click", () => goStep(1));
      return;
    }
    if (state.recommendationState === "loading") {
      stateNode.className = "fs3-intent-state";
      stateNode.innerHTML = `<b>${escapeHtml(state.selectedDepartment.label)} 후보를 구성하는 중입니다.</b><span>질환과 서로 다른 평가 과업의 균형을 확인합니다.</span>`;
      list.innerHTML = Array.from({ length: 6 }, () => '<div class="fs3-intent-candidate-skeleton" aria-hidden="true"></div>').join("");
      return;
    }
    if (state.recommendationState === "error") {
      stateNode.className = "fs3-intent-state is-danger";
      stateNode.innerHTML = `<b>후보 추천을 불러오지 못했습니다.</b><span>${escapeHtml(state.recommendationError)}</span><div><button id="intent-recommendation-retry" type="button" class="secondary-action">다시 시도</button><button id="intent-recommendation-manual" type="button" class="text-action">직접 설정</button></div>`;
      list.innerHTML = "";
      $("#intent-recommendation-retry")?.addEventListener("click", () => loadIntentRecommendations());
      $("#intent-recommendation-manual")?.addEventListener("click", () => setIntentMode("manual"));
      return;
    }
    if (state.recommendationState === "idle") {
      stateNode.className = "fs3-intent-state is-quiet";
      stateNode.innerHTML = '<b>후보를 아직 불러오지 않았습니다.</b><button id="intent-recommendation-load" type="button" class="secondary-action">후보 6개 불러오기</button>';
      list.innerHTML = "";
      $("#intent-recommendation-load")?.addEventListener("click", () => loadIntentRecommendations());
      return;
    }
    if (!state.intentCandidates.length) {
      stateNode.className = "fs3-intent-state is-warning";
      stateNode.innerHTML = '<b>현재 구성 가능한 후보가 없습니다.</b><span>다른 과를 선택하거나 직접 설정으로 출제할 수 있습니다.</span><div><button id="intent-empty-department" type="button" class="secondary-action">과 다시 선택</button><button id="intent-empty-manual" type="button" class="text-action">직접 설정</button></div>';
      list.innerHTML = "";
      $("#intent-empty-department")?.addEventListener("click", () => goStep(1));
      $("#intent-empty-manual")?.addEventListener("click", () => setIntentMode("manual"));
      return;
    }
    const tooFew = state.intentCandidates.length < 2;
    stateNode.className = `fs3-intent-state ${tooFew ? "is-warning" : "is-quiet"}`;
    stateNode.innerHTML = tooFew
      ? '<b>구성 가능한 후보가 2개 미만입니다.</b><span>자동 세트를 만들 수 없어 직접 설정 또는 다른 과 선택이 필요합니다.</span>'
      : `<b>${escapeHtml(state.intentCandidates.length)}개 후보</b><span>${state.selectedIntentIds.size < state.intentCount ? `${state.intentCount - state.selectedIntentIds.size}개를 더 선택하세요.` : "선택이 완료됐습니다. 후보별 과업을 확인하세요."}</span>`;
    const maxReached = state.selectedIntentIds.size >= state.intentCount;
    list.innerHTML = state.intentCandidates.map((candidate) => {
      const effective = effectiveIntent(candidate);
      const selected = state.selectedIntentIds.has(candidate.intent_id);
      const locked = maxReached && !selected;
      const reasons = (candidate.recommendation?.reasons || []).slice(0, 2);
      const status = candidate.evidence_contract?.coverage_status || "unsupported";
      const statusLabel = status === "partial" ? "근거 보강·검수 필요" : status === "grounded" ? "검토 가능한 근거 연결" : "근거 보강 필요";
      return `<article class="fs3-intent-candidate${selected ? " is-selected" : ""}${locked ? " is-locked" : ""}">
        <div class="fs3-intent-candidate-head"><div><b>${escapeHtml(effective.target?.label || effective.title)}</b><span>${escapeHtml(effective.assessment_claim?.task_label || effective.assessment_claim?.task || "평가 과업")}</span></div><button type="button" data-intent-toggle="${escapeHtml(candidate.intent_id)}" aria-pressed="${selected}" ${locked ? "disabled" : ""}>${selected ? "✓ 선택됨" : locked ? "선택 한도" : "선택"}</button></div>
        <p>“${escapeHtml(effective.assessment_claim?.faculty_claim || "교수 출제 의도를 확인하세요.")}”</p>
        <ul>${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
        <div class="fs3-intent-candidate-foot"><span class="is-${escapeHtml(status)}">${escapeHtml(statusLabel)}</span><small>검토용 Ontology · 의학검토 전</small><button type="button" data-intent-task-jump="${escapeHtml(candidate.intent_id)}">과업 변경</button></div>
      </article>`;
    }).join("");
    $$('[data-intent-toggle]').forEach((button) => button.addEventListener("click", () => toggleIntentSelection(button.dataset.intentToggle)));
    $$('[data-intent-task-jump]').forEach((button) => button.addEventListener("click", () => {
      const intentId = button.dataset.intentTaskJump;
      if (!state.selectedIntentIds.has(intentId)) toggleIntentSelection(intentId);
      if (state.selectedIntentIds.has(intentId)) goStep(3);
    }));
  }

  function toggleIntentSelection(intentId) {
    if (!state.intentCandidates.some((item) => item.intent_id === intentId)) return;
    if (state.selectedIntentIds.has(intentId)) state.selectedIntentIds.delete(intentId);
    else if (state.selectedIntentIds.size >= state.intentCount) {
      toast(`배정 문항 수는 ${state.intentCount}개입니다. 기존 선택을 해제한 뒤 바꿔 주세요.`);
      return;
    } else state.selectedIntentIds.add(intentId);
    invalidateIntentPreflight();
    renderIntentCandidates();
    renderIntentTasks();
    renderSummary();
  }

  function renderIntentTasks() {
    const box = $("#intent-task-list");
    if (!box) return;
    const selected = selectedIntentCandidates();
    if (!selected.length) {
      box.innerHTML = '<div class="fs3-intent-empty"><b>선택한 후보가 없습니다.</b><span>2단계에서 2~3개 후보를 먼저 선택하세요.</span><button id="intent-task-back" type="button" class="secondary-action">후보 선택으로</button></div>';
      $("#intent-task-back")?.addEventListener("click", () => goStep(2));
      return;
    }
    box.innerHTML = selected.map((candidate, index) => {
      const effective = effectiveIntent(candidate);
      const override = state.intentTaskOverrides.get(candidate.intent_id);
      const options = [candidate.assessment_claim, ...(candidate.alternative_tasks || [])].filter((item, optionIndex, rows) => item?.task && rows.findIndex((row) => row?.task === item.task) === optionIndex);
      return `<article class="fs3-intent-task-row"><span class="fs3-intent-index">${String(index + 1).padStart(2, "0")}</span><div><b>${escapeHtml(effective.target?.label || effective.title)}</b><p>${escapeHtml(effective.assessment_claim?.faculty_claim || "")}</p><small>${override ? "변경됨 · 생성 계약에 반영" : "추천 기본값"}</small></div><label><span>평가 과업</span><select data-intent-task-select="${escapeHtml(candidate.intent_id)}">${options.map((option) => `<option value="${escapeHtml(option.task)}" ${option.task === effective.assessment_claim?.task ? "selected" : ""}>${escapeHtml(option.task_label || option.task)}</option>`).join("")}</select></label><button type="button" data-intent-task-reset="${escapeHtml(candidate.intent_id)}" ${override ? "" : "disabled"}>기본값 되돌리기</button></article>`;
    }).join("");
    $$('[data-intent-task-select]').forEach((select) => select.addEventListener("change", () => changeIntentTask(select.dataset.intentTaskSelect, select.value)));
    $$('[data-intent-task-reset]').forEach((button) => button.addEventListener("click", () => changeIntentTask(button.dataset.intentTaskReset, "")));
  }

  function changeIntentTask(intentId, taskId) {
    const candidate = state.intentCandidates.find((item) => item.intent_id === intentId);
    if (!candidate) return;
    if (!taskId || taskId === candidate.assessment_claim?.task) state.intentTaskOverrides.delete(intentId);
    else {
      const alternative = (candidate.alternative_tasks || []).find((item) => item.task === taskId);
      if (!alternative) return;
      state.intentTaskOverrides.set(intentId, { ...alternative });
    }
    invalidateIntentPreflight();
    renderIntentTasks();
    renderIntentCandidates();
    renderSummary();
  }

  function renderIntentEvidence() {
    const box = $("#intent-evidence-list");
    if (!box) return;
    const selected = selectedEffectiveIntents();
    if (!selected.length) {
      box.innerHTML = '<div class="fs3-intent-empty"><b>선택한 후보가 없습니다.</b><span>2단계에서 후보를 선택하세요.</span></div>';
      return;
    }
    box.innerHTML = selected.map((intent) => {
      const evidence = intent.evidence_contract || {};
      const status = evidence.coverage_status || "unsupported";
      const label = status === "partial" ? "부분 연결 · 검수 필요" : status === "grounded" ? "직접 근거 연결 검토" : "unsupported · 생성 보류";
      const warnings = (intent.recommendation?.warnings || []).slice(0, 2);
      return `<article class="fs3-intent-evidence-row is-${escapeHtml(status)}"><div><b>${escapeHtml(intent.title)}</b><small>${escapeHtml(intent.intent_id)}</small></div><span>${escapeHtml(label)}</span><p>오답 원문 후보 ${escapeHtml(evidence.distractor_source_count || 0)} · 교재 장 포인터 ${evidence.chapter_pointer_available ? "있음" : "없음"}<br>${warnings.map(escapeHtml).join(" · ") || "교수 검수 후 사용"}</p></article>`;
    }).join("");
  }

  function renderIntentBlueprint() {
    const box = $("#intent-blueprint-list");
    const preflight = $("#intent-preflight-state");
    if (!box || !preflight) return;
    const selected = selectedEffectiveIntents();
    if (!selected.length) {
      box.innerHTML = '<div class="fs3-intent-empty"><b>선택한 후보가 없습니다.</b><span>2단계에서 후보를 선택하세요.</span></div>';
    } else {
      box.innerHTML = selected.map((intent, index) => {
        const unsupported = intent.evidence_contract?.coverage_status === "unsupported";
        return `<article class="fs3-intent-blueprint-row${unsupported ? " is-blocked" : ""}"><span>${String(index + 1).padStart(2, "0")}</span><div><b>${escapeHtml(intent.target?.label)} · ${escapeHtml(intent.assessment_claim?.task_label || intent.assessment_claim?.task)}</b><small>증례형 · ${escapeHtml(intent.task_model?.reasoning_hops || 2)}단계 추론 · ${escapeHtml(intent.task_model?.phase_of_care || "initial")}</small></div><strong>${unsupported ? "생성 보류" : "생성 가능 · 검수 필요"}</strong></article>`;
      }).join("");
    }
    if (!state.intentPreflight.checked) {
      preflight.className = "preflight-state";
      preflight.innerHTML = "<b>아직 후보 사전 점검을 실행하지 않았습니다.</b><span>생성 가능한 후보와 보류 사유를 구분합니다.</span>";
    } else if (state.intentPreflight.blockedIntentIds.length) {
      preflight.className = "preflight-state is-danger";
      preflight.innerHTML = `<b>${escapeHtml(state.intentPreflight.blockedIntentIds.length)}개 후보 생성 보류</b><span>${escapeHtml(state.intentPreflight.reasons.join(" · "))}</span>`;
    } else {
      preflight.className = "preflight-state is-warning";
      preflight.innerHTML = "<b>후보 사전 점검 완료</b><span>모든 후보는 교수 검수용 초안으로만 생성되며 학생에게 자동 공개되지 않습니다.</span>";
    }
  }

  function runIntentPreflight() {
    const selected = selectedEffectiveIntents();
    const blocked = selected.filter((item) => item.evidence_contract?.coverage_status === "unsupported");
    state.intentPreflight = {
      checked: selected.length === state.intentCount,
      blockedIntentIds: blocked.map((item) => item.intent_id),
      reasons: blocked.map((item) => `${item.target?.label || item.title}: 근거 보강 또는 과업 변경 필요`),
    };
    if (selected.length !== state.intentCount) toast(`${state.intentCount}개 후보를 선택한 뒤 점검하세요.`);
    else if (blocked.length) toast("unsupported 후보는 생성이 보류됩니다.");
    else toast("후보 사전 점검을 완료했습니다.");
    renderIntentBlueprint();
    renderSummary();
  }

  function renderTaskGroups() {
    $("#task-groups").innerHTML = tasks.map((group) => `<section class="task-group"><h2>${escapeHtml(group.group)}</h2><div class="task-options">${group.items.map((item) => `<button type="button" class="${state.selectedTasks.includes(item[0]) ? "selected" : ""} ${item[3] ? "scarce" : ""}" data-task="${item[0]}" title="${item[3] ? "현재 Ontology 축 지원이 부분적입니다." : ""}">${escapeHtml(item[1])}${item[3] ? " · 축 부족" : ""}</button>`).join("")}</div></section>`).join("");
    $$('[data-task]').forEach((button) => button.addEventListener("click", () => {
      const id = button.dataset.task;
      state.selectedAxisIds = [];
      if (state.selectedTasks.includes(id)) state.selectedTasks = state.selectedTasks.filter((item) => item !== id);
      else if (state.selectedTasks.length < 2) state.selectedTasks.push(id);
      else { state.selectedTasks = [state.selectedTasks[1], id]; toast("평가 과업은 최대 2개까지 선택합니다."); }
      invalidatePreflight();
      renderTaskGroups();
      renderSummary();
    }));
  }

  async function loadCourses() {
    try {
      const payload = await api("/api/student/catalog");
      state.courses = payload.courses || [];
    } catch {
      state.courses = [{ id: "gi", name: "소화기및영양학" }, { id: "hemeonc", name: "혈액및종양학" }, { id: "neuro", name: "신경및특수감각기학" }];
    }
    const select = $("#course-select");
    select.innerHTML = state.courses.map((course) => `<option value="${escapeHtml(course.id)}">${escapeHtml(course.name)}</option>`).join("");
    if (state.courses.some((course) => course.id === state.courseId)) select.value = state.courseId;
    else if (state.courses[0]) { state.courseId = state.courses[0].id; state.courseName = state.courses[0].name; }
  }

  async function loadMedia() {
    try { state.media = (await api("/api/media")).assets || []; }
    catch { state.media = []; }
  }

  function renderConceptResults(message = "") {
    const box = $("#concept-results");
    if (message) { box.innerHTML = `<div class="empty-state"><b>${escapeHtml(message)}</b><span>한국어명, 영문명 또는 Ontology ID로 다시 검색해 보세요.</span></div>`; return; }
    if (!state.searchResults.length) { box.innerHTML = `<div class="empty-state"><b>연결된 개념을 찾지 못했습니다</b><span>현재 검색어를 주제 문장으로 사용할 수 있지만 Ontology 상속은 적용되지 않습니다.</span></div>`; return; }
    box.innerHTML = state.searchResults.map((item) => `<button type="button" class="concept-card" data-concept-id="${escapeHtml(item.disease_concept_id)}"><span><b>${escapeHtml(item.label)}<small>${escapeHtml(item.disease_concept_id)}</small></b><span>관계 ${item.relation_count || 0} · 임상 축 ${item.axis_count || 0} · 연결 문항 ${item.question_count || 0}${item.has_harrison ? " · Harrison 위치 있음" : ""}</span></span><span class="review-badge">검토용</span></button>`).join("");
    $$('[data-concept-id]').forEach((button) => button.addEventListener("click", () => selectConcept(button.dataset.conceptId)));
  }

  async function searchConcepts() {
    const query = $("#concept-query").value.trim();
    state.conceptQuery = query;
    state.concept = null;
    state.context = null;
    invalidatePreflight();
    $("#selected-concept").hidden = true;
    renderConceptResults("Ontology 후보를 찾는 중…");
    if (!query) { renderConceptResults("검색어를 입력하세요"); renderSummary(); return; }
    try {
      const payload = await api(`/api/ontology/search?q=${encodeURIComponent(query)}&limit=8`);
      state.searchResults = payload.results || [];
      renderConceptResults();
    } catch (error) {
      state.searchResults = [];
      renderConceptResults(`검색 실패 · ${error.message}`);
    }
    renderSummary();
  }

  async function selectConcept(conceptId) {
    const item = state.searchResults.find((row) => row.disease_concept_id === conceptId);
    if (!item) return;
    const selected = $("#selected-concept");
    selected.hidden = false;
    selected.innerHTML = `<span><b>${escapeHtml(item.label)}</b><span>${escapeHtml(conceptId)} · 상세 연결 확인 중…</span></span>`;
    try {
      const context = await api(`/api/ontology/context?disease_concept_id=${encodeURIComponent(conceptId)}&review_policy=faculty_draft`);
      state.concept = item;
      state.context = context;
      state.selectedAxisIds = [];
      invalidatePreflight();
      selected.innerHTML = `<span><b>${escapeHtml(item.label)}</b><span>${escapeHtml(conceptId)} · 검토용 Ontology · 의학검토 전</span></span><button type="button" id="concept-change">다시 선택</button>`;
      $("#concept-change").addEventListener("click", () => { state.concept = null; state.context = null; selected.hidden = true; invalidatePreflight(); renderSummary(); });
      renderSummary();
      toast("Ontology 개념을 선택했습니다.");
    } catch (error) {
      selected.innerHTML = `<span><b>상세 연결 실패</b><span>${escapeHtml(error.message)}</span></span>`;
    }
  }

  function renderCoverage() {
    const value = coverage();
    const node = $("#coverage-card");
    node.className = `coverage-card ${value.status === "partial" ? "is-warning" : value.status === "grounded" ? "is-success" : "is-danger"}`;
    node.innerHTML = `<b>근거 상태 · ${escapeHtml(value.label)}</b><span>${escapeHtml(value.message)}</span>`;
  }

  function renderBlueprint() {
    const taskLabels = selectedTaskObjects().map((item) => item.label).join(" + ") || "선택 필요";
    const explicitAxisIds = targetAxisIds();
    const serverAxisIds = state.preflight.payload?.question_blueprint?.target?.axis_ids || [];
    const contextAxisIds = (state.context?.axis_context?.types?.[primaryAxis()] || []).map((row) => row.axis_id).filter(Boolean);
    const candidateAxisIds = serverAxisIds.length ? serverAxisIds : contextAxisIds;
    const evidence = state.context?.evidence?.harrison;
    $("#blueprint-preview").innerHTML = [
      ["대상 개념", state.concept ? `${state.concept.label} · ${state.concept.disease_concept_id}` : state.conceptQuery || "미선택"],
      ["평가 과업", taskLabels],
      ["문항 형식", `${formatLabel(state.questionType)} · ${state.reasoningHops}단계 추론 · ${state.count}문항`],
      ["Ontology 축", explicitAxisIds.length ? `${primaryAxis()} · ${explicitAxisIds.length}개 명시 선택` : candidateAxisIds.length ? `${primaryAxis()} · ${candidateAxisIds.length}개 후보 · 생성 후 1개 이하 확정` : `${primaryAxis() || "미선택"} · 후보 없음`],
      ["근거 위치", evidence ? `${evidence.title || "Harrison"} · Ch.${evidence.chapter || "-"} p.${evidence.page || "-"}` : "직접 연결 근거 없음"],
      ["오답 후보", `${state.context?.distractor_pool?.length || 0}개 · 모두 교수 검토 필요`],
    ].map(([key, value]) => `<div class="blueprint-item"><span>${escapeHtml(key)}</span><b>${escapeHtml(value)}</b></div>`).join("");
    const preflight = $("#preflight-state");
    if (!state.preflight.checked) { preflight.className = "preflight-state"; preflight.innerHTML = "<b>아직 설계도를 점검하지 않았습니다.</b><span>현재 선택을 서버 계약과 비교합니다.</span>"; }
    else if (state.preflight.policyBlocked) { preflight.className = "preflight-state is-danger"; preflight.innerHTML = `<b>정책상 생성 차단</b><span>${escapeHtml(state.preflight.reasons.join(" · ") || "의학검토 정책을 확인하세요.")}</span>`; }
    else if (state.preflight.softBlocked) { preflight.className = "preflight-state is-warning"; preflight.innerHTML = `<b>Ontology 근거 미완성 · 검수 필요</b><span>${escapeHtml(state.preflight.reasons.join(" · ") || "근거 상속 없이 검토용 초안을 만들 수 있습니다.")}</span>`; }
    else { preflight.className = "preflight-state is-success"; preflight.innerHTML = "<b>설계도 점검 완료</b><span>검수용 초안 생성 계약을 통과했습니다.</span>"; }
  }

  async function runPreflight() {
    const topic = state.facultyRequest.trim() || state.conceptQuery.trim() || state.concept?.label || "";
    if (!topic || !primaryAxis()) { toast("대상과 평가 과업을 먼저 선택하세요."); return false; }
    const node = $("#preflight-state");
    node.className = "preflight-state";
    node.innerHTML = "<b>출제 설계 확인 중…</b><span>Ontology 연결과 정책 차단 사유를 확인합니다.</span>";
    try {
      const payload = await api("/api/ontology/question-blueprint", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({
        topic,
        disease_concept_id: state.concept?.disease_concept_id || "",
        review_policy: "faculty_draft",
        question_type: state.questionType,
        target_axis_type: primaryAxis(),
        target_axis_ids: targetAxisIds(),
        supporting_axis_types: supportingAxes(),
        option_domain: state.optionDomain,
      }) });
      const reasons = payload.question_blueprint?.block_reasons || payload.grounding?.block_reasons || [];
      const policyBlocked = Boolean(payload.grounding?.blocked);
      state.preflight = { checked: true, policyBlocked, softBlocked: payload.status === "blocked" && !policyBlocked, reasons, payload };
      renderBlueprint();
      renderSummary();
      return !policyBlocked;
    } catch (error) {
      state.preflight = { checked: false, policyBlocked: false, softBlocked: false, reasons: [error.message], payload: null };
      node.className = "preflight-state is-danger";
      node.innerHTML = `<b>설계 확인 실패</b><span>${escapeHtml(error.message)}</span>`;
      renderSummary();
      return false;
    }
  }

  function renderGeneration() {
    const requirements = generationRequirements();
    $("#generation-checklist").innerHTML = requirements.map(([ok, label]) => `<div class="check-item ${ok ? "" : "missing"}"><i>${ok ? "✓" : "!"}</i>${escapeHtml(label)}</div>`).join("");
    const button = $("#generate-run");
    button.disabled = !canGenerate();
    button.textContent = currentGenerating() ? "문항별 생성 진행 중…" : isIntentMode() ? `${state.intentCount}문항 초안 만들기` : "문항 초안 생성";
    const box = $("#generation-state");
    const job = currentGenerationJob();
    const generation = currentGeneration();
    if (currentGenerating() && job) {
      box.className = "generation-state";
      box.innerHTML = `<b>${escapeHtml(job.success_count || 0)} / ${escapeHtml(job.requested_count || (isIntentMode() ? state.intentCount : state.count))}문항 생성됨</b><span>브라우저를 닫거나 다른 화면으로 이동해도 서버 작업은 계속됩니다. 돌아오면 이 화면이 진행 상태를 복구합니다.</span>`;
    }
    else if (currentGenerating()) { box.className = "generation-state"; box.innerHTML = "<b>문항 초안을 생성 중입니다.</b><span>서버가 선택한 대상·평가 축·근거 범위로 검토용 초안을 만들고 있습니다.</span>"; }
    else if (job?.status === "partial") { box.className = "generation-state is-warning"; box.innerHTML = `<b>${escapeHtml(job.success_count)}문항 저장 · ${escapeHtml(job.failed_count)}문항 재시도 필요</b><span>성공 문항은 보존되어 있으며 실패 문항만 다시 생성할 수 있습니다.</span>`; }
    else if (job?.status === "failed") { box.className = "generation-state is-danger"; box.innerHTML = "<b>다문항 생성에 실패했습니다.</b><span>같은 요청을 중복 생성하지 않고 실패 문항만 다시 시도할 수 있습니다.</span>"; }
    else if (job?.status === "cancelled") { box.className = "generation-state is-warning"; box.innerHTML = "<b>생성 작업을 중단했습니다.</b><span>이미 완료된 문항은 보존됩니다. 새 설계로 다시 시작할 수 있습니다.</span>"; }
    else if (generation?.error) { box.className = "generation-state is-danger"; box.innerHTML = "<b>초안 생성에 실패했습니다.</b><span>저장된 초안은 없습니다. 오류를 확인한 뒤 같은 설계로 다시 시도할 수 있습니다.</span>"; }
    else if (generation) { box.className = "generation-state is-success"; box.innerHTML = "<b>초안 생성이 완료되었습니다.</b><span>모든 문항은 교수 검토 전 상태로 저장됐습니다.</span>"; }
    else if (canGenerate()) { box.className = `generation-state ${coverage().status === "partial" ? "is-warning" : ""}`; box.innerHTML = `<b>초안 생성 준비 완료</b><span>${escapeHtml(coverage().message)}</span>`; }
    else { box.className = "generation-state"; box.innerHTML = "<b>생성 조건을 확인하세요.</b><span>완료되지 않은 항목을 해결한 뒤 생성할 수 있습니다.</span>"; }
    renderGenerationResult();
  }

  function formatLabel(value) {
    return ({ clinical_case: "증례형", image_based: "검사표·영상 해석형", basic_concept: "개념 적용형" })[value] || value;
  }

  async function generateDraft() {
    if (currentGenerating()) return;
    if (isIntentMode()) {
      if (!state.intentPreflight.checked) { goStep(5); toast("후보 사전 점검을 먼저 실행하세요."); return; }
      if (!canGenerate()) { toast("선택 수와 근거 준비 상태를 확인하세요."); return; }
      await startIntentGeneration();
      return;
    }
    if (!state.preflight.checked) { goStep(5); toast("출제 설계를 먼저 확인하세요."); return; }
    if (!canGenerate()) { toast("생성 조건을 모두 확인하세요."); return; }
    if (state.count > 1 && !state.lectureFile) {
      await startQueuedGeneration();
      return;
    }
    state.generating = true;
    state.generation = null;
    state.generationJob = null;
    window.localStorage.removeItem(generationJobStorageKey);
    goStep(6);
    renderGeneration();
    try {
      const payload = state.lectureFile || state.selectedMediaIds.size ? await generateMultipart() : await generateTopic();
      state.generation = payload;
      toast("문항 초안 생성이 완료되었습니다.");
    } catch (error) {
      state.generation = { error: error.message };
    } finally {
      state.generating = false;
      renderGeneration();
      renderSummary();
    }
  }

  async function startIntentGeneration() {
    state.intentGenerating = true;
    state.intentGeneration = null;
    state.intentGenerationJob = null;
    window.localStorage.removeItem(intentGenerationJobStorageKey);
    goStep(6);
    renderGeneration();
    renderSummary();
    const selected = selectedEffectiveIntents();
    try {
      const response = await api("/api/faculty/item-intents/generation-jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          department: { id: state.selectedDepartment.id, label: state.selectedDepartment.label },
          faculty_id: "local_faculty",
          set_name: state.intentSetName,
          difficulty: "국가고시형",
          selected_intents: selected,
        }),
      });
      setCurrentGenerationJob(response.job);
      toast(response.duplicate ? "진행 중인 같은 출제 작업에 다시 연결했습니다." : "선택한 출제 의도로 문항 세트 생성을 시작했습니다.");
      await pollGenerationJob();
    } catch (error) {
      state.intentGenerating = false;
      state.intentGeneration = { error: error.message };
      renderGeneration();
      renderSummary();
    }
  }

  function generationTopic() {
    return state.facultyRequest.trim() || state.conceptQuery.trim() || state.concept?.label || state.setName;
  }

  function topicGenerationPayload() {
    return {
      topic: generationTopic(), set_name: state.setName, teaching_points: state.teachingPoints, textbook_reference: state.textbookReference,
      subject: state.courseName, unit: state.concept?.label || state.conceptQuery || "미분류", num_questions: state.count,
      difficulty: state.difficulty, question_type: state.questionType, reasoning_hops: state.reasoningHops,
      reveal_specialty: false, provider: "auto", model: "auto", ontology_review_policy: "faculty_draft",
      disease_concept_id: state.concept?.disease_concept_id || "", target_axis_type: primaryAxis(),
      target_axis_ids: targetAxisIds(), supporting_axis_types: supportingAxes(), option_domain: state.optionDomain,
      selected_media_ids: [...state.selectedMediaIds],
      faculty_question_intent: facultyIntent(),
    };
  }

  async function generateTopic() {
    return api("/api/generate-from-topic", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...topicGenerationPayload(), generation_profile: "fast" }) });
  }

  function clearGenerationPoll() {
    clearCurrentGenerationPoll();
  }

  function generationFromJob(job) {
    return {
      status: "generated",
      set_id: job.result_set_id,
      question_count: job.success_count,
      requested_num_questions: job.requested_count,
      generation_job_id: job.job_id,
    };
  }

  function saveGenerationJob(job) {
    setCurrentGenerationJob(job);
  }

  async function startQueuedGeneration() {
    state.generating = true;
    state.generation = null;
    state.generationJob = null;
    goStep(6);
    renderGeneration();
    renderSummary();
    try {
      const response = await api("/api/generation-jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(topicGenerationPayload()),
      });
      saveGenerationJob(response.job);
      toast(response.duplicate ? "진행 중인 같은 작업에 다시 연결했습니다." : "다문항 생성 작업을 시작했습니다.");
      await pollGenerationJob();
    } catch (error) {
      state.generating = false;
      state.generation = { error: error.message };
      renderGeneration();
      renderSummary();
    }
  }

  async function pollGenerationJob() {
    clearCurrentGenerationPoll();
    const jobId = currentGenerationJob()?.job_id || window.localStorage.getItem(activeStorageKey());
    if (!jobId) return;
    try {
      let job = await api(`/api/generation-jobs/${encodeURIComponent(jobId)}`);
      if (job.recoverable) {
        job = await api(`/api/generation-jobs/${encodeURIComponent(jobId)}/resume`, { method: "POST" });
        toast("중단됐던 생성 작업을 이어서 진행합니다.");
      }
      setCurrentGenerationJob(job);
      const active = ["queued", "running", "retrying"].includes(job.status);
      setCurrentGenerating(active);
      if (job.status === "done") {
        setCurrentGeneration(generationFromJob(job));
        window.localStorage.removeItem(activeStorageKey());
        toast("모든 문항 초안 생성이 완료되었습니다.");
      } else if (!active) {
        setCurrentGeneration(null);
      }
      renderGeneration();
      renderSummary();
      if (active) scheduleCurrentGenerationPoll();
    } catch (error) {
      setCurrentGenerating(false);
      setCurrentGeneration({ error: `진행 상태를 불러오지 못했습니다: ${error.message}` });
      renderGeneration();
      renderSummary();
    }
  }

  async function retryFailedGeneration() {
    const jobId = currentGenerationJob()?.job_id;
    if (!jobId || currentGenerating()) return;
    try {
      setCurrentGenerating(true);
      setCurrentGeneration(null);
      setCurrentGenerationJob(await api(`/api/generation-jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" }));
      renderGeneration();
      renderSummary();
      await pollGenerationJob();
    } catch (error) {
      setCurrentGenerating(false);
      setCurrentGeneration({ error: error.message });
      renderGeneration();
      renderSummary();
    }
  }

  async function cancelQueuedGeneration() {
    const jobId = currentGenerationJob()?.job_id;
    if (!jobId) return;
    try {
      setCurrentGenerationJob(await api(`/api/generation-jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" }));
      toast("현재 문항이 끝난 뒤 생성을 중단합니다.");
      renderGeneration();
    } catch (error) {
      toast(error.message);
    }
  }

  async function restoreGenerationJob() {
    const intentJobId = window.localStorage.getItem(intentGenerationJobStorageKey);
    const directJobId = window.localStorage.getItem(generationJobStorageKey);
    const jobId = intentJobId || directJobId;
    if (!jobId) return false;
    state.intentMode = intentJobId ? "recommended" : "manual";
    const shell = { job_id: jobId, status: "queued", requested_count: intentJobId ? state.intentCount : state.count, success_count: 0, failed_count: 0, items: [] };
    if (intentJobId) {
      state.intentGenerationJob = shell;
      state.intentGenerating = true;
    } else {
      state.generationJob = shell;
      state.generating = true;
    }
    await pollGenerationJob();
    return true;
  }

  async function generateMultipart() {
    const form = new FormData();
    if (state.lectureFile) form.append("lecture_file", state.lectureFile);
    const set = (key, value) => { if (value !== undefined && value !== null && value !== "") form.append(key, String(value)); };
    set("topic", `${generationTopic()}${state.teachingPoints ? `\n[교수 출제 의도] ${state.teachingPoints}` : ""}`);
    set("set_name", state.setName);
    set("subject", state.courseName); set("unit", state.concept?.label || state.conceptQuery || "미분류");
    set("num_questions", state.count); set("difficulty", state.difficulty); set("question_type", state.questionType);
    set("generation_profile", state.count === 1 && !state.selectedMediaIds.size ? "fast" : "standard");
    set("reasoning_hops", state.reasoningHops); set("reveal_specialty", "false"); set("provider", "auto"); set("model", "auto");
    set("ontology_review_policy", "faculty_draft"); set("disease_concept_id", state.concept?.disease_concept_id || "");
    set("target_axis_type", primaryAxis()); set("target_axis_ids", targetAxisIds().join(",")); set("supporting_axis_types", supportingAxes().join(","));
    set("option_domain", state.optionDomain); set("selected_media_ids", [...state.selectedMediaIds].join(","));
    set("image_policy", state.selectedMediaIds.size ? "clinical_visuals" : "none"); set("reference_policy", "local_open");
    return api("/api/generate", { method: "POST", body: form });
  }

  function facultyIntent() {
    return {
      target: { type: state.targetType, id: state.concept?.disease_concept_id || null, label: state.concept?.label || state.conceptQuery || null },
      assessment_claim: state.facultyRequest || selectedTaskObjects().map((item) => item.label).join(" + "),
      task_model: { tasks: state.selectedTasks, format: state.questionType, reasoning_hops: state.reasoningHops, care_phase: state.carePhase },
      evidence_contract: { selected_media_ids: [...state.selectedMediaIds], textbook_reference: state.textbookReference || null, requires_faculty_review: true },
    };
  }

  function renderGenerationResult() {
    const box = $("#generation-result");
    const job = currentGenerationJob();
    const generation = currentGeneration();
    if (job && !generation) {
      box.hidden = false;
      const statusLabels = { queued: "대기", running: "생성 중", retrying: "재시도 대기", done: "완료", failed: "실패", partial: "일부 완료", cancelled: "중단" };
      const items = Array.isArray(job.items) ? job.items : [];
      const active = ["queued", "running", "retrying"].includes(job.status);
      const canRetry = Number(job.failed_count || 0) > 0 && !active;
      const canReviewPartial = Number(job.success_count || 0) > 0 && Boolean(job.result_set_id) && !active;
      box.className = `generation-result job-result ${job.status === "failed" ? "is-danger" : job.status === "partial" || job.status === "cancelled" ? "is-warning" : ""}`;
      box.innerHTML = `
        <div class="job-progress-head"><b>${escapeHtml(job.success_count || 0)} / ${escapeHtml(job.requested_count || (isIntentMode() ? state.intentCount : state.count))}문항 완료</b><span>${escapeHtml(statusLabels[job.status] || job.status)}</span></div>
        <div class="job-progress-track"><i style="width:${Math.max(0, Math.min(100, Number(job.progress_percent || 0)))}%"></i></div>
        <div class="job-items">${items.map((item) => `<div class="job-item ${escapeHtml(item.status)}"><span>${escapeHtml(item.index)}번</span><b>${escapeHtml(item.intent_title || statusLabels[item.status] || item.status)}</b><small>${escapeHtml(statusLabels[item.status] || item.status)}${item.intent_id ? ` · ${escapeHtml(item.intent_id)}` : ""}</small>${item.attempts > 1 ? `<small>${escapeHtml(item.attempts)}회 시도</small>` : ""}${item.error ? `<small>${escapeHtml(item.error)}</small>` : ""}</div>`).join("")}</div>
        ${job.error ? `<p>${escapeHtml(job.error)}</p>` : ""}
        <div class="job-actions">
          ${active ? '<button class="secondary-action" id="generation-cancel" type="button">생성 중단</button>' : ""}
          ${canRetry ? '<button class="primary-action" id="generation-failed-retry" type="button">실패 문항만 다시 시도</button>' : ""}
          ${canReviewPartial ? '<button class="secondary-action" id="generation-partial-review" type="button">저장된 문항 검토</button>' : ""}
        </div>`;
      $("#generation-cancel")?.addEventListener("click", cancelQueuedGeneration);
      $("#generation-failed-retry")?.addEventListener("click", retryFailedGeneration);
      $("#generation-partial-review")?.addEventListener("click", () => { setCurrentGeneration(generationFromJob(job)); goStep(7); });
      return;
    }
    if (!generation) { box.hidden = true; return; }
    box.hidden = false;
    if (generation.error) { box.className = "generation-result is-danger"; box.innerHTML = `<b>초안 생성 실패</b><p>${escapeHtml(generation.error)}</p><button class="secondary-action" id="generation-retry" type="button">같은 설계로 다시 시도</button>`; $("#generation-retry").addEventListener("click", generateDraft); return; }
    const made = Number(generation.question_count ?? generation.num_questions ?? 0);
    const requested = Number(generation.requested_num_questions ?? (isIntentMode() ? state.intentCount : state.count));
    box.className = "generation-result";
    box.innerHTML = `<b>${made}문항 초안 생성됨${made < requested ? ` · 요청 ${requested}문항 중 일부` : ""}</b><p>세트 ID · ${escapeHtml(generation.set_id || "서버 응답 확인 필요")}<br>needs_review=true · 학생 자동 공개 안 됨</p><button class="primary-action" id="generation-next" type="button">교수 검토로 보내기 →</button>`;
    $("#generation-next").addEventListener("click", () => goStep(7));
  }

  function renderReviewHandoff() {
    const box = $("#review-handoff");
    const generation = currentGeneration();
    if (!generation || generation.error) { box.innerHTML = "<div><b>아직 보낼 초안이 없습니다.</b><p>6단계에서 초안을 생성한 뒤 검토·승인 큐로 이동할 수 있습니다.</p></div>"; return; }
    box.innerHTML = `<div><b>${escapeHtml(generation.question_count ?? generation.num_questions ?? (isIntentMode() ? state.intentCount : state.count))}문항을 한 세트로 검토할 준비가 됐습니다.</b><p>검토·승인 큐에서 원래 선택한 출제 의도, 본문, 선지, 정답, 해설과 연결 자료를 확인하세요. 교수 승인은 검수 완료 상태이며 학생 공개·배포는 별도 기능입니다.</p><a data-workflow-complete href="/faculty-studio-v2/review.html${generation.set_id ? `?set=${encodeURIComponent(generation.set_id)}` : ""}">검토·승인으로 이동 →</a></div>`;
  }

  function renderSummary() {
    if (isIntentMode()) {
      const selected = selectedEffectiveIntents();
      const blocked = selected.filter((item) => item.evidence_contract?.coverage_status === "unsupported");
      const badge = $("#coverage-badge");
      badge.textContent = blocked.length ? "근거 보강 필요" : selected.length ? "교수 검수 필요" : "준비 전";
      badge.className = blocked.length ? "unsupported" : selected.length ? "partial" : "";
      $("#summary-list").innerHTML = [
        ["과", state.selectedDepartment?.label || "미선택"],
        ["후보", selected.length ? selected.map((item) => item.target?.label).join(" · ") : "미선택"],
        ["과업", selected.length ? selected.map((item) => item.assessment_claim?.task_label || item.assessment_claim?.task).join(" · ") : "선택 필요"],
        ["형식", `증례형 · ${state.intentCount}문항`],
        ["근거", blocked.length ? `${blocked.length}개 생성 보류` : selected.length ? "검토용 연결" : "확인 전"],
        ["설계 점검", state.intentPreflight.checked ? blocked.length ? "보류 후보 있음" : "완료" : "실행 전"],
      ].map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
      const missing = generationRequirements().filter(([ok]) => !ok).map(([, label]) => label);
      $("#summary-alert").textContent = missing.length ? `생성 전 확인 · ${missing.join(" · ")}` : "교수 검수용 초안 · 학생에게 자동 공개되지 않음";
      const primary = $("#summary-primary");
      const job = currentGenerationJob();
      const generation = currentGeneration();
      const retryableJob = job && Number(job.failed_count || 0) > 0 && !currentGenerating();
      primary.disabled = currentGenerating() || (!generation && !retryableJob && !canGenerate());
      primary.textContent = currentGenerating() ? `${job?.success_count || 0}/${job?.requested_count || state.intentCount}문항 생성 중…` : retryableJob ? "실패 문항만 다시 시도" : generation?.error ? "같은 설계로 다시 시도" : generation ? "검토 단계 보기 →" : `${state.intentCount}문항 초안 만들기`;
      $("#concept-detail-open").disabled = true;
      $("#save-state").textContent = `단계 ${state.step} · ${state.selectedIntentIds.size}/${state.intentCount} 선택`;
      if (state.step === 6) renderGeneration();
      return;
    }
    const cov = coverage();
    const badge = $("#coverage-badge");
    badge.textContent = cov.label;
    badge.className = cov.status;
    const taskText = selectedTaskObjects().map((item) => item.label).join(" · ") || "선택 필요";
    const sourceCount = Number(Boolean(state.lectureFile || state.teachingPoints.trim() || state.textbookReference.trim())) + state.selectedMediaIds.size;
    $("#summary-list").innerHTML = [
      ["과목", state.courseName || "미선택"], ["대상", state.concept?.label || state.conceptQuery || "미선택"], ["과업", taskText],
      ["형식", `${formatLabel(state.questionType)} · ${state.count}문항`], ["근거", `${sourceCount}개 · 미디어 ${state.selectedMediaIds.size}개`],
      ["설계 점검", state.preflight.checked ? state.preflight.policyBlocked ? "정책 차단" : state.preflight.softBlocked ? "경고 · 검수 필요" : "완료" : "실행 전"],
    ].map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
    const missing = generationRequirements().filter(([ok]) => !ok).map(([, label]) => label);
    $("#summary-alert").textContent = missing.length ? `생성 전 확인 · ${missing.join(" · ")}` : cov.message;
    const primary = $("#summary-primary");
    const retryableJob = state.generationJob && Number(state.generationJob.failed_count || 0) > 0 && !state.generating;
    primary.disabled = state.generating || (!state.generation && !retryableJob && !canGenerate());
    primary.textContent = state.generating ? `${state.generationJob?.success_count || 0}/${state.generationJob?.requested_count || state.count}문항 생성 중…` : retryableJob ? "실패 문항만 다시 시도" : state.generation?.error ? "같은 설계로 다시 시도" : state.generation ? "검토 단계 보기 →" : "문항 초안 생성";
    $("#concept-detail-open").disabled = !state.context;
    $("#save-state").textContent = `단계 ${state.step} · ${cov.label}`;
    if (state.step === 6) renderGeneration();
  }

  function openDrawer(name) {
    $("#drawer-backdrop").hidden = false;
    ["copilot", "media-drawer", "concept-drawer"].forEach((id) => { $("#" + id).hidden = id !== name && !(name === "media" && id === "media-drawer") && !(name === "concept" && id === "concept-drawer"); });
    const actual = name === "media" ? "media-drawer" : name === "concept" ? "concept-drawer" : name;
    $("#" + actual).hidden = false;
    $("#copilot-toggle").setAttribute("aria-expanded", String(actual === "copilot"));
  }

  function closeDrawers() {
    $("#drawer-backdrop").hidden = true;
    ["copilot", "media-drawer", "concept-drawer"].forEach((id) => { $("#" + id).hidden = true; });
    $("#copilot-toggle").setAttribute("aria-expanded", "false");
  }

  function renderMedia(filter = "") {
    const query = filter.trim().toLowerCase();
    const rows = state.media.filter((item) => !query || `${item.caption || ""} ${item.diagnosis || ""} ${item.subject || ""} ${item.unit || ""} ${item.modality || ""}`.toLowerCase().includes(query));
    const box = $("#media-list");
    if (!rows.length) { box.innerHTML = '<div class="empty-state"><b>저장된 자료가 없습니다</b><span>근거·미디어에서 먼저 승인 가능한 자료를 준비하세요.</span></div>'; return; }
    box.innerHTML = rows.map((item) => {
      const allowed = Boolean(item.approved_for_question_use && item.deidentified);
      return `<button type="button" class="media-card ${state.drawerMediaIds.has(item.asset_id) ? "selected" : ""} ${allowed ? "" : "blocked"}" data-media-id="${escapeHtml(item.asset_id)}" ${allowed ? "" : "disabled"}><img src="${escapeHtml(item.url || "")}" alt=""/><span><b>${escapeHtml(item.caption || item.diagnosis || item.modality || item.asset_id)}</b><span>${escapeHtml(allowed ? "승인·비식별 · 선택 가능" : `${item.approved_for_question_use ? "승인" : "사용 미승인"} · ${item.deidentified ? "비식별" : "비식별 미확인"}`)}</span></span></button>`;
    }).join("");
    $$('[data-media-id]').forEach((button) => button.addEventListener("click", () => { const id = button.dataset.mediaId; if (state.drawerMediaIds.has(id)) state.drawerMediaIds.delete(id); else state.drawerMediaIds.add(id); renderMedia($("#media-search").value); $("#media-selected-label").textContent = `${state.drawerMediaIds.size}개 선택`; }));
  }

  function openMedia() {
    state.drawerMediaIds = new Set(state.selectedMediaIds);
    $("#media-selected-label").textContent = `${state.drawerMediaIds.size}개 선택`;
    $("#media-search").value = "";
    renderMedia();
    openDrawer("media");
  }

  function openConceptDetail() {
    if (!state.context) return;
    const edges = state.context.inherited_edges || {};
    $("#concept-detail").innerHTML = `<h2>${escapeHtml(state.concept?.label || state.context.label || state.context.disease_concept_id)}</h2><p>${escapeHtml(state.context.disease_concept_id)} · needs_review=true</p><div class="warning-strip"><b>검토용 관계</b><span>아래 연결은 검색·설계 보조이며 정답 근거 승인이 아닙니다.</span></div>${Object.entries(edges).filter(([, values]) => Array.isArray(values) && values.length).map(([relation, values]) => `<section class="relation-group"><h3>${escapeHtml(relation)}</h3><div>${values.slice(0, 16).map((value) => `<span>${escapeHtml(typeof value === "string" ? value : value.id || value.label || "연결")}</span>`).join("")}</div></section>`).join("") || '<div class="empty-state"><b>표시할 관계가 없습니다</b></div>'}`;
    openDrawer("concept");
  }

  function makeProposal(input) {
    const clean = input.trim();
    const first = clean.split(/(?:환자에서|환자에게|에서|의)\s*/)[0].replace(/^(?:교수용|학생에게)\s*/, "").trim();
    const countMatch = clean.match(/(\d+)\s*문항/);
    const suggestedTasks = [];
    const add = (id) => { if (!suggestedTasks.includes(id) && suggestedTasks.length < 2) suggestedTasks.push(id); };
    if (/중증|병기/.test(clean)) add("severity_staging");
    if (/감별/.test(clean)) add("differential_diagnosis");
    if (/진단/.test(clean)) add("most_likely_diagnosis");
    if (/검사.*해석|해석/.test(clean)) add("test_interpretation");
    else if (/검사/.test(clean)) add("test_selection");
    if (/즉시|먼저|초기 처치|응급/.test(clean)) add("immediate_management");
    else if (/치료|처치|약물/.test(clean)) add("first_line_treatment");
    if (/금기/.test(clean)) add("contraindication");
    if (/예후/.test(clean)) add("prognostic_factor");
    if (!suggestedTasks.length) add("most_likely_diagnosis");
    return { input: clean, query: first || clean, count: Math.max(1, Math.min(30, Number(countMatch?.[1] || state.count))), difficulty: /임종평|국시|국가고시/.test(clean) ? "국가고시형" : state.difficulty, questionType: /영상|사진|검사표|자료 해석/.test(clean) ? "image_based" : "clinical_case", tasks: suggestedTasks };
  }

  function renderProposal() {
    const proposal = state.proposal;
    const box = $("#copilot-proposal");
    if (!proposal) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<dl><div><dt>대상</dt><dd>${escapeHtml(proposal.query)} · 검색 제안</dd></div><div><dt>과업</dt><dd>${escapeHtml(proposal.tasks.map((id) => taskById.get(id)?.label).filter(Boolean).join(" + "))}</dd></div><div><dt>형식</dt><dd>${escapeHtml(formatLabel(proposal.questionType))} · ${proposal.count}문항 · ${escapeHtml(proposal.difficulty)}</dd></div></dl><button id="proposal-apply" type="button">제안 적용</button>`;
    $("#proposal-apply").addEventListener("click", applyProposal);
  }

  function applyProposal() {
    if (!state.proposal) return;
    state.intentMode = "manual";
    state.facultyRequest = state.proposal.input;
    state.conceptQuery = state.proposal.query;
    state.count = state.proposal.count;
    state.difficulty = state.proposal.difficulty;
    state.questionType = state.proposal.questionType;
    state.selectedTasks = [...state.proposal.tasks];
    $("#faculty-request").value = state.facultyRequest;
    $("#concept-query").value = state.conceptQuery;
    $("#question-count").textContent = String(state.count);
    $$("#difficulty-options button").forEach((button) => button.classList.toggle("selected", button.dataset.value === state.difficulty));
    $$("#format-options button").forEach((button) => button.classList.toggle("selected", button.dataset.value === state.questionType));
    renderTaskGroups();
    invalidatePreflight();
    renderSummary();
    closeDrawers();
    goStep(2);
    toast("Copilot 제안을 적용했습니다. Ontology 후보를 확인하세요.");
  }

  async function performLogout(button) {
    button.disabled = true;
    try {
      const response = await fetch("/api/auth/logout", {method: "POST"});
      if (!response.ok) throw new Error(`로그아웃 실패 (${response.status})`);
      window.location.replace("/login");
    } catch (error) {
      button.disabled = false;
      bypassLeaveGuard = false;
      throw error;
    }
  }

  function bindStaticEvents() {
    document.addEventListener("click", (event) => {
      const anchor = event.target.closest("a[href]");
      if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      if (anchor.hasAttribute("data-workflow-complete")) {
        state.workflowComplete = true;
        clearWorkflowDraft();
        bypassLeaveGuard = true;
        return;
      }
      if (!hasUnfinishedWorkflow()) return;
      event.preventDefault();
      requestLeave(() => window.location.assign(anchor.href));
    });
    window.addEventListener("beforeunload", (event) => {
      if (!bypassLeaveGuard && hasUnfinishedWorkflow()) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
    $("#leave-guard-stay").addEventListener("click", closeLeaveGuard);
    $("#leave-guard-save").addEventListener("click", () => resolveLeave({ save: true }));
    $("#leave-guard-discard").addEventListener("click", () => resolveLeave({ save: false }));
    $("#logout-button")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      if (hasUnfinishedWorkflow()) {
        requestLeave(() => performLogout(button));
        return;
      }
      try { await performLogout(button); }
      catch (error) { toast(error.message || "로그아웃하지 못했습니다. 다시 시도해 주세요."); }
    });
    $$('[data-intent-mode]').forEach((button) => button.addEventListener("click", () => setIntentMode(button.dataset.intentMode)));
    $("#intent-set-name").addEventListener("input", (event) => { state.intentSetName = event.target.value; renderSummary(); });
    $$('[data-intent-count]').forEach((button) => button.addEventListener("click", () => {
      const count = Number(button.dataset.intentCount);
      const allowed = Array.isArray(state.departmentDefaults.allowed_item_count) ? state.departmentDefaults.allowed_item_count.map(Number) : [2, 3];
      if (!allowed.includes(count)) return;
      state.intentCount = count;
      while (state.selectedIntentIds.size > count) state.selectedIntentIds.delete([...state.selectedIntentIds].at(-1));
      state.recommendationState = state.selectedDepartment ? "idle" : state.recommendationState;
      invalidateIntentPreflight();
      renderDepartments();
      renderIntentCandidates();
      renderSummary();
    }));
    $("#intent-refresh").addEventListener("click", () => loadIntentRecommendations({ refresh: true }));
    $("#intent-manual-entry").addEventListener("click", () => setIntentMode("manual"));
    $("#intent-preflight-run").addEventListener("click", runIntentPreflight);
    $("#course-select").addEventListener("change", (event) => { const course = state.courses.find((item) => item.id === event.target.value); state.courseId = event.target.value; state.courseName = course?.name || event.target.selectedOptions[0]?.textContent || ""; invalidatePreflight(); renderSummary(); });
    $("#set-name").addEventListener("input", (event) => { state.setName = event.target.value; });
    $("#faculty-request").addEventListener("input", (event) => { state.facultyRequest = event.target.value; invalidatePreflight(); renderSummary(); });
    $$('[data-count]').forEach((button) => button.addEventListener("click", () => { state.count = Math.max(1, Math.min(30, state.count + Number(button.dataset.count))); $("#question-count").textContent = String(state.count); invalidatePreflight(); renderSummary(); }));
    $$("#difficulty-options button").forEach((button) => button.addEventListener("click", () => { state.difficulty = button.dataset.value; $$("#difficulty-options button").forEach((node) => node.classList.toggle("selected", node === button)); invalidatePreflight(); renderSummary(); }));
    $$("#target-types button").forEach((button) => button.addEventListener("click", () => { state.targetType = button.dataset.value; $$("#target-types button").forEach((node) => node.classList.toggle("selected", node === button)); invalidatePreflight(); }));
    $("#concept-search").addEventListener("click", searchConcepts);
    $("#concept-query").addEventListener("keydown", (event) => { if (event.key === "Enter") searchConcepts(); });
    $("#concept-query").addEventListener("input", (event) => { state.conceptQuery = event.target.value; invalidatePreflight(); renderSummary(); });
    $$("#format-options button").forEach((button) => button.addEventListener("click", () => { state.questionType = button.dataset.value; $$("#format-options button").forEach((node) => node.classList.toggle("selected", node === button)); invalidatePreflight(); renderSummary(); }));
    $("#reasoning-hops").addEventListener("change", (event) => { state.reasoningHops = Number(event.target.value); invalidatePreflight(); renderSummary(); });
    $("#care-phase").addEventListener("change", (event) => { state.carePhase = event.target.value; invalidatePreflight(); });
    $("#option-domain").addEventListener("input", (event) => { state.optionDomain = event.target.value; invalidatePreflight(); });
    $("#intent-lecture-manual")?.addEventListener("click", () => {
      setIntentMode("manual");
      goStep(4);
      toast("직접 설정의 강의자료 첨부로 전환했습니다.");
    });
    $("#manual-lecture-file")?.addEventListener("change", (event) => { state.lectureFile = event.target.files?.[0] || null; invalidatePreflight(); renderCoverage(); renderSummary(); });
    $("#teaching-points").addEventListener("input", (event) => { state.teachingPoints = event.target.value; invalidatePreflight(); renderCoverage(); renderSummary(); });
    $("#textbook-reference").addEventListener("input", (event) => { state.textbookReference = event.target.value; invalidatePreflight(); renderCoverage(); renderSummary(); });
    $("#preflight-run").addEventListener("click", runPreflight);
    $("#generate-run").addEventListener("click", generateDraft);
    $("#summary-primary").addEventListener("click", () => {
      const generation = currentGeneration();
      const job = currentGenerationJob();
      if (generation && !generation.error) goStep(7);
      else if (job && Number(job.failed_count || 0) > 0 && !currentGenerating()) retryFailedGeneration();
      else generateDraft();
    });
    $("#previous-step").addEventListener("click", () => goStep(state.step - 1));
    $("#next-step").addEventListener("click", () => goStep(state.step + 1));
    $("#copilot-toggle").addEventListener("click", () => $("#copilot").hidden ? openDrawer("copilot") : closeDrawers());
    $$('[data-drawer-close]').forEach((button) => button.addEventListener("click", closeDrawers));
    $("#drawer-backdrop").addEventListener("click", closeDrawers);
    $("#media-open").addEventListener("click", openMedia);
    $("#manual-media-open")?.addEventListener("click", openMedia);
    $("#media-search").addEventListener("input", (event) => renderMedia(event.target.value));
    $("#media-apply").addEventListener("click", () => { state.selectedMediaIds = new Set(state.drawerMediaIds); $("#media-count").textContent = String(state.selectedMediaIds.size); closeDrawers(); invalidatePreflight(); renderCoverage(); renderSummary(); });
    $("#concept-detail-open").addEventListener("click", openConceptDetail);
    $("#copilot-send").addEventListener("click", () => { const input = $("#copilot-input").value.trim(); if (!input) return; $("#copilot-messages").innerHTML += `<div class="user-message">${escapeHtml(input)}</div><div class="assistant-message">요청을 구조 후보로 정리했습니다. 적용 전까지 중앙 설계는 바뀌지 않습니다.</div>`; state.proposal = makeProposal(input); renderProposal(); $("#copilot-input").value = ""; });
  }

  async function init() {
    renderStepRail();
    renderTaskGroups();
    bindStaticEvents();
    renderIntentMode();
    await Promise.all([loadCourses(), loadMedia(), loadDepartments()]);
    const restoredDraft = restoreWorkflowDraft();
    const restoredStep = state.step;
    if (restoredDraft) syncRestoredDraftControls();
    renderCoverage();
    renderSummary();
    const restoredJob = await restoreGenerationJob();
    goStep(restoredJob ? 6 : restoredDraft ? restoredStep : 1);
    if (restoredDraft) toast(state.savedLectureFileName ? `임시저장 작업을 복구했습니다. ${state.savedLectureFileName} 파일은 다시 선택해 주세요.` : "임시저장한 문항 세트를 복구했습니다.");
  }

  init();
})();
