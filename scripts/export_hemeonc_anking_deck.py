#!/usr/bin/env python3
"""혈액종양 강의노트 → AnKing식 Cloze 암기 덱 (개인 학습용).

AnKing Step Deck 구조를 학습해 그 스타일을 재현하되, 카드 내용은 **본인 강의노트**
(data_private/lecture_notes)에서 생성한 자체 콘텐츠다(AnKing 저작 카드 미복제).

카드 원칙(효과적인 카드 만들기 10원칙):
  Cloze · 최소화 · 구체성(하나의 답) · 트리거 · 최적화 · 개별화 · 쌍방향성 · 연합 · 이해⇋암기 · 반면교사

입력:  data_private/lecture_cards/cards_<lid>.json
       (allowlist data_private/lecture_cards/_include_lids.json 있으면 필터)
모델:  Cloze — 필드 Text/Extra/Mnemonic/Concept/Lecture/Evidence
서브덱: P:accine::혈액종양 암기(AnKing식)::<강의 라벨>
출력:  data_private/anki_exports/paccine_혈액종양_암기덱_AnKing식_YYYYMMDD.apkg
"""

import hashlib
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path

import genanki

# 재사용 가능: 환경변수로 소스/덱명/출력명 오버라이드(기본값은 기존 동작 유지).
SRC = Path(os.environ.get("ANKI_CARDS_DIR", "data_private/lecture_cards"))
OUT_DIR = Path("data_private/anki_exports")
STAMP = datetime.now().strftime("%Y%m%d")
MODEL_ID = 1987654321          # 고정(멱등)
DECK_SEED = 1987654322
PARENT = os.environ.get("ANKI_DECK_PARENT", "P:accine::혈액종양 암기(AnKing식)")
OUT_NAME = os.environ.get("ANKI_OUT_NAME", f"paccine_혈액종양_암기덱_AnKing식_{STAMP}")


def sid(v, digits=10):
    return int(hashlib.sha1(str(v).encode()).hexdigest()[:digits], 16)


