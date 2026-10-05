#!/usr/bin/env python3
"""Interactive MONDO-taxonomy tree of the ontology (standard is-a backbone).

Groups the MONDO-matched nodes as top_category -> primary_category -> disease leaf, each leaf
showing Korean name, MONDO id, and Harrison chapter. Self-contained HTML (P:accine brand).
"""
from __future__ import annotations
import json
import html
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data_private" / "concept_registry.json"
OUT = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/"
           "de303da3-bc32-4d7d-8ccd-2e818e9e83d7/scratchpad/ontology_taxonomy.html")

# stable colors per top category (P:accine palette family)
CAT_COLOR = {
    "hematologic disorder": "#a4303f", "cardiovascular disorder": "#c25b4e",
    "nervous system disorder": "#3b6ea5", "digestive system disorder": "#c98a3a",
    "reproductive system disorder": "#b0578d", "endocrine system disorder": "#6a5acd",
    "respiratory system disorder": "#2a9d8f", "urinary system disorder": "#4c8577",
    "psychiatric disorder": "#7b5ea7", "infectious disease": "#1f7a6d",
    "musculoskeletal system disorder": "#8a7a5c", "integumentary system disorder": "#c98aa8",
    "metabolic disease": "#5c8a6a", "immune system disorder": "#9c6b3f",
    "neoplasm": "#8f2d56", "cancer": "#7a1f3d", "disorder of ear": "#888",
}


def ko_of(c: dict) -> str:
    for a in c.get("aliases", []):
        if any("가" <= ch <= "힣" for ch in a):
            return a
    return c["disease_concept_id"]


def main() -> None:
    reg = json.loads(REG.read_text(encoding="utf-8"))["concepts"]
    tree = defaultdict(lambda: defaultdict(list))
    n_leaf = 0
    for cid, c in reg.items():
        tax = c.get("taxonomy")
        if not tax or not tax.get("top_category"):
            continue
        top = tax["top_category"]
        prim = tax.get("primary_category") or "(기타)"
        h = (c.get("evidence") or {}).get("harrison")
        x = (c.get("evidence") or {}).get("ontology_xref")
        tree[top][prim].append({
            "id": cid, "ko": ko_of(c),
            "mondo": (x or {}).get("mondo_id", ""),
            "harrison": f"Ch{h['chapter']} p{h['page']}" if h else "",
            "nt": c.get("node_type", ""),
        })
        n_leaf += 1

    parts = []
    tops = sorted(tree.items(), key=lambda kv: -sum(len(v) for v in kv[1].values()))
    for top, prims in tops:
        col = CAT_COLOR.get(top, "#0e7c7b")
        tcount = sum(len(v) for v in prims.values())
        parts.append(f'<details class="cat" style="--c:{col}"><summary><span class="dot"></span>'
                     f'<b>{html.escape(top)}</b><span class="ct">{tcount}</span></summary>')
        for prim, leaves in sorted(prims.items(), key=lambda kv: -len(kv[1])):
            parts.append(f'<details class="sub"><summary>{html.escape(prim)}'
                         f'<span class="ct">{len(leaves)}</span></summary><ul>')
            for lf in sorted(leaves, key=lambda x: x["id"]):
                meta = " · ".join([m for m in [html.escape(lf["mondo"]), html.escape(lf["harrison"])] if m])
                parts.append(
                    f'<li data-s="{html.escape(lf["id"]+" "+lf["ko"])}"><span class="ko">{html.escape(lf["ko"])}</span>'
                    f'<span class="id">{html.escape(lf["id"])}</span>'
                    f'<span class="mh">{meta}</span></li>')
            parts.append("</ul></details>")
        parts.append("</details>")

    body = "\n".join(parts)
    n_cat = len(tree)
    HTML = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>P:accine 온톨로지 분류 트리 (MONDO)</title>
