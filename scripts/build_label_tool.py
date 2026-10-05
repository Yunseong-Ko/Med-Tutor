#!/usr/bin/env python3
"""사람이 직접 이미지 라벨링하는 로컬 HTML 도구 v3 (해설 전문 병렬 표시).

⚠ 교훈(2026-08, 라벨 153건 유실 사고): 원인은 저장 필터였다 — 드롭다운 미입력 행을
  save()가 조용히 걸러 버려 입력 전량이 날아갔다. v3 규칙: **어떤 행도 조용히 버리지
  않는다.** 필수 필드가 비어도 저장하고 needs_fix=true로 표시한다. '사용 안 함' 체크만
  사람이 명시한 제외로 허용한다. 이 규칙을 되돌리는 수정 금지.

v3 변경(설문 T2 "초음파라 해놓고 CT" 대응, 스키마 v3):
  - modality: 표준 enum(modality_lexicon.MODALITY_ENUM) 드롭다운 **필수**
  - modality_detail(세부) · body_region(부위) · laterality(좌/우/양측/해당없음)
  - key_finding(핵심 소견 1줄, 필수) · quality_flag(화질 불량 체크)
  - 기존 labels_manual.json(v2)을 migrate_label_row로 변환해 프리필

레이아웃: 문항 단위 행(row)
  [왼쪽] 이미지(클릭 확대) + 입력칸  [오른쪽] 문두 전문 + 풀이(해설) 전문
자동 저장(localStorage) · [JSON 저장]으로 labels_manual_v3.json 내려받기.
출력: data_private/professor_items/pma_labels_v2/label_tool.html
"""
import html
import json
import re
from pathlib import Path

from modality_lexicon import LEGACY_MODALITY_MAP, MODALITY_ENUM, migrate_label_row

OUT = Path("data_private/professor_items/pma_labels_v2")

# 세부검사 자동완성 후보: 레거시 맵의 세부값 + 자주 쓰는 구체 검사명
MODALITY_DETAILS = sorted(
    {d for _, (_, d, _) in LEGACY_MODALITY_MAP.items() if d}
    | {"위내시경", "대장내시경", "기관지내시경", "조영증강CT", "HRCT", "경질초음파"}
)
LATERALITIES = ("해당없음", "좌", "우", "양측")


def hl(text: str) -> str:
    """진단명 후보가 될 만한 표현을 시각적으로 강조(진단/치료/검사 키워드)."""
    t = html.escape(text or "")
    t = re.sub(r"(정답[은는]?\s*[①-⑤]?\s*[0-9]?[번]?)", r"<mark class='ans'>\1</mark>", t)
    t = re.sub(r"(진단(은|명)?\s*[:은는]?)", r"<mark class='dx'>\1</mark>", t)
    return t


def js_json(obj) -> str:
    """HTML 인라인 <script>에 안전하게 심을 JSON(</script> 조기 종료 방지)."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def load_prefill() -> dict:
    """기존 v2 라벨(labels_manual.json) → image 파일명 키의 v3 프리필 맵."""
    mp = OUT / "labels_manual.json"
    if not mp.exists():
        return {}
    pre = {}
    for r in json.loads(mp.read_text(encoding="utf-8")):
        v3 = migrate_label_row(r)
        pre[r["image"]] = {k: v3.get(k, "") for k in (
            "dx", "modality", "modality_detail", "body_region", "laterality",
            "key_finding", "quality_flag", "needs_fix", "note")}
    return pre


def main():
    led = json.loads((OUT / "label_ledger.json").read_text(encoding="utf-8"))
    prefill = load_prefill()
    sug = set()
    try:
        reg = json.loads(Path("data_private/concept_registry.json").read_text(encoding="utf-8"))["concepts"]
        for cid, c in reg.items():
            for a in (c.get("aliases") or []):
                if any("가" <= ch <= "힣" for ch in str(a)):
                    sug.add(str(a))
    except Exception:
        pass
    datalist = "".join(f"<option value='{html.escape(s)}'>" for s in sorted(sug)[:1500])
    detlist = "".join(f"<option value='{html.escape(s)}'>" for s in MODALITY_DETAILS)

    rows, n = [], 0
    for r in led:
        for im in r["images"]:
            n += 1
            rid = f"{r['key']}__{im['sha12']}"
            opts = "<option value=''>— 검사종류(필수) —</option>" + "".join(
                f"<option>{m}</option>" for m in MODALITY_ENUM)
            latopts = "".join(f"<option>{v}</option>" for v in LATERALITIES)
            guess = r.get("modality_guess") or ""
            qt = r.get("q_text", "")
            st = r.get("sol_text", "")
            rows.append(f"""