def ht(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def tg(v):
    return re.sub(r"[^\w:./&-]+", "_", re.sub(r"\s+", "_", str(v or "").strip())).strip("_")


def lecture_label(lid, source_name):
    m = re.match(r"(\d{4})(\d{2})(\d{2})_([\d_]+교시)_(.+)", str(lid))
    if m:
        _, mo, da, gy, title = m.groups()
        base = (source_name or title).replace("_", " ").replace(".pdf", "").replace(".docx", "").strip()
        return f"{int(mo)}·{int(da)} {gy.replace('_','·')} {base}"
    return (source_name or lid).replace(".pdf", "").strip()


# --- Cloze 모델 (AnKing식) — P:accine 웜페이퍼+틸 브랜드 --------------------
MODEL = genanki.Model(
    MODEL_ID, "P:accine 혈액종양 Cloze (AnKing식)",
    model_type=genanki.Model.CLOZE,
    fields=[{"name": n} for n in ["Text", "Extra", "Mnemonic", "Concept", "Lecture", "Evidence"]],
    templates=[{
        "name": "Cloze",
        "qfmt": """
{{#Lecture}}<div class="src">{{Lecture}}</div>{{/Lecture}}
<div class="cloze-body">{{cloze:Text}}</div>
""",
        "afmt": """
{{#Lecture}}<div class="src">{{Lecture}}</div>{{/Lecture}}
<div class="cloze-body">{{cloze:Text}}</div>
{{#Extra}}<div class="panel extra"><span class="tag">보충</span>{{Extra}}</div>{{/Extra}}
{{#Mnemonic}}<div class="panel mnem"><span class="tag">암기</span>{{Mnemonic}}</div>{{/Mnemonic}}
<div class="foot">
  {{#Concept}}<span class="chip concept">{{Concept}}</span>{{/Concept}}
  {{#Evidence}}<span class="chip ev">{{Evidence}}</span>{{/Evidence}}
</div>
""",
    }],
    css="""
.card { font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;
  font-size:20px; line-height:1.7; color:#20302e; background:#faf7f2; text-align:left;
  padding:22px 18px; }
.src { display:inline-block; margin-bottom:14px; padding:5px 11px; border-radius:999px;
  background:#eef4f3; border:1px solid #cfe0dd; color:#0e7c7b; font-size:12.5px; font-weight:800;
  letter-spacing:.2px; }
.cloze-body { font-size:21px; font-weight:600; line-height:1.75; color:#152220; }
.cloze { color:#0e7c7b; font-weight:900; }
.cloze-body b, .cloze-body strong { color:#0b5f5c; }
hr { border:0; border-top:1px solid #e6ded2; margin:16px 0; }
.panel { margin:14px 0 0; padding:12px 15px; border-radius:13px; font-size:17px; line-height:1.6; }
.panel .tag { display:block; margin-bottom:5px; font-size:12px; font-weight:900; letter-spacing:.4px; }
.extra { background:#fff; border:1px solid #e6ded2; }
.extra .tag { color:#8a6d3b; }
.mnem  { background:#fdf6ec; border:1px solid #f0dcbb; }
.mnem  .tag { color:#b9791a; }
.foot { margin-top:16px; display:flex; flex-wrap:wrap; gap:7px; }
.chip { display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; }
.chip.concept { background:#0e7c7b; color:#fff; }
.chip.ev { background:#f3efe6; color:#6b5a3e; border:1px solid #e6ded2; }
.verify { color:#b23b3b; font-weight:800; }
img { max-width:100%; max-height:420px; border-radius:10px; border:1px solid #e6ded2; }
"""
)

def format_harrison(h):
    """온톨로지 근거(dict) → 'Harrison Ch.344 p.2605 — Title' 간결 표기."""
    if isinstance(h, str):
        return h
    if isinstance(h, dict):
        ch, pg, ti = h.get("chapter"), h.get("page"), h.get("title")
        s = "Harrison"
        if ch:
            s += f" Ch.{ch}"
        if pg:
            s += f" p.{pg}"
        if ti:
            s += f" — {ti}"
        return s
    return ""


SYS_ORDER = {  # 강의 흐름 기반 상위 계통(태그용)
    "조혈·기초": 0, "검사": 1, "RBC": 2, "WBC": 3, "지혈·혈전": 4,
    "종양·항암": 5, "이식": 6, "기타": 9,
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    allow = None
    allow_path = SRC / "_include_lids.json"
    if allow_path.exists():
        try:
            allow = set(json.loads(allow_path.read_text(encoding="utf-8")))
        except Exception:
            allow = None

    decks, n, dropped = [], 0, 0
    per_lecture = []
    for f in sorted(SRC.glob("cards_*.json"), key=lambda p: p.name):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        lid = d.get("lecture_id")
        if allow is not None and lid not in allow:
            continue
        cards = d.get("cards") or []
        if not cards:
            continue
        label = lecture_label(lid, d.get("source_name"))
        evidence = " · ".join(d.get("harrison") or [])
        deck = genanki.Deck(sid(f"{PARENT}::{label}", 9), f"{PARENT}::{label}")
        kept = 0
        for i, c in enumerate(cards, 1):
            text = (c.get("text") or "").strip()
            if "{{c" not in text:               # cloze 없는 카드는 스킵(품질 게이트)
                dropped += 1
                continue
            # Text/Extra는 ht()로 이스케이프해야 안전 — html.escape는 cloze `{{...}}`를
            # 건드리지 않으므로, 지문 속 '<80', '<책제목>' 같은 부등호가 HTML 태그로
            # 오인돼 렌더링에서 사라지는 문제를 막는다.
            text_f = ht(text)
            extra_f = ht(c.get("extra") or "")
            # verify 플래그 강조 (이스케이프된 평문 'verify'/'확인필요'를 span으로 치환)
            extra_f = re.sub(r"⚠︎?\s*(?:verify|확인\s*필요|확인\s*요)[:：]?",
                             '<span class="verify">⚠︎ 확인필요</span>', extra_f, flags=re.I)
            tags = ["paccine", "혈액종양", "AnKing식", tg(lid)]
            if c.get("system"):
                tags.append(tg(f"계통::{c['system']}"))
            if c.get("concept"):
                tags.append(tg(f"개념::{c['concept']}"))
            for t in (c.get("tags") or []):
                tags.append(tg(t))

            # 검증 플래그(verify_cards_ontology 워크플로 결과)
            v = c.get("verification") or {}
            onto_flagged = v.get("status") in ("error", "review") and v.get("dimension") == "ontology"

            # 온톨로지 근거: 카드 개념근거 우선(단, 매핑이 검증에서 flag되면 잘못된 근거이므로 강의근거로 대체)
            onto = c.get("ontology") or {}
            if onto.get("harrison") and not onto_flagged:
                ev_card = format_harrison(onto["harrison"])
            else:
                ev_card = evidence
            if onto.get("disease_concept_id") and not onto_flagged:
                tags.append(tg(f"온톨로지::{onto['disease_concept_id']}"))

            if v.get("status") in ("error", "review"):
                tags.append(tg(f"검토플래그::{v.get('dimension','기타')}"))
                badge = "⚠︎ 검토필요" if v["status"] == "review" else "⛔ 오류의심"
                iss = ht(v.get("issue") or "")
                extra_f = f'<div class="verify">{badge}</div>{iss}<br>' + extra_f

            note = genanki.Note(
                model=MODEL,
                fields=[text_f, extra_f,
                        ht(c.get("mnemonic")), ht(c.get("concept")),
                        ht(label), ht(ev_card) if "<" not in ev_card else ev_card],
                tags=sorted(set(t for t in tags if t)),
                guid=f"{PARENT}::{lid}::{i}::{sid(text,8)}")
            deck.add_note(note)
            kept += 1
            n += 1
        if kept:
            decks.append(deck)
            per_lecture.append((label, kept))

    out = OUT_DIR / f"{OUT_NAME}.apkg"
    genanki.Package(decks).write_to_file(str(out))
    manifest = {
        "deck": PARENT, "output": str(out), "model": "Cloze (AnKing식)",
        "card_count": n, "subdecks": len(decks), "dropped_no_cloze": dropped,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "data_private/lecture_notes → 10원칙 cloze 생성 · 자체콘텐츠",
        "per_lecture": [{"lecture": l, "cards": k} for l, k in per_lecture],
    }
    (OUT_DIR / f"{OUT_NAME}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {out}")
    print(f"  카드 {n} · 서브덱(강의) {len(decks)} · cloze없어 스킵 {dropped}")


if __name__ == "__main__":
    raise SystemExit(main())
