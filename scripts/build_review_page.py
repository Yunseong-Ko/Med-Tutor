#!/usr/bin/env python3
"""합성 세트1·2(160문항)를 브라우저에서 펼쳐볼 수 있는 자체완결 로컬 HTML 리뷰 페이지 생성.

비공개: 파일시스템에만 저장(외부 전송 없음).
"""

import json
import html
from pathlib import Path

SETS = [
    ("세트1", Path("data_private/exam_sets/SYNTH_2026_SET1.json")),
    ("세트2", Path("data_private/exam_sets/SYNTH_2026_SET2.json")),
]
OUT = Path("data_private/exam_sets/review_synth_sets.html")


def esc(s):
    return html.escape(str(s or ""))


def main():
    payload = []
    for label, path in SETS:
        data = json.loads(path.read_text(encoding="utf-8"))
        for q in data["questions"]:
            ri = q.get("reused_image")
            ei = q.get("external_image")
            img = None
            if ri:
                # 리뷰 HTML(data_private/exam_sets/)에서 media(data_private/course_exams/media/)로의 상대경로
                img = {"src": f"../course_exams/media/{ri['folder']}/{ri['file']}",
                       "caption": ri.get("caption") + "  · [기존 기출 재사용]"}
            elif ei:
                img = {"src": f"../course_exams/media/{ei['folder']}/{ei['file']}",
                       "caption": f"{ei.get('caption')}  · [{ei.get('license')} · {ei.get('attribution')}]"}
            payload.append({
                "set": label,
                "n": q["question_number"],
                "system": q.get("system"),
                "type": q.get("question_type"),
                "difficulty": q.get("difficulty"),
                "stem": q.get("stem"),
                "choices": q.get("choices") or {},
                "answer": str(q.get("answer")),
                "explanation": q.get("explanation"),
                "rationale": q.get("answer_rationale"),
                "klp": q.get("key_learning_points") or [],
                "ce": q.get("choice_explanations") or {},
                "img": img,
                "labs": q.get("lab_values") or [],
            })

    data_json = json.dumps(payload, ensure_ascii=False)

    html_doc = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>합성 시험지 세트1·2 리뷰</title>
