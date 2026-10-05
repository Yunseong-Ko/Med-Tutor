#!/usr/bin/env python3
"""Mirror Korean official guideline metadata and selected public attachments.

The default source is the Korean Academy of Medical Sciences Clinical Practice
Guideline Information Center.  Catalog presence does not prove that a record is
the newest guideline for its topic.  Every record therefore remains
``cataloged_not_latest_verified`` until a separate official-source check marks
it current.

Downloaded files stay under ``data_private`` and are never automatically used
for medical claims, generation, or student-facing output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from jsonschema import Draft7Validator, FormatChecker
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://www.guideline.or.kr"
LIST_URL = BASE_URL + "/guide/index.php?sub_depth=3&page={page}"
OUT = ROOT / "data_private" / "kr_guidelines" / "catalog" / "kams_registered_catalog.json"
FILES = ROOT / "data_private" / "kr_guidelines" / "source_files" / "kams"
SCHEMA = ROOT / "schemas" / "kr_guideline_source_registry.schema.json"
CHECKED_AT = date.today().isoformat()
ALLOWED_DOWNLOAD_HOSTS = {
    "guideline.or.kr",
    "www.guideline.or.kr",
    "kams.or.kr",
    "www.kams.or.kr",
}
AXES = [
    "screening",
    "prevention",
    "epidemiology",
    "risk_factor",
    "diagnosis",
    "treatment",
    "indication",
    "contraindication",
    "prognosis",
    "follow_up",
    "rehabilitation",
    "procedure",
]


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def infer_specialties(title: str, body: str) -> list[str]:
    haystack = f"{title} {body}".lower()
    rules = {
        "cardiology": ("심장", "심방", "고혈압", "심부전", "관상", "혈관", "정맥"),
        "pulmonology": ("호흡", "폐렴", "폐질환", "천식", "copd", "결핵"),
        "gastroenterology_hepatology": ("소화", "위장", "장내시경", "대장", "간염", "간질환", "담도"),
        "hematology_oncology": ("혈액", "빈혈", "백혈병", "림프종", "암", "종양", "항암"),
        "endocrinology": ("당뇨", "갑상", "내분비", "골다공증", "이상지질"),
        "nephrology": ("신장", "콩팥", "투석", "ckrt"),
        "infectious_disease": ("감염", "항생제", "결핵", "코로나", "성매개"),
        "neurology": ("뇌졸중", "신경", "치매", "두통", "간질", "파킨슨"),
        "rheumatology": ("류마", "관절염", "통풍", "루푸스"),
        "obstetrics_gynecology": ("임신", "산전", "산후", "산부인", "자궁", "난소"),
        "pediatrics": ("소아", "신생아", "어린이", "청소년"),
        "emergency_critical_care": ("응급", "중환자", "소생", "외상", "쇼크"),
        "psychiatry": ("정신", "우울", "조현", "자살", "중독"),
        "surgery_procedure": ("수술", "시술", "절제", "마취", "방사선치료"),
        "radiology": ("영상", "초음파", "ct", "mri", "방사선"),
        "primary_care_prevention": ("금연", "검진", "예방", "일차의료", "비만"),
    }
    matched = [name for name, terms in rules.items() if any(term in haystack for term in terms)]
    return sorted(set(matched)) or ["unclassified"]


def infer_axes(title: str, body: str) -> list[str]:
    haystack = f"{title} {body}".lower()
    selected = []
    axis_terms = {
        "screening": ("검진", "선별"),
        "prevention": ("예방", "백신", "금연"),
        "diagnosis": ("진단", "검사", "평가", "영상"),
        "treatment": ("치료", "관리", "처치", "약물", "재활"),
        "indication": ("적응", "사용", "시행"),
        "contraindication": ("금기", "안전"),
        "prognosis": ("예후", "위험도", "중증도"),
        "follow_up": ("추적", "감시"),
        "rehabilitation": ("재활",),
        "procedure": ("시술", "수술", "검사", "방사선치료"),
    }
    for axis, terms in axis_terms.items():
        if any(term in haystack for term in terms):
            selected.append(axis)
    return sorted(set(selected)) or AXES.copy()


def list_records(session: requests.Session, *, max_pages: int) -> list[dict]:
    records: dict[str, dict] = {}
    empty_pages = 0
    for page in range(1, max_pages + 1):
        response = session.get(LIST_URL.format(page=page), timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        found = 0
        for row in soup.select("table tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 6:
                continue
            view = cells[2].find("a", href=re.compile(r"view\.php\?number="))
            if not view:
                continue
            number_match = re.search(r"number=(\d+)", view.get("href", ""))
            if not number_match:
                continue
            record_id = number_match.group(1)
            year_text = clean(cells[1].get_text(" ", strip=True))
            attachment_links = []
            for index, link in enumerate(cells[5].find_all("a", href=True), start=1):
                image = link.find("img")
                filename = clean((image or {}).get("alt") if image else link.get_text(" ", strip=True))
                attachment_links.append(
                    {
                        "attachment_id": f"kr-cpg:kams:{record_id}:a{index}",
                        "filename": filename or f"attachment_{index}",
                        "source_url": urljoin(BASE_URL, link["href"]),
                    }
                )
            records[record_id] = {
                "record_id": record_id,
                "row_number": clean(cells[0].get_text(" ", strip=True)),
                "publication_year": int(year_text) if year_text.isdigit() else None,
                "title": clean(view.get_text(" ", strip=True)),
                "issuing_body": clean(cells[3].get_text(" ", strip=True)),
                "download_count": clean(cells[4].get_text(" ", strip=True)),
                "official_landing_url": urljoin(BASE_URL + "/guide/", view["href"]),
                "attachments": attachment_links,
            }
            found += 1
        if found == 0:
            empty_pages += 1
            if empty_pages >= 2:
                break
        else:
            empty_pages = 0
    return sorted(
        records.values(),
        key=lambda row: (row.get("publication_year") or 0, int(row["record_id"])),
        reverse=True,
    )


def detail_record(session: requests.Session, record: dict) -> dict:
    response = session.get(record["official_landing_url"], timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    fields: dict[str, str] = {}
    attachments: list[dict] = []
    for row in soup.select("table.inputTbl tr"):
        heading = row.find("th")
        value = row.find("td")
        if not heading or not value:
            continue
        key = clean(heading.get_text(" ", strip=True))
        fields[key] = clean(value.get_text(" ", strip=True))
        if key == "진료지침파일":
            for index, link in enumerate(value.find_all("a", href=True), start=1):
                attachments.append(
                    {
                        "attachment_id": f"kr-cpg:kams:{record['record_id']}:a{index}",
                        "filename": clean(link.get_text(" ", strip=True)) or f"attachment_{index}",
                        "source_url": urljoin(BASE_URL, link["href"]),
                    }
                )
    development_text = fields.get("개발일자", "")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", development_text)
    abstract = fields.get("Abstract", "")
    record["details"] = {
        "start_date": dates[0] if dates else None,
        "completion_date": dates[1] if len(dates) > 1 else None,
        "method": fields.get("진료지침 개발방식") or None,
        "multidisciplinary": fields.get("다학제 연구개발") or None,
        "society_certification": fields.get("학회내 인증 여부와 인증학회명") or None,
        "keywords": fields.get("Keywords") or None,
        "abstract_sha256": sha256_bytes(abstract.encode("utf-8")) if abstract else None,
        "abstract": abstract,
    }
    if attachments:
        record["attachments"] = attachments
    return record


def empty_attachment(row: dict) -> dict:
    suffix = Path(urlparse(row["filename"]).path).suffix.lower()
    if not suffix:
        suffix = Path(row["filename"]).suffix.lower()
    return {
        **row,
        "file_type": suffix.lstrip(".") or "unknown",
        "public_download": urlparse(row["source_url"]).hostname in ALLOWED_DOWNLOAD_HOSTS,
        "download_status": "not_requested",
        "relative_path": None,
        "bytes": None,
        "sha256": None,
        "content_type": None,
        "pdf_pages": None,
        "pdf_encrypted": None,
        "pdf_text_chars": None,
        "error": None,
    }


def inspect_pdf(path: Path) -> tuple[int | None, bool | None, int | None]:
    try:
        reader = PdfReader(path)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            return len(reader.pages), True, 0
        chars = 0
        for page in reader.pages:
            chars += len(page.extract_text() or "")
        return len(reader.pages), False, chars
    except Exception:
        return None, None, None


def download_attachment(
    session: requests.Session,
    source_id: str,
    attachment: dict,
    *,
    overwrite: bool,
) -> dict:
    row = dict(attachment)
    host = urlparse(row["source_url"]).hostname
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        row["download_status"] = "metadata_only"
        row["error"] = f"download_host_not_allowlisted:{host}"
        return row
    suffix = Path(row["filename"]).suffix.lower() or ".bin"
    ordinal = row["attachment_id"].rsplit(":a", 1)[-1]
    destination = FILES / source_id.rsplit(":", 1)[-1] / f"attachment_{ordinal}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not destination.exists() or overwrite:
            response = session.get(row["source_url"], timeout=120)
            response.raise_for_status()
            destination.write_bytes(response.content)
            content_type = response.headers.get("content-type")
        else:
            content_type = mimetypes.guess_type(destination.name)[0]
        payload = destination.read_bytes()
        row.update(
            {
                "download_status": "downloaded",
                "relative_path": str(destination.relative_to(ROOT)),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "content_type": content_type,
                "error": None,
            }
        )
        if suffix == ".pdf":
            pages, encrypted, chars = inspect_pdf(destination)
            row["pdf_pages"] = pages
            row["pdf_encrypted"] = encrypted
            row["pdf_text_chars"] = chars
    except Exception as exc:
        row["download_status"] = "failed"
        row["error"] = f"{type(exc).__name__}:{exc}"
    return row


def normalize_source(record: dict) -> dict:
    detail = record.get("details") or {}
    body = " ".join(
        filter(None, [record.get("issuing_body"), detail.get("keywords"), detail.get("abstract")])
    )
    attachments = [empty_attachment(row) for row in record.get("attachments", [])]
    return {
        "source_id": f"kr-cpg:kams:{record['record_id']}",
        "title": record["title"],
        "issuing_body": record.get("issuing_body", ""),
        "publication_year": record.get("publication_year"),
        "jurisdiction": "KR",
        "document_type": "clinical_practice_guideline",
        "catalog_provider": "대한의학회 임상진료지침정보센터",
        "catalog_record_id": record["record_id"],
        "official_landing_url": record["official_landing_url"],
        "latest_status": "cataloged_not_latest_verified",
        "latest_checked_at": CHECKED_AT,
        "specialties": infer_specialties(record["title"], body),
        "clinical_axes": infer_axes(record["title"], body),
        "topic_concept_ids": [],
        "development": {
            "start_date": detail.get("start_date"),
            "completion_date": detail.get("completion_date"),
            "method": detail.get("method"),
            "multidisciplinary": detail.get("multidisciplinary"),
            "society_certification": detail.get("society_certification"),
            "keywords": detail.get("keywords"),
            "abstract_sha256": detail.get("abstract_sha256"),
        },
        "license": {
            "status": "society_copyright",
            "redistribution_allowed": False,
            "commercial_reuse_allowed": None,
            "notes": "Public catalog/download does not establish redistribution or commercial reuse permission.",
        },
        "attachments": attachments,
        "needs_review": True,
        "medical_approval": False,
        "student_visible": False,
    }


def validate(payload: dict) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        sample = "\n".join(f"{list(error.path)}: {error.message}" for error in errors[:20])
        raise ValueError(f"registry schema validation failed ({len(errors)} errors)\n{sample}")


def build(args: argparse.Namespace) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": "PaccineGuidelineInventory/1.0 (+private research mirror)"})
    raw = list_records(session, max_pages=args.max_pages)
    if args.with_details:
        for index, record in enumerate(raw, start=1):
            raw[index - 1] = detail_record(session, record)
            if index % 50 == 0 or index == len(raw):
                print(f"details {index}/{len(raw)}", flush=True)
    sources = [normalize_source(record) for record in raw]
    requested_ids = set(args.download_id or [])
    if args.download_year_min is not None or requested_ids:
        for source in sources:
            should_download = (
                source["source_id"] in requested_ids
                or source["catalog_record_id"] in requested_ids
                or (
                    args.download_year_min is not None
                    and (source["publication_year"] or 0) >= args.download_year_min
                )
            )
            if not should_download:
                continue
            source["attachments"] = [
                download_attachment(session, source["source_id"], row, overwrite=args.overwrite)
                for row in source["attachments"]
            ]
    statuses = Counter(
        attachment["download_status"]
        for source in sources
        for attachment in source["attachments"]
    )
    payload = {
        "schema_version": "kr_guideline_source_registry.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_checked_at": CHECKED_AT,
        "registry_role": "source_inventory_not_medical_approval",
        "catalog": {
            "provider": "대한의학회 임상진료지침정보센터",
            "landing_url": BASE_URL + "/guide/index.php?sub_depth=3",
            "scope": "domestic_registered_guidelines",
            "latest_interpretation": "Catalog presence is not proof that a topic's newest edition was found.",
        },
        "summary": {
            "sources": len(sources),
            "attachments": sum(len(row["attachments"]) for row in sources),
            "publication_years": dict(
                sorted(Counter(str(row["publication_year"]) for row in sources).items())
            ),
            "download_statuses": dict(sorted(statuses.items())),
            "medical_approval": 0,
            "student_visible": 0,
        },
        "safety_boundary": {
            "needs_review": True,
            "medical_approval": False,
            "student_visible": False,
            "generation_eligible": False,
            "automatic_claim_promotion": False,
        },
        "sources": sources,
    }
    validate(payload)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--with-details", action="store_true")
    parser.add_argument("--download-year-min", type=int)
    parser.add_argument("--download-id", action="append")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    result = build(parse_args())
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
