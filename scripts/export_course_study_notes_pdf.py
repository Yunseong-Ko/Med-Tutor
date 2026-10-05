#!/usr/bin/env python3
"""Export the complete hematology-oncology study-note vault as one A4 PDF."""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import markdown
from bs4 import BeautifulSoup
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]")
DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
TEXT_REPLACEMENTS = {
    "🔥": "[반복]",
    "⭐": "[강조]",
    "✅": "[확인]",
    "❌": "[주의]",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("tmp/pdfs"))
    return parser.parse_args()


def normalize_print_text(value: str) -> str:
    value = value.translate(DASH_TRANSLATION)
    for source, target in TEXT_REPLACEMENTS.items():
        value = value.replace(source, target)
    return value


def display_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def file_uri(path: Path) -> str:
    return "file://" + quote(path.resolve().as_posix(), safe="/:@")


def render_note_markdown(
    path: Path,
    *,
    vault_root: Path,
    link_map: dict[str, str],
) -> str:
    raw = normalize_print_text(path.read_text(encoding="utf-8"))
    raw = FRONTMATTER_RE.sub("", raw, count=1)

    def replace_wikilink(match: re.Match[str]) -> str:
        target = match.group(1)
        label = match.group(2) or Path(target).name
        anchor = link_map.get(target) or link_map.get(Path(target).name)
        if anchor:
            return f"[{label}](#{anchor})"
        return label

    raw = WIKILINK_RE.sub(replace_wikilink, raw)
    rendered = markdown.markdown(
        raw,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    soup = BeautifulSoup(rendered, "html.parser")

    for image in soup.find_all("img"):
        source = html.unescape(image.get("src", ""))
        if not re.match(r"^[a-z]+://", source):
            resolved = (path.parent / source).resolve()
            image["src"] = file_uri(resolved)
        image["loading"] = "eager"

    for details in soup.find_all("details"):
        replacement = soup.new_tag("div")
        replacement["class"] = "answer-block"
        summary = details.find("summary")
        title = soup.new_tag("div")
        title["class"] = "answer-title"
        title.string = summary.get_text(" ", strip=True) if summary else "정답 및 해설"
        replacement.append(title)
        if summary:
            summary.extract()
        answer_markdown = details.decode_contents()
        answer_html = markdown.markdown(
            answer_markdown,
            extensions=["tables", "sane_lists"],
            output_format="html5",
        )
        answer_soup = BeautifulSoup(answer_html, "html.parser")
        for child in list(answer_soup.contents):
            replacement.append(child.extract())
        details.replace_with(replacement)

    return str(soup)


def build_link_map(groups: list[dict]) -> dict[str, str]:
    result: dict[str, str] = {
        "01_시험직전_통합복습": "rapid-review",
        "02_제작_검증_기록": "verification-record",
    }
    for group in groups:
        note_path = Path(group["note_path"])
        relative = Path("notes") / note_path.name
        anchor = group["group_id"]
        result[relative.with_suffix("").as_posix()] = anchor
        result[note_path.stem] = anchor
        result[relative.as_posix()] = anchor
    return result


def toc_row(anchor: str, title: str, page_map: dict[str, int]) -> str:
    page_number = str(page_map.get(anchor, "---"))
    return (
        f'<a class="toc-row" href="#{html.escape(anchor)}">'
        f'<span class="toc-title">{html.escape(normalize_print_text(title))}</span>'
        '<span class="toc-dots"></span>'
        f'<span class="toc-page">{html.escape(page_number)}</span>'
        "</a>"
    )


def build_html(
    *,
    inventory: dict,
    vault_root: Path,
    page_map: dict[str, int],
) -> str:
    groups = inventory["groups"]
    link_map = build_link_map(groups)
    by_date: dict[str, list[dict]] = defaultdict(list)
    for group in groups:
        by_date[group["date"]].append(group)

    toc_parts = [
        toc_row("rapid-review", "시험 직전 통합복습", page_map),
    ]
    for date in sorted(by_date):
        toc_parts.append(f'<h3 class="toc-date">{display_date(date)}</h3>')
        for group in sorted(
            by_date[date], key=lambda row: (row["periods"] or [99], row["group_id"])
        ):
            periods = ", ".join(str(value) for value in group["periods"])
            title = f"{periods}교시 - {group['title']}"
            toc_parts.append(toc_row(group["group_id"], title, page_map))
    toc_parts.append(toc_row("verification-record", "제작 및 검증 기록", page_map))

    rapid_path = vault_root / "01_시험직전_통합복습.md"
    verification_path = vault_root / "02_제작_검증_기록.md"
    rapid_html = render_note_markdown(
        rapid_path, vault_root=vault_root, link_map=link_map
    )
    verification_html = render_note_markdown(
        verification_path, vault_root=vault_root, link_map=link_map
    )

    article_parts = [
        '<article id="rapid-review" class="document-section rapid-review">'
        '<div class="document-marker">DOCUMENT ID: RAPID-REVIEW</div>'
        f"{rapid_html}</article>"
    ]
    for group in groups:
        note_path = Path(group["note_path"])
        periods = ", ".join(str(value) for value in group["periods"])
        source_formats = "/".join(
            sorted(
                {
                    source["source_suffix"].lstrip(".").upper()
                    for source in group["sources"]
                }
            )
        )
        article_html = render_note_markdown(
            note_path, vault_root=vault_root, link_map=link_map
        )
        article_parts.append(
            f'<article id="{html.escape(group["group_id"])}" class="document-section lecture-note">'
            f'<div class="document-marker">DOCUMENT ID: {html.escape(group["group_id"])}</div>'
            '<div class="lecture-meta">'
            f'<span>{display_date(group["date"])}</span>'
            f'<span>{html.escape(periods)}교시</span>'
            f'<span>{html.escape(source_formats)}</span>'
            "</div>"
            f"{article_html}</article>"
        )
    article_parts.append(
        '<article id="verification-record" class="document-section verification-record">'
        '<div class="document-marker">DOCUMENT ID: VERIFICATION-RECORD</div>'
        f"{verification_html}</article>"
    )

    css = r"""
@page {
  size: A4;
  margin: 16mm 15mm 18mm 15mm;
}
@page cover {
  size: A4;
  margin: 0;
}
* { box-sizing: border-box; }
html { font-size: 10pt; }
body {
  margin: 0;
  color: #17212b;
  background: white;
  font-family: "Apple SD Gothic Neo", "Nanum Gothic", sans-serif;
  line-height: 1.58;
  word-break: keep-all;
  overflow-wrap: anywhere;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
.cover {
  page: cover;
  width: 210mm;
  height: 297mm;
  padding: 26mm 22mm;
  position: relative;
  overflow: hidden;
  color: #fff;
  background:
    radial-gradient(circle at 82% 15%, rgba(244,114,182,.28), transparent 31%),
    radial-gradient(circle at 12% 88%, rgba(45,212,191,.20), transparent 32%),
    linear-gradient(145deg, #111827 0%, #2a1621 60%, #4c1626 100%);
  break-after: page;
}
.cover::before {
  content: "";
  position: absolute;
  inset: 18mm;
  border: .35mm solid rgba(255,255,255,.22);
  border-radius: 6mm;
}
.cover-kicker {
  position: relative;
  margin-top: 16mm;
  color: #fda4af;
  font-size: 11pt;
  font-weight: 700;
  letter-spacing: .16em;
}
.cover h1 {
  position: relative;
  margin: 38mm 0 5mm;
  max-width: 150mm;
  color: #fff;
  font-size: 34pt;
  line-height: 1.18;
  letter-spacing: -.04em;
}
.cover-subtitle {
  position: relative;
  max-width: 145mm;
  color: #d1d5db;
  font-size: 14pt;
  line-height: 1.6;
}
.cover-stats {
  position: absolute;
  left: 22mm;
  right: 22mm;
  bottom: 42mm;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4mm;
}
.cover-stat {
  padding: 5mm 3mm;
  border: .3mm solid rgba(255,255,255,.20);
  border-radius: 3mm;
  background: rgba(255,255,255,.08);
  text-align: center;
}
.cover-stat strong { display: block; font-size: 20pt; color: #fff; }
.cover-stat span { display: block; margin-top: 1mm; color: #d1d5db; font-size: 8pt; }
.cover-foot {
  position: absolute;
  left: 22mm;
  bottom: 24mm;
  color: #9ca3af;
  font-size: 8pt;
  letter-spacing: .04em;
}
.toc-section {
  break-after: page;
  min-height: 250mm;
}
.toc-section h1 { margin-top: 0; }
.toc-intro {
  margin: 0 0 6mm;
  color: #667085;
  font-size: 9pt;
}
.toc-columns {
  column-count: 2;
  column-gap: 10mm;
  column-rule: .2mm solid #e4e7ec;
}
.toc-date {
  margin: 4mm 0 1.5mm;
  color: #9f1239;
  font-size: 10pt;
  break-after: avoid;
}
.toc-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: baseline;
  gap: 1.5mm;
  margin: 0 0 1.6mm;
  color: #344054;
  font-size: 7.8pt;
  line-height: 1.28;
  text-decoration: none;
  break-inside: avoid;
}
.toc-title { max-width: 74mm; }
.toc-dots { border-bottom: .25mm dotted #c8cdd5; transform: translateY(-.7mm); }
.toc-page { min-width: 7mm; text-align: right; color: #9f1239; font-variant-numeric: tabular-nums; }
.document-section { break-before: page; }
.document-marker {
  margin-bottom: 2mm;
  color: #98a2b3;
  font-family: Helvetica, Arial, sans-serif;
  font-size: 6.5pt;
  letter-spacing: .06em;
}
.lecture-meta {
  display: flex;
  gap: 2.5mm;
  margin: 0 0 4mm;
  color: #667085;
  font-size: 7.5pt;
}
.lecture-meta span {
  padding: 1.1mm 2.3mm;
  border-radius: 9mm;
  background: #f2f4f7;
}
h1 {
  margin: 0 0 5mm;
  color: #111827;
  font-size: 23pt;
  line-height: 1.24;
  letter-spacing: -.035em;
  break-after: avoid;
}
h2 {
  margin: 8mm 0 3mm;
  padding: 0 0 1.7mm;
  border-bottom: .55mm solid #e4e7ec;
  color: #7f1d1d;
  font-size: 15pt;
  line-height: 1.35;
  break-after: avoid;
}
h3 {
  margin: 5.5mm 0 2mm;
  color: #344054;
  font-size: 11.5pt;
  line-height: 1.4;
  break-after: avoid;
}
h4 { margin: 4mm 0 1.5mm; font-size: 10.3pt; break-after: avoid; }
p { margin: 0 0 2.5mm; orphans: 3; widows: 3; }
ul, ol { margin: 1.5mm 0 3mm; padding-left: 5.6mm; }
li { margin: 0 0 1.1mm; }
strong { color: #101828; }
a { color: #7f1d1d; text-decoration: none; }
blockquote {
  margin: 4mm 0 5mm;
  padding: 3.5mm 4.2mm;
  border-left: 1.2mm solid #be123c;
  border-radius: 0 2.5mm 2.5mm 0;
  background: #fff1f2;
  color: #4c0519;
  break-inside: avoid;
}
blockquote p:last-child { margin-bottom: 0; }
table {
  width: 100%;
  margin: 3mm 0 4mm;
  border-collapse: collapse;
  table-layout: auto;
  font-size: 8.1pt;
  line-height: 1.42;
}
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td {
  padding: 2mm 2.2mm;
  border: .25mm solid #d0d5dd;
  vertical-align: top;
}
th { background: #f2f4f7; color: #344054; font-weight: 700; }
tbody tr:nth-child(even) { background: #fcfcfd; }
p:has(> img) { break-inside: avoid; text-align: center; margin-top: 4mm; }
img {
  display: block;
  max-width: 100%;
  max-height: 122mm;
  width: auto;
  height: auto;
  margin: 0 auto 1.5mm;
  border: .25mm solid #e4e7ec;
  border-radius: 2mm;
  object-fit: contain;
}
p > em:only-child {
  display: block;
  margin-top: -1mm;
  color: #667085;
  font-size: 7.4pt;
  line-height: 1.35;
  text-align: center;
}
.answer-block {
  margin: 3mm 0 5mm;
  padding: 3.5mm 4mm;
  border: .3mm solid #86efac;
  border-radius: 2.5mm;
  background: #f0fdf4;
  break-inside: avoid-page;
}
.answer-title {
  margin-bottom: 2mm;
  color: #166534;
  font-size: 10pt;
  font-weight: 800;
}
.answer-block p:last-child { margin-bottom: 0; }
code {
  padding: .25mm .8mm;
  border-radius: .8mm;
  background: #f2f4f7;
  font-family: Menlo, monospace;
  font-size: 8.2pt;
}
hr { margin: 7mm 0; border: 0; border-top: .3mm solid #e4e7ec; }
.verification-record { font-size: 9.2pt; }
"""

    cover = f"""
<section class="cover">
  <div class="cover-kicker">PACCINE · COURSE STUDY EDITION</div>
  <h1>혈액종양<br>강의별 시험노트</h1>
  <div class="cover-subtitle">강의자료, 원본 이미지, 과거 시험 반복주제와<br>Ontology consistency check를 한 권으로 정리한 통합본</div>
  <div class="cover-stats">
    <div class="cover-stat"><strong>{inventory['source_file_count']}</strong><span>원본 파일</span></div>
    <div class="cover-stat"><strong>{inventory['lecture_group_count']}</strong><span>강의 노트</span></div>
    <div class="cover-stat"><strong>67</strong><span>연관 문항</span></div>
    <div class="cover-stat"><strong>175</strong><span>강의 이미지</span></div>
  </div>
  <div class="cover-foot">2026-07-19 · 강의자료가 1차 근거이며 Ontology는 일관성 확인용입니다.</div>
</section>
"""
    return f"""<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><title>혈액종양 강의별 시험노트</title><style>{css}</style></head>
<body>
{cover}
<section class="toc-section">
  <h1>목차</h1>
  <p class="toc-intro">각 항목을 누르면 해당 강의로 이동합니다. 페이지 번호는 최종 PDF 기준입니다.</p>
  <div class="toc-columns">{''.join(toc_parts)}</div>
</section>
{''.join(article_parts)}
</body></html>"""


def chrome_path() -> Path:
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No supported Chromium browser found")


def print_pdf(html_path: Path, pdf_path: Path, work_dir: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.unlink(missing_ok=True)
    profile_dir = work_dir / "chrome-profile"
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    command = [
        str(chrome_path()),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile_dir}",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.resolve()}",
        file_uri(html_path),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 600
    last_size = -1
    stable_checks = 0
    valid_pdf = False
    try:
        while time.monotonic() < deadline:
            if pdf_path.exists() and pdf_path.stat().st_size > 10_000:
                current_size = pdf_path.stat().st_size
                if current_size == last_size:
                    stable_checks += 1
                else:
                    stable_checks = 0
                    last_size = current_size
                if stable_checks >= 3:
                    try:
                        valid_pdf = len(PdfReader(str(pdf_path)).pages) > 0
                    except Exception:
                        valid_pdf = False
                    if valid_pdf:
                        break
            if process.poll() is not None:
                if pdf_path.exists():
                    try:
                        valid_pdf = len(PdfReader(str(pdf_path)).pages) > 0
                    except Exception:
                        valid_pdf = False
                break
            time.sleep(1)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        subprocess.run(
            ["pkill", "-TERM", "-f", f"user-data-dir={profile_dir}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if not valid_pdf:
        raise RuntimeError("Chromium PDF export did not produce a readable PDF")


def locate_documents(pdf_path: Path, groups: list[dict]) -> dict[str, int]:
    reader = PdfReader(str(pdf_path))
    markers = {
        "rapid-review": "DOCUMENT ID: RAPID-REVIEW",
        "verification-record": "DOCUMENT ID: VERIFICATION-RECORD",
    }
    markers.update(
        {group["group_id"]: f'DOCUMENT ID: {group["group_id"]}' for group in groups}
    )
    locations: dict[str, int] = {}
    remaining = dict(markers)
    for page_index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for key, marker in list(remaining.items()):
            if marker in text:
                locations[key] = page_index + 1
                remaining.pop(key)
        if not remaining:
            break
    if remaining:
        raise RuntimeError(f"Could not locate PDF document markers: {sorted(remaining)}")
    return locations


def footer_overlay(page_number: int, total_pages: int) -> PdfReader:
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    c.setStrokeColor(Color(0.83, 0.85, 0.88, alpha=1))
    c.setLineWidth(0.35)
    c.line(42, 31, A4[0] - 42, 31)
    c.setFillColor(Color(0.42, 0.45, 0.50, alpha=1))
    c.setFont("Helvetica", 7.2)
    c.drawString(42, 18, "PACCINE | Hematology-Oncology Study Notes")
    c.drawRightString(A4[0] - 42, 18, f"{page_number} / {total_pages}")
    c.save()
    packet.seek(0)
    return PdfReader(packet)


def finalize_pdf(
    *,
    source_pdf: Path,
    destination: Path,
    locations: dict[str, int],
    groups: list[dict],
) -> None:
    reader = PdfReader(str(source_pdf))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    total_pages = len(writer.pages)
    for index, page in enumerate(writer.pages):
        if index == 0:
            continue
        overlay = footer_overlay(index + 1, total_pages)
        page.merge_page(overlay.pages[0], over=True)

    writer.add_metadata(
        {
            "/Title": "혈액종양 강의별 시험노트 통합본",
            "/Author": "PACCINE",
            "/Subject": "혈액종양 강의자료 기반 시험 대비 노트",
            "/Keywords": "hematology oncology study notes PACCINE",
        }
    )
    writer.add_outline_item("표지", 0)
    writer.add_outline_item("시험 직전 통합복습", locations["rapid-review"] - 1)
    date_parents: dict[str, object] = {}
    for group in groups:
        date = group["date"]
        if date not in date_parents:
            date_parents[date] = writer.add_outline_item(
                display_date(date), locations[group["group_id"]] - 1
            )
        periods = ", ".join(str(value) for value in group["periods"])
        writer.add_outline_item(
            f"{periods}교시 - {normalize_print_text(group['title'])}",
            locations[group["group_id"]] - 1,
            parent=date_parents[date],
        )
    writer.add_outline_item("제작 및 검증 기록", locations["verification-record"] - 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output_file:
        writer.write(output_file)


def main() -> None:
    args = parse_args()
    inventory_path = args.inventory.resolve()
    vault_root = args.vault_root.resolve()
    destination = args.output.resolve()
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    page_map: dict[str, int] = {}
    final_pass_pdf: Path | None = None
    final_locations: dict[str, int] = {}
    for pass_number in range(1, 4):
        html_path = work_dir / f"hematology_study_notes_pass{pass_number}.html"
        pdf_path = work_dir / f"hematology_study_notes_pass{pass_number}.pdf"
        html_text = build_html(
            inventory=inventory,
            vault_root=vault_root,
            page_map=page_map,
        )
        html_path.write_text(html_text, encoding="utf-8")
        print_pdf(html_path, pdf_path, work_dir)
        locations = locate_documents(pdf_path, inventory["groups"])
        final_pass_pdf = pdf_path
        final_locations = locations
        if page_map and locations == page_map:
            break
        page_map = locations

    if final_pass_pdf is None:
        raise RuntimeError("PDF export did not produce a pass")
    finalize_pdf(
        source_pdf=final_pass_pdf,
        destination=destination,
        locations=final_locations,
        groups=inventory["groups"],
    )
    reader = PdfReader(str(destination))
    print(
        json.dumps(
            {
                "output": destination.as_posix(),
                "pages": len(reader.pages),
                "bytes": destination.stat().st_size,
                "documents": len(inventory["groups"]) + 2,
                "locations": final_locations,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
