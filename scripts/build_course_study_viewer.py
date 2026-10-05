#!/usr/bin/env python3
"""Build a self-contained, file:// friendly study-note viewer.

The generated HTML embeds all Markdown text while keeping lecture images as
relative files under ``assets/``.  It therefore works without a server and is
also easy to serve from any static web server later.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import markdown


QUESTION_RE = re.compile(r"(?m)^###\s+(?:새\s+)?문항\s+\d+")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")


def render_markdown(text: str, note_dir: Path, output_dir: Path) -> str:
    text = FRONTMATTER_RE.sub("", text, count=1)
    rendered = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )

    # Notes live in notes/, so their ../assets references become assets/ in
    # the root viewer.  Absolute paths are relativized when possible.
    rendered = rendered.replace('src="../assets/', 'src="assets/')
    rendered = rendered.replace("src='../assets/", "src='assets/")
    for match in set(re.findall(r'src="([^"]+)"', rendered)):
        candidate = Path(html.unescape(match))
        if candidate.is_absolute():
            try:
                relative = candidate.relative_to(output_dir)
            except ValueError:
                continue
            rendered = rendered.replace(
                f'src="{match}"', f'src="{html.escape(relative.as_posix())}"'
            )
    return rendered


def document_record(
    *,
    key: str,
    title: str,
    subtitle: str,
    path: Path,
    output_dir: Path,
    group_id: str,
    date: str,
    expected_questions: int,
) -> dict:
    raw = path.read_text(encoding="utf-8")
    image_links = IMAGE_RE.findall(raw)
    image_records = []
    for link in image_links:
        if re.match(r"^[a-z]+://", link):
            image_records.append({"link": link, "external": True})
            continue
        image_path = (path.parent / html.unescape(link)).resolve()
        record = {
            "link": link,
            "external": False,
            "exists": image_path.exists(),
        }
        if image_path.exists():
            try:
                record["relative_path"] = image_path.relative_to(output_dir).as_posix()
            except ValueError:
                record["absolute_path"] = image_path.as_posix()
            record["sha256"] = hashlib.sha256(image_path.read_bytes()).hexdigest()
        image_records.append(record)
    return {
        "key": key,
        "dom_id": safe_id(key),
        "title": title,
        "subtitle": subtitle,
        "path": path,
        "relative_path": path.relative_to(output_dir).as_posix(),
        "group_id": group_id,
        "date": date,
        "expected_questions": expected_questions,
        "question_count": len(QUESTION_RE.findall(raw)),
        "image_count": len(image_links),
        "images": image_records,
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "html": render_markdown(raw, path.parent, output_dir),
    }


def main() -> None:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    output_path = args.output.resolve()
    output_dir = output_path.parent
    docs: list[dict] = []

    rapid_review = output_dir / "01_시험직전_통합복습.md"
    if rapid_review.exists():
        docs.append(
            document_record(
                key="rapid-review",
                title="시험 직전 통합복습",
                subtitle="전 범위 고빈도 개념 지도",
                path=rapid_review,
                output_dir=output_dir,
                group_id="rapid-review",
                date="",
                expected_questions=0,
            )
        )

    verification_record = output_dir / "02_제작_검증_기록.md"
    if verification_record.exists():
        docs.append(
            document_record(
                key="verification-record",
                title="제작·검증 기록",
                subtitle="원본·필기본·문항·Ontology QA",
                path=verification_record,
                output_dir=output_dir,
                group_id="verification-record",
                date="",
                expected_questions=0,
            )
        )

    for group in inventory["groups"]:
        note_path = Path(group["note_path"])
        if not note_path.exists():
            continue
        periods = ", ".join(str(period) for period in group["periods"])
        subtitle = f'{group["date"]} · {periods}교시'
        docs.append(
            document_record(
                key=group["group_id"],
                title=group["title"],
                subtitle=subtitle,
                path=note_path,
                output_dir=output_dir,
                group_id=group["group_id"],
                date=group["date"],
                expected_questions=group["expected_question_count"],
            )
        )

    lecture_docs = [doc for doc in docs if doc["group_id"].startswith("L")]
    total_questions = sum(doc["question_count"] for doc in lecture_docs)
    total_images = sum(doc["image_count"] for doc in lecture_docs)

    nav_items = []
    article_items = []
    last_date = None
    for index, doc in enumerate(docs):
        if doc["date"] and doc["date"] != last_date:
            formatted_date = datetime.strptime(doc["date"], "%Y%m%d").strftime("%m월 %d일")
            nav_items.append(
                f'<div class="date-label" data-date="{html.escape(doc["date"])}">'
                f"{html.escape(formatted_date)}</div>"
            )
            last_date = doc["date"]
        active = " active" if index == 0 else ""
        search_text = f'{doc["title"]} {doc["subtitle"]} {doc["group_id"]}'.lower()
        nav_items.append(
            f'<button class="note-link{active}" data-target="{doc["dom_id"]}" '
            f'data-search="{html.escape(search_text)}">'
            f'<span class="nav-title">{html.escape(doc["title"])}</span>'
            f'<span class="nav-meta">{html.escape(doc["subtitle"])}</span>'
            "</button>"
        )
        hidden = "" if index == 0 else " hidden"
        article_items.append(
            f'<article id="{doc["dom_id"]}" class="note-article{hidden}" '
            f'data-title="{html.escape(doc["title"])}">'
            '<div class="article-toolbar">'
            f'<span>{html.escape(doc["subtitle"])}</span>'
            f'<a href="{html.escape(doc["relative_path"])}">원본 Markdown 열기</a>'
            "</div>"
            f'{doc["html"]}'
            "</article>"
        )

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>혈액종양 AI 시험노트</title>
  <style>
    :root {{ color-scheme: light; --bg:#f4f6f8; --panel:#ffffff; --ink:#17202a;
      --muted:#667085; --line:#e4e7ec; --brand:#7f1d1d; --brand-soft:#fff1f2;
      --accent:#0f766e; --shadow:0 12px 35px rgba(17,24,39,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,
      BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif; line-height:1.72; }}
    .app {{ min-height:100vh; display:grid; grid-template-columns:320px minmax(0,1fr); }}
    aside {{ position:sticky; top:0; height:100vh; overflow:auto; background:#111827;
      color:white; padding:24px 18px; }}
    .brand {{ padding:0 8px 18px; }}
    .brand h1 {{ margin:0 0 5px; font-size:21px; }}
    .brand p {{ margin:0; color:#aeb8c7; font-size:13px; }}
    .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:7px; margin:14px 0; }}
    .stat {{ background:#1f2937; border:1px solid #344054; border-radius:10px; padding:9px 5px;
      text-align:center; }}
    .stat b {{ display:block; font-size:16px; }} .stat span {{ color:#aeb8c7; font-size:10px; }}
    #search {{ width:100%; background:#1f2937; color:white; border:1px solid #475467;
      border-radius:10px; padding:11px 12px; outline:none; }}
    #search:focus {{ border-color:#fca5a5; }}
    nav {{ margin-top:16px; }}
    .date-label {{ margin:20px 8px 7px; color:#98a2b3; font-size:11px; font-weight:700;
      letter-spacing:.08em; }}
    .note-link {{ width:100%; display:block; border:0; color:#d0d5dd; background:transparent;
      text-align:left; border-radius:9px; padding:10px; cursor:pointer; margin-bottom:2px; }}
    .note-link:hover {{ background:#1f2937; }}
    .note-link.active {{ background:#3f1d24; color:#fff; box-shadow:inset 3px 0 #fb7185; }}
    .nav-title,.nav-meta {{ display:block; }} .nav-title {{ font-weight:700; font-size:13px; }}
    .nav-meta {{ color:#98a2b3; font-size:10px; margin-top:2px; }}
    main {{ min-width:0; padding:38px clamp(18px,5vw,74px) 80px; }}
    .note-article {{ max-width:980px; margin:0 auto; background:var(--panel); border:1px solid var(--line);
      border-radius:18px; padding:clamp(22px,4vw,54px); box-shadow:var(--shadow); }}
    .note-article.hidden {{ display:none; }}
    .article-toolbar {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--line);
      padding-bottom:12px; color:var(--muted); font-size:12px; }}
    .article-toolbar a {{ color:var(--brand); text-decoration:none; font-weight:700; }}
    h1 {{ line-height:1.3; margin-top:28px; font-size:clamp(28px,4vw,43px); letter-spacing:-.04em; }}
    h2 {{ margin-top:44px; padding-bottom:9px; border-bottom:2px solid #f0f1f3; font-size:24px; }}
    h3 {{ margin-top:31px; color:#344054; font-size:19px; }}
    h4 {{ margin-top:24px; }}
    strong {{ color:#101828; }}
    blockquote {{ margin:20px 0; padding:15px 18px; border-left:4px solid var(--brand);
      background:var(--brand-soft); border-radius:0 10px 10px 0; }}
    table {{ width:100%; border-collapse:collapse; display:block; overflow:auto; margin:18px 0; }}
    th,td {{ border:1px solid var(--line); padding:10px 12px; vertical-align:top; }}
    th {{ background:#f9fafb; }}
    img {{ display:block; max-width:100%; max-height:650px; width:auto; margin:20px auto 8px;
      border-radius:12px; border:1px solid var(--line); box-shadow:0 8px 28px rgba(17,24,39,.08); }}
    details {{ border:1px solid #a7f3d0; background:#ecfdf5; border-radius:11px; padding:12px 15px;
      margin:12px 0 22px; }}
    summary {{ cursor:pointer; color:#065f46; font-weight:800; }}
    code {{ background:#f2f4f7; border-radius:4px; padding:2px 5px; }}
    .mobile-head {{ display:none; position:sticky; top:0; z-index:10; background:#111827; color:white;
      padding:12px 16px; align-items:center; justify-content:space-between; }}
    .mobile-head button {{ background:#344054; color:white; border:0; border-radius:8px; padding:8px 11px; }}
    .empty {{ display:none; color:#98a2b3; padding:16px 9px; font-size:13px; }}
    @media (max-width:860px) {{
      .app {{ display:block; }} .mobile-head {{ display:flex; }} aside {{ position:fixed; inset:0 auto 0 0;
        width:min(88vw,340px); z-index:20; transform:translateX(-105%); transition:.2s; }}
      aside.open {{ transform:translateX(0); }} main {{ padding:20px 12px 50px; }}
      .note-article {{ border-radius:13px; padding:21px 17px; }} .article-toolbar {{ flex-direction:column; }}
    }}
    @media print {{ aside,.mobile-head,.article-toolbar {{ display:none!important; }} .app {{ display:block; }}
      main {{ padding:0; }} .note-article {{ box-shadow:none; border:0; max-width:none; }} }}
  </style>
</head>
<body>
  <div class="mobile-head"><strong>혈액종양 시험노트</strong><button id="menuButton">목차</button></div>
  <div class="app">
    <aside id="sidebar">
      <div class="brand">
        <h1>혈액종양 시험노트</h1>
        <p>강의자료 · 기출 · Ontology 교차검증</p>
        <div class="stats">
          <div class="stat"><b>{len(lecture_docs)}</b><span>강의 노트</span></div>
          <div class="stat"><b>{total_questions}</b><span>새 문항</span></div>
          <div class="stat"><b>{total_images}</b><span>삽입 이미지</span></div>
        </div>
        <input id="search" type="search" placeholder="강의명·날짜 검색" aria-label="노트 검색">
      </div>
      <nav id="nav">{''.join(nav_items)}<div class="empty" id="empty">검색 결과가 없습니다.</div></nav>
    </aside>
    <main>{''.join(article_items)}</main>
  </div>
  <script>
    const links=[...document.querySelectorAll('.note-link')];
    const articles=[...document.querySelectorAll('.note-article')];
    const sidebar=document.getElementById('sidebar');
    function show(id, push=true) {{
      articles.forEach(a=>a.classList.toggle('hidden',a.id!==id));
      links.forEach(b=>b.classList.toggle('active',b.dataset.target===id));
      if(push) history.replaceState(null,'','#'+id);
      sidebar.classList.remove('open'); window.scrollTo({{top:0,behavior:'instant'}});
    }}
    links.forEach(button=>button.addEventListener('click',()=>show(button.dataset.target)));
    document.getElementById('menuButton').addEventListener('click',()=>sidebar.classList.toggle('open'));
    document.getElementById('search').addEventListener('input',event=>{{
      const query=event.target.value.trim().toLowerCase(); let visible=0;
      links.forEach(button=>{{ const match=button.dataset.search.includes(query); button.style.display=match?'':'none';
        if(match) visible++; }});
      document.querySelectorAll('.date-label').forEach(label=>{{
        let node=label.nextElementSibling, any=false;
        while(node && !node.classList.contains('date-label')) {{ if(node.classList.contains('note-link') && node.style.display!=='none') any=true; node=node.nextElementSibling; }}
        label.style.display=any?'':'none';
      }});
      document.getElementById('empty').style.display=visible?'none':'block';
    }});
    const requested=decodeURIComponent(location.hash.slice(1));
    if(requested && document.getElementById(requested)) show(requested,false);
  </script>
</body>
</html>
"""
    output_path.write_text(page, encoding="utf-8")

    manifest_path = args.manifest or output_dir / "study_notes_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "source_file_count": inventory["source_file_count"],
        "lecture_group_count": inventory["lecture_group_count"],
        "completed_note_count": len(lecture_docs),
        "question_count": total_questions,
        "embedded_image_reference_count": total_images,
        "ontology_role": "consistency_check_only",
        "medical_approval": False,
        "viewer": output_path.as_posix(),
        "documents": [
            {key: value for key, value in doc.items() if key not in {"html", "path"}}
            for doc in docs
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "viewer": output_path.as_posix(),
                "notes": len(lecture_docs),
                "questions": total_questions,
                "images": total_images,
                "manifest": manifest_path.as_posix(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
