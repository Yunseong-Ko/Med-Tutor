/* 교수 검토 콘솔 — 클로드 디자인 시안(Faculty_Review_Console.dc.html, 2026-09-05)을 실제 API에 붙인 격리 entrypoint.
   계약: docs/api/Faculty_Student_Ops_API_Contract_20260906.md §A(가입 승인) §B(문항 확정) + summary 확장(세트별 분포·7지표).
   빌드 없이 동작하는 단일 파일(vanilla JS). 모든 문자열은 esc()로 출력한다. */

const app = document.querySelector("#frc-app");
const tabsRoot = document.querySelector("#frc-tabs");
const progressRoot = document.querySelector("#frc-progress");
const toastEl = document.querySelector("#frc-toast");

const FILTERS = [["all", "전체"], ["needs_review", "검토 필요"], ["revise", "수정필요"], ["discard", "폐기"], ["answer_changed", "정답변경"]];
const SCORE_LABELS = ["정확성", "명확성", "해설"];
const REVIEWER_NAMES = ["A", "B", "C", "D", "E", "F"];
const DECISION_LABEL = {approve: "승인됨", revise: "수정 지시됨", discard: "폐기됨"};
const ACTION_CLASS = {"그대로": "green", "경미": "teal", "수정필요": "amber", "폐기": "coral"};
const VERDICT_CLASS = {"수정없이 사용": "green", "소폭 수정하여 사용": "teal", "대폭 수정 필요": "amber", "사용 불가": "coral"};
const ENTAIL = {
  fully: ["✓ 완전 (fully)", "green"], partially: ["△ 핵심 (partially)", "amber"], not: ["✗ 미확인 (not)", "coral"],
  fully_supported: ["✓ 완전", "green"], partially_supported: ["△ 핵심", "amber"], not_supported: ["✗ 미확인", "coral"],
};
const MEDIA_BASE = "/api/course-exams/media/SYNTH_GENERATED/";

const state = {
  tab: "adj",
  filter: "all",
  queue: {items: [], counts: {}},
  queueLoading: true,
  qid: null,
  item: null,
  itemLoading: false,
  itemError: "",
  editing: null,          // {kind: "stem"|"explanation"|"choice", n?, value}
  memo: "",
  showHistory: false,
  saved: "",
  gateWarn: null,         // failed_rules after PUT
  bookForm: {book_id: "", chapter: "", page: ""},
  summary: null,
  signups: {status: "pending", items: [], counts: {pending: 0, approved: 0, rejected: 0}, loading: true},
  sel: new Set(),
  creds: new Map(),       // request_id → {login_email, initial_password} (세션 내 1회 표시)
  copied: "",
  reportSet: "all",
  sourceText: {open: false, loading: false, qid: null, payload: null, sourceIndex: 0, page: null, error: ""},   // 원문 보기 패널
};

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"})[char]);
}

function toast(message, kind = "") {
  toastEl.textContent = message;
  toastEl.className = `frc-toast show ${kind}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toastEl.classList.remove("show"), kind === "error" ? 4200 : 2600);
}

async function api(url, options = {}) {
  const response = await fetch(url, {...options, headers: {"content-type": "application/json", ...(options.headers || {})}});
  if (response.status === 401) {
    location.href = `/login?next=${encodeURIComponent("/faculty-review-console/")}`;
    throw new Error("로그인이 필요합니다.");
  }
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const error = new Error(payload.detail || `요청 실패 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}
const get = (url) => api(url);
const send = (method, url, body) => api(url, {method, body: JSON.stringify(body ?? {})});
const API = {
  queue: (filter) => get(`/api/faculty/adjudication/queue?filter=${encodeURIComponent(filter)}`),
  item: (qid) => get(`/api/faculty/adjudication/items/${encodeURIComponent(qid)}`),
  update: (qid, changes) => send("PUT", `/api/faculty/adjudication/items/${encodeURIComponent(qid)}`, changes),
  decide: (qid, decision, note) => send("POST", `/api/faculty/adjudication/items/${encodeURIComponent(qid)}/decision`, {decision, note}),
  summary: () => get("/api/faculty/adjudication/summary"),
  sourceText: (qid) => get(`/api/faculty/adjudication/items/${encodeURIComponent(qid)}/source-text?context=1`),
  signups: (status) => get(`/api/faculty/signups?status=${encodeURIComponent(status)}`),
  approve: (id, note) => send("POST", `/api/faculty/signups/${encodeURIComponent(id)}/approve`, {note}),
  reject: (id, reason) => send("POST", `/api/faculty/signups/${encodeURIComponent(id)}/reject`, {reason}),
  bulkApprove: (ids) => send("POST", "/api/faculty/signups/bulk-approve", {request_ids: ids}),
};

