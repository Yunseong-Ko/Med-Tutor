#!/usr/bin/env python3
"""Demo viz: ontology-grounded generated items with per-choice provenance.

Shows that every distractor is traceable to an ontology edge (differential_of / is_a sibling /
shared-finding bridge) — not the LLM's imagination. Self-contained HTML (P:accine brand).
"""
from __future__ import annotations
import json
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data_private" / "curriculum" / "ontology_grounded_items.json"
OUT = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/"
           "de303da3-bc32-4d7d-8ccd-2e818e9e83d7/scratchpad/ontology_item_demo.html")

PROV = {
    "target": ("정답", "#0e7c7b"),
    "differential_of": ("감별 (differential_of)", "#3b6ea5"),
    "is_a_sibling": ("동일 상위분류 형제 (is_a)", "#7b5ea7"),
    "shared_finding_bridge": ("공유 소견 브리지 (presents_with)", "#c98a3a"),
}


def esc(s):
    return html.escape(str(s or ""))


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    cards = []
    for r in data["items"]:
        it = r["item"]; v = r.get("verify", {})
        choices = sorted(it["choices"], key=lambda c: c["n"])
        rows = []
        for c in choices:
            label, col = PROV.get(c["provenance"], ("?", "#9a917c"))
            correct = c["is_correct"]
            mark = "✓" if correct else ""
            rat = f'<div class="rat">{esc(c.get("rationale",""))}</div>' if c.get("rationale") else ""
            rows.append(
                f'<li class="ch{" ok" if correct else ""}"><span class="n">{c["n"]}</span>'
                f'<div class="cbody"><div class="ct"><span class="ctext">{esc(c["text"])} <span class="mark">{mark}</span></span>'
                f'<span class="badge" style="--b:{col}">{esc(label)}</span></div>'
                f'<div class="did">{esc(c["disease_id"])}</div>{rat}</div></li>')
        title_ko = next((c["text"] for c in choices if c.get("is_correct")), it.get("target_ko") or it["target"])
        edges = " · ".join(esc(e) for e in it.get("ontology_edges_used", []))
        vbadge = ('<span class="v ok">검증 good</span>' if v.get("verdict") == "good" else f'<span class="v">{esc(v.get("verdict"))}</span>')
        grounded = '<span class="v ok">오답 100% 온톨로지 유래</span>' if v.get("distractors_ontology_grounded") else '<span class="v bad">grounding 미달</span>'
        cards.append(f"""
<article class="card">
 <header><h2>{esc(title_ko)}</h2><code>{esc(it['target'])}</code>
   <div class="vs">{vbadge} {grounded} {'<span class="v ok">답 누출 없음</span>' if v.get('no_answer_leak') else ''}</div></header>
 <div class="stem">{esc(it['stem'])}</div>
 <div class="lead">{esc(it['lead_in'])}</div>
 <ol class="choices">{''.join(rows)}</ol>
 <footer>정답 <b>{it['answer']}</b> · 사용한 온톨로지 근거: <code>{edges}</code></footer>
</article>""")

    prov_legend = "".join(
        f'<span class="k"><span class="dot" style="background:{c}"></span>{esc(l)}</span>'
        for l, c in PROV.values())
    body = "\n".join(cards)
    HTML = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>P:accine 온톨로지 기반 문항 생성 데모</title>
<style>
 :root{{--paper:#f4efe4;--ink:#241f18;--muted:#8a8271;--line:#e4dccb;--teal:#0e7c7b;--surface:#fffdf8;--ok:#0e7c7b}}
 *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);
   font-family:"Pretendard",-apple-system,"Malgun Gothic",sans-serif;line-height:1.6}}
 .top{{padding:20px 22px;border-bottom:1px solid var(--line);background:var(--surface)}}
 .top h1{{font-size:19px;margin:0 0 4px}}.top p{{margin:0;font-size:12.5px;color:var(--muted);max-width:70ch}}
 .legend{{display:flex;flex-wrap:wrap;gap:14px;margin-top:11px;font-size:11.5px;color:var(--muted)}}
 .legend .k{{display:inline-flex;align-items:center;gap:5px}}.dot{{width:11px;height:11px;border-radius:50%}}
 .wrap{{max-width:820px;margin:0 auto;padding:16px 22px 60px;display:flex;flex-direction:column;gap:20px}}
 .card{{border:1px solid var(--line);border-radius:12px;background:var(--surface);overflow:hidden}}
 .card header{{padding:13px 16px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}}
 .card h2{{font-size:16px;margin:0}}.card code{{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--muted)}}
 .vs{{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}}
 .v{{font-size:10.5px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--muted)}}
 .v.ok{{color:#fff;background:var(--ok);border-color:var(--ok)}}.v.bad{{color:#fff;background:#a4303f;border-color:#a4303f}}
 .stem{{padding:14px 16px;font-size:14px;background:var(--paper)}}
 .lead{{padding:10px 16px 4px;font-weight:600;font-size:14px}}
 .choices{{list-style:none;margin:0;padding:6px 16px 14px}}
 .ch{{display:flex;gap:10px;padding:9px;border-radius:9px;border:1px solid transparent}}
 .ch.ok{{background:rgba(14,124,123,.07);border-color:rgba(14,124,123,.3)}}
 .ch .n{{flex:none;width:24px;height:24px;border-radius:50%;background:var(--paper);border:1px solid var(--line);
   display:grid;place-items:center;font-size:12px;font-variant-numeric:tabular-nums}}
 .ch.ok .n{{background:var(--teal);color:#fff;border-color:var(--teal)}}
 .cbody{{flex:1}}.ct{{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}}.ctext{{font-size:14px;font-weight:500}}
 .mark{{color:var(--teal);font-weight:700}}
 .badge{{margin-left:auto;font-size:10px;padding:2px 9px;border-radius:20px;color:#fff;background:var(--b)}}
 .did{{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--muted);margin-top:1px}}
 .rat{{font-size:12px;color:#5a5344;margin-top:4px}}
 .card footer{{padding:10px 16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}}
 .card footer code{{color:var(--teal)}}
 @media (prefers-color-scheme:dark){{:root{{--paper:#1c1a16;--ink:#ece6d8;--muted:#9a9484;--line:#39352c;--surface:#252119}}.rat{{color:#c3bca9}}}}
</style></head><body>
<div class="top"><h1>P:accine · 온톨로지 기반 문항 생성 데모</h1>
<p>각 문항의 <b>오답(distractor)은 LLM이 상상한 게 아니라 온톨로지에서 나온 실제 감별질환</b>입니다. 선지마다 어느 엣지에서 나왔는지 근거(provenance)를 붙였고, 적대 검증으로 정답 타당성·오답 grounding·답 누출을 확인했습니다. 6문항 전부 검증 통과.</p>
<div class="legend">{prov_legend}</div></div>
<div class="wrap">{body}</div>
</body></html>"""
    OUT.write_text(HTML, encoding="utf-8")
    print(f"wrote {OUT.name} · {len(data['items'])} items")


if __name__ == "__main__":
    main()