<div class="row" data-id="{html.escape(rid)}" data-img="{html.escape(im['file'])}" id="r{n}">
  <div class="left">
    <div class="num">#{n}</div>
    <img src="images/{html.escape(im['file'])}" loading="lazy" onclick="zoom(this)">
    <div class="meta">{html.escape(r['turn'])}턴 {html.escape(r['period'])}교시 <b>{r['qno']}번</b>
      · {html.escape(r.get('subject_hint',''))}</div>
    <label class="use"><input type="checkbox" class="f-use" checked> 문항 자료로 사용</label>
    <div class="hint">자동추정(참고): {html.escape(guess) or '없음'}</div>
    <select class="f-mod req" title="검사종류(필수)">{opts}</select>
    <div class="pair">
      <input class="f-det" list="detlist" placeholder="세부검사(선택)">
      <input class="f-reg" placeholder="부위(선택)">
    </div>
    <div class="pair">
      <select class="f-lat" title="좌우측성">{latopts}</select>
      <label class="qf"><input type="checkbox" class="f-qf"> 화질 불량</label>
    </div>
    <input class="f-dx req" list="dxlist" placeholder="진단명(필수) ← 오른쪽 풀이 보고 입력">
    <input class="f-kf req" placeholder="핵심 소견 1줄(필수) 예: 우상엽 공동성 병변">
    <input class="f-note" placeholder="메모(선택)">
  </div>
  <div class="right">
    <div class="sec">문항</div><div class="txt q">{hl(qt) or '<i>(문두 텍스트 없음)</i>'}</div>
    <div class="sec">풀이 / 해설</div><div class="txt s">{hl(st) or '<i>(풀이 텍스트 없음)</i>'}</div>
  </div>