/* ── 유틸 ─────────────────────────────────────────────────────────── */
function stamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// lab_box: "백혈구 9,800/mm³(4,000~10,000), CRP 0.8 mg/dL(<0.5)" 또는 줄바꿈 구분 → [{name,value,ref}]
function parseLabBox(text) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const tokens = raw.includes("\n") ? raw.split(/\n+/) : raw.split(/,\s+(?=[^\d\s(])/);
  return tokens.map((token) => token.trim()).filter(Boolean).map((token) => {
    const withRef = token.match(/^(.+?)\s+(\S.*?)\s*\(([^()]*)\)\s*$/);
    if (withRef) return {name: withRef[1], value: withRef[2], ref: withRef[3]};
    const attachedRef = token.match(/^(.+?)\s+([^\s(]+)\(([^()]*)\)\s*$/);
    if (attachedRef) return {name: attachedRef[1], value: attachedRef[2], ref: attachedRef[3]};
    const colon = token.match(/^(.+?):\s*(.+)$/);
    if (colon) return {name: colon[1], value: colon[2], ref: ""};
    const spaced = token.match(/^(\S+(?:\s\S+)?)\s+(\S.*)$/);
    if (spaced) return {name: spaced[1], value: spaced[2], ref: ""};
    return {name: token, value: "", ref: ""};
  });
}

function labTableHtml(text) {
  const rows = parseLabBox(text);
  if (!rows.length) return "";
  const quantitative = (row) => /\d/.test(`${row.value} ${row.ref}`) || /(mg|g\/dL|dL|mL|mmol|mEq|IU|U\/L|%|mmHg|×10|x10|\/mm|μ|㎍|㎕|㎗)/i.test(row.value);
  const structured = rows.length >= 2
    && rows.filter((row) => row.value).length >= Math.ceil(rows.length / 2)
    && rows.filter(quantitative).length >= Math.ceil(rows.length / 2);
  if (!structured) return `<div class="lab-raw">${esc(text)}</div>`;
  return `<div class="lab-table"><div class="h"><span>검사항목</span><span>수치</span><span>참고치</span></div>${rows.map((row) => `<div class="r"><span>${esc(row.name)}</span><span class="v">${esc(row.value)}</span><span class="ref">${esc(row.ref)}</span></div>`).join("")}</div>`;
}

function chip(label, cls = "") { return `<span class="chip ${cls}">${esc(label)}</span>`; }
function entailChip(value) {
  const found = ENTAIL[String(value || "")] || ["미판정", ""];
  return chip(found[0], found[1]);
}
function scoreColor(v) { return v >= 4 ? "var(--green)" : v === 3 ? "var(--amber)" : "var(--coral)"; }
function ratingsRange(review) {
  const all = (review?.ratings || []).flat().filter((n) => Number.isFinite(n));
  return all.length ? Math.max(...all) - Math.min(...all) : 0;
}
function bookTitle(bookId) {
  const books = state.item?.available_books || [];
  return books.find((b) => b.book_id === bookId)?.title || bookId;
}
function isTyping(event) {
  const tag = (event.target?.tagName || "").toLowerCase();
  return tag === "textarea" || tag === "input" || tag === "select" || event.target?.isContentEditable;
}

/* ── 상단: 탭 · 진행률 ───────────────────────────────────────────── */
function renderTabs() {
  const pending = state.signups.counts?.pending ?? 0;
  const tabs = [["adj", "문항 확정"], ["signup", "가입 승인"], ["report", "세트 품질 리포트"]];
  tabsRoot.innerHTML = tabs.map(([id, label]) => `<button type="button" data-tab="${id}" class="${state.tab === id ? "active" : ""}">${label}${id === "signup" ? ` <span class="count ${pending ? "" : "zero"}">${pending}</span>` : ""}</button>`).join("");
  tabsRoot.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  const total = state.summary?.total ?? state.queue.counts?.all ?? 0;
  const decided = state.summary ? Object.values(state.summary.decided || {}).reduce((a, b) => a + b, 0) : (state.queue.counts?.decided ?? 0);
  progressRoot.innerHTML = `<div class="row"><span>확정 진행</span><b>${decided} / ${total}</b></div><div class="bar"><i style="width:${total ? (decided / total) * 100 : 0}%"></i></div>`;
}

function switchTab(tab) {
  state.tab = tab;
  state.editing = null;
  renderTabs();
  render();
  if (tab === "signup") loadSignups(state.signups.status);
  if (tab === "report") loadSummary();
}

/* ── F1 데이터 로딩 ──────────────────────────────────────────────── */
async function loadQueue(filter = state.filter, {keepSelection = true} = {}) {
  state.queueLoading = true;
  render();
  try {
    state.queue = await API.queue(filter);
    state.filter = filter;
    const ids = state.queue.items.map((entry) => entry.qid);
    if (!keepSelection || !ids.includes(state.qid)) state.qid = ids[0] || null;
  } catch (error) {
    toast(error.message, "error");
    state.queue = {items: [], counts: state.queue.counts || {}};
  }
  state.queueLoading = false;
  renderTabs();
  render();
  if (state.qid && (!state.item || state.item.qid !== state.qid)) loadItem(state.qid);
}

async function loadItem(qid) {
  state.itemLoading = true;
  state.itemError = "";
  state.item = null;
  state.editing = null;
  state.saved = "";
  state.gateWarn = null;
  state.showHistory = false;
  closeSourceDrawer();
  render();
  try {
    const item = await API.item(qid);
    if (state.qid !== qid) return;
    state.item = item;
    state.bookForm = {book_id: (item.recommended_book_ids || [])[0] || (item.available_books || [])[0]?.book_id || "", chapter: "", page: ""};
  } catch (error) {
    state.itemError = error.message;
  }
  state.itemLoading = false;
  render();
}

async function loadSummary() {
  try {
    state.summary = await API.summary();
  } catch (error) {
    toast(error.message, "error");
  }
  renderTabs();
  if (state.tab === "report") render();
}

async function loadSignups(status = "pending") {
  state.signups.loading = true;
  state.signups.status = status;
  render();
  try {
    const payload = await API.signups(status);
    state.signups.items = payload.items || [];
    state.signups.counts = payload.counts || state.signups.counts;
    // 처리된 신청은 선택에서 제거
    const pendingIds = new Set(state.signups.items.filter((row) => row.status === "pending").map((row) => row.request_id));
    state.sel = new Set([...state.sel].filter((id) => pendingIds.has(id)));
  } catch (error) {
    toast(error.message, "error");
  }
  state.signups.loading = false;
  renderTabs();
  render();
}

/* ── F1 렌더 ─────────────────────────────────────────────────────── */
function selectQid(qid) {
  if (state.qid === qid) return;
  state.qid = qid;
  loadItem(qid);
}

function move(delta) {
  const ids = state.queue.items.map((entry) => entry.qid);
  const index = ids.indexOf(state.qid);
  if (index < 0) return;
  const next = ids[Math.min(ids.length - 1, Math.max(0, index + delta))];
  if (next && next !== state.qid) selectQid(next);
}

function queueItemHtml(entry) {
  const review = entry.review || null;
  const range = ratingsRange(review);
  const flags = [];
  if (entry.answer_changed) flags.push(chip("정답변경", "solid-coral"));
  if (review?.disagreement) flags.push(chip(`불일치 범위 ${review.score_range ?? range}`, "amber"));
  if (entry.professor_review_required) flags.push(chip("검토 필요", "amber"));
  if ((entry.hard_rule_failures || []).length) flags.push(chip(`하드룰 ${entry.hard_rule_failures.length}`, "coral"));
  if (entry.faculty_edited) flags.push(chip("교수 수정본", "solid-deep"));
  if (entry.faculty_decision) flags.push(chip(DECISION_LABEL[entry.faculty_decision.decision] || entry.faculty_decision.decision, entry.faculty_decision.decision === "discard" ? "coral" : "green"));
  const action = review?.action || "미검토";
  return `<button type="button" class="adj-queue-item ${entry.qid === state.qid ? "active" : ""} ${entry.faculty_decision ? "decided" : ""}" data-qid="${esc(entry.qid)}">
    <div class="head"><span class="qid">${esc(entry.qid)}</span>${chip(action, ACTION_CLASS[action] || "")}</div>
    <div class="subject">${esc(entry.subject || "")}<span>· ${esc(entry.axis || "")}</span></div>
    <div class="preview">${esc(entry.stem_preview || "")}</div>
    <div class="flags">${flags.join("")}</div>
  </button>`;
}

function editorHtml(kind, extra = "") {
  const value = state.editing?.value ?? "";
  const rows = kind === "choice" ? 2 : 5;
  return `<div class="editor"><textarea data-editor rows="${rows}">${esc(value)}</textarea><div class="row"><button type="button" class="btn" data-commit-edit>저장</button><button type="button" class="btn ghost" data-cancel-edit>취소 (Esc)</button>${extra}</div></div>`;
}

function itemPanelHtml(item) {
  const failures = item.hard_rule_failures || [];
  const quality = item.item_quality || {};
  const hardRule = failures.length
    ? chip(`하드룰 실패 ${failures.length}`, "amber")
    : chip(quality.hard_rule_total ? `하드룰 ${quality.hard_rule_passed ?? quality.hard_rule_total}/${quality.hard_rule_total}` : "하드룰 통과", "green");
  const decided = item.faculty_decision ? chip(item.faculty_decision.decision === "approve" ? "승인됨 · medical_approval" : DECISION_LABEL[item.faculty_decision.decision], item.faculty_decision.decision === "discard" ? "coral" : "green") : "";
  const editing = state.editing;
  const choices = Object.keys(item.choices || {}).sort().map((n) => {
    const isAnswer = String(item.answer) === n;
    const expl = item.choice_explanations?.[n] || {};
    const explText = expl.why_correct || expl.why_attractive || "";
    const isEditing = editing?.kind === "choice" && editing.n === n;
    return `<div class="choice-row ${isAnswer ? "answer" : ""}"><span class="n">${esc(n)}</span>
      ${isEditing ? editorHtml("choice") : `<div class="text" data-edit-choice="${esc(n)}" title="클릭하여 편집">${esc(item.choices[n])}${explText ? `<div class="expl">${esc(explText)}</div>` : ""}</div>
      ${isAnswer ? chip("정답", "solid-green") : `<button type="button" class="set-answer" data-set-answer="${esc(n)}">정답으로</button>`}`}
    </div>`;
  }).join("");
  const edits = (item.edit_history || []).filter((edit) => edit.field !== "faculty_decision");
  const historyRows = [...edits].reverse().map((edit) => `<div class="row"><div class="meta"><span class="mono">${esc(stamp(edit.at))}</span><span>${esc(edit.editor)}</span><span class="field">${esc(edit.field)}</span></div><div class="before">${esc(typeof edit.before === "string" ? edit.before : JSON.stringify(edit.before ?? ""))}</div><div class="after">${esc(typeof edit.after === "string" ? edit.after : JSON.stringify(edit.after ?? ""))}</div></div>`).join("");
  const imageHtml = item.image ? `<div class="item-image"><a class="thumb" href="${esc(MEDIA_BASE + encodeURIComponent(item.image))}" target="_blank" rel="noopener" title="새 탭에서 원본 보기"><img src="${esc(MEDIA_BASE + encodeURIComponent(item.image))}" alt="${esc(item.modality || "제시자료")}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{textContent:'${esc(item.modality || "이미지")} · 파일 미배포'}))"></a><div class="meta"><span>modality: <span class="mono">${esc(item.modality || "-")}</span></span><span>파일: <span class="mono">${esc(item.image)}</span> <span style="color:var(--soft)">(교수 화면 전용)</span></span></div></div>` : "";
  return `<section class="adj-panel">
    <div class="adj-meta"><span class="id">${esc(item.qid)} · 세트 ${esc(item.set)} · ${esc(item.subject || "")} · ${esc(item.axis || "")}${item.cognitive_level ? ` · ${esc(item.cognitive_level)}` : ""}${item.difficulty_tier ? ` · 난이도 ${esc(item.difficulty_tier)}` : ""}</span>${hardRule}${item.faculty_edited ? chip("교수 수정본", "solid-deep") : ""}${decided}<span class="spacer"></span>${state.saved ? `<span class="saved-pill">${esc(state.saved)}</span>` : ""}</div>
    ${state.gateWarn ? `<div class="gate-warn"><b>⚠ 저장됨 — 하드룰 재검사 실패 ${state.gateWarn.length}건 (저장은 유지)</b><code>${esc(state.gateWarn.join(" · "))}</code><span>확정 전에 문두·선지를 다시 확인하세요. 통과 규칙만 남기면 이 경고는 사라집니다.</span></div>` : ""}
    ${item.professor_note ? `<div class="banner note">검수 메모 · ${esc(item.professor_note)}</div>` : ""}
    <span class="section-label">STEM · 클릭하여 편집</span>
    ${editing?.kind === "stem" ? editorHtml("stem") : `<p class="editable" data-edit-stem title="클릭하여 편집">${esc(item.stem || "")}</p>`}
    ${item.lab_box ? labTableHtml(item.lab_box) : ""}
    ${imageHtml}
    <span class="section-label">CHOICES · 텍스트 클릭 편집 · 정답 재지정 가능</span>
    <div class="choices">${choices}</div>
    <span class="section-label">EXPLANATION · 클릭하여 편집</span>
    ${editing?.kind === "explanation" ? editorHtml("explanation") : `<p class="editable explanation" data-edit-explanation title="클릭하여 편집">${esc(item.explanation || "")}</p>`}
    ${edits.length ? `<div class="history"><button type="button" data-toggle-history><span>수정 이력<span class="n">${edits.length}건</span></span><span style="color:var(--soft)">${state.showHistory ? "⌃" : "⌵"}</span></button>${state.showHistory ? `<div class="rows">${historyRows}</div>` : ""}</div>` : ""}
  </section>`;
}

function evidencePanelHtml(item) {
  const sources = item.badge?.sources || [];
  const textbookSources = item.textbook_sources || [];
  const locators = sources.map((src) => {
    const isHarrison = src.book_id === "harrison_22e";
    const status = isHarrison ? entailChip(src.entailment_status) : chip("과별 교과서", "teal");
    const removable = !isHarrison && textbookSources.some((t) => t.book_id === src.book_id);
    const canOpen = isHarrison ? src.page != null : (src.page != null || src.chapter != null);   // 과별 교과서는 장만 있어도 열기(로컬 쪽 텍스트가 있을 때만 실제 표시)
    return `<div class="locator"><div class="head"><b>${esc(bookTitle(src.book_id) || src.locator)}</b>${status}</div><span class="loc">${esc(src.locator)}</span><div class="locator-actions">${canOpen ? `<button type="button" class="btn outline src-open" data-open-book="${esc(src.book_id)}" data-open-source="${esc(src.chapter ?? "")}" data-open-page="${esc(src.page)}">원문 보기</button>` : ""}${removable ? `<button type="button" class="remove" data-remove-source="${esc(src.book_id)}">이 근거 제거</button>` : ""}</div></div>`;
  }).join("");
  const books = item.available_books || [];
  const recommended = new Set(item.recommended_book_ids || []);
  const options = [...books].sort((a, b) => Number(recommended.has(b.book_id)) - Number(recommended.has(a.book_id)))
    .map((book) => `<option value="${esc(book.book_id)}" ${state.bookForm.book_id === book.book_id ? "selected" : ""}>${esc(book.title)}${recommended.has(book.book_id) ? " · 권장" : ""}</option>`).join("");
  const unsupported = item.entailment_unsupported_points || [];
  return `<section class="adj-panel side">
    <div class="panel-head"><span class="section-label">EVIDENCE · 항상 펼침</span>${entailChip(item.entailment_verdict)}</div>
    <div class="locators">${locators || `<span style="font-size:12.5px;color:var(--soft)">연결된 근거 포인터가 없습니다.</span>`}</div>
    <div class="book-form">
      <label>과별 교과서 근거 추가·변경 (변경 시 이력 기록)</label>
      <select data-book-select>${options}</select>
      <div class="row"><input data-book-chapter type="text" inputmode="numeric" placeholder="장(chapter) · 필수" value="${esc(state.bookForm.chapter)}"><input data-book-page type="text" inputmode="numeric" placeholder="쪽(page) · 선택" value="${esc(state.bookForm.page)}"></div>
      <div class="row"><button type="button" class="btn" data-save-book>근거 저장</button><span class="hint">서버는 장 번호를 요구합니다. 같은 책이 이미 있으면 그 항목을 대체합니다.</span></div>
    </div>
    ${item.evidence ? `<div class="evidence-summary"><b>근거 요약</b><br>${esc(item.evidence)}</div>` : ""}
    <div class="unsupported"><span class="title">확인 필요 포인트<span class="n">${unsupported.length}</span></span>${unsupported.length ? unsupported.map((point) => `<div class="point">△ ${esc(point)}</div>`).join("") : `<span class="none">미확인 지점 없음</span>`}</div>
  </section>`;
}

function reviewPanelHtml(item) {
  const review = item.review;
  const action = review?.action || "미검토";
  const answerChanged = item.answer_changed;
  const answerNote = (item.edit_history || []).some((edit) => edit.field === "answer")
    ? "교수 편집으로 정답이 바뀜. 해설·선지 해설 재검토 필요"
    : "v2 개정에서 정답이 변경됨. 해설과 일치하는지 확인";
  let reviewers = "";
  if (review) {
    const commentsByWho = new Map((review.comments || []).map((comment) => [comment.who, comment]));
    reviewers = (review.ratings || []).map((scores, index) => {
      const who = (review.reviewers || [])[index];
      const verdict = (review.verdicts || [])[index] || "";
      const comment = commentsByWho.get(who);
      return `<div class="reviewer"><div class="head"><b>검토자 ${REVIEWER_NAMES[index] || index + 1}</b>${verdict ? chip(verdict, VERDICT_CLASS[verdict] || "") : ""}</div>
        <div class="scores">${scores.map((value, i) => `<div class="score"><span>${esc(SCORE_LABELS[i] || `항목${i + 1}`)}</span><div class="bar"><i style="width:${(value / 5) * 100}%;background:${scoreColor(value)}"></i></div><span class="v">${esc(value)}</span></div>`).join("")}</div>
        ${comment?.note ? `<p>"${esc(comment.note)}"</p>` : `<p style="color:var(--soft)">의견 없음</p>`}
        ${comment?.themes?.length ? `<div class="themes">${comment.themes.map((theme) => chip(theme, theme === comment.primary_theme ? "teal" : "")).join("")}</div>` : ""}
      </div>`;
    }).join("");
  }
  const v2 = item.v2_revision;
  return `<section class="adj-panel side">
    <div class="panel-head"><span class="section-label">STUDENT REVIEW · ${review ? `${review.reviewer_count}인` : "미검토"}</span>${chip(`조치: ${action}`, ACTION_CLASS[action] || "")}</div>
    ${answerChanged ? `<div class="banner answer-changed">⚠ 정답 변경 — ${esc(answerNote)}</div>` : ""}
    ${review?.disagreement ? `<div class="banner disagree">검토자 불일치 · 점수범위 ${esc(review.score_range)} · 최저점 ${esc(review.score_worst)}</div>` : ""}
    ${reviewers || `<span style="font-size:12.5px;color:var(--soft)">이 문항에는 졸업반 검토 기록이 없습니다.</span>`}
    ${v2?.log?.length ? `<div class="v2log"><span class="title">v2 수정 로그${v2.date ? ` · ${esc(v2.date)}` : ""}${v2.fields?.length ? ` · ${esc(v2.fields.join("·"))}` : ""}</span>${v2.log.map((line) => `<span class="line">· ${esc(line)}</span>`).join("")}</div>` : ""}
  </section>`;
}

function actionBarHtml(item) {
  const decided = item.faculty_decision;
  return `<div class="adj-actionbar">
    <div class="policy-note"><b>승인</b> = medical_approval 기록 → 학생 화면에 '교수 승인' 배지가 <b>즉시</b> 켜집니다(스튜디오 검토·승인과 다름) · 편집한 문두·정답·해설도 학생 채점에 바로 반영 · <b>폐기</b>는 학생 큐에서 제외 · 수정 지시/폐기로 되돌릴 수 있음 · 메모창 Cmd/Ctrl+Enter = 승인</div>
    <input data-memo value="${esc(state.memo)}" placeholder="결정 메모 (선택) — 수정 지시 시 무엇을 왜 바꿀지">
    <button type="button" class="btn ghost" data-quote-comments ${item.review?.comments?.length ? "" : "disabled"}>검토 의견 인용</button>
    ${decided ? `<span class="decided-note">${esc(DECISION_LABEL[decided.decision] || decided.decision)} · ${esc(stamp(decided.at))}${decided.note ? ` · "${esc(decided.note)}"` : ""} — 다시 결정하면 덮어씁니다</span>` : ""}
    <button type="button" class="btn outline danger" data-decide="discard">폐기<span class="key">D</span></button>
    <button type="button" class="btn outline" data-decide="revise">수정 지시<span class="key">R</span></button>
    <button type="button" class="btn primary-lg" data-decide="approve">승인<span class="key">A</span></button>
  </div>`;
}

function renderAdj() {
  const counts = state.queue.counts || {};
  const filters = FILTERS.map(([id, label]) => `<button type="button" data-filter="${id}" class="${state.filter === id ? "active" : ""}">${label}<span class="n">${counts[id] ?? "–"}</span></button>`).join("");
  let body;
  if (state.itemLoading || (state.queueLoading && !state.item)) {
    body = `<div class="frc-center"><span class="frc-spinner"></span>문항을 불러오는 중…<span class="hint">GET /api/faculty/adjudication/items/${esc(state.qid || "{qid}")}</span></div>`;
  } else if (state.itemError) {
    body = `<div class="frc-center"><div class="frc-error"><b>문항을 불러올 수 없습니다</b><span>원인: ${esc(state.itemError)} · 세션은 유지됩니다.</span><button type="button" class="btn outline" data-retry-item>다시 시도</button></div></div>`;
  } else if (!state.item) {
    body = `<div class="frc-center"><div class="frc-empty-mark">✓</div><b>이 필터에 남은 문항이 없습니다</b><span>다른 필터를 선택하거나 전체 큐로 돌아가세요.</span></div>`;
  } else {
    body = `<div class="adj-body"><div class="adj-grid">${itemPanelHtml(state.item)}${evidencePanelHtml(state.item)}${reviewPanelHtml(state.item)}</div>${actionBarHtml(state.item)}</div>`;
  }
  app.innerHTML = `<div class="adj-layout">
    <aside class="adj-aside">
      <div class="adj-filters">${filters}</div>
      <div class="adj-queue-head" title="대상: AI 생성 세트 1~4(320문항). 스튜디오에서 만든 문항은 스튜디오 '검토·승인' 화면에서 승인합니다."><span>AI 생성 세트 1~4 · 정답변경 → 폐기 → 수정필요 → 불일치</span><span class="mono">${state.queue.items.length}건</span></div>
      <div class="adj-queue">${state.queueLoading ? `<div class="frc-center" style="padding:20px"><span class="frc-spinner"></span></div>` : state.queue.items.map(queueItemHtml).join("") || `<div class="frc-center" style="padding:20px;font-size:12.5px">비어 있음</div>`}</div>
    </aside>
    ${body}
  </div>`;
  bindAdj();
}

function bindAdj() {
  app.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => loadQueue(button.dataset.filter, {keepSelection: false})));
  app.querySelectorAll("[data-qid]").forEach((button) => button.addEventListener("click", () => selectQid(button.dataset.qid)));
  app.querySelector("[data-retry-item]")?.addEventListener("click", () => loadItem(state.qid));
  const item = state.item;
  if (!item) return;
  app.querySelector("[data-edit-stem]")?.addEventListener("click", () => startEdit({kind: "stem", value: item.stem || ""}));
  app.querySelector("[data-edit-explanation]")?.addEventListener("click", () => startEdit({kind: "explanation", value: item.explanation || ""}));
  app.querySelectorAll("[data-edit-choice]").forEach((el) => el.addEventListener("click", () => startEdit({kind: "choice", n: el.dataset.editChoice, value: item.choices[el.dataset.editChoice] || ""})));
  app.querySelectorAll("[data-set-answer]").forEach((button) => button.addEventListener("click", () => saveChanges({answer: button.dataset.setAnswer}, `정답 ${button.dataset.setAnswer}번으로 변경 저장됨 ✓`)));
  const textarea = app.querySelector("[data-editor]");
  if (textarea) {
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    textarea.addEventListener("input", (event) => { state.editing.value = event.target.value; });
    textarea.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); commitEdit(); }
    });
  }
  app.querySelector("[data-commit-edit]")?.addEventListener("click", commitEdit);
  app.querySelector("[data-cancel-edit]")?.addEventListener("click", cancelEdit);
  app.querySelector("[data-toggle-history]")?.addEventListener("click", () => { state.showHistory = !state.showHistory; render(); });
  app.querySelector("[data-book-select]")?.addEventListener("change", (event) => {
    state.bookForm.book_id = event.target.value;
    const existing = (item.textbook_sources || []).find((src) => src.book_id === event.target.value);
    state.bookForm.chapter = existing?.chapter != null ? String(existing.chapter) : "";
    state.bookForm.page = existing?.page != null ? String(existing.page) : "";
    render();
  });
  app.querySelector("[data-book-chapter]")?.addEventListener("input", (event) => { state.bookForm.chapter = event.target.value; });
  app.querySelector("[data-book-page]")?.addEventListener("input", (event) => { state.bookForm.page = event.target.value; });
  app.querySelector("[data-save-book]")?.addEventListener("click", saveBookSource);
  app.querySelectorAll("[data-open-source]").forEach((button) => button.addEventListener("click", () => openSourceDrawer(Number(button.dataset.openSource), Number(button.dataset.openPage), button.dataset.openBook)));
  app.querySelectorAll("[data-remove-source]").forEach((button) => button.addEventListener("click", () => {
    const remaining = (item.textbook_sources || []).filter((src) => src.book_id !== button.dataset.removeSource).map(cleanSource);
    saveChanges({textbook_sources: remaining}, "근거 제거 저장됨 ✓");
  }));
  const memo = app.querySelector("[data-memo]");
  memo?.addEventListener("input", (event) => { state.memo = event.target.value; });
  memo?.addEventListener("keydown", (event) => {
    // 일반 Enter 는 아무것도 하지 않는다(메모 작성 중 실수로 승인되는 사고 방지). 편집기와 같은 규약: Cmd/Ctrl+Enter = 승인.
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); decide("approve"); }
    else if (event.key === "Enter") { event.preventDefault(); }
  });
  app.querySelector("[data-quote-comments]")?.addEventListener("click", () => {
    const quoted = (item.review?.comments || []).filter((comment) => comment.note).map((comment, index) => `[검토자 ${REVIEWER_NAMES[(item.review.reviewers || []).indexOf(comment.who)] || index + 1}] ${comment.note}`).join(" / ");
    state.memo = (state.memo ? `${state.memo} ` : "") + quoted;
    render();
  });
  app.querySelectorAll("[data-decide]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decide)));
}

