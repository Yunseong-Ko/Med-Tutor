"""Build a standalone, self-contained HTML demo (interview prop) from the
중재원 정형/성형 subsets — now combining two sources:
  - 조정분석 (outcome/배상): ortho 85 + plastic 20
  - 감정분석 (education): ortho 38, with 양측쟁점 + 감정결과 + 의료사고예방팁

No server, no deps — opens anywhere. THROWAWAY prop to provoke interview reactions.
Output: data_private/medlegal/demo/kmedi_pattern_explorer.html  (gitignored)
"""
from __future__ import annotations

import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data_private/medlegal/processed"
OUT = ROOT / "data_private/medlegal/demo/kmedi_pattern_explorer.html"

DOC_PAT = re.compile(r"기록|설명의무|설명 의무|동의서|차트")
MONEY_PAT = re.compile(r"[0-9][0-9,]{4,}\s*원")
KW_SPLIT = re.compile(r"[,/、·]")


def load(name):
    p = PROC / name
    return [json.loads(l) for l in p.open(encoding="utf-8")] if p.exists() else []


def from_jojeong(r):
    blob = " ".join(str(r.get(k, "")) for k in ("key_issues", "liability_content", "dispute_content"))
    return {
        "source": "조정", "title": r.get("title", ""), "dept": r.get("clinical_dept", ""),
        "is_ortho": r.get("is_ortho"), "is_plastic": r.get("is_plastic"),
        "result": r.get("processing_result", ""),
        "keywords": r.get("keyword_list") or [],
        "doc_flag": bool(DOC_PAT.search(blob)),
        "has_money": bool(MONEY_PAT.search(str(r.get("liability_scope", "")))),
        "has_tip": False,
        "secs": [
            ("사안 쟁점", r.get("key_issues")), ("감정 결과", r.get("expert_opinion")),
            ("책임 내용(과실 판단)", r.get("liability_content")),
            ("손해배상 책임범위", r.get("liability_scope")), ("사고 경위", r.get("accident_circumstance")),
        ],
        "issues": None, "tip": "",
    }


def from_gamjeong(r):
    blob = " ".join(str(r.get(k, "")) for k in ("issue_patient", "issue_hospital", "expert_opinion"))
    tip = r.get("prevention_tip", "")
    tip = "" if "해당사항없음" in tip else tip
    return {
        "source": "감정", "title": r.get("title", ""), "dept": r.get("clinical_dept", ""),
        "is_ortho": r.get("is_ortho"), "is_plastic": r.get("is_plastic"),
        "result": r.get("mediation_result", "")[:0] and "" or "감정사례",
        "keywords": [k.strip() for k in KW_SPLIT.split(r.get("keywords", "")) if k.strip()],
        "doc_flag": bool(DOC_PAT.search(blob)),
        "has_money": bool(MONEY_PAT.search(str(r.get("mediation_result", "")))),
        "has_tip": bool(tip),
        "secs": [
            ("사건 개요", r.get("case_summary")), ("치료 과정", r.get("treatment_course")),
            ("감정 결과", r.get("expert_opinion")), ("조정 결과", r.get("mediation_result")),
        ],
        "issues": {"환자측": r.get("issue_patient", ""), "병원측": r.get("issue_hospital", "")},
        "tip": tip,
    }


def main():
    recs = [from_jojeong(r) for r in (load("kmedi_disputes_ortho.jsonl") + load("kmedi_disputes_plastic.jsonl"))]
    recs += [from_gamjeong(r) for r in load("kmedi_gamjeong.jsonl") if r.get("is_ortho")]
    if not recs:
        raise SystemExit("No subsets found. Run ingest_kmedi_disputes.py and ingest_kmedi_extra.py first.")

    stats = dict(
        n=len(recs),
        jo=sum(r["source"] == "조정" for r in recs),
        gam=sum(r["source"] == "감정" for r in recs),
        doc=sum(r["doc_flag"] for r in recs),
        tip=sum(r["has_tip"] for r in recs),
    )
    data_json = json.dumps(recs, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data_json)
    for k, v in stats.items():
        html = html.replace(f"__{k.upper()}__", str(v))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  (총 {stats['n']}: 조정 {stats['jo']} + 감정 {stats['gam']}, 기록쟁점 {stats['doc']}, 예방팁 {stats['tip']})")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>의료분쟁 패턴 탐색기 — 정형·성형 (데모)</title>
