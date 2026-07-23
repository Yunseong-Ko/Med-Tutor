const root = document.querySelector("#reader");
const toastEl = document.querySelector("#toast");
const topBookmark = document.querySelector("#bookmark-top");
const params = new URLSearchParams(location.search);

const state = {
  items: [], index: 0, selected: null, eliminated: new Set(), feedback: null,
  tab: "explanation", mode: params.get("mode") === "exam" ? "exam" : "study",
  bookmarks: new Set(), startedAt: Date.now(), elapsed: 0, results: [],
  examAnswers: new Map(), saving: false, fsrsSaved: false,
};
const sessionId = `student_v3_${Date.now()}_${Math.random().toString(36).slice(2,8)}`;

function esc(value) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]); }
function toast(message) { toastEl.textContent = message; toastEl.classList.add("show"); clearTimeout(toast._timer); toast._timer = setTimeout(() => toastEl.classList.remove("show"), 2300); }
async function api(url, options = {}) { const response = await fetch(url,{...options,headers:{"content-type":"application/json",...(options.headers||{})}}); let payload={}; try{payload=await response.json();}catch(_){} if(!response.ok) throw new Error(payload.detail||"요청을 처리하지 못했습니다."); return payload; }
function current() { return state.items[state.index]; }
function formatTime(seconds) { const m=Math.floor(seconds/60), s=seconds%60; return `${m}:${String(s).padStart(2,"0")}`; }
function imageUrl(image) { return typeof image === "string" ? image : image?.src || image?.url || ""; }
function imageCaption(image) { return typeof image === "string" ? "제시자료" : image?.cap || image?.caption || "제시자료"; }

function updateTop() {
  const q=current();
  document.querySelector("#session-title").textContent=q?.exam||"문항 풀이";
  document.querySelector("#session-progress").textContent=`${state.index+1}/${state.items.length}`;
  topBookmark.classList.toggle("on", state.bookmarks.has(q?.id));
  topBookmark.textContent=state.bookmarks.has(q?.id)?"★":"☆";
}

function render() {
  if (!state.items.length) return;
  const q=current(), feedback=state.feedback;
  const feedbackVisible=state.mode==="study" && feedback;
  root.innerHTML=`
    <div class="reader-meta"><div><span class="mode-chip">${state.mode==="study"?"학습 모드":"시험 모드"}</span><span>${esc(q.course_name||q.course||q.subject)}</span><span>·</span><span>${esc(q.topic||q.major||"미분류")}</span></div><span>문항 ID · ${esc(q.id)}</span></div>
    <article class="question-card">
      <div class="question-stem">${q.stimulus?`<span class="stimulus">${esc(q.stimulus)}</span>\n\n`:""}${esc(q.stem)}</div>
      ${(q.imgs||[]).length?`<div class="question-media">${q.imgs.map((img)=>`<figure><img src="${esc(imageUrl(img))}" alt="${esc(imageCaption(img))}"><figcaption>${esc(imageCaption(img))}</figcaption></figure>`).join("")}</div>`:""}
      <div class="choices">${q.choices.map((choice)=>choiceHtml(choice,feedbackVisible?feedback:null)).join("")}</div>
    </article>
    ${state.mode==="exam"?`<div class="exam-note">시험 모드에서는 세션 종료 전까지 정답·해설·Ontology 연결을 공개하지 않습니다.</div>`:""}
    <div class="reader-actionbar"><p>${state.mode==="study"?(feedback?"아래 학습 피드백을 확인한 뒤 다음 문항으로 이동하세요.":"답안을 선택하면 서버에서 정답을 확인합니다."):"답안은 마지막 문항에서 한 번에 제출됩니다."}</p><button id="primary-action" class="button primary" ${state.selected==null||state.saving?"disabled":""}>${state.saving?"저장 중…":state.mode==="study"&&!feedback?"정답 확인":state.index===state.items.length-1?"세션 완료":"다음 문항 →"}</button></div>
    ${feedbackVisible?feedbackHtml(q,feedback):""}`;
  root.querySelectorAll(".choice").forEach((button)=>button.addEventListener("click",(event)=>{ if(event.target.closest(".eliminate")||state.feedback)return; const n=button.dataset.choice; if(state.eliminated.has(n))return; state.selected=state.selected===n?null:n; render(); }));
  root.querySelectorAll(".eliminate").forEach((button)=>button.addEventListener("click",(event)=>{event.stopPropagation(); if(state.feedback)return; const n=button.dataset.eliminate; state.eliminated.has(n)?state.eliminated.delete(n):state.eliminated.add(n); if(state.selected===n)state.selected=null; render();}));
  root.querySelector("#primary-action")?.addEventListener("click",primaryAction);
  root.querySelectorAll("[data-feedback-tab]").forEach((button)=>button.addEventListener("click",()=>{state.tab=button.dataset.feedbackTab;render();}));
  root.querySelectorAll("[data-fsrs-rating]").forEach((button)=>button.addEventListener("click",()=>saveFsrs(Number(button.dataset.fsrsRating),button)));
  updateTop();
}