<style>
 :root{{--paper:#f4efe4;--ink:#241f18;--muted:#8a8271;--line:#e4dccb;--teal:#0e7c7b;--surface:#fffdf8}}
 *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);
   font-family:"Pretendard",-apple-system,"Malgun Gothic",sans-serif;line-height:1.5}}
 .top{{padding:16px 22px;border-bottom:1px solid var(--line);background:var(--surface);position:sticky;top:0;z-index:5}}
 .top h1{{font-size:18px;margin:0 0 3px}}.top p{{margin:0;font-size:12px;color:var(--muted)}}
 .top input{{margin-top:9px;padding:8px 11px;border:1px solid var(--line);border-radius:8px;background:var(--paper);font-size:13px;width:min(340px,100%)}}
 .wrap{{max-width:900px;margin:0 auto;padding:14px 22px 60px}}
 details.cat{{border:1px solid var(--line);border-left:4px solid var(--c);border-radius:9px;margin:9px 0;background:var(--surface);overflow:hidden}}
 details.cat>summary{{padding:11px 14px;font-size:15px;cursor:pointer;list-style:none;display:flex;align-items:center;gap:9px}}
 .dot{{width:11px;height:11px;border-radius:50%;background:var(--c);flex:none}}
 details.sub{{margin:2px 0 2px 20px}}
 details.sub>summary{{padding:5px 10px;font-size:13px;color:#4a4436;cursor:pointer;list-style:none;font-weight:600}}
 summary::-webkit-details-marker{{display:none}}
 .ct{{margin-left:8px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;background:var(--paper);border:1px solid var(--line);border-radius:20px;padding:1px 8px}}
 ul{{list-style:none;margin:0 0 6px;padding:0 0 0 34px}}
 li{{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;padding:3px 8px;border-radius:6px}}
 li:hover{{background:var(--paper)}}
 .ko{{font-size:13px}}.id{{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--muted)}}
 .mh{{margin-left:auto;font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--teal)}}
 mark{{background:#ffe08a;color:inherit}}
 @media (prefers-color-scheme:dark){{:root{{--paper:#1c1a16;--ink:#ece6d8;--muted:#9a9484;--line:#39352c;--surface:#252119}}}}
</style></head><body>
<div class="top"><h1>P:accine 온톨로지 · 표준 분류 트리 (MONDO is-a)</h1>
<p>{n_leaf}개 질환을 MONDO 표준 계층으로 분류 · {n_cat}개 최상위 카테고리 · 각 잎 = 질환(한글) · id · MONDO ID · Harrison 챕터. 클릭하여 펼치기.</p>
<input id="q" placeholder="질환 검색 (한글/영문)…" autocomplete="off"></div>
<div class="wrap">{body}</div>
<script>
const q=document.getElementById('q');
q.addEventListener('input',()=>{{
 const v=q.value.trim().toLowerCase();
 document.querySelectorAll('li').forEach(li=>{{
   const t=li.dataset.s.toLowerCase();const hit=!v||t.includes(v);li.style.display=hit?'':'none';
   const ko=li.querySelector('.ko');ko.innerHTML=ko.textContent;
   if(v&&hit){{const i=ko.textContent.toLowerCase().indexOf(v);if(i>=0)ko.innerHTML=ko.textContent.slice(0,i)+'<mark>'+ko.textContent.slice(i,i+v.length)+'</mark>'+ko.textContent.slice(i+v.length);}}
 }});
 document.querySelectorAll('details.sub').forEach(d=>{{const any=[...d.querySelectorAll('li')].some(li=>li.style.display!=='none');d.style.display=any?'':'none';if(v&&any)d.open=true;}});
 document.querySelectorAll('details.cat').forEach(d=>{{const any=[...d.querySelectorAll('li')].some(li=>li.style.display!=='none');d.style.display=any?'':'none';if(v&&any)d.open=true;}});
}});
</script></body></html>"""
    OUT.write_text(HTML, encoding="utf-8")
    print(f"wrote {OUT.name} · {n_leaf} leaves · {n_cat} top categories")


if __name__ == "__main__":
    main()