function startEdit(editing) {
  state.editing = editing;
  state.saved = "";
  render();
}

function cancelEdit() {
  state.editing = null;
  render();
}

function cleanSource(src) {
  const row = {book_id: src.book_id, chapter: src.chapter};
  if (src.page != null && src.page !== "") row.page = src.page;
  return row;
}

async function commitEdit() {
  const editing = state.editing;
  const item = state.item;
  if (!editing || !item) return;
  const value = String(editing.value ?? "").trim();
  if (!value) return toast("빈 값은 저장할 수 없습니다.", "warn");
  let changes;
  let label;
  if (editing.kind === "stem") { changes = {stem: value}; label = "문두 저장됨 ✓"; }
  else if (editing.kind === "explanation") { changes = {explanation: value}; label = "해설 저장됨 ✓"; }
  else { changes = {choices: {...item.choices, [editing.n]: value}}; label = `선지 ${editing.n} 저장됨 ✓`; }
  await saveChanges(changes, label);
}

async function saveBookSource() {
  const item = state.item;
  const form = state.bookForm;
  if (!item) return;
  if (!form.book_id) return toast("교과서를 선택하세요.", "warn");
  const chapter = String(form.chapter || "").trim();
  if (!chapter) return toast("장(chapter) 번호가 필요합니다 — 서버가 근거 위치 없이 책만 바꾸는 것을 허용하지 않습니다.", "warn");
  const row = {book_id: form.book_id, chapter: /^\d+$/.test(chapter) ? Number(chapter) : chapter};
  const page = String(form.page || "").trim();
  if (page) row.page = /^\d+$/.test(page) ? Number(page) : page;
  const others = (item.textbook_sources || []).filter((src) => src.book_id !== form.book_id).map(cleanSource);
  await saveChanges({textbook_sources: [...others, row]}, `근거 교과서 저장됨 ✓ · ${bookTitle(form.book_id)} Ch.${chapter}`);
}