<style>
:root{--navy:#0B1F3A;--teal:#0F766E;--ink:#1a2330;--muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;--ok:#0F766E;}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;color:var(--ink);background:var(--bg);line-height:1.55}
header{background:var(--navy);color:#fff;padding:22px 20px}
header h1{margin:0 0 4px;font-size:20px}header .sub{opacity:.8;font-size:13px}
.wrap{max-width:900px;margin:0 auto;padding:16px 20px 60px}
.toolbar{position:sticky;top:0;background:var(--bg);padding:12px 0;border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;align-items:center;z-index:5}
.toolbar select,.toolbar input{padding:7px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#fff}
.count{font-size:13px;color:var(--muted);margin-left:auto}
.q{background:#fff;border:1px solid var(--line);border-radius:12px;margin:12px 0;overflow:hidden}
.q summary{list-style:none;cursor:pointer;padding:14px 16px;display:flex;gap:10px;align-items:flex-start}
.q summary::-webkit-details-marker{display:none}
.badge{font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;white-space:nowrap}
.b-set{background:#e0e7ff;color:#3730a3}.b-sys{background:#ccfbf1;color:#115e59}
.b-type{background:#f1f5f9;color:#334155}.b-dif{background:#fef3c7;color:#92400e}
.qnum{font-weight:700;color:var(--navy);min-width:52px}
.stem{flex:1;font-size:14px}
.body{padding:0 16px 16px;border-top:1px solid var(--line)}
.choices{margin:12px 0;display:grid;gap:6px}
.choice{padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px;display:flex;gap:8px}
.choice.correct{border-color:var(--teal);background:#f0fdfa}
.choice .k{font-weight:700;color:var(--muted);min-width:18px}
.choice.correct .k{color:var(--teal)}
.choice .cx{color:var(--muted);font-size:12px;margin-top:2px}
.sec{margin-top:12px}.sec h4{margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--teal)}
.sec p{margin:0;font-size:13.5px}
ul.klp{margin:4px 0 0;padding-left:18px;font-size:13px}ul.klp li{margin:2px 0}
.note{font-size:12px;color:var(--muted);margin-top:6px}
.labbox2{border:1px solid var(--line);border-radius:8px;overflow:hidden;margin:10px 0}
.labbox2 .labt{background:var(--teal);color:#fff;font-weight:700;padding:6px 12px;font-size:12px}
.labbox2 table{width:100%;border-collapse:collapse}
.labbox2 td{padding:5px 12px;border-top:1px solid #edf2f7;font-size:13px}
.labbox2 td.lr{color:#7688a0;text-align:right;font-size:11px;white-space:nowrap}
.hidden{display:none}
</style></head><body>
<header><h1>합성 임상종합 모의고사 · 세트1 · 세트2</h1>
<div class="sub">AI 생성 초안 160문항 · 전 문항 needs_review · 학생 배포 전 사람 검토 필요</div></header>
<div class="wrap">
<div class="toolbar">
<select id="fSet"><option value="">전체 세트</option><option>세트1</option><option>세트2</option></select>
<select id="fSys"><option value="">전체 계통</option></select>
<select id="fDif"><option value="">전체 난이도</option><option>하</option><option>중</option><option>상</option></select>
<input id="fSearch" placeholder="검색(주제·본문)" style="min-width:160px">
<span class="count" id="count"></span>
</div>
<div id="list"></div>
</div>
<script>
const DATA = __DATA__;
const list=document.getElementById('list');
const sysSel=document.getElementById('fSys');
[...new Set(DATA.map(q=>q.system))].sort().forEach(s=>{const o=document.createElement('option');o.textContent=s;sysSel.appendChild(o);});
function render(){
  const fs=document.getElementById('fSet').value, fy=sysSel.value, fd=document.getElementById('fDif').value;
  const q=document.getElementById('fSearch').value.trim();
  list.innerHTML='';
  let shown=0;
  DATA.forEach(item=>{
    if(fs&&item.set!==fs)return; if(fy&&item.system!==fy)return; if(fd&&item.difficulty!==fd)return;
    if(q){const hay=(item.stem+' '+item.system+' '+item.explanation).toLowerCase();if(!hay.includes(q.toLowerCase()))return;}
    shown++;
    const d=document.createElement('details');d.className='q';
    const ch=Object.entries(item.choices).map(([k,v])=>{
      const correct=k===item.answer; const cx=(item.ce[k]||{}).rationale||'';
      return `<div class="choice ${correct?'correct':''}"><span class="k">${k}</span><span>${esc(v)}${cx?`<div class="cx">${esc(cx)}</div>`:''}</span></div>`;
    }).join('');
    const klp=(item.klp||[]).map(x=>`<li>${esc(x)}</li>`).join('');
    d.innerHTML=`<summary>
      <span class="qnum">Q${String(item.n).padStart(3,'0')}${item.img?' 🖼':''}</span>
      <span class="stem">${esc(item.stem)}</span>
      </summary>
      <div class="body">
        <div style="margin:10px 0 2px">
          <span class="badge b-set">${esc(item.set)}</span>
          <span class="badge b-sys">${esc(item.system)}</span>
          <span class="badge b-type">${esc(item.type)}</span>
          <span class="badge b-dif">난이도 ${esc(item.difficulty)}</span>
        </div>
        ${(item.labs&&item.labs.length)?`<div class="labbox2"><div class="labt">검사 결과</div><table>${item.labs.map(r=>`<tr><td>${esc(r.item||r.name)}</td><td class="lr">${r.ref?('참고치 '+esc(r.ref)):''}</td></tr>`).join('')}</table></div>`:''}
        ${item.img?`<div class="sec"><h4>제시 이미지</h4><img src="${item.img.src}" style="max-width:100%;border:1px solid var(--line);border-radius:8px"><div class="note">${esc(item.img.caption)}</div></div>`:''}
        <div class="choices">${ch}</div>
        <div class="sec"><h4>정답근거</h4><p>${esc(item.rationale)}</p></div>
        <div class="sec"><h4>통합해설</h4><p>${esc(item.explanation)}</p></div>
        <div class="sec"><h4>핵심 학습 포인트</h4><ul class="klp">${klp}</ul></div>
        <div class="note">정답: ${esc(item.answer)}번 · review_status=generated_draft</div>
      </div>`;
    list.appendChild(d);
  });
  document.getElementById('count').textContent=shown+' / '+DATA.length+' 문항';
}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
['fSet','fSys','fDif','fSearch'].forEach(id=>document.getElementById(id).addEventListener('input',render));
render();
</script></body></html>"""

    html_doc = html_doc.replace("__DATA__", data_json)
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"[done] 리뷰 페이지 생성 → {OUT}")
    print(f"       총 {len(payload)}문항 (세트1·2), 계통·난이도·검색 필터 포함")


if __name__ == "__main__":
    raise SystemExit(main())