function choiceHtml(choice,feedback) {
  const n=String(choice.n), selected=state.selected===n, eliminated=state.eliminated.has(n);
  let resultClass="";
  if(feedback){ if(feedback.answer_keys.includes(n))resultClass="correct"; else if(selected)resultClass="wrong"; }
  return `<button class="choice ${selected?"selected":""} ${eliminated?"eliminated":""} ${resultClass}" data-choice="${esc(n)}"><span class="choice-number">${esc(n)}</span><span class="choice-text">${esc(choice.text)}</span><span class="eliminate" data-eliminate="${esc(n)}" title="선택지 지우기">⊘</span></button>`;
}

function feedbackHtml(q,feedback) {
  const correct=feedback.is_correct;
  const tabs=[
    ["explanation","해설"],["points","출제 포인트"],["media","검사·자료"],["concept","개념 노트"],["anki","Anki"],
  ];
  return `<section class="feedback-wrap"><div class="result-banner ${correct?"correct":"wrong"}"><strong>${correct?"✓ 정답이에요":"✕ 다시 확인해볼 문항이에요"}</strong><span>· 내 선택 ${esc(feedback.selected_choices.join(", "))} · 정답 ${esc(feedback.answer_keys.join(", "))}</span></div>
    <div class="feedback-panel"><div class="feedback-tabs">${tabs.map(([id,label])=>`<button class="${state.tab===id?"active":""}" data-feedback-tab="${id}">${label}</button>`).join("")}</div><div class="feedback-body">${feedbackBody(q,feedback)}</div></div>
    <div class="fsrs-card"><div><strong>이 문항을 얼마나 기억했나요?</strong><p>응답에 따라 FSRS-6가 다음 복습 시점을 계산합니다.</p></div><div class="rating-buttons">${[[1,"Again"],[2,"Hard"],[3,"Good"],[4,"Easy"]].map(([value,label])=>`<button data-fsrs-rating="${value}" ${state.fsrsSaved?"disabled":""}>${label}</button>`).join("")}</div></div>
  </section>`;
}