</div>""")

    doc = f"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<title>PMA 이미지 라벨링 v3 ({n}장)</title>
<style>
body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#eef2f7;margin:0;padding:0 0 70px}}
header{{position:sticky;top:0;z-index:9;background:#0e7c7b;color:#fff;padding:11px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
header b{{font-size:16px}} .stat{{font-size:13px;opacity:.92}}
button{{background:#fff;color:#0b5450;border:0;border-radius:8px;padding:7px 13px;font-weight:800;cursor:pointer}}
button.ghost{{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.6)}}
.row{{display:grid;grid-template-columns:340px 1fr;gap:16px;background:#fff;border:1px solid #dbe3ec;
     border-radius:12px;margin:14px;padding:12px;scroll-margin-top:70px}}
.row.off{{opacity:.42}} .row.done{{border-color:#0e7c7b;box-shadow:0 0 0 2px #d5efee inset}}
.row.fix{{border-color:#d97706;box-shadow:0 0 0 2px #fef3c7 inset}}
.num{{font-size:12px;font-weight:900;color:#94a3b8}}
.left img{{width:100%;max-height:300px;object-fit:contain;background:#fafafa;border-radius:8px;cursor:zoom-in}}
.meta{{font-size:12px;color:#475569;font-weight:700;margin:6px 0}}
.use,.qf{{display:block;font-size:12px;color:#334155;margin:3px 0}}
.qf{{display:flex;align-items:center;gap:4px;white-space:nowrap}}
.hint{{font-size:11px;color:#a0aab6;margin:2px 0}}
select,input{{width:100%;box-sizing:border-box;margin:4px 0;padding:7px 9px;border:1px solid #cbd5e1;border-radius:7px;font-size:14px}}
.pair{{display:flex;gap:6px;align-items:center}}
.req{{border-color:#0e7c7b}} .req.miss{{border-color:#d97706;background:#fffbeb}}
.f-dx{{font-weight:700}}
.right{{min-width:0}}
.sec{{font-size:11px;font-weight:900;color:#0e7c7b;margin:6px 0 3px;letter-spacing:1px}}
.txt{{font-size:13.5px;line-height:1.65;color:#1f2937;background:#f8fafc;border:1px solid #eef2f7;
     border-radius:8px;padding:10px 12px;max-height:230px;overflow:auto;white-space:pre-wrap;word-break:break-word}}
.txt.s{{background:#f0fdfa}}
mark.ans{{background:#fde68a}} mark.dx{{background:#bbf7d0}}
#zoomer{{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;align-items:center;justify-content:center;z-index:99}}
#zoomer img{{max-width:95%;max-height:95%}}
footer{{position:fixed;bottom:0;left:0;right:0;background:#111827;color:#fff;padding:9px 16px;display:flex;gap:14px;align-items:center;font-size:13px}}
</style></head><body>
<header>
  <b>PMA 이미지 라벨링 v3</b>
  <span class="stat">{n}장 · <b>검사종류·진단명·핵심소견</b>이 필수 (미입력도 저장은 되고 needs_fix로 표시)</span>
  <button onclick="save()">💾 JSON 저장</button>
  <button class="ghost" onclick="jumpNext()">다음 미완료 ↓</button>
</header>
<datalist id="dxlist">{datalist}</datalist>
<datalist id="detlist">{detlist}</datalist>
{''.join(rows)}
<div id="zoomer" onclick="this.style.display='none'"><img></div>
<footer><span id="prog"></span><span style="opacity:.7">자동 저장됩니다 · 끝나면 💾 JSON 저장 → labels_manual_v3.json</span></footer>
<script>
const KEY='pma_manual_labels_v2';           // 진행분 보존을 위해 v2 키 유지(값은 아래서 v3로 승격)
const ENUM={js_json(list(MODALITY_ENUM))};
const LEGACY={js_json({k: list(v) for k, v in LEGACY_MODALITY_MAP.items()})};  // 구 라벨값 → [modality, 세부, 부위]
const PREFILL={js_json(prefill)};           // 기존 labels_manual.json(v2→v3 변환) 프리필
function state(){{ try{{return JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{return {{}}}} }}
function put(id,o){{ const s=state(); s[id]=Object.assign(s[id]||{{}},o); localStorage.setItem(KEY,JSON.stringify(s)); prog(); }}
document.querySelectorAll('.row').forEach(c=>{{
  const id=c.dataset.id, img=c.dataset.img;
  let s=state()[id]||{{}};
  // localStorage 우선, 없으면 기존 라벨 파일 프리필
  if(!s.dx && !s.modality && PREFILL[img]) s=Object.assign({{}},PREFILL[img],s);
  // 구 라벨값(가슴X선·ECG…)은 표준 enum + 세부/부위로 승격
  if(s.modality && !ENUM.includes(s.modality) && LEGACY[s.modality]){{
    const m=LEGACY[s.modality];
    s.modality_detail=s.modality_detail||m[1]; s.body_region=s.body_region||m[2]; s.modality=m[0];
  }}
  const use=c.querySelector('.f-use'),mod=c.querySelector('.f-mod'),det=c.querySelector('.f-det'),
        reg=c.querySelector('.f-reg'),lat=c.querySelector('.f-lat'),qf=c.querySelector('.f-qf'),
        dx=c.querySelector('.f-dx'),kf=c.querySelector('.f-kf'),note=c.querySelector('.f-note');
  if(s.use===false) use.checked=false;
  if(s.modality) mod.value=s.modality; if(s.modality_detail) det.value=s.modality_detail;
  if(s.body_region) reg.value=s.body_region; lat.value=s.laterality||'해당없음';
  qf.checked=!!s.quality_flag; if(s.dx) dx.value=s.dx; if(s.key_finding) kf.value=s.key_finding;
  if(s.note) note.value=s.note;
  const sync=()=>{{
    const filled=!!mod.value&&!!dx.value.trim()&&!!kf.value.trim();
    c.classList.toggle('off',!use.checked);
    c.classList.toggle('done', use.checked&&filled);
    c.classList.toggle('fix', use.checked&&!filled&&(!!dx.value.trim()||!!mod.value||!!kf.value.trim()));
    mod.classList.toggle('miss',!mod.value); dx.classList.toggle('miss',!dx.value.trim());
    kf.classList.toggle('miss',!kf.value.trim());
    put(id,{{use:use.checked,modality:mod.value,modality_detail:det.value.trim(),
      body_region:reg.value.trim(),laterality:lat.value,quality_flag:qf.checked?'저화질':'',
      dx:dx.value.trim(),key_finding:kf.value.trim(),note:note.value.trim(),image:img}});
  }};
  [use,mod,det,reg,lat,qf,dx,kf,note].forEach(el=>{{el.addEventListener('change',sync);el.addEventListener('input',sync);}});
  sync();
}});
function prog(){{ const s=state();
  const d=Object.values(s).filter(v=>v.use!==false&&v.dx&&v.modality&&v.key_finding).length;
  document.getElementById('prog').textContent=`완료 ${{d}} / {n}`; }}
function jumpNext(){{ const el=[...document.querySelectorAll('.row')].find(c=>!c.classList.contains('done')&&!c.classList.contains('off'));
  if(el) el.scrollIntoView({{behavior:'smooth',block:'start'}}); else alert('모두 완료!'); }}
function zoom(i){{ const z=document.getElementById('zoomer'); z.querySelector('img').src=i.src; z.style.display='flex'; }}
function save(){{ const s=state(),rows=[]; let miss=0,off=0;
  // ⚠ 2026-08 교훈(153건 유실): 저장 필터가 미입력 행을 조용히 버려 입력 전량이 날아갔다.
  // 어떤 행도 조용히 버리지 말 것 — 필수 미입력도 저장하고 needs_fix=true로만 표시한다.
  // '사용 안 함' 체크만 사람이 명시한 제외로 허용(개수는 아래 alert에 보고).
  document.querySelectorAll('.row').forEach(c=>{{ const v=s[c.dataset.id]||{{}};
    if(v.use===false){{off++;return;}}
    const missing=[];
    if(!(v.dx||'').trim()) missing.push('dx');
    if(!(v.modality||'')) missing.push('modality');
    if(!(v.key_finding||'').trim()) missing.push('key_finding');
    if(missing.length) miss++;
    rows.push({{key:c.dataset.id.split('__')[0],image:c.dataset.img,
      dx:(v.dx||'').trim(),modality:v.modality||'',modality_detail:(v.modality_detail||'').trim(),
      body_region:(v.body_region||'').trim(),laterality:v.laterality||'해당없음',
      key_finding:(v.key_finding||'').trim(),quality_flag:v.quality_flag||'',
      needs_fix:missing.length>0,fix_reason:missing.join(','),note:(v.note||'').trim()}}); }});
  const b=new Blob([JSON.stringify(rows,null,1)],{{type:'application/json'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download='labels_manual_v3.json'; a.click();
  alert(rows.length+'행 저장(전량) · 미비 needs_fix '+miss+' · 사용제외 '+off+
        ' — 어떤 행도 조용히 버리지 않았습니다 → Downloads/labels_manual_v3.json'); }}
prog();
</script></body></html>"""
    p = OUT / "label_tool.html"
    p.write_text(doc, encoding="utf-8")
    withtxt = sum(1 for r in led if r.get("sol_text"))
    print(f"[라벨링 도구 v3] {p}")
    print(f"  이미지 {n}장 · 풀이 텍스트 보유 문항 {withtxt}/{len(led)} · 진단명 자동완성 {len(sug)}개")
    print(f"  프리필(기존 v2 라벨 승격) {len(prefill)}건 · modality enum {len(MODALITY_ENUM)}종")


if __name__ == "__main__":
    raise SystemExit(main())
