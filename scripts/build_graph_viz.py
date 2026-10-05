#!/usr/bin/env python3
"""Render the concept ontology as an interactive force-directed SVG graph.

Reads concept_registry.json (edges populated by P2) + qbank_relabeled.json (coverage).
Builds a disease-concept network from the typed edges, computes a spring layout with
networkx, and emits a self-contained interactive HTML (hover-highlight neighbors,
pan/zoom, search, edge-type toggle). Out-of-registry endpoints are included as small
attribute leaves only when they connect an in-registry disease.
"""
from __future__ import annotations
import json, re
from collections import Counter, defaultdict
from pathlib import Path
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / "data_private"
SCRATCH = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/de303da3-bc32-4d7d-8ccd-2e818e9e83d7/scratchpad")
OUT = SCRATCH / "ontology_graph.html"

reg = json.loads((DP / "concept_registry.json").read_text(encoding="utf-8"))["concepts"]
rel = json.loads((DP / "embedding" / "qbank_relabeled.json").read_text(encoding="utf-8"))["items"]

PART = {1:"의학총론",2:"주요증상",3:"약리",4:"혈액종양",5:"감염",6:"순환기",7:"호흡기",8:"중환자",9:"신장비뇨",
        10:"소화기",11:"면역류마",12:"내분비",13:"신경",14:"중독",15:"환경",16:"유전",17:"국제",18:"노화",19:"자문",20:"신흥"}
SPEC = {"혈액종양":"혈액종양","산부인과":"산부인과","정신":"정신","소아":"소아","소아외과":"소아","소화기":"소화기",
        "순환기":"순환기","신경":"신경","신장비뇨":"신장비뇨","비뇨의학":"신장비뇨","내분비":"내분비","감염":"감염",
        "호흡기":"호흡기","외과":"외과","면역알레르기":"면역류마"}
GROUP_COLORS = {"혈액종양":"#b0413e","감염":"#0e7c7b","순환기":"#c85a54","호흡기":"#3d9b86","소화기":"#c8791f",
    "신장비뇨":"#5b8ac2","내분비":"#7b5ea7","신경":"#4a72b0","정신":"#9a5ba6","산부인과":"#c25a8f","소아":"#d19a3c",
    "면역류마":"#4a9b8e","주요증상":"#8a8271","외과":"#a06a4a","기타":"#9a917c",
    "근골격":"#8a7a5c","피부":"#c98aa8","대사":"#5c8a6a","종양":"#8f2d56","이비인후":"#7a8a99"}

# MONDO top_category -> Korean label (aligned to the specialty labels so one color map serves both facets)
MONDO_LABEL = {"hematologic disorder":"혈액종양","cardiovascular disorder":"순환기","nervous system disorder":"신경",
    "digestive system disorder":"소화기","reproductive system disorder":"산부인과","endocrine system disorder":"내분비",
    "respiratory system disorder":"호흡기","urinary system disorder":"신장비뇨","psychiatric disorder":"정신",
    "infectious disease":"감염","musculoskeletal system disorder":"근골격","integumentary system disorder":"피부",
    "metabolic disease":"대사","immune system disorder":"면역류마","neoplasm":"종양","cancer":"종양","disorder of ear":"이비인후"}

def group_mondo(cid):
    c = reg.get(cid) or {}
    top = (c.get("taxonomy") or {}).get("top_category")
    return MONDO_LABEL.get(top) if top else group_of(cid)   # fallback to specialty for the ~56% w/o MONDO

def group_of(cid):
    c = reg.get(cid)
    if not c:
        return "기타"
    h = (c.get("evidence") or {}).get("harrison") or {}
    if h.get("part") in PART:
        return PART[h["part"]]
    sp = c.get("specialty")
    if sp:
        head = re.split(r"[/· ]", sp)[0]
        return SPEC.get(sp) or SPEC.get(head) or "기타"
    if c.get("source") == "heme_onc_curriculum_expansion":
        return "혈액종양"
    return "기타"

cov = Counter()
for r in rel:
    for cid in r["disease_concept_id"]:
        cov[cid] += 1

reg_keys = set(reg.keys())
EDGE_TYPES = ["differential_of", "caused_by", "treated_with", "diagnosed_by"]