function feedbackBody(q,feedback) {
  if(state.tab==="explanation") {
    const evidence=(feedback.evidence||[]);
    return `<h3>문항 해설</h3><p>${esc(feedback.explanation||"등록된 해설이 없습니다.")}</p><div class="choice-explanations">${q.choices.map((choice)=>`<div class="choice-expl"><b>${esc(choice.n)}</b><span>${esc(feedback.choice_explanations?.[String(choice.n)]||"선택지별 해설이 없습니다.")}</span></div>`).join("")}</div>
      <h3 class="feedback-subtitle">근거·출처</h3>${evidence.length?`<div class="evidence-list">${evidence.map((item)=>`<article class="evidence-item"><span>${esc(item.source_id||"근거")}</span><div><strong>${esc(item.locator||item.title||"학습 근거")}</strong><small>${esc(item.support_scope==="chapter_pointer_not_claim_entailment"?"Harrison 위치 안내 · 문장 단위 인용 검증 전":item.source_type==="answer_key_aligned_learning_explanation"?"정답키와 대조된 학습 해설":"공개 가능한 근거 위치")}</small></div></article>`).join("")}</div>`:`<div class="context-state">연결된 공개 근거 위치가 없습니다.</div>`}
      ${feedback.enrichment_release?.release_mode==="owner_curated_demo"?`<div class="demo-review-note">시연용 검수 콘텐츠입니다. 실제 교수 의학 검수는 별도로 진행됩니다.</div>`:""}`;
  }
  if(state.tab==="points") return `<h3>출제 포인트</h3>${(feedback.points||[]).length?`<ul>${feedback.points.map((point)=>`<li>${esc(point)}</li>`).join("")}</ul>`:`<div class="context-state">등록된 출제 포인트가 없습니다.</div>`}`;
  if(state.tab==="media") { const media=(feedback.connected_media||q.imgs||[]); return `<h3>검사·자료</h3>${media.length?`<div class="question-media" style="padding:0">${media.map((img)=>`<figure><img src="${esc(imageUrl(img))}" alt="${esc(imageCaption(img))}"><figcaption>${esc(imageCaption(img))}</figcaption></figure>`).join("")}</div>`:feedback.media_requirement_satisfied_by_text?`<div class="context-state ready">필요한 영상 소견이 문제 본문에 문장으로 제시되어 있습니다.</div>`:`<div class="context-state">이 문항에는 연결된 검사·이미지 자료가 없습니다.</div>`}`; }
  if(state.tab==="concept") {
    const c=feedback.learning_context?.concept_note||{}, hasRoute=Boolean(feedback.concept_id);
    return `<h3>개념 노트</h3>${hasRoute?`<div class="ontology-route"><span>Concept</span><strong>${esc(feedback.concept_label||feedback.concept_id)}</strong><small>${esc(feedback.concept_id)}</small></div><div class="ontology-route"><span>10-Axis</span><strong>${esc(feedback.target_axis_label||feedback.target_axis_type||"미분류")}</strong><small>${esc(feedback.target_axis_resolution||"type_level")}</small></div>`:""}<div class="context-state ${c.status==="ready"?"ready":""}">${esc(c.message||c.title||(hasRoute?"Ontology 연결은 완료되었고 상세 개념 노트는 교수 검수 대기 중입니다.":"승인된 개념 노트가 없습니다."))}</div>${c.status==="ready"?Object.entries(c.sections||{}).map(([title,section])=>`<h3 style="margin-top:18px">${esc(title)}</h3><p>${esc(section?.body||"")}</p>`).join(""):""}`;
  }
  const cards=feedback.anki_cards||[];
  return `<h3>Anki 카드</h3>${cards.length?`<div class="anki-list">${cards.map((card,index)=>`<article class="anki-item"><span>Card ${index+1}</span><strong>${esc(card.anki_text||card.front||card.plain_text||"")}</strong>${card.plain_text&&card.plain_text!==card.anki_text?`<p>${esc(card.plain_text)}</p>`:""}<small>${esc((card.tags||[]).join(" · "))}</small></article>`).join("")}</div>`:`<div class="context-state">연결된 Anki 카드가 없습니다.</div>`}<div class="context-state ready">FSRS 복습 기록과 문항별 Anki 학습 포인트가 함께 저장됩니다.</div>`;
}

async function submitCurrent(selected=state.selected) {
  const q=current();
  return api(`/api/student/questions/${encodeURIComponent(q.id)}/answer`,{method:"POST",body:JSON.stringify({event_id:`${sessionId}_${q.id}`,session_id:sessionId,selected_choices:[String(selected)],time_ms:Math.max(1000,state.elapsed*1000),is_bookmarked:state.bookmarks.has(q.id)})});
}

async function primaryAction() {
  if(state.selected==null||state.saving)return;
  if(state.mode==="study"&&!state.feedback){
    state.saving=true; render();
    try { const feedback=await submitCurrent(); state.feedback=feedback; state.results.push(resultRecord(current(),state.selected,feedback)); state.saving=false; render(); window.scrollTo({top:document.querySelector(".feedback-wrap")?.offsetTop-80||0,behavior:"smooth"}); }
    catch(error){state.saving=false;render();toast(error.message);} return;
  }
  if(state.mode==="exam") state.examAnswers.set(current().id,String(state.selected));
  if(state.index===state.items.length-1){ await finish(); return; }
  state.index+=1; state.selected=state.mode==="exam"?(state.examAnswers.get(current().id)||null):null; state.eliminated=new Set(); state.feedback=null; state.tab="explanation"; state.fsrsSaved=false; render(); window.scrollTo({top:0,behavior:"smooth"});
}

function resultRecord(q,selected,feedback){return {questionId:q.id,topic:q.topic||q.major||q.subject,stem:q.stem,selected:String(selected),answer:(feedback.answer_keys||[]).join(","),isCorrect:Boolean(feedback.is_correct)};}

async function finish(){
  if(state.mode==="exam"){
    state.saving=true;render();
    try { state.results=[]; for(let i=0;i<state.items.length;i++){state.index=i;const q=current(),selected=state.examAnswers.get(q.id)||(i===state.items.length-1?String(state.selected):null);if(!selected)continue;const feedback=await submitCurrent(selected);state.results.push(resultRecord(q,selected,feedback));} }
    catch(error){state.saving=false;render();toast(error.message);return;}
  }
  renderResult();
}