async function saveChanges(changes, label) {
  const item = state.item;
  if (!item) return;
  try {
    const result = await API.update(item.qid, changes);
    state.editing = null;
    if (result.saved) {
      state.item = result.item || {...item, ...changes};
      state.saved = `${label} · PUT items/${item.qid}`;
      const failed = result.gate?.failed_rules || [];
      state.gateWarn = failed.length ? failed : null;
      if (failed.length) toast(`저장됨 — 하드룰 재검사 실패 ${failed.length}건. 경고를 확인하세요.`, "warn");
      refreshQueueQuietly();
    } else {
      state.saved = "변경 없음 (이미 같은 값)";
    }
  } catch (error) {
    toast(error.message, "error");
  }
  render();
}

async function decide(decision) {
  const item = state.item;
  if (!item || state.itemLoading) return;
  if (state.editing) return toast("편집 중입니다. 먼저 저장하거나 취소하세요 (Esc).", "warn");
  if (decision === "discard" && !confirm(`${item.qid}을(를) 폐기로 기록할까요? (medical_approval=false)`)) return;
  try {
    const result = await API.decide(item.qid, decision, state.memo);
    const label = {approve: "승인", revise: "수정 지시", discard: "폐기"}[decision];
    toast(decision === "approve" ? `${item.qid} 승인 기록됨 — 학생 화면에 '교수 승인' 배지 표시` : decision === "discard" ? `${item.qid} 폐기 기록됨 — 학생 큐에서 제외` : `${item.qid} ${label} 기록됨`);
    state.memo = "";
    // 큐 상태 갱신 후 다음 미결정 문항으로 이동
    const ids = state.queue.items.map((entry) => entry.qid);
    const index = ids.indexOf(item.qid);
    const entry = state.queue.items[index];
    if (entry) {
      entry.faculty_decision = result.faculty_decision;
      entry.medical_approval = result.medical_approval;
      entry.professor_review_required = result.professor_review_required;
    }
    const nextEntry = [...state.queue.items.slice(index + 1), ...state.queue.items.slice(0, index)].find((candidate) => !candidate.faculty_decision);
    loadSummary();
    if (nextEntry) {
      state.qid = nextEntry.qid;
      loadItem(nextEntry.qid);
    } else {
      state.item = {...item, faculty_decision: result.faculty_decision, medical_approval: result.medical_approval, professor_review_required: result.professor_review_required};
      render();
    }
    refreshQueueQuietly();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function refreshQueueQuietly() {
  try {
    const payload = await API.queue(state.filter);
    if (payload.filter !== state.filter) return;
    state.queue = payload;
    if (state.tab === "adj" && !state.itemLoading) render();
    renderTabs();
  } catch (_) {}
}

/* ── F2 가입 승인 ─────────────────────────────────────────────────── */
function renderSignup() {
  const s = state.signups;
  const counts = s.counts || {};
  const total = (counts.pending || 0) + (counts.approved || 0) + (counts.rejected || 0);
  const tabs = [["pending", "대기", counts.pending || 0], ["approved", "승인", counts.approved || 0], ["rejected", "거절", counts.rejected || 0], ["all", "전체", total]]
    .map(([id, label, n]) => `<button type="button" data-signup-status="${id}" class="${s.status === id ? "active" : ""}">${label}<span class="n">${n}</span></button>`).join("");
  const pendingRows = s.items.filter((row) => row.status === "pending");
  const allChecked = pendingRows.length > 0 && pendingRows.every((row) => state.sel.has(row.request_id));
  const rows = s.items.map((row) => {
    const pending = row.status === "pending";
    const cred = state.creds.get(row.request_id);
    return `<div class="signup-entry"><div class="signup-row">
      ${pending ? `<input type="checkbox" data-sel="${esc(row.request_id)}" ${state.sel.has(row.request_id) ? "checked" : ""} aria-label="선택">` : "<span></span>"}
      <b>${esc(row.name || "")}</b>
      <span class="sid">${esc(row.student_id || "")}</span>
      <span class="email">${esc(row.email || "")}</span>
      <span class="note">${esc(row.note || "")}${row.decision_note ? ` <span style="color:var(--soft)">· 결정 메모: ${esc(row.decision_note)}</span>` : ""}</span>
      <span class="at">${esc(stamp(row.submitted_at))}${row.decided_at ? `<br><span style="color:var(--soft)">결정 ${esc(stamp(row.decided_at))}</span>` : ""}</span>
      <div class="actions">${pending
        ? `<button type="button" class="btn outline danger" data-reject="${esc(row.request_id)}">거절</button><button type="button" class="btn" data-approve="${esc(row.request_id)}">승인</button>`
        : row.status === "approved"
          ? `${chip("승인됨", "green")}<button type="button" class="btn outline" data-approve="${esc(row.request_id)}" title="초기 비밀번호를 다시 표시합니다 — 승인 상태·메모는 바뀌지 않습니다">비밀번호 다시 보기</button><button type="button" class="btn ghost" data-reject="${esc(row.request_id)}" title="승인 취소 — 즉시 로그인 차단">승인 취소</button>`
          : `${chip("거절됨", "coral")}<button type="button" class="btn ghost" data-approve="${esc(row.request_id)}" title="거절을 뒤집어 승인합니다">재승인</button>`}</div>
    </div>
    ${cred ? (cred.initial_password
      ? `<div class="cred-box"><span class="label">승인 완료 · 초기 비밀번호</span><span class="pw">${esc(cred.initial_password)}</span><span class="email">${esc(cred.login_email)}</span><span class="spacer"></span><span class="warn">화면을 떠나면 사라집니다 — 학생에게 지금 전달하세요('비밀번호 다시 보기'로 재표시 가능)</span><button type="button" class="btn outline" data-copy="${esc(row.request_id)}">${state.copied === row.request_id ? "복사됨 ✓" : "비밀번호 복사"}</button></div>`
      : `<div class="cred-box"><span class="label" style="color:var(--coral-ink)">승인은 기록됐지만 비밀번호를 발급하지 못했습니다</span><span class="email">${esc(cred.login_email)}</span><span class="spacer"></span><span class="warn">서버에 APP_ROSTER_SECRET 이 없습니다 — 이 계정은 로그인할 수 없습니다. Railway Variables 에 넣은 뒤 '비밀번호 다시 보기'를 누르세요.</span></div>`) : ""}
    </div>`;
  }).join("");
  app.innerHTML = `<div class="signup-page">
    <div class="page-head"><h1>가입 승인</h1><span class="desc">승인 시 초기 비밀번호가 1회 표시됩니다 — 학생에게 직접 전달하세요. 서버는 비밀번호를 저장하지 않습니다.</span><span class="spacer"></span><div class="seg">${tabs}</div></div>
    <div class="signup-table">
      <div class="signup-head"><input type="checkbox" data-sel-all ${allChecked ? "checked" : ""} ${pendingRows.length ? "" : "disabled"} aria-label="대기 전체 선택"><span>이름</span><span>학번</span><span>이메일</span><span>메모</span><span>신청일</span><span class="right">조치</span></div>
      ${s.loading ? `<div class="signup-empty"><span class="frc-spinner" style="display:inline-block;vertical-align:middle;margin-right:8px"></span>불러오는 중…</div>` : rows || `<div class="signup-empty">이 상태의 신청이 없습니다.</div>`}
    </div>
    <div class="signup-foot"><span>선택 <span class="n">${state.sel.size}</span>건</span><button type="button" class="btn" data-bulk-approve ${state.sel.size ? "" : "disabled"}>선택 일괄 승인</button><span class="hint">POST /api/faculty/signups/bulk-approve · 승인된 계정의 비밀번호는 각 행에 표시 · 학생 실명·학번은 이 화면에만 표시됩니다</span></div>
  </div>`;
  app.querySelectorAll("[data-signup-status]").forEach((button) => button.addEventListener("click", () => loadSignups(button.dataset.signupStatus)));
  app.querySelectorAll("[data-sel]").forEach((input) => input.addEventListener("change", () => { input.checked ? state.sel.add(input.dataset.sel) : state.sel.delete(input.dataset.sel); render(); }));
  app.querySelector("[data-sel-all]")?.addEventListener("change", (event) => { state.sel = event.target.checked ? new Set(pendingRows.map((row) => row.request_id)) : new Set(); render(); });
  app.querySelectorAll("[data-approve]").forEach((button) => button.addEventListener("click", () => approveSignup(button.dataset.approve)));
  app.querySelectorAll("[data-reject]").forEach((button) => button.addEventListener("click", () => rejectSignup(button.dataset.reject)));
  app.querySelector("[data-bulk-approve]")?.addEventListener("click", bulkApprove);
  app.querySelectorAll("[data-copy]").forEach((button) => button.addEventListener("click", async () => {
    const cred = state.creds.get(button.dataset.copy);
    if (!cred?.initial_password) return toast("발급된 비밀번호가 없습니다.", "warn");
    try { await navigator.clipboard.writeText(`${cred.login_email} / ${cred.initial_password}`); state.copied = button.dataset.copy; render(); }
    catch (_) { toast("클립보드 복사가 차단되었습니다. 직접 선택해 복사하세요.", "warn"); }
  }));
}

async function approveSignup(requestId) {
  try {
    const result = await API.approve(requestId, "");
    state.creds.set(requestId, {login_email: result.login_email, initial_password: result.initial_password});
    state.sel.delete(requestId);
    if (result.initial_password) toast(`${result.login_email} 승인 — 초기 비밀번호를 전달하세요`);
    else toast("승인은 기록됐지만 APP_ROSTER_SECRET 미설정으로 비밀번호를 발급하지 못했습니다 — 이 계정은 로그인할 수 없습니다", "error");
    // 승인 행이 계속 보이도록: 대기 탭이면 승인 탭으로 옮기지 않고 목록만 갱신(승인된 행은 '전체'에서 확인)
    await loadSignups(state.signups.status === "pending" ? "all" : state.signups.status);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function rejectSignup(requestId) {
  const row = state.signups.items.find((item) => item.request_id === requestId);
  const wasApproved = row?.status === "approved";
  const reason = prompt(wasApproved ? "승인 취소 사유(선택) — 즉시 로그인이 차단됩니다" : "거절 사유(선택)", "");
  if (reason === null) return;
  try {
    await API.reject(requestId, reason);
    state.creds.delete(requestId);
    state.sel.delete(requestId);
    toast(wasApproved ? "승인 취소됨 — 기존 세션도 즉시 차단" : "거절 기록됨");
    await loadSignups(state.signups.status);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function bulkApprove() {
  const ids = [...state.sel];
  if (!ids.length) return;
  try {
    const result = await API.bulkApprove(ids);
    (result.approved || []).forEach((row) => state.creds.set(row.request_id, {login_email: row.login_email, initial_password: row.initial_password}));
    state.sel = new Set();
    const skipped = (result.skipped || []).length;
    const missingPw = (result.approved || []).some((row) => !row.initial_password);
    if (missingPw) toast(`${(result.approved || []).length}건 승인 기록 — APP_ROSTER_SECRET 미설정으로 비밀번호를 발급하지 못했습니다(로그인 불가)`, "error");
    else toast(`${(result.approved || []).length}건 승인${skipped ? ` · ${skipped}건 건너뜀` : ""} — 각 행의 초기 비밀번호를 전달하세요`);
    await loadSignups("all");
  } catch (error) {
    toast(error.message, "error");
  }
}

/* ── F3 세트 품질 리포트 ────────────────────────────────────────────── */
function renderReport() {
  const summary = state.summary;
  if (!summary) {
    app.innerHTML = `<div class="report-page"><div class="frc-center"><span class="frc-spinner"></span>리포트를 불러오는 중…</div></div>`;
    return;
  }
  const sets = summary.sets || [];
  const scope = state.reportSet === "all" ? summary : sets.find((set) => String(set.set) === String(state.reportSet)) || summary;
  const total = scope.items ?? summary.total ?? 0;
  const tabs = [`<button type="button" data-report-set="all" class="${state.reportSet === "all" ? "active" : ""}">전체<span class="n">${summary.total}</span></button>`]
    .concat(sets.map((set) => `<button type="button" data-report-set="${set.set}" class="${String(state.reportSet) === String(set.set) ? "active" : ""}">세트 ${set.set}<span class="n">${set.items}</span></button>`)).join("");
  const metricsPayload = summary.quality_metrics || {metrics: []};
  const metrics = metricsPayload.metrics || [];
  const metricRows = metrics.map((metric) => {
    const fail = metric.pass === false;
    return `<div class="metric"><span class="name">${esc(metric.name)}</span><div class="track"><div class="fill ${fail ? "fail" : ""}" style="width:${Math.max(0, Math.min(100, metric.value))}%"></div>${metric.baseline != null ? `<div class="base" style="left:${Math.max(0, Math.min(100, metric.baseline))}%" title="기준 ${esc(metric.op)} ${esc(metric.baseline)}%"></div>` : ""}</div><div class="val"><b>${esc(metric.value.toFixed(1))}${esc(metric.unit || "%")}</b>${metric.pass == null ? "" : chip(fail ? "미달" : "통과", fail ? "coral" : "green")}</div></div>`;
  }).join("");
  const failing = metrics.filter((metric) => metric.pass === false);
  const ent = scope.entailment || {fully: 0, partially: 0, not: 0, unknown: 0};
  const entTotal = Math.max(1, ent.fully + ent.partially + ent.not + ent.unknown);
  const pct = (n) => `${(n / entTotal) * 100}%`;
  const kv = (obj) => Object.entries(obj || {}).map(([k, v]) => `${esc(k)} <b>${esc(v)}</b>`).join(" · ") || "-";
  const decided = scope.decided || {};
  const actions = scope.review_actions || {};
  const actionTotal = Math.max(1, Object.values(actions).reduce((a, b) => a + b, 0));
  app.innerHTML = `<div class="report-page">
    <div class="page-head"><h1>세트 품질 리포트</h1><div class="seg">${tabs}</div>${state.reportSet !== "all" ? chip("7지표는 전체(320) 실측만 — 분포·진행은 이 세트 기준", "amber") : ""}</div>
    <div class="report-grid">
      <section class="card">
        <div class="head"><h2>자동 기술검증 7지표</h2><small>실측(${esc(summary.total)}) vs 기준선${metricsPayload.measured_at ? ` · ${esc(metricsPayload.measured_at)}` : ""}${metricsPayload.source ? ` · ${esc(metricsPayload.source)}` : ""}</small></div>
        ${metricRows || `<div class="metric-note">7지표 파일(review/quality_metrics.json)이 없어 표시할 값이 없습니다.</div>`}
        ${failing.map((metric) => `<div class="metric-note fail">${esc(metric.name)} ${esc(metric.value.toFixed(1))}% — 기준 ${esc(metric.op)} ${esc(metric.baseline)}% 미달. ${esc(metric.note || "")}</div>`).join("")}
        ${metrics.filter((metric) => metric.pass !== false && metric.note).map((metric) => `<div class="metric-note"><b>${esc(metric.name)}</b> · ${esc(metric.note)}</div>`).join("")}
      </section>
      <div class="report-col">
        <section class="card">
          <h2>교과서 근거 검증 (entailment)</h2>
          <div class="stack"><i class="c-green" style="width:${pct(ent.fully)}"></i><i class="c-amber" style="width:${pct(ent.partially)}"></i><i class="c-coral" style="width:${pct(ent.not)}"></i><i class="c-gray" style="width:${pct(ent.unknown)}"></i></div>
          <div class="legend"><span><i class="c-green"></i>fully <b>${esc(ent.fully)}</b></span><span><i class="c-amber"></i>partially <b>${esc(ent.partially)}</b></span><span><i class="c-coral"></i>not <b>${esc(ent.not)}</b></span><span><i class="c-gray"></i>미판정 <b>${esc(ent.unknown)}</b></span></div>
          <div class="tiles">
            <div class="tile"><div class="t">축 분포</div>${kv(scope.axis)}</div>
            <div class="tile"><div class="t">인지수준</div>${kv(scope.cognitive_level)}</div>
            <div class="tile"><div class="t">lab_box 보유</div><b>${esc(scope.lab_box ?? 0)}</b> / ${esc(total)}</div>
            <div class="tile"><div class="t">이미지 보유</div><b>${esc(scope.image ?? 0)}</b> / ${esc(total)}</div>
            <div class="tile"><div class="t">하드룰 실패 잔여</div><b>${esc(scope.hard_rule_failures ?? 0)}</b></div>
            <div class="tile"><div class="t">정답 변경(v2·교수)</div><b>${esc(scope.answer_changed ?? 0)}</b></div>
          </div>
        </section>
        <section class="card">
          <h2>졸업반 검토 조치 4등급</h2>
          <div class="stack"><i class="c-green" style="width:${((actions["그대로"] || 0) / actionTotal) * 100}%"></i><i class="c-teal" style="width:${((actions["경미"] || 0) / actionTotal) * 100}%"></i><i class="c-amber" style="width:${((actions["수정필요"] || 0) / actionTotal) * 100}%"></i><i class="c-coral" style="width:${((actions["폐기"] || 0) / actionTotal) * 100}%"></i></div>
          <div class="legend"><span><i class="c-green"></i>그대로 <b>${esc(actions["그대로"] || 0)}</b></span><span><i class="c-teal"></i>경미 <b>${esc(actions["경미"] || 0)}</b></span><span><i class="c-amber"></i>수정필요 <b>${esc(actions["수정필요"] || 0)}</b></span><span><i class="c-coral"></i>폐기 <b>${esc(actions["폐기"] || 0)}</b></span></div>
          <div class="metric-note">미검토 ${esc(scope.unreviewed ?? 0)} · 검토자 불일치(점수범위≥2) ${esc(scope.disagreement ?? 0)} · 검수 필요 표시 ${esc(scope.professor_review_required ?? 0)}</div>
        </section>
        <section class="card">
          <h2>확정 진행</h2>
          <div class="tiles four">
            <div class="tile green big"><div class="t">승인</div><b>${esc(decided.approve || 0)}</b></div>
            <div class="tile amber big"><div class="t">수정 지시</div><b>${esc(decided.revise || 0)}</b></div>
            <div class="tile coral big"><div class="t">폐기</div><b>${esc(decided.discard || 0)}</b></div>
            <div class="tile big"><div class="t">대기</div><b>${esc(scope.pending ?? 0)}</b></div>
          </div>
          <div class="metric-note">교수 수정본 ${esc(scope.faculty_edited ?? 0)} · medical_approval ${esc(scope.medical_approved ?? 0)} — 승인은 이 콘솔의 결정 API로만 기록됩니다.</div>
        </section>
      </div>
    </div>
  </div>`;
  app.querySelectorAll("[data-report-set]").forEach((button) => button.addEventListener("click", () => { state.reportSet = button.dataset.reportSet; render(); }));
}

/* ── 원문 보기 패널 (교수 전용 · 텍스트 발췌만) ─────────────────────── */
function sourceDrawerEl() {
  let el = document.querySelector("#frc-source-drawer");
  if (!el) {
    el = document.createElement("aside");
    el.id = "frc-source-drawer";
    el.className = "src-drawer";
    el.setAttribute("aria-label", "인용 원문 대조");
    document.body.appendChild(el);
  }
  return el;
}

function closeSourceDrawer() {
  state.sourceText = {...state.sourceText, open: false};
  const el = document.querySelector("#frc-source-drawer");
  if (el) { el.classList.remove("open"); el.innerHTML = ""; }
}

async function openSourceDrawer(chapter, page, bookId) {
  const item = state.item;
  if (!item) return;
  const st = state.sourceText;
  state.sourceText = {...st, open: true, loading: st.qid !== item.qid || !st.payload, error: ""};
  renderSourceDrawer();
  if (st.qid !== item.qid || !st.payload) {
    try {
      const payload = await API.sourceText(item.qid);
      if (state.item?.qid !== item.qid) return;
      state.sourceText = {...state.sourceText, qid: item.qid, payload, loading: false};
    } catch (error) {
      state.sourceText = {...state.sourceText, loading: false, error: error.message};
      renderSourceDrawer();
      return;
    }
  }
  const sources = state.sourceText.payload?.sources || [];
  const hasChapter = Number.isFinite(chapter) && chapter > 0;
  const hasPage = Number.isFinite(page) && page > 0;   // 과별 교과서는 클릭한 쪽이 비어 있음(Number("") === 0)
  const sameBook = (src) => src.available && (!bookId || src.book_id === bookId);
  const sameChapter = (src) => !hasChapter || Number(src.chapter) === chapter;
  let index = sources.findIndex((src) => sameBook(src) && sameChapter(src) && (!hasPage || Number(src.printed_page) === page));
  if (index < 0) index = sources.findIndex((src) => sameBook(src) && sameChapter(src));
  if (index < 0) index = sources.findIndex((src) => src.available);
  state.sourceText = {...state.sourceText, sourceIndex: Math.max(0, index), page: sources[index]?.book_id === "harrison_22e" ? page : null};
  renderSourceDrawer();
}

// 원문 하이라이트 — 인용 조각을 단어 단위로 풀어, 원문의 줄바꿈·하이픈 분철("Diver-\nticulitis")·공백 차이를 허용해 매칭한다.
function flexiblePattern(term) {
  const words = String(term).split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  const parts = words.map((word) => word.split("").map((ch) => ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[-\\u00ad]?\\s*"));
  return new RegExp(parts.join("[\\s\\-]+"), "gi");
}

// 인용문 조각별 원문 대조 — 서버(quote_fragments)와 같은 규칙으로 생략 부호(…/...)에서 잘라, 각 조각이 어느 쪽에 있는지 찾는다.
const QUOTE_ELLIPSIS = /\s*(?:…|\.{3,})\s*/;
const MIN_FRAGMENT_CHARS = 12;
function quoteFragments(quote) {
  return String(quote || "").split(QUOTE_ELLIPSIS).map((p) => p.replace(/^[\s,;:]+|[\s,;:]+$/g, "")).filter((p) => p.length >= MIN_FRAGMENT_CHARS);
}
function quoteMatches(quote, pages) {
  const fragments = quoteFragments(quote);
  const found = new Set();
  let missing = 0;
  for (const fragment of fragments) {
    const pattern = flexiblePattern(fragment);
    const hits = pages.filter((p) => pattern && new RegExp(pattern.source, "i").test(p.text || ""));
    if (hits.length) hits.forEach((p) => found.add(pageKey(p)));
    else missing += 1;
  }
  return {fragments: fragments.length, pages: [...found].sort((a, b) => a - b), missing};
}
function countMarks(text, terms) {
  return (terms || []).reduce((n, term) => { const pattern = flexiblePattern(term); return n + (pattern ? (String(text || "").match(pattern) || []).length : 0); }, 0);
}

function highlightHtml(text, terms) {
  // 원문 텍스트에 먼저 표식(\u0001/\u0002)을 넣고 마지막에 이스케이프 → <mark>로 바꾼다(이스케이프된 문자열을 정규식으로 건드리지 않음)
  let marked = String(text || "");
  const done = [];
  for (const term of [...(terms || [])].sort((a, b) => b.length - a.length)) {
    if (!term || done.some((d) => d.includes(term))) continue;
    const pattern = flexiblePattern(term);
    if (!pattern) continue;
    marked = marked.replace(pattern, (m) => (m.includes("\u0001") ? m : `\u0001${m}\u0002`));
    done.push(term);
  }
  return esc(marked).replace(/\u0001/g, "<mark>").replace(/\u0002/g, "</mark>").replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>");
}

// 쪽 식별자 — Harrison은 printed_page(숫자), 과별 교과서는 pdf_page(인쇄 라벨이 없을 수 있음)
const pageKey = (p) => (p.printed_page ?? p.pdf_page);
const pageLabel = (p) => (p.printed_page != null ? `p.${p.printed_page}` : (p.printed_label ? `p.${p.printed_label}` : `PDF p.${p.pdf_page}`));
const AUTO_LOCATORS = ["chapter_term_match", "chapter_start"];
/* 장 제목 표시 정리(데이터 파일은 그대로): 실측 산출물 흔적만 — Sabiston 제목의 앞 "- "(하이픈+공백), Speroff 제목 뒤의 "?" 2개 이상 연속(실측 최소 52개).
   뒤 "?" 하나는 진짜 제목("What Is Sepsis?")이므로 남긴다. */
const cleanTitle = (t) => String(t ?? "").replace(/^-\s+/, "").replace(/\s*[?？]{2,}\s*$/, "").trim();

function renderSourceDrawer() {
  const el = sourceDrawerEl();
  const st = state.sourceText;
  if (!st.open) { el.classList.remove("open"); el.innerHTML = ""; return; }
  el.classList.add("open");
  const payload = st.payload;
  const header = (title, sub = "") => `<div class="src-head"><div><span class="section-label">SOURCE TEXT · 교수 전용 발췌</span><b>${title}</b>${sub ? `<small>${sub}</small>` : ""}</div><button type="button" class="src-close" data-src-close aria-label="닫기">✕</button></div>`;
  if (st.loading || !payload) {
    el.innerHTML = header("원문을 불러오는 중…") + (st.error ? `<div class="src-error">${esc(st.error)}</div>` : `<div class="frc-center" style="padding:30px"><span class="frc-spinner"></span></div>`);
  } else {
    const sources = payload.sources || [];
    const src = sources[st.sourceIndex];
    const available = sources.filter((s) => s.available);
    const tabs = sources.map((s, i) => `<button type="button" class="${i === st.sourceIndex ? "active" : ""}" data-src-index="${i}" ${s.available ? "" : "disabled"} title="${s.available ? "" : (s.reason === "chapter_index_only" ? "장 단위 인덱스만 있음(쪽 텍스트 없음)" : "쪽 텍스트가 인덱스에 없음")}">${esc(bookTitle(s.book_id) || s.book_id)}${s.chapter ? ` Ch.${esc(s.chapter)}` : ""}${s.printed_page ? ` p.${esc(s.printed_page)}` : ""}</button>`).join("");
    let body = "";
    if (!src || !src.available) {
      body = `<div class="src-empty">이 근거는 서버에 쪽 단위 텍스트가 없습니다${src?.reason === "chapter_index_only" ? " (과별 교과서는 장 정보만 보유)" : ""}. 아래 열람 링크로 확인하세요.</div>`;
    } else {
      const pages = src.pages || [];
      const active = pages.find((p) => pageKey(p) === st.page) || pages.find((p) => p.is_cited) || pages[0];
      const pageTabs = pages.map((p) => `<button type="button" class="${p === active ? "active" : ""} ${p.is_cited ? "cited" : ""}" data-src-page="${esc(pageKey(p))}">${esc(pageLabel(p))}${p.is_cited ? (AUTO_LOCATORS.includes(src.page_locator) ? " · 자동 선택" : " · 인용") : ""}</button>`).join("");
      body = `<div class="src-meta"><b>${esc(src.book_title || "Harrison 22e")}</b><span>Ch.${esc(src.chapter)} ${esc(cleanTitle(src.chapter_title))}</span>${src.section?.path?.length ? `<span class="src-section-path">› ${esc(src.section.path.join(" › "))}</span>` : ""}${src.page_locator === "section" ? `<span class="chip" title="인용한 절 제목(또는 절 번호)으로 그 절의 시작 쪽을 찾았습니다">절 제목으로 찾은 쪽</span>` : ""}${src.section_ambiguous ? chip("같은 제목의 절이 여러 개 — 첫 절", "amber") : ""}${src.section_not_found ? chip(src.section_not_citable ? "인용한 절은 참고문헌 항목 — 근거로 쓸 수 없음" : "인용한 절을 찾지 못함", "amber") : ""}${src.term_match_ambiguous ? chip("같은 문구가 여러 쪽에 있음 — 첫 쪽", "amber") : ""}${src.text_quality && src.text_quality.usable_for_evidence === false ? chip("본문 추출 품질 낮음 — 근거 대조 불가", "amber") : ""}${AUTO_LOCATORS.includes(src.page_locator) ? `<span class="chip" title="인용 쪽이 지정되지 않아 장 안에서 인용문·용어가 가장 많이 맞는 쪽(없으면 장 첫 쪽)을 자동으로 골랐습니다">장 안에서 자동으로 찾은 쪽</span>` : ""}${src.accessmedicine_url ? `<a class="src-chapter-link" href="${esc(src.accessmedicine_url)}" target="_blank" rel="noopener" title="AccessMedicine 장 본문(교내·VPN)">본문 ↗</a>` : ""}${src.chapter_mismatch ? chip(src.resolved_chapter != null ? `장 불일치 — 실제 Ch.${src.resolved_chapter}${src.resolved_chapter_title ? " " + cleanTitle(src.resolved_chapter_title) : ""}` : "장 번호 불일치 — 같은 쪽수의 다른 장 텍스트", "amber") : ""}${src.page_ignored ? chip("이 책은 쪽 번호 없음", "amber") : ""}${src.page_not_found ? chip("인용 쪽을 찾지 못함", "amber") : ""}${src.entailment_status ? entailChip(src.entailment_status) : ""}</div>
        <div class="src-pages">${pageTabs}</div>
        ${active?.section_path?.length ? `<div class="src-section-line mono">절 · ${esc(active.section_path.join(" › "))}</div>` : ""}
        ${payload.quotes?.length ? `<div class="src-quotes"><span class="section-label">검증 인용문 ${payload.quotes.length} · 조각별 원문 대조</span>${payload.quotes.map((q) => {
          const hit = quoteMatches(q, pages);
          const where = hit.pages.map((pg) => `<button type="button" class="quote-hit ok" data-src-page="${esc(pg)}" title="이 쪽으로 이동">p.${esc(pg)}</button>`).join("");
          const miss = hit.missing ? `<span class="quote-hit miss" title="인용문 조각 ${hit.missing}/${hit.fragments}개가 불러온 쪽(${esc(pages.map((p) => pageKey(p)).join(", "))})의 원문과 글자 그대로 일치하지 않음 — 축약·의역 여부를 확인하세요">${hit.pages.length ? "일부 " : ""}원문과 표현 상이 ${hit.missing}/${hit.fragments}</span>` : "";
          return `<span class="quote">“${esc(q)}” ${where}${miss}</span>`;
        }).join("")}</div>` : ""}
        <div class="src-text"><p>${highlightHtml(active?.text || "", payload.highlight_terms)}</p></div>
        <div class="src-foot mono">pdf p.${esc(active?.pdf_page ?? "-")} · 인쇄 p.${esc(active?.printed_page ?? active?.printed_label ?? "-")} · 하이라이트 ${payload.highlight_terms?.length || 0}개(인용문 조각+해설 수치) · 이 쪽 매칭 ${countMarks(active?.text, payload.highlight_terms)}곳</div>`;
    }
    const linkRows = payload.library_links || [];
    const links = linkRows.map((l) => `<a class="btn outline${l.verified === "partial" ? " partial" : ""}${l.kind === "accessmedicine_chapter" ? " primary-link" : ""}" href="${esc(l.url)}" target="_blank" rel="noopener" title="${esc(l.note || "")}">${esc(l.label)} ↗</a>`).join("");
    const caveat = linkRows.some((l) => l.verified === "partial") ? `<div class="src-caveat">교외 링크는 도서관 로그인 후 이 장으로 자동 이동하는지 아직 실측되지 않았습니다. 안 되면 도서관 홈 → 학술DB → AccessMedicine으로 들어가 장을 검색하세요. 교내·VPN에서는 본문 링크가 바로 열립니다.</div>` : "";
    el.innerHTML = header(`원문 대조 · ${esc(payload.qid || "")}`, `${available.length}/${sources.length} 근거에 쪽 텍스트 있음 · 학생 화면에는 노출되지 않습니다`) + `<div class="src-tabs">${tabs}</div>${body}<div class="src-links">${links}</div>${caveat}`;
  }
  el.querySelector("[data-src-close]")?.addEventListener("click", closeSourceDrawer);
  el.querySelectorAll("[data-src-index]").forEach((button) => button.addEventListener("click", () => { state.sourceText = {...state.sourceText, sourceIndex: Number(button.dataset.srcIndex), page: null}; renderSourceDrawer(); }));
  el.querySelectorAll("[data-src-page]").forEach((button) => button.addEventListener("click", () => { state.sourceText = {...state.sourceText, page: Number(button.dataset.srcPage)}; renderSourceDrawer(); }));
}

/* ── 라우팅 · 키보드 ─────────────────────────────────────────────── */
function render() {
  if (state.tab === "adj") renderAdj();
  else if (state.tab === "signup") renderSignup();
  else renderReport();
}

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.sourceText.open) { event.preventDefault(); closeSourceDrawer(); return; }
  if (event.key === "Escape" && state.editing) { event.preventDefault(); cancelEdit(); return; }
  if (isTyping(event) || state.tab !== "adj" || !state.item) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === "a") decide("approve");
  else if (key === "r") decide("revise");
  else if (key === "d") decide("discard");
  else if (event.key === "ArrowRight") move(1);
  else if (event.key === "ArrowLeft") move(-1);
});

async function logout(button) {
  if (state.editing && !confirm("편집 중인 내용이 있습니다. 저장하지 않고 로그아웃할까요?")) return;
  button.disabled = true;
  try {
    const response = await fetch("/api/auth/logout", {method: "POST"});
    if (!response.ok) throw new Error(`로그아웃 실패 (${response.status})`);
    location.replace("/login");
  } catch (error) {
    button.disabled = false;
    toast(error.message, "error");
  }
}

async function boot() {
  document.querySelector("#frc-logout")?.addEventListener("click", (event) => logout(event.currentTarget));
  renderTabs();
  render();
  loadSummary();
  API.signups("pending").then((payload) => { state.signups.counts = payload.counts || state.signups.counts; renderTabs(); }).catch(() => {});
  await loadQueue("all", {keepSelection: false});
}

boot();