# collect edges: keep an edge if the target is an in-registry concept (disease-disease network)
G = nx.Graph()
edge_list = []
for cid, c in reg.items():
    edges = c.get("edges") or {}
    for et in EDGE_TYPES:
        for ep in edges.get(et, []):
            tid = ep.get("id") if isinstance(ep, dict) else ep
            if not tid or tid == cid:
                continue
            if tid in reg_keys:                     # disease-disease / registry endpoint
                edge_list.append((cid, tid, et))
                G.add_edge(cid, tid)

# only nodes with degree >= 1 are shown
if G.number_of_nodes() == 0:
    OUT.write_text("<p style='font-family:sans-serif;padding:2rem'>아직 엣지가 없습니다 (P2 미완).</p>", encoding="utf-8")
    print("no edges yet — wrote placeholder"); raise SystemExit

# keep the giant connected component for a clean main graph; note what is dropped
comps = sorted(nx.connected_components(G), key=len, reverse=True)
giant = G.subgraph(comps[0]).copy()
DROPPED_NODES = G.number_of_nodes() - giant.number_of_nodes()
DROPPED_COMPS = len(comps) - 1
G = giant
try:
    pos = nx.kamada_kawai_layout(G)
except Exception:
    pos = nx.spring_layout(G, k=2.4 / (G.number_of_nodes() ** 0.5), iterations=300, seed=42)
xs = [p[0] for p in pos.values()]; ys = [p[1] for p in pos.values()]
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
W, Hh, PAD = 1600, 1100, 60
def sx(x): return PAD + (x - minx) / (maxx - minx + 1e-9) * (W - 2 * PAD)
def sy(y): return PAD + (y - miny) / (maxy - miny + 1e-9) * (Hh - 2 * PAD)

deg = dict(G.degree())
nodes = []
for nid in G.nodes():
    ko = next((a for a in reg.get(nid, {}).get("aliases", []) if any("가" <= ch <= "힣" for ch in a)), "")
    g = group_of(nid); gm = group_mondo(nid)
    _c = reg.get(nid) or {}; _ev = _c.get("evidence") or {}
    _h = _ev.get("harrison") or {}; _x = _ev.get("ontology_xref") or {}
    nodes.append({"id": nid, "ko": ko or nid.replace("_", " "), "x": round(sx(pos[nid][0]), 1),
                  "y": round(sy(pos[nid][1]), 1), "g": g, "gm": gm, "c": GROUP_COLORS.get(g, "#9a917c"),
                  "deg": deg.get(nid, 0), "cov": cov.get(nid, 0),
                  "h": (f"Harrison Ch{_h['chapter']} p{_h['page']}" if _h.get("chapter") else ""),
                  "mondo": _x.get("mondo_id", "")})
# dedupe edges (undirected) keeping a representative type; only edges inside the giant component
gnodes = set(G.nodes())
seen = set(); edges = []
for s, t, et in edge_list:
    if s not in gnodes or t not in gnodes:
        continue
    key = tuple(sorted((s, t)))
    if key in seen:
        continue
    seen.add(key); edges.append({"s": s, "t": t, "et": et})

DATA = {"nodes": nodes, "edges": edges,
        "stats": {"n": len(nodes), "e": len(edges), "groups": dict(Counter(n["g"] for n in nodes))}}
DATA_JSON = json.dumps(DATA, ensure_ascii=False)

HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>P:accine 개념 그래프</title>
<style>
 :root{--paper:#f4efe4;--ink:#241f18;--muted:#8a8271;--line:#e4dccb;--teal:#0e7c7b;--surface:#fffdf8}
 *{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--paper);color:var(--ink);font-family:"Pretendard",-apple-system,"Malgun Gothic",sans-serif}
 .top{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;align-items:center;background:var(--surface)}
 .top h1{font-size:18px;margin:0}.top .st{font-size:12px;color:var(--muted)}
 .top input{margin-left:auto;padding:8px 11px;border:1px solid var(--line);border-radius:8px;background:var(--paper);font-size:13px;min-width:200px}
 .legend{display:flex;flex-wrap:wrap;gap:10px;padding:8px 18px;font-size:11px;color:var(--muted);border-bottom:1px solid var(--line);background:var(--surface)}
 .legend .k{display:inline-flex;align-items:center;gap:5px}.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
 #wrap{position:absolute;top:0;left:0;right:0;bottom:0;overflow:hidden;cursor:grab}#wrap.drag{cursor:grabbing}
 svg{display:block}line.edge{stroke:#c9bfa9;stroke-width:1}line.edge.hl{stroke:#0e7c7b;stroke-width:2}
 circle.node{stroke:#fff;stroke-width:1.5;cursor:pointer}circle.node.dim{opacity:.12}text.lbl{font-size:11px;fill:#3a352b;pointer-events:none}text.lbl.dim{opacity:.08}
 #tip{position:fixed;pointer-events:none;background:#241f18;color:#f4efe4;border-radius:8px;padding:8px 10px;font-size:12px;opacity:0;transition:.1s;z-index:9;max-width:240px}
 #tip .id{font-family:"IBM Plex Mono",monospace;color:#8fd0c6;font-size:10px}
 .hint{position:fixed;bottom:12px;left:14px;font-size:11px;color:var(--muted);background:rgba(255,253,248,.85);padding:5px 9px;border-radius:6px}
 #facet{margin-left:auto;padding:7px 12px;border:1px solid var(--teal);border-radius:8px;background:var(--paper);color:var(--teal);font-size:12px;cursor:pointer;font-weight:600}
 #facet:hover{background:var(--teal);color:#fff}.top input{margin-left:0}
</style></head><body>
<div class="top"><h1>P:accine 임상의학 개념 그래프</h1><span class="st">거대 연결요소 __N__ 개념 · __E__ 감별/근거 엣지 (소규모 __DC__군 __DN__개념 별도) · 스크롤=줌, 드래그=이동, 호버=이웃 강조</span>
<button id="facet" title="색상 그룹 전환">색상: 진료과</button>
<input id="q" placeholder="개념 검색…" autocomplete="off"></div>
<div class="legend" id="legend"></div>
<div id="wrap"><svg id="svg"></svg></div>
<div id="tip"></div><div class="hint">엣지 = P2 저작 differential_of/caused_by/treated_with/diagnosed_by (레지스트리 개념 간). needs_review 초안.</div>
<script>
const DATA=__DATA__;const {nodes,edges}=DATA;
const NIX={};nodes.forEach(n=>NIX[n.id]=n);
const adj={};nodes.forEach(n=>adj[n.id]=new Set());
edges.forEach(e=>{if(NIX[e.s]&&NIX[e.t]){adj[e.s].add(e.t);adj[e.t].add(e.s);}});
const svg=document.getElementById('svg');const NS='http://www.w3.org/2000/svg';
let vb={x:0,y:0,w:1600,h:1100};function setVB(){svg.setAttribute('viewBox',`${vb.x} ${vb.y} ${vb.w} ${vb.h}`);}
svg.setAttribute('width','100%');svg.setAttribute('height','100%');setVB();
const gE=document.createElementNS(NS,'g'),gN=document.createElementNS(NS,'g'),gL=document.createElementNS(NS,'g');
svg.appendChild(gE);svg.appendChild(gN);svg.appendChild(gL);
const eEls=edges.map(e=>{const l=document.createElementNS(NS,'line');const a=NIX[e.s],b=NIX[e.t];if(!a||!b)return null;
 l.setAttribute('x1',a.x);l.setAttribute('y1',a.y);l.setAttribute('x2',b.x);l.setAttribute('y2',b.y);l.setAttribute('class','edge');l._e=e;gE.appendChild(l);return l;}).filter(Boolean);
const maxDeg=Math.max(...nodes.map(n=>n.deg));
nodes.forEach(n=>{const c=document.createElementNS(NS,'circle');const r=4+Math.sqrt(n.deg)*2.4;
 c.setAttribute('cx',n.x);c.setAttribute('cy',n.y);c.setAttribute('r',r);c.setAttribute('fill',n.c);c.setAttribute('class','node');c._n=n;c._r=r;gN.appendChild(c);
 if(n.deg>=5){const t=document.createElementNS(NS,'text');t.setAttribute('x',n.x+r+2);t.setAttribute('y',n.y+3);t.setAttribute('class','lbl');t.textContent=n.ko;t._n=n;gL.appendChild(t);}
 c.addEventListener('mousemove',ev=>tip(ev,n));c.addEventListener('mouseleave',clr);c.addEventListener('mouseenter',()=>hl(n));});
const tp=document.getElementById('tip');
function tip(ev,n){tp.innerHTML=`<b>${n.ko}</b><div class="id">${n.id}</div><div>${n[facet]} · 이웃 ${n.deg} · 문항 ${n.cov}</div>`+(n.h?`<div class="id">${n.h}</div>`:'')+(n.mondo?`<div class="id">${n.mondo}</div>`:'');tp.style.opacity=1;tp.style.left=(ev.clientX+12)+'px';tp.style.top=(ev.clientY+12)+'px';}
function clr(){tp.style.opacity=0;}
function hl(n){const keep=new Set([n.id,...adj[n.id]]);
 gN.querySelectorAll('circle').forEach(c=>c.classList.toggle('dim',!keep.has(c._n.id)));
 gL.querySelectorAll('text').forEach(t=>t.classList.toggle('dim',!keep.has(t._n.id)));
 eEls.forEach(l=>{const on=(l._e.s===n.id||l._e.t===n.id);l.classList.toggle('hl',on);l.style.opacity=on?1:.15;});}
function unhl(){gN.querySelectorAll('.dim').forEach(c=>c.classList.remove('dim'));gL.querySelectorAll('.dim').forEach(t=>t.classList.remove('dim'));eEls.forEach(l=>{l.classList.remove('hl');l.style.opacity=1;});}
document.getElementById('wrap').addEventListener('mouseleave',unhl);
gN.addEventListener('mouseleave',unhl);
// zoom
const wrap=document.getElementById('wrap');
wrap.addEventListener('wheel',e=>{e.preventDefault();const s=e.deltaY>0?1.12:0.89;const r=svg.getBoundingClientRect();
 const mx=vb.x+(e.clientX-r.left)/r.width*vb.w,my=vb.y+(e.clientY-r.top)/r.height*vb.h;
 vb.w*=s;vb.h*=s;vb.x=mx-(e.clientX-r.left)/r.width*vb.w;vb.y=my-(e.clientY-r.top)/r.height*vb.h;setVB();},{passive:false});
let drag=null;wrap.addEventListener('mousedown',e=>{drag={x:e.clientX,y:e.clientY,vx:vb.x,vy:vb.y};wrap.classList.add('drag');});
window.addEventListener('mousemove',e=>{if(!drag)return;const r=svg.getBoundingClientRect();vb.x=drag.vx-(e.clientX-drag.x)/r.width*vb.w;vb.y=drag.vy-(e.clientY-drag.y)/r.height*vb.h;setVB();});
window.addEventListener('mouseup',()=>{drag=null;wrap.classList.remove('drag');});
// search
document.getElementById('q').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();
 if(!q){unhl();return;}gN.querySelectorAll('circle').forEach(c=>{const hit=c._n.id.includes(q)||c._n.ko.toLowerCase().includes(q);c.classList.toggle('dim',!hit);});
 gL.querySelectorAll('text').forEach(t=>{const hit=t._n.id.includes(q)||t._n.ko.toLowerCase().includes(q);t.classList.toggle('dim',!hit);});});
