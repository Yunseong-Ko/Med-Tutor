/* Faculty Studio V2 — isolated controller. No dependency on the legacy app.js.
   Talks only to existing API contracts (audited): /api/generate (multipart),
   /api/generate-from-topic (JSON), /api/ontology/context, /api/ontology/question-blueprint,
   /api/media, /api/models. Every output is a faculty draft (needs_review). Never
   renders asset.file_path — only asset.url. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const AXIS_LABEL = {
    symptom: "증상·임상 소견", diagnosis: "진단", pathophysiology: "병태생리",
    etiology: "원인", risk_factor: "위험요인", prognosis: "예후", epidemiology: "역학",
    treatment: "치료", indication: "적응증", contraindication: "금기",
  };
  const QTYPE_LABEL = { clinical_case: "임상 증례", basic_concept: "개념 확인", image_based: "이미지·자료 해석" };

  const state = {
    source: "topic",           // topic | lecture | evidence
    concept: { id: "", label: "", status: "" },
    axis: "",
    qtype: "clinical_case",
    count: 3,
    fast: false,
    selectedMediaIds: new Set(),   // owned by THIS draft; starts empty, reset on new draft
    blueprint: { checked: false, policyBlocked: false, softBlocked: false, reasons: [] },
    submitting: false,
    mediaAssets: [],
    drawerMode: "image",
    drawerTemp: new Set(),
  };

  // ---------- helpers ----------
  const sourceTopic = () => {
    if (state.source === "lecture") return ($("#fs2-lecture-topic")?.value || "").trim();
    if (state.source === "evidence") return ($("#fs2-evidence-topic")?.value || "").trim();
    return ($("#fs2-topic")?.value || "").trim();
  };
  const conceptQuery = () => ($("#fs2-concept")?.value || "").trim() || sourceTopic();
  const lectureFile = () => $("#fs2-lecture-file")?.files?.[0] || null;
  const effectiveCount = () => (state.fast ? 1 : state.count);
  const reviewPolicy = "faculty_draft";

  const sourceReady = () => {
    if (state.source === "lecture") return !!lectureFile() || !!sourceTopic();
    return !!sourceTopic();
  };

  // ---------- summary + CTA gating ----------
  function updateSummary() {
    const parts = [];
    if (state.concept.label) parts.push(state.concept.label);
    else if (sourceTopic()) parts.push(sourceTopic().slice(0, 24));
    parts.push(state.axis ? `${AXIS_LABEL[state.axis]} 축` : "축 미선택");
    parts.push(QTYPE_LABEL[state.qtype]);
    parts.push(`${effectiveCount()}문항`);
    $("#fs2-summary-line").textContent = parts.join(" · ");

    const setText = (selector, value) => {
      const node = $(selector);
      if (node) node.textContent = value;
    };
    const sourceLabel = state.source === "lecture"
      ? (lectureFile()?.name || "강의자료")
      : state.source === "evidence"
        ? `저장 근거 ${state.selectedMediaIds.size}개`
        : "주제 입력";
    const conceptLabel = state.concept.label
      || conceptQuery()
      || "미연결";
    setText("#fs2-summary-source", sourceLabel);
    setText("#fs2-summary-concept", conceptLabel);
    setText("#fs2-summary-axis", state.axis ? AXIS_LABEL[state.axis] : "선택 필요");
    setText("#fs2-summary-type", QTYPE_LABEL[state.qtype]);
    setText("#fs2-summary-count", `${effectiveCount()}문항`);
    setText("#fs2-summary-media", state.selectedMediaIds.size ? `${state.selectedMediaIds.size}개 연결` : "선택 안 함");

    const okToGen = sourceReady() && !!state.axis && !state.submitting;
    const btn = $("#fs2-generate-btn");
    btn.disabled = !okToGen;
    let hint = "";
    if (!sourceReady()) hint = state.source === "lecture" ? "다음: 강의자료 또는 주제를 입력하세요." : "다음: 출제 주제를 입력하세요.";
    else if (!state.axis) hint = "다음: 평가 축을 선택하세요.";
    else if (state.blueprint.checked && state.blueprint.policyBlocked) hint = "정책상 차단됨 — 생성할 수 없습니다.";
    else hint = "생성 준비 완료 · 검수용 초안으로 만들어집니다.";
    $("#fs2-cta-hint").textContent = hint;
  }

  // Any input that changes the design invalidates a prior preflight OK.
  function invalidatePreflight() {
    state.blueprint = { checked: false, policyBlocked: false, softBlocked: false, reasons: [] };
    const el = $("#fs2-preflight");
    el.textContent = ""; el.className = "fs2-preflight";
  }

  // ---------- source ----------
  function wireSource() {
    const chips = Array.from(document.querySelectorAll("#fs2-source-chips .fs2-chip"));
    chips.forEach((chip) => chip.addEventListener("click", () => {
      chips.forEach((c) => c.setAttribute("aria-checked", String(c === chip)));
      state.source = chip.dataset.source;
      document.querySelectorAll("[data-source-body]").forEach((body) => {
        body.hidden = body.dataset.sourceBody !== state.source;
      });
      invalidatePreflight();
      updateSummary();
    }));
  }

  // ---------- concept ----------
  async function checkConcept() {
    const q = conceptQuery();
    const el = $("#fs2-concept-state");
    if (!q) { el.textContent = "개념 또는 주제를 먼저 입력하세요."; el.className = "fs2-concept-state"; return; }
    el.textContent = "개념 확인 중…"; el.className = "fs2-concept-state";
    try {
      const url = `/api/ontology/context?topic=${encodeURIComponent(q)}&review_policy=${reviewPolicy}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "확인 실패");
      if (data.status === "blocked") {
        state.concept = { id: "", label: "", status: "blocked" };
        el.textContent = `연결 차단: ${(data.block_reasons || []).join(", ") || "정책상 차단"}`;
        el.className = "fs2-concept-state is-blocked";
      } else if (data.status === "matched" && data.disease_concept_id) {
        state.concept = { id: data.disease_concept_id, label: data.label || data.disease_concept_id, status: "matched" };
        el.textContent = `${state.concept.label} · Ontology 연결됨 · 검토용`;
        el.className = "fs2-concept-state is-matched";
      } else {
        state.concept = { id: "", label: "", status: "unmatched" };
        el.textContent = "Ontology 미연결 — 근거 상속 없이 생성됩니다(주제 기반).";
        el.className = "fs2-concept-state is-unmatched";
      }
    } catch (err) {
      state.concept = { id: "", label: "", status: "" };
      el.textContent = `개념 확인 실패: ${err.message}`;
      el.className = "fs2-concept-state is-unmatched";
    }
    invalidatePreflight();
    updateSummary();
  }

  // ---------- single-select chip groups ----------
  function wireRadioChips(containerSel, dataKey, onPick) {
    const chips = Array.from(document.querySelectorAll(`${containerSel} .fs2-chip`));
    chips.forEach((chip) => chip.addEventListener("click", () => {
      chips.forEach((c) => c.setAttribute("aria-checked", String(c === chip)));
      onPick(chip.dataset[dataKey]);
      invalidatePreflight();
      updateSummary();
    }));
  }

  // ---------- count + fast ----------
  function wireCount() {
    document.querySelectorAll("[data-count]").forEach((btn) => btn.addEventListener("click", () => {
      const delta = Number(btn.dataset.count);
      state.count = Math.min(30, Math.max(1, state.count + delta));
      renderCount();
      invalidatePreflight();
      updateSummary();
    }));
    $("#fs2-fast").addEventListener("change", (e) => {
      state.fast = e.target.checked;
      renderCount();
      invalidatePreflight();
      updateSummary();
    });
  }
  function renderCount() {
    $("#fs2-count").textContent = state.fast ? "1" : String(state.count);
  }

  // ---------- media drawer ----------
  async function loadMedia() {
    try {
      const res = await fetch("/api/media");
      const data = await res.json();
      state.mediaAssets = data.assets || [];
    } catch { state.mediaAssets = []; }
  }
  const isSelectable = (a) => Boolean(a.approved_for_question_use) && Boolean(a.deidentified);

  function openDrawer(mode) {
    state.drawerMode = mode;
    state.drawerTemp = new Set(state.selectedMediaIds);
    $("#fs2-drawer-title").textContent = mode === "evidence" ? "저장된 근거 선택" : "이미지 선택";
    $("#fs2-drawer").hidden = false;
    renderDrawer("");
  }
  function closeDrawer() { $("#fs2-drawer").hidden = true; }

  function renderDrawer(filter) {
    const grid = $("#fs2-drawer-grid");
    const q = (filter || "").toLowerCase();
    const list = state.mediaAssets.filter((a) => {
      const hay = `${a.caption || ""} ${a.diagnosis || ""} ${a.subject || ""} ${a.unit || ""} ${a.modality || ""}`.toLowerCase();
      return !q || hay.includes(q);
    });
    if (!list.length) { grid.innerHTML = '<p class="fs2-note">저장된 자료가 없습니다.</p>'; updateDrawerFoot(); return; }
    grid.innerHTML = list.map((a) => {
      const selectable = isSelectable(a);
      const sel = state.drawerTemp.has(a.asset_id) ? " is-selected" : "";
      const dis = selectable ? "" : " is-disabled";
      const badge = selectable
        ? '<span class="fs2-media-badge">승인·비식별</span>'
        : `<span class="fs2-media-badge is-blocked">${a.approved_for_question_use ? "" : "미승인 "}${a.deidentified ? "" : "미비식별"}</span>`;
      // Only asset.url is rendered — never asset.file_path.
      return `<button type="button" class="fs2-media-card${sel}${dis}" data-asset="${escAttr(a.asset_id)}" ${selectable ? "" : "disabled"}>
        <img src="${escAttr(a.url || "")}" alt="${escAttr(a.caption || "media")}" loading="lazy" />
        <span class="fs2-media-meta"><span class="fs2-media-cap">${escHtml(a.caption || a.diagnosis || a.modality || a.asset_id)}</span>${badge}</span>
      </button>`;
    }).join("");
    grid.querySelectorAll(".fs2-media-card:not(.is-disabled)").forEach((card) => {
      card.addEventListener("click", () => {
        const id = card.dataset.asset;
        if (state.drawerTemp.has(id)) { state.drawerTemp.delete(id); card.classList.remove("is-selected"); }
        else { state.drawerTemp.add(id); card.classList.add("is-selected"); }
        updateDrawerFoot();
      });
    });
    updateDrawerFoot();
  }
  function updateDrawerFoot() { $("#fs2-drawer-selected").textContent = `${state.drawerTemp.size}개 선택`; }

  function commitDrawer() {
    state.selectedMediaIds = new Set(state.drawerTemp);
    $("#fs2-image-count").textContent = `${state.selectedMediaIds.size}개`;
    $("#fs2-evidence-count").textContent = `${state.selectedMediaIds.size}개`;
    if (state.selectedMediaIds.size && $("#fs2-image-policy").value === "none") {
      $("#fs2-image-policy").value = "clinical_visuals";
    }
    closeDrawer();
    invalidatePreflight();
    updateSummary();
  }

  // ---------- blueprint preflight ----------
  async function runPreflight() {
    const el = $("#fs2-preflight");
    if (!state.axis) { el.textContent = "평가 축을 먼저 선택하세요."; el.className = "fs2-preflight is-blocked"; return false; }
    el.textContent = "출제 설계 확인 중…"; el.className = "fs2-preflight";
    try {
      const res = await fetch("/api/ontology/question-blueprint", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic: sourceTopic() || conceptQuery(),
          disease_concept_id: state.concept.id,
          review_policy: reviewPolicy,
          question_type: state.qtype,
          target_axis_type: state.axis,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "확인 실패");
      // Two distinct block kinds:
      //  - grounding.blocked = POLICY fail-closed (e.g. student_approved w/ 0 approved claims) → hard stop.
      //  - blueprint.status="blocked" w/o policy block = ontology grounding incomplete
      //    (distractor_pool_lt_4, target_axis_ids_missing). Under faculty_draft this is EXPECTED
      //    while the ontology is unapproved, so it is a caution, not a hard stop — the draft is
      //    generated ungrounded and stays needs_review. (Blocking here would make generation
      //    impossible while all 37k claims are draft_unreviewed.)
      const reasons = (data.question_blueprint?.block_reasons) || (data.grounding?.block_reasons) || [];
      const policyBlocked = Boolean(data.grounding?.blocked);
      const softBlocked = data.status === "blocked" && !policyBlocked;
      state.blueprint = { checked: true, policyBlocked, softBlocked, reasons };
      updateSummary();
      if (policyBlocked) {
        el.textContent = `정책 차단: ${reasons.join(" · ") || "검토 정책상 생성 불가"}`;
        el.className = "fs2-preflight is-blocked";
        return false;
      }
      if (softBlocked) {
        el.textContent = `근거 미완성(${reasons.join(" · ")}) — 근거 상속 없이 초안 생성 · 검수 필요`;
        el.className = "fs2-preflight is-warn";
        return true;
      }
      el.textContent = "설계 확인됨 · 검수용 초안 생성 가능";
      el.className = "fs2-preflight is-ok";
      return true;
    } catch (err) {
      state.blueprint = { checked: false, blocked: false, reasons: [] };
      el.textContent = `설계 확인 실패: ${err.message}`;
      el.className = "fs2-preflight is-blocked";
      return false;
    }
  }

  // ---------- generation ----------
  function advancedCommon(setField) {
    const hops = $("#fs2-hops").value;
    const optionDomain = ($("#fs2-option-domain").value || "").trim();
    // subject/unit intentionally omitted — the legacy fixed-example values (신경과/뇌혈관질환)
    // must not be sent as real classification. The backend accepts their absence.
    if (hops) setField("reasoning_hops", hops);
    if (optionDomain) setField("option_domain", optionDomain);
    setField("reveal_specialty", $("#fs2-reveal-specialty").checked ? "true" : "false");
    setField("provider", "auto");
    setField("model", "auto");
    setField("difficulty", $("#fs2-difficulty").value || "보통");
    setField("question_type", state.qtype);
    setField("target_axis_type", state.axis);
    setField("ontology_review_policy", reviewPolicy);
    if (state.concept.id) setField("disease_concept_id", state.concept.id);
  }

  async function generate() {
    if (state.submitting) return;                         // dup-submit guard
    if (!sourceReady() || !state.axis) return;
    setSubmitting(true);
    $("#fs2-result").hidden = true;                        // clear any prior result
    showStatus("출제 설계 확인 중…");
    const ok = await runPreflight();
    if (!ok) { showStatus("검토 정책상 생성이 차단되었습니다. Ontology 의학검토 승인 후 다시 시도하세요.", "warn"); setSubmitting(false); return; }

    const useMultipart = state.source === "lecture" || state.selectedMediaIds.size > 0;
    const caution = state.blueprint.softBlocked ? " (Ontology 근거 미완성 · 검수 필요)" : "";
    showStatus(`문항 초안 생성 중…${caution} (수십 초 소요될 수 있습니다)`);
    try {
      let payload;
      if (useMultipart) {
        payload = await postMultipart();
      } else {
        payload = await postTopicJson();
      }
      renderResult(payload);
    } catch (err) {
      showStatus(`생성 실패: ${err.message}`, "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function postTopicJson() {
    const body = {
      topic: sourceTopic(),
      teaching_points: $("#fs2-teaching")?.value || "",
      textbook_reference: $("#fs2-textbook")?.value || "",
      subject: "",
      unit: "",
      num_questions: effectiveCount(),
      question_type: state.qtype,
      target_axis_type: state.axis,
      difficulty: $("#fs2-difficulty").value || "보통",
      reasoning_hops: $("#fs2-hops").value ? Number($("#fs2-hops").value) : undefined,
      reveal_specialty: $("#fs2-reveal-specialty").checked,
      provider: "auto",
      model: "auto",
      ontology_review_policy: reviewPolicy,
      disease_concept_id: state.concept.id || "",
      target_axis_ids: [],
    };
    const res = await fetch("/api/generate-from-topic", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "생성 실패");
    return data;
  }

  async function postMultipart() {
    const fd = new FormData();
    const set = (k, v) => { if (v !== undefined && v !== null && v !== "") fd.append(k, v); };
    const file = lectureFile();
    if (file) set("lecture_file", file);
    // topic carries teaching intent so nothing is lost on the multipart path
    let topic = sourceTopic();
    const tp = ($("#fs2-teaching")?.value || "").trim();
    const tb = ($("#fs2-textbook")?.value || "").trim();
    if (tp) topic = `${topic}\n[출제 의도] ${tp}`;
    if (tb) topic = `${topic}\n[참고 교재] ${tb}`;
    set("topic", topic);
    set("num_questions", String(effectiveCount()));
    set("generation_profile", state.fast ? "fast" : "standard");
    set("image_policy", state.selectedMediaIds.size ? $("#fs2-image-policy").value : "none");
    if (state.selectedMediaIds.size) set("selected_media_ids", Array.from(state.selectedMediaIds).join(","));
    set("reference_policy", $("#fs2-reference-policy").value || "local_open");
    if ($("#fs2-include-tables").checked) set("include_tables", "true");
    advancedCommon(set);
    const res = await fetch("/api/generate", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "생성 실패");
    return data;
  }

  // ---------- result ----------
  function renderResult(payload) {
    const box = $("#fs2-result");
    box.hidden = false;
    if (payload.status === "prompt_ready") {
      showStatus("프롬프트만 준비됨");
      box.className = "fs2-result is-warn";
      box.innerHTML = `<strong>문항 설계 자료만 준비되었습니다.</strong><br>
        실제 문항은 생성되지 않았습니다. 생성 엔진 연결 상태를 확인한 뒤 같은 조건으로 다시 시도하세요.`;
      return;
    }
    const made = Number(payload.question_count ?? payload.num_questions ?? 0);
    const requested = Number(payload.requested_num_questions ?? effectiveCount());
    const partial = made > 0 && made < requested;
    showStatus(made > 0 ? "문항 초안 생성 완료" : "생성 결과 확인 필요");
    box.className = `fs2-result ${partial ? "is-warn" : "is-ok"}`;
    const setId = payload.set_id || "";
    box.innerHTML = `
      <strong>${made}문항 초안 생성됨${partial ? ` (요청 ${requested}문항 중 일부)` : ""}.</strong>
      교수 검수용 초안이며 학생에게 공개되지 않았습니다.${setId ? `<br><span class="fs2-note">세트 ID: ${escHtml(setId)}</span>` : ""}
      <div class="fs2-result-actions">
        <button type="button" class="fs2-btn-primary" id="fs2-go-review">문항 검토로 이동</button>
        <button type="button" class="fs2-btn-secondary" id="fs2-make-another" style="color:var(--action-hover);border-color:var(--action);">새 문항 만들기</button>
      </div>`;
    $("#fs2-go-review").addEventListener("click", () => window.location.assign("./review.html"));
    $("#fs2-make-another").addEventListener("click", resetDraft);
  }

  function showStatus(text, tone) {
    $("#fs2-status-card").hidden = false;
    const el = $("#fs2-status-text");
    el.textContent = text;
    el.style.color = tone === "error" ? "var(--danger)" : tone === "warn" ? "var(--warning)" : "var(--text)";
  }
  function setSubmitting(v) {
    state.submitting = v;
    $("#fs2-generate-btn").disabled = v || !(sourceReady() && state.axis);
    $("#fs2-preflight-btn").disabled = v;
    updateSummary();
  }

  function resetDraft() {
    state.selectedMediaIds = new Set();       // per-draft isolation
    $("#fs2-image-count").textContent = "0개";
    $("#fs2-evidence-count").textContent = "0개";
    $("#fs2-status-card").hidden = true;
    $("#fs2-result").hidden = true;
    invalidatePreflight();
    updateSummary();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------- escaping ----------
  function escHtml(s) { return String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
  function escAttr(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  // ---------- wire ----------
  function init() {
    wireSource();
    wireRadioChips("#fs2-axis-chips", "axis", (v) => { state.axis = v; });
    wireRadioChips("#fs2-qtype-chips", "qtype", (v) => { state.qtype = v; });
    wireCount();
    $("#fs2-concept-check").addEventListener("click", checkConcept);
    document.querySelectorAll("[data-open-drawer]").forEach((b) =>
      b.addEventListener("click", () => openDrawer(b.dataset.openDrawer)));
    $("#fs2-drawer-close").addEventListener("click", closeDrawer);
    $("#fs2-drawer-done").addEventListener("click", commitDrawer);
    $("#fs2-drawer-search").addEventListener("input", (e) => renderDrawer(e.target.value));
    $("#fs2-drawer").addEventListener("click", (e) => { if (e.target === $("#fs2-drawer")) closeDrawer(); });
    $("#fs2-preflight-btn").addEventListener("click", runPreflight);
    $("#fs2-generate-btn").addEventListener("click", generate);
    // recompute gating as source text changes
    ["#fs2-topic", "#fs2-lecture-topic", "#fs2-evidence-topic"].forEach((sel) => {
      $(sel)?.addEventListener("input", () => { invalidatePreflight(); updateSummary(); });
    });
    $("#fs2-lecture-file")?.addEventListener("change", (e) => {
      const f = e.target.files?.[0];
      $("#fs2-lecture-label").textContent = f ? f.name : "강의자료 선택 (PDF · PPTX · DOCX · HWP · TXT)";
      invalidatePreflight(); updateSummary();
    });
    renderCount();
    updateSummary();
    loadMedia();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