<style>
:root{--ortho:#2563eb;--plastic:#db2777;--bg:#f6f7f9;--card:#fff;--ink:#1a1f2b;--mut:#6b7280;--line:#e5e7eb}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
header{background:linear-gradient(135deg,#111827,#1f2937);color:#fff;padding:22px 20px 18px}
header h1{margin:0;font-size:19px;font-weight:700}
header .sub{color:#9ca3af;font-size:12px;margin-top:5px;line-height:1.5}
.wrap{max-width:920px;margin:0 auto;padding:16px 14px 60px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:-30px 0 14px}
.stat{flex:1;min-width:120px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.stat .n{font-size:23px;font-weight:800}
.stat .l{font-size:11px;color:var(--mut);margin-top:2px}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:5}
.controls input,.controls select{padding:9px 11px;border:1px solid var(--line);border-radius:9px;font-size:13px;background:#fff}
.controls input{flex:1;min-width:150px}
.seg{display:flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}
.seg button{border:0;background:#fff;padding:9px 12px;font-size:13px;cursor:pointer;color:var(--mut)}
.seg button.on{background:var(--ink);color:#fff;font-weight:600}
.count{font-size:12px;color:var(--mut);margin:0 0 10px 2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:15px 16px;margin-bottom:11px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.card h3{margin:0 0 9px;font-size:15px;line-height:1.4}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:9px}
.b{font-size:11px;font-weight:700;padding:3px 9px;border-radius:20px}
.b.ortho{background:#dbeafe;color:var(--ortho)}
.b.plastic{background:#fce7f3;color:var(--plastic)}
.b.src-jo{background:#dcfce7;color:#15803d}
.b.src-gam{background:#fef3c7;color:#b45309}
.b.doc{background:#ffedd5;color:#c2410c}
.b.money{background:#ede9fe;color:#6d28d9}
.b.tip{background:#cffafe;color:#0e7490}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px}
.chip{font-size:11px;background:#f3f4f6;color:#374151;padding:2px 8px;border-radius:6px}
.tipbox{background:#ecfeff;border:1px solid #a5f3fc;border-radius:9px;padding:9px 11px;margin:9px 0;font-size:13px;line-height:1.6}
.tipbox b{color:#0e7490}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:9px 0}
.two .col{background:#f9fafb;border:1px solid var(--line);border-radius:9px;padding:9px 10px}
.two .col .h{font-size:11px;font-weight:700;margin-bottom:4px}
.two .col.pt .h{color:var(--plastic)} .two .col.hs .h{color:var(--ortho)}
.two .col .t{font-size:12.5px;line-height:1.55;white-space:pre-wrap}
details{margin-top:8px;border-top:1px dashed var(--line);padding-top:8px}
summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--ortho)}
.sec{margin:9px 0}
.sec .k{font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.3px}
.sec .v{font-size:13px;line-height:1.65;white-space:pre-wrap;margin-top:3px}
mark{background:#fff3bf;padding:0 2px;border-radius:3px}
.foot{font-size:11px;color:var(--mut);text-align:center;margin-top:24px;line-height:1.6}
@media(max-width:560px){.two{grid-template-columns:1fr}}
</style></head><body>
<header>
  <h1>의료분쟁 패턴 탐색기 <span style="font-weight:400;color:#9ca3af">· 정형외과 / 성형외과</span></h1>
  <div class="sub">출처: 한국의료분쟁조정중재원 조정·감정분석 (data.go.kr 3049716·15025792, KOGL) · <b>데모 prototype</b> · 교육·검증용, 법률자문 아님</div>
</header>
<div class="wrap">
  <div class="stats">
    <div class="stat"><div class="n">__N__</div><div class="l">정형·성형 케이스</div></div>
    <div class="stat"><div class="n" style="color:#15803d">__JO__</div><div class="l">조정(배상·결과)</div></div>
    <div class="stat"><div class="n" style="color:#b45309">__GAM__</div><div class="l">감정(교육·양측쟁점)</div></div>
    <div class="stat"><div class="n" style="color:#0e7490">__TIP__</div><div class="l">예방팁 보유</div></div>
  </div>
  <div class="controls">
    <div class="seg" id="src">
      <button data-s="all" class="on">전체</button><button data-s="조정">조정</button><button data-s="감정">감정</button>
    </div>
    <div class="seg" id="seg">
      <button data-d="all" class="on">전과</button><button data-d="ortho">정형</button><button data-d="plastic">성형</button>
    </div>
    <select id="flag"><option value="">필터 없음</option><option value="doc">기록·설명 쟁점</option><option value="tip">예방팁 보유</option><option value="money">배상금액 명시</option></select>
    <input id="q" placeholder="제목·키워드 검색…">
  </div>
  <div class="count" id="count"></div>
  <div id="list"></div>
  <div class="foot">중재원 큐레이션 대표사례(발생률 통계 아님) · 환자 식별정보 없음 · 인터뷰용 throwaway 데모</div>
</div>
<script>
const DATA=__DATA__,$=s=>document.querySelector(s);
let src="all",dept="all";
function hl(t){return String(t==null?"":t).replace(/&/g,"&amp;").replace(/</g,"&lt;")
  .replace(/([0-9][0-9,]{4,}\s*원)/g,"<mark>$1</mark>")
  .replace(/(기록|설명의무|동의서|주의의무 위반|경과관찰)/g,"<mark>$1</mark>");}
const sec=(k,v)=>v&&String(v).trim()?`<div class="sec"><div class="k">${k}</div><div class="v">${hl(v)}</div></div>`:"";
function card(r){
  const fail=/불성립|부조정/.test(r.result);
  const issues=r.issues?`<div class="two"><div class="col pt"><div class="h">환자측 주장</div><div class="t">${hl(r.issues['환자측'])}</div></div><div class="col hs"><div class="h">병원측 주장</div><div class="t">${hl(r.issues['병원측'])}</div></div></div>`:"";
  const tip=r.tip?`<div class="tipbox"><b>🛡 의료사고 예방팁</b><br>${hl(r.tip)}</div>`:"";
  return `<div class="card"><h3>${r.title||"(제목없음)"}</h3>
  <div class="badges">
    <span class="b ${r.is_ortho?'ortho':'plastic'}">${r.dept}</span>
    <span class="b src-${r.source==='조정'?'jo':'gam'}">${r.source}</span>
    ${r.source==='조정'&&r.result?`<span class="b src-jo" style="background:${fail?'#fee2e2':'#dcfce7'};color:${fail?'#b91c1c':'#15803d'}">${r.result}</span>`:''}
    ${r.doc_flag?'<span class="b doc">기록·설명 쟁점</span>':''}
    ${r.has_tip?'<span class="b tip">예방팁</span>':''}
    ${r.has_money?'<span class="b money">배상금액</span>':''}
  </div>
  <div class="chips">${(r.keywords||[]).slice(0,8).map(k=>`<span class="chip">${k}</span>`).join("")}</div>
  ${tip}${issues}
  <details><summary>상세 보기</summary>${r.secs.map(s=>sec(s[0],s[1])).join("")}</details></div>`;
}
function render(){
  const q=$("#q").value.trim().toLowerCase(),flag=$("#flag").value;
  let rows=DATA.filter(r=>{
    if(src!=="all"&&r.source!==src)return false;
    if(dept==="ortho"&&!r.is_ortho)return false;
    if(dept==="plastic"&&!r.is_plastic)return false;
    if(flag==="doc"&&!r.doc_flag)return false;
    if(flag==="tip"&&!r.has_tip)return false;
    if(flag==="money"&&!r.has_money)return false;
    if(q&&!((r.title+r.keywords.join("")).toLowerCase().includes(q)))return false;
    return true;});
  $("#count").textContent=`${rows.length}건 표시`;
  $("#list").innerHTML=rows.map(card).join("")||"<p style='color:#6b7280'>결과 없음</p>";
}
$("#src").addEventListener("click",e=>{if(e.target.dataset.s){src=e.target.dataset.s;[...$("#src").children].forEach(b=>b.classList.toggle("on",b===e.target));render();}});
$("#seg").addEventListener("click",e=>{if(e.target.dataset.d){dept=e.target.dataset.d;[...$("#seg").children].forEach(b=>b.classList.toggle("on",b===e.target));render();}});
["#q","#flag"].forEach(s=>$(s).addEventListener("input",render));
render();
</script></body></html>"""


if __name__ == "__main__":
    main()