function renderResult(){
  const total=state.results.length,correct=state.results.filter((item)=>item.isCorrect).length,pct=total?Math.round(correct/total*100):0,wrong=state.results.filter((item)=>!item.isCorrect);
  document.querySelector("#session-title").textContent="세션 결과";document.querySelector("#session-progress").textContent=`${correct}/${total}`;topBookmark.hidden=true;
  root.innerHTML=`<section class="result-page"><article class="card result-hero"><span class="eyebrow" style="color:#76d7ca">Session Complete</span><h1>학습을 완료했습니다</h1><p>모든 답안은 서버에 저장됐고 리포트와 복습 일정에 반영됩니다.</p><div class="result-score">${pct}%</div></article><div class="result-grid"><article class="card summary-card"><span>정답</span><strong>${correct}/${total}</strong></article><article class="card summary-card"><span>풀이 시간</span><strong>${formatTime(state.elapsed)}</strong></article><article class="card summary-card"><span>오답</span><strong>${wrong.length}</strong></article></div><section class="result-items">${state.results.map((item)=>`<article class="card result-item ${item.isCorrect?"":"wrong"}"><span class="mark">${item.isCorrect?"✓":"!"}</span><div class="row-main"><h3>${esc(item.topic)}</h3><p>${esc(item.stem)}</p></div><span>${esc(item.selected)} → ${esc(item.answer)}</span></article>`).join("")}</section><div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap"><a class="button primary" href="/student/#report">리포트 보기 →</a>${wrong.length?`<a class="button secondary" href="${`/student/reader.html?ids=${encodeURIComponent(wrong.map((item)=>item.questionId).join(","))}&mode=study&count=${wrong.length}`}">오답 다시 풀기</a>`:""}<a class="button secondary" href="/student/#library">서재로 돌아가기</a></div></section>`;
}

async function saveFsrs(rating,button){
  if(state.fsrsSaved)return; button.disabled=true;
  try { const payload=await api("/api/student/fsrs/reviews",{method:"POST",body:JSON.stringify({event_id:`${sessionId}_${current().id}_fsrs`,question_id:current().id,rating})});state.fsrsSaved=true;button.classList.add("saved");const due=payload.card?.due?new Date(payload.card.due).toLocaleString("ko-KR",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}):"다음 일정";toast(`FSRS 복습 일정 저장 · ${due}`);render(); }
  catch(error){button.disabled=false;toast(error.message);}
}

async function toggleBookmark(){
  const q=current(),on=!state.bookmarks.has(q.id);topBookmark.disabled=true;
  try{await api(`/api/student/questions/${encodeURIComponent(q.id)}/bookmark`,{method:"PATCH",body:JSON.stringify({on})});on?state.bookmarks.add(q.id):state.bookmarks.delete(q.id);toast(on?"북마크했습니다.":"북마크를 해제했습니다.");updateTop();}catch(error){toast(error.message);}finally{topBookmark.disabled=false;}
}

async function boot(){
  try{
    const [qbank,bookmarks]=await Promise.all([api("/api/student/qbank"),api("/api/student/bookmarks")]);
    let items=(qbank.questions||[]).filter((question)=>question.practice_ready!==false);
    const ids=(params.get("ids")||"").split(",").filter(Boolean),exam=params.get("exam"),courseId=params.get("courseId"),count=Math.max(1,Math.min(100,Number(params.get("count"))||20));
    if(ids.length){const byId=new Map(items.map((q)=>[q.id,q]));items=ids.map((id)=>byId.get(id)).filter(Boolean);} else if(exam)items=items.filter((q)=>q.exam===exam);else if(courseId)items=items.filter((q)=>q.course_id===courseId);
    state.items=items.slice(0,count);state.bookmarks=new Set(bookmarks.question_ids||[]);
    if(!state.items.length)throw new Error("선택한 범위에 공개된 문항이 없습니다.");
    render();
  }catch(error){root.innerHTML=`<section class="card empty-card" style="margin-top:60px"><strong>문항을 열 수 없습니다</strong><p>${esc(error.message)}</p><a class="button primary" href="/student/#library">서재로 돌아가기</a></section>`;}
}

topBookmark.addEventListener("click",toggleBookmark);
setInterval(()=>{state.elapsed=Math.floor((Date.now()-state.startedAt)/1000);document.querySelector("#timer").textContent=formatTime(state.elapsed);},1000);
boot();
