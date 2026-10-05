#!/usr/bin/env python3
"""혈액/조직 현미경 사진 판독 카드 → Anki 덱 (개인 학습용).

앞면: 검체칩(예 말초혈액도말) + 사진 + "이 소견을 판독하세요"
뒷면: 식별 + 판독 단서 + 감별 + 임상맥락 + 핵심 + confidence 배지
입력: data_private/histo_cards/cards.json  (+ media/)
출력: data_private/anki_exports/paccine_혈액종양_조직사진판독_YYYYMMDD.apkg
자동생성물 needs_review — 확신 낮은 카드는 배지로 표시, 강의 슬라이드로 재확인 전제.
"""

import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path

import genanki

SRC = Path("data_private/histo_cards")
MEDIA = SRC / "media"
OUT_DIR = Path("data_private/anki_exports")
STAMP = datetime.now().strftime("%Y%m%d")
MODEL_ID = 1607399111
PARENT = "P:accine::혈액종양 조직사진 판독"

LECT_LABEL = {
    "조혈계조직학": "조혈계 조직학", "PB_BM": "말초혈액·골수(PB/BM)", "혈액검사": "혈액검사",
    "철결핍": "철결핍성 빈혈", "기타_빈혈": "빈혈 감별", "대구성빈혈": "대구성 빈혈",
    "후천성용혈": "후천 용혈성 빈혈", "선천용혈": "선천 용혈성 빈혈", "소아_빈혈": "소아 빈혈",
    "백혈구질환1": "백혈구질환 1", "백혈구질환2": "백혈구질환 2·비장",
    "acute_leukemia": "급성 백혈병", "만성백혈병1": "만성 골수성 백혈병",
    "만성백혈병2": "만성 림프구성 백혈병", "골수증식성": "골수증식성 종양",
    "PBS_BME": "PB·BM 사례", "Lymphoma": "림프종 병리",
}


def sid(v, n=10):
    return int(hashlib.sha1(str(v).encode()).hexdigest()[:n], 16)


def ht(v):
    return html.escape(str(v or "")).replace("\n", "<br>")


def tg(v):
    return re.sub(r"[^\w:.-]+", "_", str(v or "").strip()).strip("_")


def label_of(lid):
    for k, v in LECT_LABEL.items():
        if k in lid:
            return v
    return lid


MODEL = genanki.Model(
    MODEL_ID, "P:accine 조직사진 판독",
    fields=[{"name": n} for n in ["Specimen", "Image", "Answer", "Features",
                                  "Differential", "Context", "Teaching", "Confidence", "Source"]],
    templates=[{
        "name": "판독",
        "qfmt": """
<section class="spec">{{Specimen}}</section>
<section class="img">{{Image}}</section>
<section class="ask">이 소견을 판독하세요 — 무엇이 보이고, 무엇을 시사합니까?</section>
""",
        "afmt": """
{{FrontSide}}
<hr id=answer>
<section class="ans">{{Answer}}</section>
{{#Features}}<section class="panel"><span class="pt">판독 단서</span>{{Features}}</section>{{/Features}}
{{#Differential}}<section class="panel"><span class="pt">감별</span>{{Differential}}</section>{{/Differential}}
{{#Context}}<section class="panel"><span class="pt">임상 맥락</span>{{Context}}</section>{{/Context}}
{{#Teaching}}<section class="panel key"><span class="pt">핵심</span>{{Teaching}}</section>{{/Teaching}}
{{#Confidence}}<section class="conf">{{Confidence}}</section>{{/Confidence}}
<section class="src">{{Source}}</section>
""",
    }],
    css="""
.card{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;font-size:18px;line-height:1.55;color:#172033;background:#faf7f2;text-align:left;}
.spec{display:inline-block;margin-bottom:10px;padding:5px 12px;border-radius:999px;background:#0e7c7b;color:#fff;font-size:13px;font-weight:800;}
.img{text-align:center;margin:8px 0;}
.img img{max-width:100%;max-height:460px;border:1px solid #cbb;border-radius:10px;}
.ask{margin-top:10px;color:#6b5a3e;font-weight:700;}
.ans{margin:14px 0;padding:14px 16px;border-left:5px solid #0e7c7b;border-radius:12px;background:#e6f3f2;font-size:20px;font-weight:800;color:#0b5450;}
.panel{margin:12px 0;padding:12px 15px;border:1px solid #e5ddcf;border-radius:12px;background:#fff;}
.pt{display:block;margin-bottom:6px;color:#0e7c7b;font-size:13px;font-weight:900;}
.panel ul{margin:0;padding-left:20px;}
.key{background:#fbf5e9;}
.conf{margin-top:10px;font-size:13px;font-weight:800;}
.conf.low{color:#b45309;} .conf.med{color:#a16207;} .conf.high{color:#15803d;}
.src{margin-top:10px;color:#8a7a5c;font-size:12px;}
"""
)


def features_html(feats):
    feats = [f for f in (feats or []) if f]
    if not feats:
        return ""
    return "<ul>" + "".join(f"<li>{ht(f)}</li>" for f in feats) + "</ul>"


def conf_html(c):
    if not c:
        return ""
    cls = {"low": "low", "medium": "med", "high": "high"}.get(c, "med")
    txt = {"low": "⚠︎ 확신 낮음 — 강의 슬라이드로 재확인",
           "medium": "◐ 중간 확신 — 재확인 권장", "high": "● 확신 높음"}.get(c, c)
    return f'<span class="conf {cls}">{txt}</span>'


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cards = json.loads((SRC / "cards.json").read_text(encoding="utf-8"))
    decks, media_files, n = {}, [], 0
    for c in cards:
        img = c.get("image")
        if not img or not (MEDIA / img).exists():
            continue
        lab = label_of(c.get("lid", ""))
        deck_name = f"{PARENT}::{lab}"
        if deck_name not in decks:
            decks[deck_name] = genanki.Deck(sid(deck_name, 9), deck_name)
        spec = ht(c.get("category") or "현미경 사진")
        conf = c.get("confidence")
        note = genanki.Note(
            model=MODEL,
            fields=[spec, f'<img src="{ht(img)}">', ht(c.get("identification")),
                    features_html(c.get("key_features")), ht(c.get("differential")),
                    ht(c.get("dx_context")), ht(c.get("teaching_point")),
                    conf_html(conf), ht(lab)],
            tags=["paccine", "혈액종양", "조직사진판독", tg(c.get("lid")),
                  tg(f"검체::{c.get('category')}")] + ([f"검토플래그::low_confidence"] if conf == "low" else []),
            guid=f"{PARENT}::{c.get('lid')}::{c.get('idx')}")
        decks[deck_name].add_note(note)
        media_files.append(str(MEDIA / img))
        n += 1
    out = OUT_DIR / f"paccine_혈액종양_조직사진판독_{STAMP}.apkg"
    pkg = genanki.Package(list(decks.values()))
    pkg.media_files = sorted(set(media_files))
    pkg.write_to_file(str(out))
    (OUT_DIR / f"paccine_혈액종양_조직사진판독_{STAMP}.manifest.json").write_text(
        json.dumps({"deck": PARENT, "cards": n, "subdecks": len(decks),
                    "created_at": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {out}")
    print(f"  카드 {n} · 서브덱 {len(decks)}")


if __name__ == "__main__":
    raise SystemExit(main())