// legend + facet toggle (진료과 specialty  <->  MONDO 표준분류)
const L=document.getElementById('legend');const GC=__GC__;const circles=[...gN.querySelectorAll('circle')];
let facet='g';
function colorFor(n){return GC[n[facet]]||'#9a917c';}
function draw(){
 circles.forEach(c=>c.setAttribute('fill',colorFor(c._n)));
 const cnt={};nodes.forEach(n=>cnt[n[facet]]=(cnt[n[facet]]||0)+1);
 L.innerHTML='';Object.entries(cnt).sort((a,b)=>b[1]-a[1]).forEach(([g,n])=>{const k=document.createElement('span');k.className='k';
  k.innerHTML=`<span class="dot" style="background:${GC[g]||'#9a917c'}"></span>${g} ${n}`;L.appendChild(k);});
}
draw();
document.getElementById('facet').addEventListener('click',e=>{facet=(facet==='g')?'gm':'g';
 e.target.textContent=(facet==='g')?'색상: 진료과':'색상: MONDO 표준분류';draw();});
</script></body></html>"""

HTML = (HTML.replace("__N__", str(len(nodes))).replace("__E__", str(len(edges)))
        .replace("__DC__", str(DROPPED_COMPS)).replace("__DN__", str(DROPPED_NODES))
        .replace("__DATA__", DATA_JSON).replace("__GC__", json.dumps(GROUP_COLORS, ensure_ascii=False)))
OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT.name} · giant {len(nodes)} nodes · {len(edges)} edges · dropped {DROPPED_NODES} nodes/{DROPPED_COMPS} small comps · groups {len(DATA['stats']['groups'])}")
