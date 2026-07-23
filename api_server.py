from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import fcntl
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.services.anki_export import build_anki_export, build_practice_anki_export
from src.services.cbt_hwp_export import build_cbt_hwp_export
from src.services.cbt_docx_export import build_studio_cbt_docx_export
from src.services.choice_explanations import build_choice_explanation_draft
from src.services.lecture_studio import (
    EXPORT_SET_DIR,
    IMAGE_DIR,
    MEDIA_ASSET_DIR,
    MediaAssetInUseError,
    archive_question_set,
    delete_media_asset,
    generate_studio_questions,
    get_model_catalog,
    load_question_set,
    list_media_assets,
    list_question_sets,
    save_media_asset,
    save_upload_bytes,
    split_metadata_values,
    update_question_review,
)
from src.services.medlegal_studio import (
    load_medlegal_case,
    load_medlegal_submission,
    list_medlegal_cases,
    submit_medlegal_note,
)
from src.services.notebooklm_import import import_notebooklm_question_set
from src.services.ontology_feedback import build_feedback_packet
from src.services.external_kg_review import list_external_kg_review
from src.services.rag_library import (
    DEFAULT_COURSE_ID as DEFAULT_RAG_COURSE_ID,
    draft_anki_cards_from_evidence,
    get_rag_index_status,
    search_rag_evidence,
)
from src.services.kr_guideline_library import (
    build_guideline_study_assistant,
    get_guideline_library_status,
    sanitize_student_guideline_source,
    search_guideline_library,
)
from src.services.guideline_agent_map import (
    get_guideline_agent_map_status,
    route_guideline_sources,
)
from src.services.medical_copilot import (
    build_medical_copilot_response,
    get_medical_copilot_status,
)
from src.services.medical_copilot_jobs import (
    cancel_medical_copilot_job,
    create_medical_copilot_job,
    get_medical_copilot_job,
    retry_medical_copilot_job,
)
from src.services.kr_guideline_claim_review import (
    create_claim_draft,
    decide_claim,
    get_claim_source_document,
    list_claim_drafts,
    list_claim_review_tasks,
    list_valid_released_claims,
)
from src.services.studio_generation_jobs import (
    cancel_generation_job,
    create_generation_job,
    get_generation_job,
    resume_generation_job,
    retry_failed_generation_job,
)
from src.services.faculty_item_intents import (
    build_department_catalog,
    recommend_item_intents,
    target_axis_for_task,
)
from scripts.extract_course_exam_hwp import (
    extract_file as extract_course_exam_hwp_file,
    render_markdown as render_course_exam_markdown,
    slugify as course_exam_slugify,
)
from scripts.extract_course_exam_pdf import extract_file as extract_course_exam_pdf_file
from scripts.render_course_exam_preview import render_record as render_course_exam_preview
from scripts.extract_answer_key_xlsx import (
    apply_answer_key_to_record,
    parse_answer_key_xlsx,
)
from scripts.generation_grounding import build_generation_grounding
from scripts.question_blueprint import build_question_blueprint
from scripts.ontology_trust_kernel_gate import (
    evaluate_release,
    file_sha256,
    load_release_registry,
    question_content_sha256,
)


ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"
COURSE_EXAM_ROOT = ROOT / "data_private" / "course_exams"
COURSE_EXAM_UPLOAD_DIR = COURSE_EXAM_ROOT / "uploads"
COURSE_EXAM_EXTRACTED_DIR = COURSE_EXAM_ROOT / "extracted"
COURSE_EXAM_MARKDOWN_DIR = COURSE_EXAM_ROOT / "markdown"
COURSE_EXAM_MEDIA_DIR = COURSE_EXAM_ROOT / "media"
COURSE_EXAM_PREVIEW_DIR = COURSE_EXAM_ROOT / "previews"
LEARNING_ANALYTICS_DIR = COURSE_EXAM_ROOT / "analytics"
STUDENT_RELEASES_PATH = ROOT / "data_private" / "studio" / "student_releases.json"
ANKI_EXPORT_DIR = ROOT / "data_private" / "anki_exports"
ATTEMPTS_LOG_PATH = LEARNING_ANALYTICS_DIR / "attempts.jsonl"
FEEDBACK_LOG_PATH = LEARNING_ANALYTICS_DIR / "feedback.jsonl"
PRACTICE_SESSIONS_LOG_PATH = LEARNING_ANALYTICS_DIR / "practice_sessions.jsonl"
PRACTICE_BOOKMARKS_LOG_PATH = LEARNING_ANALYTICS_DIR / "practice_bookmarks.jsonl"
PRACTICE_SNAPSHOTS_LOG_PATH = LEARNING_ANALYTICS_DIR / "practice_snapshots.jsonl"
STUDENT_QBANK_PATH = ROOT / "data_private" / "student" / "qbank.json"
STUDENT_COURSE_PREFERENCES_LOG_PATH = LEARNING_ANALYTICS_DIR / "student_course_preferences.jsonl"
STUDENT_FSRS_LOG_PATH = LEARNING_ANALYTICS_DIR / "student_fsrs_reviews.jsonl"
STUDENT_CLAIM_FSRS_LOG_PATH = LEARNING_ANALYTICS_DIR / "student_claim_fsrs_reviews.jsonl"
STUDENT_CONCEPT_NOTES_PATH = ROOT / "data_private" / "concept_notes" / "hemeonc_concept_notes.json"
STUDENT_QUESTION_LINKS_PATH = ROOT / "data_private" / "ontology" / "question_links.json"
ONTOLOGY_READINESS_PATH = ROOT / "docs" / "Ontology_V1_Readiness_20260711.json"
ONTOLOGY_HARDENING_PATH = ROOT / "data_private" / "curriculum" / "ontology_hardening_worklist_20260712.json"
ONTOLOGY_REVIEW_WORKLIST_PATH = ROOT / "data_private" / "curriculum" / "clinical_axis_review_worklist_20260712.json"
ONTOLOGY_FINDING_ENDPOINT_WORKLIST_PATH = ROOT / "data_private" / "curriculum" / "finding_endpoint_review_worklist_20260712.json"
ONTOLOGY_REVIEW_DECISIONS_PATH = ROOT / "data_private" / "curriculum" / "ontology_review_decisions.json"
ONTOLOGY_AXIS_REGISTRY_PATH = ROOT / "data_private" / "curriculum" / "axis_registry.json"
ONTOLOGY_CONCEPT_REGISTRY_PATH = ROOT / "data_private" / "concept_registry.json"
ONTOLOGY_REGISTRY_INDEX_PATH = ROOT / "data_private" / "curriculum" / "registry_index.json"
ONTOLOGY_QUERY_MAP_PATH = ROOT / "data_private" / "curriculum" / "ontology_query_map.json"
ONTOLOGY_TRUST_KERNEL_RELEASES_PATH = ROOT / "data_private" / "curriculum" / "ontology_trust_kernel_releases.json"
VIEWABLE_COURSE_MEDIA_EXTS = {".bmp", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

STUDENT_COURSE_CATALOG = (
    {"id": "infect", "name": "감염학", "status": "preparing"},
    {"id": "msk", "name": "근골격학", "status": "preparing"},
    {"id": "endo", "name": "내분비학", "status": "preparing"},
    {"id": "immder", "name": "면역및피부질환", "status": "preparing"},
    {"id": "repro", "name": "생식계의학", "status": "preparing"},
    {"id": "grow", "name": "성장발달노화", "status": "preparing"},
    {"id": "gi", "name": "소화기및영양학", "status": "preparing"},
    {"id": "cardio", "name": "순환기학", "status": "preparing"},
    {
        "id": "neuro",
        "name": "신경및특수감각기학",
        "status": "released",
        "qbank_course": "신경 및 특수감각기학",
    },
    {"id": "renal", "name": "신장비뇨기학", "status": "preparing"},
    {"id": "hsm1", "name": "인간·사회·의료(I)", "status": "no_public_questions"},
    {"id": "hsm2", "name": "인간·사회·의료(II)", "status": "no_public_questions"},
    {"id": "psych", "name": "정신의학", "status": "no_public_questions"},
    {"id": "pharm", "name": "질병의이해와약물요법", "status": "preparing"},
    {
        "id": "hemeonc",
        "name": "혈액및종양학",
        "status": "released",
        "qbank_course": "혈액종양내과",
    },
    {"id": "resp", "name": "호흡기학", "status": "preparing"},
)
DEFAULT_STUDENT_FAVORITE_COURSE_IDS = ("neuro", "hemeonc")

app = FastAPI(
    title="P:accine Studio API",
    description="HTML/CSS 교수용 Studio UI를 위한 로컬 API",
    version="0.1.0",
)

_DEFAULT_ALLOWED_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"]
_EXTRA_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("APP_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([*_DEFAULT_ALLOWED_ORIGINS, *_EXTRA_ALLOWED_ORIGINS])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 접근 게이트 — 허용된 이메일 1개(+ 비밀번호)만 로그인 가능. 이메일 자체는 비밀이 아니므로
# 반드시 비밀번호와 함께 확인한다("허용 계정 1개" 게이트이지, 이메일만 치면 들어오는 게 아님).
# 환경변수 미설정 시(로컬 개발) 완전히 비활성 — 동작 변화 없음.
# 배포 시 APP_ALLOWED_EMAIL / APP_AUTH_PASSWORD 를 설정하면 전체 앱에 로그인이 걸린다.
_ALLOWED_EMAIL = os.getenv("APP_ALLOWED_EMAIL", "").strip().lower()
_AUTH_PASSWORD = os.getenv("APP_AUTH_PASSWORD", "")
# 세션 서명 비밀키. 미설정 시 프로세스 시작할 때마다 새로 생성(재시작하면 기존 세션 무효 — 배포 시엔
# 명시적으로 설정 권장, DEPLOYMENT_NOTES.md 참고).
_SESSION_SECRET = os.getenv("APP_SESSION_SECRET") or hashlib.sha256(os.urandom(32)).hexdigest()
_SESSION_COOKIE = "paccine_session"
_ROLE_COOKIE = "paccine_role"
_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30일
_COOKIE_SECURE = os.getenv("APP_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}
_AUTH_PUBLIC_PATHS = {"/login", "/api/auth/login", "/api/health"}


def _sign_session_token(email: str, expires_at: int) -> str:
    payload = f"{email}:{expires_at}"
    signature = hmac.new(_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _verify_session_token(token: str) -> str | None:
    try:
        email, expires_at_str, signature = token.split(":", 2)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return None
    expected = _sign_session_token(email, expires_at)
    if not hmac.compare_digest(expected, token):
        return None
    if time.time() > expires_at:
        return None
    return email


def _auth_gate_enabled() -> bool:
    return bool(_ALLOWED_EMAIL and _AUTH_PASSWORD)


def _request_identity(request: Request) -> str | None:
    if not _auth_gate_enabled():
        return None
    token = request.cookies.get(_SESSION_COOKIE, "")
    return _verify_session_token(token) if token else None


def _require_faculty_reviewer(request: Request) -> str:
    """교수 검수 API를 학생 workspace에서 호출하지 못하게 한다."""
    if request.cookies.get(_ROLE_COOKIE, "") != "faculty":
        raise HTTPException(status_code=403, detail="교수 스튜디오 로그인이 필요합니다.")
    identity = _request_identity(request)
    if _auth_gate_enabled() and not identity:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return f"faculty:{identity}" if identity else "faculty:local-reviewer"


_LOGIN_PAGE_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>로그인 · P:accine</title>
<style>
:root{--deep:#0f2a29;--teal:#0e7c7b;--teal2:#0a5d5c;--paper:#f4f2ec;--ink:#12211f;
  --body:#39504d;--muted:#758581;--line:#d9d3c6;--danger:#a13f31}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--paper);color:var(--ink);
  font-family:"Pretendard","Apple SD Gothic Neo","Noto Sans KR",sans-serif}
.shell{min-height:100vh;display:grid;grid-template-columns:minmax(0,1.02fr) minmax(440px,.98fr)}
.brand-panel{position:relative;overflow:hidden;padding:48px 52px;display:flex;flex-direction:column;
  justify-content:space-between;background:var(--deep);color:#eaf4f3}
.brand-panel:before,.brand-panel:after{content:"";position:absolute;border:1px solid rgba(95,208,190,.18);border-radius:50%}
.brand-panel:before{width:440px;height:440px;right:-180px;top:90px}.brand-panel:after{width:260px;height:260px;left:-100px;bottom:-80px}
.brand{position:relative;display:flex;align-items:center;gap:13px}.brand-mark{width:46px;height:46px;border-radius:14px;
  display:grid;place-items:center;background:var(--teal);font-size:23px;font-weight:850}.brand strong{display:block;font-size:20px}
.brand small{display:block;margin-top:3px;color:#7fa8a5;font-size:12px}.brand-copy{position:relative;max-width:470px}
.brand-copy span{display:block;margin-bottom:13px;color:#76d7ca;font-size:11px;font-weight:850;letter-spacing:.15em;text-transform:uppercase}
.brand-copy h1{margin:0;font-size:clamp(31px,4vw,48px);line-height:1.22;letter-spacing:-.045em}
.brand-copy p{max-width:430px;margin:20px 0 0;color:#a8ccc9;font-size:15px;line-height:1.75}
.capabilities{position:relative;display:flex;flex-wrap:wrap;gap:9px}.capabilities span{padding:7px 10px;border:1px solid rgba(234,244,243,.14);
  border-radius:999px;color:#a8ccc9;font-size:11px;font-weight:700}.form-panel{display:grid;place-items:center;padding:46px}
.card{width:min(430px,100%)}.eyebrow{margin:0 0 9px;color:var(--teal);font-size:11px;font-weight:850;letter-spacing:.14em;text-transform:uppercase}
h2{margin:0;font-size:29px;letter-spacing:-.04em}.hint{margin:9px 0 23px;color:var(--muted);font-size:14px;line-height:1.6}
.role-picker{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:20px;padding:5px;background:#e9e6df;border-radius:13px}
.role-picker button{min-height:48px;border:1px solid transparent;border-radius:10px;background:transparent;color:var(--muted);font-weight:800}
.role-picker button.active{border-color:var(--line);background:#fff;color:var(--deep);box-shadow:0 6px 18px rgba(15,42,41,.08)}
.role-note{min-height:37px;margin:-8px 0 17px;color:var(--muted);font-size:12px;line-height:1.55}
form{display:grid;gap:14px}label{display:grid;gap:7px;color:var(--body);font-size:13px;font-weight:700}
input{width:100%;padding:13px 14px;border:1px solid var(--line);border-radius:11px;background:#fbfaf7;color:var(--ink);font:inherit}
input:focus{outline:0;border-color:var(--teal);box-shadow:0 0 0 3px rgba(14,124,123,.13)}
.submit{min-height:50px;margin-top:2px;border:0;border-radius:12px;background:var(--deep);color:#fff;font:inherit;font-weight:800;cursor:pointer}
.submit:hover{background:#16413e}.submit:disabled{opacity:.65;cursor:wait}.err{min-height:20px;margin:0;color:var(--danger);font-size:12px}
.boundary{margin:18px 0 0;padding-top:17px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;line-height:1.6}
@media(max-width:820px){.shell{display:block}.brand-panel{min-height:245px;padding:28px 24px;gap:46px}.brand-copy h1{font-size:30px}.brand-copy p{display:none}
  .capabilities{display:none}.form-panel{padding:34px 22px}.card{max-width:480px}}
</style></head><body>
<main class="shell">
  <section class="brand-panel">
    <div class="brand"><span class="brand-mark">P</span><span><strong>P:accine</strong><small>PNU Medicine · Learning OS</small></span></div>
    <div class="brand-copy"><span>Ontology-powered medical learning</span><h1>문항 생성부터<br>학습과 복습까지,<br>하나의 흐름으로.</h1><p>교수자는 근거를 확인하며 문항을 만들고, 학생은 문제를 풀고 피드백과 FSRS 복습을 이어갑니다.</p></div>
    <div class="capabilities"><span>Ontology 문항 생성</span><span>근거·가이드라인</span><span>FSRS-6 복습</span><span>의료 학습 챗봇</span></div>
  </section>
  <section class="form-panel"><div class="card">
    <p class="eyebrow">Select workspace</p><h2>P:accine 로그인</h2><p class="hint">접속할 작업공간을 선택한 뒤 발표용 계정으로 로그인하세요.</p>
    <div class="role-picker" role="group" aria-label="작업공간 선택">
      <button type="button" data-role="student" class="active">학생 학습</button><button type="button" data-role="faculty">교수 스튜디오</button>
    </div>
    <p class="role-note" id="role-note">과목 선택, 문항 풀이, 피드백, FSRS 복습과 의료 챗봇을 사용합니다.</p>
    <form id="f">
      <label>아이디 또는 이메일<input type="text" id="email" autocomplete="username" required></label>
      <label>비밀번호<input type="password" id="password" autocomplete="current-password" required></label>
      <p class="err" id="err" role="alert"></p><button class="submit" id="submit" type="submit">학생 화면으로 로그인</button>
    </form>
    <p class="boundary">시연용 단일 계정입니다. 학생 화면과 교수 화면은 로그인 이후 서로 다른 주소와 내비게이션으로 분리됩니다.</p>
  </div></section>
</main>
<script>
let role = 'student';
const params = new URLSearchParams(location.search);
const requestedNext = params.get('next') || '';
if (requestedNext.startsWith('/faculty')) role = 'faculty';
const notes = {
  student: '과목 선택, 문항 풀이, 피드백, FSRS 복습과 의료 챗봇을 사용합니다.',
  faculty: 'Ontology 기반 문항 생성, 검토·승인, 근거 관리와 내보내기를 사용합니다.'
};
function renderRole() {
  document.querySelectorAll('[data-role]').forEach((button) => button.classList.toggle('active', button.dataset.role === role));
  document.getElementById('role-note').textContent = notes[role];
  document.getElementById('submit').textContent = role === 'faculty' ? '교수 화면으로 로그인' : '학생 화면으로 로그인';
}
document.querySelectorAll('[data-role]').forEach((button) => button.addEventListener('click', () => { role = button.dataset.role; renderRole(); }));
renderRole();
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const submit = document.getElementById('submit');
  submit.disabled = true;
  document.getElementById('err').textContent = '';
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({email, password, role, next: requestedNext}),
  });
  let payload = {};
  try { payload = await res.json(); } catch (_) {}
  if (res.ok) {
    window.location.href = payload.redirect_to || (role === 'faculty' ? '/faculty-studio-v2/' : '/student/');
  } else {
    document.getElementById('err').textContent = '이메일 또는 비밀번호가 올바르지 않습니다.';
    submit.disabled = false;
  }
});
</script></body></html>"""


@app.get("/login")
def login_page() -> HTMLResponse:
    return HTMLResponse(_LOGIN_PAGE_HTML)


def _safe_next_path(value: object) -> str:
    path = str(value or "").strip()
    if not path.startswith("/") or path.startswith("//") or "\r" in path or "\n" in path:
        return ""
    return path


@app.post("/api/auth/login")
async def auth_login(payload: Annotated[dict, Body()]) -> JSONResponse:
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    role = "faculty" if str(payload.get("role") or "").strip().lower() == "faculty" else "student"
    requested_next = _safe_next_path(payload.get("next"))
    redirect_to = requested_next if requested_next and requested_next != "/" else (
        "/faculty-studio-v2/" if role == "faculty" else "/student/"
    )
    if not _auth_gate_enabled():
        response = JSONResponse({"ok": True, "note": "게이트 비활성(로컬 개발)", "redirect_to": redirect_to, "role": role})
        response.set_cookie(
            _ROLE_COOKIE,
            role,
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=_COOKIE_SECURE,
        )
        return response
    valid = hmac.compare_digest(email, _ALLOWED_EMAIL) and hmac.compare_digest(password, _AUTH_PASSWORD)
    if not valid:
        return JSONResponse({"ok": False, "detail": "이메일 또는 비밀번호가 올바르지 않습니다."}, status_code=401)
    expires_at = int(time.time()) + _SESSION_TTL_SECONDS
    token = _sign_session_token(email, expires_at)
    response = JSONResponse({"ok": True, "redirect_to": redirect_to, "role": role})
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
    )
    response.set_cookie(
        _ROLE_COOKIE,
        role,
        max_age=_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
    )
    return response


@app.post("/api/auth/logout")
def auth_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(_SESSION_COOKIE, httponly=True, samesite="lax", secure=_COOKIE_SECURE)
    response.delete_cookie(_ROLE_COOKIE, httponly=True, samesite="lax", secure=_COOKIE_SECURE)
    return response


@app.middleware("http")
async def _email_login_gate(request: Request, call_next):
    if not _auth_gate_enabled():
        return await call_next(request)
    if request.url.path in _AUTH_PUBLIC_PATHS:
        return await call_next(request)

    token = request.cookies.get(_SESSION_COOKIE, "")
    email = _verify_session_token(token) if token else None
    if email and hmac.compare_digest(email, _ALLOWED_EMAIL):
        return await call_next(request)

    accepts_html = "text/html" in request.headers.get("accept", "")
    if accepts_html:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return RedirectResponse(url=f"/login?next={quote(next_path, safe='')}", status_code=307)
    return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)


async def save_upload_file(upload: UploadFile, *, kind: str):
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{upload.filename or kind} 파일이 비어 있습니다.")
    return save_upload_bytes(content, upload.filename or f"{kind}.txt", kind=kind)


def form_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def ensure_course_exam_dirs() -> None:
    for directory in (
        COURSE_EXAM_UPLOAD_DIR,
        COURSE_EXAM_EXTRACTED_DIR,
        COURSE_EXAM_MARKDOWN_DIR,
        COURSE_EXAM_MEDIA_DIR,
        COURSE_EXAM_PREVIEW_DIR,
        LEARNING_ANALYTICS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def safe_int(value, default: int | None = None) -> int | None:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalized_metadata_values(value) -> list[str]:
    """Normalize JSON arrays or comma/newline-delimited form values."""
    if isinstance(value, list):
        return list(
            dict.fromkeys(
                str(item).strip()
                for item in value
                if str(item or "").strip()
            )
        )
    return split_metadata_values(str(value or ""))


def normalize_attempt_choices(values) -> list[str]:
    if values is None:
        return []
    source = values if isinstance(values, list) else [values]
    normalized = []
    for value in source:
        text = str(value or "").strip()
        if not text:
            continue
        if text in {"①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"}:
            text = str("①②③④⑤⑥⑦⑧".index(text) + 1)
        normalized.append(text)
    return list(dict.fromkeys(normalized))


def normalize_attempt_payload(payload: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    selected = normalize_attempt_choices(
        payload.get("selected_choice_numbers")
        or payload.get("choices_selected")
        or payload.get("selected_choices")
        or payload.get("choice_selected")
    )
    answer_keys = normalize_attempt_choices(payload.get("answer_keys") or payload.get("answers"))
    labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}
    source_meta = payload.get("source_meta") if isinstance(payload.get("source_meta"), dict) else {}
    choice_texts = payload.get("choice_texts") if isinstance(payload.get("choice_texts"), dict) else {}
    time_ms = safe_int(payload.get("time_ms"))
    if time_ms is None:
        time_sec = safe_int(payload.get("time_spent_sec"), 0) or 0
        time_ms = time_sec * 1000
    time_ms = max(0, min(time_ms, 6 * 60 * 60 * 1000))
    return {
        "event_id": str(payload.get("event_id") or f"attempt_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"),
        "session_id": str(payload.get("session_id") or "local_session"),
        "user_id": str(payload.get("user_id") or "local_student"),
        "role": str(payload.get("role") or "student"),
        "exam_id": str(payload.get("exam_id") or source_meta.get("exam_id") or ""),
        "course_id": str(payload.get("course_id") or source_meta.get("course_id") or labels.get("course_id") or ""),
        "course_name": str(payload.get("course_name") or source_meta.get("course_name") or labels.get("course_name_labeled") or labels.get("course_name") or ""),
        "source_file": str(payload.get("source_file") or source_meta.get("source_file") or ""),
        "question_id": str(payload.get("question_id") or ""),
        "question_number": safe_int(payload.get("question_number")),
        "stem_preview": str(payload.get("stem_preview") or "")[:240],
        "question_type": str(payload.get("question_type") or labels.get("question_type_labeled") or labels.get("question_type") or ""),
        "choice_texts": {str(key): str(value) for key, value in choice_texts.items()},
        "selected_choices": selected,
        "answer_keys": answer_keys,
        "is_correct": bool(payload.get("is_correct")),
        "time_ms": time_ms,
        "answered_at": now,
        "is_bookmarked": bool(payload.get("is_bookmarked")),
        "flag_type": payload.get("flag_type") or None,
        "labels": labels,
        "source_meta": source_meta,
    }


def iter_attempt_events(*, exam_id: str | None = None, user_id: str | None = None) -> list[dict]:
    ensure_course_exam_dirs()
    if not ATTEMPTS_LOG_PATH.exists():
        return []
    events = []
    for line in ATTEMPTS_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if exam_id and event.get("exam_id") != exam_id:
            continue
        if user_id and event.get("user_id") != user_id:
            continue
        events.append(event)
    return events


def _append_private_jsonl(path: Path, event: dict) -> None:
    """Append one local prototype event with the same private-file guarantees as attempts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
        file.flush()
        os.fsync(file.fileno())
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    os.chmod(path, 0o600)


def _iter_private_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _practice_session_started(session_id: str) -> dict:
    for event in reversed(_iter_private_jsonl(PRACTICE_SESSIONS_LOG_PATH)):
        if event.get("event_type") == "session_started" and event.get("session_id") == session_id:
            return event
    raise HTTPException(status_code=404, detail="학습 세션을 찾을 수 없습니다.")


def attempt_label_path(event: dict) -> str:
    labels = event.get("labels") or {}
    parts = [
        labels.get("course_name_labeled") or event.get("course_name") or labels.get("course_name"),
        labels.get("major_category"),
        labels.get("topic") or labels.get("subtopic"),
        labels.get("assessment_domain"),
    ]
    return " > ".join(str(part).strip() for part in parts if str(part or "").strip()) or "미분류"


def aggregate_student_weakness(events: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        grouped[attempt_label_path(event)].append(event)
    rows = []
    for label_path, items in grouped.items():
        attempts = len(items)
        correct = sum(1 for item in items if item.get("is_correct"))
        avg_time_ms = sum(safe_int(item.get("time_ms"), 0) or 0 for item in items) / max(attempts, 1)
        rows.append(
            {
                "label_path": label_path,
                "attempt_count": attempts,
                "correct_count": correct,
                "correct_rate_pct": round(correct / attempts * 100, 1) if attempts else 0,
                "avg_time_sec": round(avg_time_ms / 1000, 1),
            }
        )
    return sorted(rows, key=lambda row: (row["correct_rate_pct"], -row["attempt_count"], row["label_path"]))


def aggregate_student_ontology_weakness(events: list[dict]) -> list[dict]:
    """Aggregate attempts by trusted ``concept x target axis`` snapshots.

    ``sample_size`` is intentionally explicit: these rows are descriptive
    learning signals, not validated mastery estimates, especially for n=1.
    Legacy events without ontology metadata remain readable elsewhere and are
    omitted from this ontology-specific view.
    """
    grouped: dict[tuple[str, str, str], dict] = {}
    for event in events:
        snapshot = event.get("ontology_snapshot") if isinstance(event.get("ontology_snapshot"), dict) else {}
        if event.get("ontology_snapshot_status") != "resolved_from_stored_question":
            continue
        if not snapshot.get("analytics_eligible"):
            continue
        blueprint = event.get("question_blueprint") if isinstance(event.get("question_blueprint"), dict) else {}
        target = blueprint.get("target") if isinstance(blueprint.get("target"), dict) else {}
        disease_concept_id = str(
            event.get("disease_concept_id")
            or snapshot.get("disease_concept_id")
            or blueprint.get("disease_concept_id")
            or target.get("disease_concept_id")
            or ""
        ).strip()
        if not disease_concept_id:
            continue
        assessment_domain = str(
            event.get("assessment_domain")
            or snapshot.get("assessment_domain")
            or blueprint.get("assessment_domain")
            or ""
        ).strip()
        explicit_axis_type = str(
            event.get("target_axis_type")
            or snapshot.get("target_axis_type")
            or blueprint.get("target_axis_type")
            or target.get("axis_type")
            or ""
        ).strip()
        axis_ids = _nonempty_string_list(
            event.get("target_axis_ids")
            or snapshot.get("target_axis_ids")
            or blueprint.get("target_axis_ids")
            or target.get("axis_ids")
        )
        if not axis_ids:
            axis_ids = [""]

        selected_metadata = event.get("selected_choice_ontology")
        if not isinstance(selected_metadata, list):
            selected_metadata = snapshot.get("selected_choices")
        selected_metadata = selected_metadata if isinstance(selected_metadata, list) else []
        event_misconceptions = {
            str(item.get("misconception_id") or "").strip()
            for item in selected_metadata
            if isinstance(item, dict)
            and not item.get("is_correct_choice")
            and str(item.get("misconception_id") or "").strip()
        }
        event_sources = {
            str(item.get("source_id") or "").strip()
            for item in selected_metadata
            if isinstance(item, dict)
            and not item.get("is_correct_choice")
            and str(item.get("source_id") or "").strip()
        }

        for axis_id in axis_ids:
            axis_type = explicit_axis_type or _axis_type_from_id(axis_id) or assessment_domain
            key = (disease_concept_id, axis_type, axis_id)
            bucket = grouped.setdefault(
                key,
                {
                    "events": 0,
                    "correct": 0,
                    "time_ms": 0,
                    "misconceptions": Counter(),
                    "distractor_sources": Counter(),
                    "assessment_domains": Counter(),
                },
            )
            bucket["events"] += 1
            if event.get("is_correct"):
                bucket["correct"] += 1
            bucket["time_ms"] += safe_int(event.get("time_ms"), 0) or 0
            bucket["misconceptions"].update(event_misconceptions)
            bucket["distractor_sources"].update(event_sources)
            if assessment_domain:
                bucket["assessment_domains"].update([assessment_domain])

    rows = []
    for (concept_id, axis_type, axis_id), bucket in grouped.items():
        sample_size = bucket["events"]
        assessment_domains = sorted(bucket["assessment_domains"])
        rows.append(
            {
                "disease_concept_id": concept_id,
                "axis_type": axis_type or None,
                "axis_id": axis_id or None,
                "assessment_domain": assessment_domains[0] if len(assessment_domains) == 1 else None,
                "assessment_domains": assessment_domains,
                "sample_size": sample_size,
                "attempt_count": sample_size,
                "correct_count": bucket["correct"],
                "incorrect_count": sample_size - bucket["correct"],
                "correct_rate_pct": round(bucket["correct"] / sample_size * 100, 1) if sample_size else 0,
                "avg_time_sec": round(bucket["time_ms"] / max(sample_size, 1) / 1000, 1),
                "misconceptions": [
                    {"misconception_id": item_id, "count": count}
                    for item_id, count in bucket["misconceptions"].most_common()
                ],
                "distractor_sources": [
                    {"source_id": source_id, "count": count}
                    for source_id, count in bucket["distractor_sources"].most_common()
                ],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["correct_rate_pct"],
            -row["sample_size"],
            row["disease_concept_id"],
            row.get("axis_type") or "",
            row.get("axis_id") or "",
        ),
    )


def question_label_path(question: dict) -> str:
    """문항 labels → attempt_label_path와 동일 형식의 라벨 경로."""
    labels = question.get("labels") or {}
    parts = [
        labels.get("course_name"),
        labels.get("major_category"),
        labels.get("topic") or labels.get("subtopic"),
        labels.get("assessment_domain"),
    ]
    return " > ".join(str(part).strip() for part in parts if str(part or "").strip()) or "미분류"


def iter_all_labeled_questions():
    """라벨 뱅크(extracted/*.json, .bak 제외)의 (exam_id, question)을 순회."""
    ensure_course_exam_dirs()
    for path in sorted(COURSE_EXAM_EXTRACTED_DIR.glob("*.json")):
        if ".bak" in path.name:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for question in record.get("questions", []):
            yield path.stem, question


def load_practice_question_lookup(exam_id: str | None) -> tuple[dict, dict]:
    if not exam_id:
        return {}, {}
    try:
        _, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        return {}, {}
    media_by_id = {
        asset.get("media_id"): asset
        for asset in record.get("media_assets", [])
        if asset.get("media_id")
    }
    questions = [
        course_exam_practice_question(question, media_by_id)
        for question in record.get("questions", [])
        if course_exam_is_practice_ready(question)
    ]
    lookup = {
        str(question.get("question_id") or question.get("question_number")): question
        for question in questions
    }
    return lookup, course_exam_summary(record)


def aggregate_faculty_items(events: list[dict], exam_id: str | None) -> tuple[list[dict], dict]:
    question_lookup, summary = load_practice_question_lookup(exam_id)
    events_by_question: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event.get("question_id"):
            events_by_question[str(event["question_id"])].append(event)

    all_question_ids = list(dict.fromkeys([*question_lookup.keys(), *events_by_question.keys()]))
    rows = []
    for question_id in all_question_ids:
        question = question_lookup.get(question_id, {})
        items = events_by_question.get(question_id, [])
        first_item = items[0] if items else {}
        attempts = len(items)
        correct = sum(1 for item in items if item.get("is_correct"))
        choice_counter = Counter()
        for item in items:
            for choice in normalize_attempt_choices(item.get("selected_choices")):
                choice_counter[choice] += 1
        choices = []
        raw_choices = question.get("choices") or first_item.get("choice_texts") or {}
        answer_keys = course_exam_answer_values(question) or (first_item.get("answer_keys") if first_item else [])
        answer_keys = normalize_attempt_choices(answer_keys)
        if not raw_choices:
            fallback_keys = sorted(
                {*answer_keys, *choice_counter.keys()},
                key=lambda value: safe_int(value, 999) or 999,
            )
            raw_choices = {key: f"{key}번 선택지" for key in fallback_keys}
        if isinstance(raw_choices, dict):
            choice_items = sorted(raw_choices.items(), key=lambda item: safe_int(item[0], 999) or 999)
        else:
            choice_items = [(str(index + 1), text) for index, text in enumerate(raw_choices or [])]
        for choice_key, choice_text in choice_items:
            key = normalize_attempt_choices(choice_key)[0] if normalize_attempt_choices(choice_key) else str(choice_key)
            selected_count = choice_counter.get(key, 0)
            choices.append(
                {
                    "choice": key,
                    "choice_text": choice_text,
                    "is_correct": key in answer_keys,
                    "selected_count": selected_count,
                    "selected_pct": round(selected_count / attempts * 100, 1) if attempts else 0,
                }
            )
        avg_time_ms = sum(safe_int(item.get("time_ms"), 0) or 0 for item in items) / max(attempts, 1)
        wrong_choices = [choice for choice in choices if not choice["is_correct"]]
        top_wrong = max(wrong_choices, key=lambda item: item["selected_count"], default=None)
        rows.append(
            {
                "question_id": question_id,
                "question_number": question.get("question_number") or first_item.get("question_number") or safe_int(question_id),
                "stem_preview": str(question.get("stem") or first_item.get("stem_preview") or "").strip()[:160],
                "labels": question.get("labels") or first_item.get("labels") or {},
                "attempt_count": attempts,
                "correct_count": correct,
                "correct_rate_pct": round(correct / attempts * 100, 1) if attempts else 0,
                "avg_time_sec": round(avg_time_ms / 1000, 1),
                "choices": choices,
                "top_wrong_choice": top_wrong,
            }
        )
    return sorted(rows, key=lambda row: safe_int(row.get("question_number"), 9999) or 9999), summary


def course_exam_summary(record: dict) -> dict:
    questions = record.get("questions", [])
    exam = record.get("exam", {})
    labeling = exam.get("labeling", {})
    def has_question_labels(question: dict) -> bool:
        labels = question.get("labels") or {}
        if labels.get("labeling_status") == "labeled":
            return True
        return any(
            labels.get(key)
            for key in (
                "course_name_labeled",
                "course_name",
                "major_category",
                "topic",
                "subtopic",
                "assessment_domain",
                "question_type_labeled",
                "question_type",
                "concept_tags",
            )
        )

    return {
        "source_exam": exam.get("source_exam"),
        "source_file": exam.get("source_file"),
        "course_id": exam.get("course_id"),
        "course_name": exam.get("course_name"),
        "grade": exam.get("grade"),
        "exam_date": exam.get("exam_date"),
        "round_label": exam.get("round_label"),
        "period_label": exam.get("period_label"),
        "parser_version": exam.get("parser_version"),
        "question_count": len(questions),
        "expected_objective_count": record.get("exam", {}).get("objective_count_from_filename"),
        "with_answer_count": sum(1 for q in questions if q.get("answer") is not None),
        "with_stimulus_count": sum(1 for q in questions if q.get("stimulus")),
        "with_explanation_count": sum(1 for q in questions if q.get("explanation")),
        "needs_review_count": sum(1 for q in questions if q.get("needs_review")),
        "media_asset_count": len(record.get("media_assets", [])),
        "media_linked_question_count": sum(
            1 for q in questions if q.get("media", {}).get("media_refs")
        ),
        "extraction_warnings": record.get("exam", {}).get("extraction_warnings", []),
        "labeling": labeling,
        "labeled_question_count": sum(
            1 for q in questions if has_question_labels(q)
        ),
    }


def archive_course_exam_review_set(record: dict) -> dict:
    """Copy a structured course exam into the Faculty Studio review queue.

    The extracted course-exam record remains the source of truth. The review set is
    a separate faculty draft so edits and approvals never mutate the imported exam.
    """
    exam = record.get("exam") if isinstance(record.get("exam"), dict) else {}
    source_exam = str(exam.get("source_exam") or "course_exam").strip() or "course_exam"
    media_by_id = {
        str(asset.get("media_id")): asset
        for asset in record.get("media_assets", [])
        if isinstance(asset, dict) and asset.get("media_id")
    }
    records = []
    for index, raw in enumerate(record.get("questions", []), 1):
        if not isinstance(raw, dict):
            continue
        choices = raw.get("choices")
        if isinstance(choices, dict):
            options = [str(choices.get(str(number)) or "").strip() for number in range(1, 6)]
        elif isinstance(choices, list):
            options = [str(value or "").strip() for value in choices[:5]]
            options.extend([""] * (5 - len(options)))
        else:
            options = [""] * 5

        answer_raw = raw.get("answer")
        try:
            answer = int(str(answer_raw).strip()) if answer_raw not in (None, "") else None
        except ValueError:
            answer = None
        if answer not in {1, 2, 3, 4, 5}:
            answer = None

        reasons = [str(value).strip() for value in (raw.get("review_reasons") or []) if str(value).strip()]
        if not all(options):
            reasons.append("choice_mapping_incomplete")
        if answer is None:
            reasons.append("answer_mapping_missing")

        media_refs = []
        raw_media = raw.get("media") if isinstance(raw.get("media"), dict) else {}
        for link in raw_media.get("media_refs", []) or []:
            if not isinstance(link, dict):
                continue
            asset = media_by_id.get(str(link.get("media_id"))) or {}
            filename = Path(str(asset.get("file_path") or asset.get("relative_path") or "")).name
            media_refs.append({
                "asset_id": link.get("media_id"),
                "modality": asset.get("modality") or "COURSE EXAM",
                "caption": asset.get("caption") or asset.get("storage_id") or link.get("media_id"),
                "url": (
                    f"/api/course-exams/media/{quote(source_exam, safe='')}/{quote(filename, safe='')}"
                    if filename else ""
                ),
                "image_match_confidence": link.get("match_confidence") or asset.get("match_confidence"),
                "needs_review": bool(link.get("needs_review", True)),
            })

        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
        reference_notes = [
            {
                "ref_no": ref_index,
                "source": item.get("title") or item.get("source") or item.get("journal") or "가져온 근거",
                "basis": " · ".join(str(value) for value in (item.get("journal"), item.get("year"), item.get("matched_concept")) if value),
                "url": item.get("url") or "",
            }
            for ref_index, item in enumerate(evidence, 1)
            if isinstance(item, dict)
        ]
        labels = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
        confidence_values = []
        for media_ref in media_refs:
            try:
                confidence_values.append(float(media_ref.get("image_match_confidence")))
            except (TypeError, ValueError):
                continue
        records.append({
            "question_id": str(raw.get("question_id") or f"{source_exam}_Q{index:03d}"),
            "problem": str(raw.get("stem") or raw.get("problem") or "").strip(),
            "options": options,
            "answer": answer,
            "explanation": str(raw.get("explanation") or "").strip(),
            "review_status": "draft",
            "needs_review": True,
            "review_reasons": sorted(set(reasons or ["course_exam_import_requires_faculty_review"])),
            "reference_notes": reference_notes,
            "evidence_refs": evidence,
            "image_refs": media_refs,
            "image_match_confidence": min(confidence_values, default=None),
            "question_type": "image_based" if media_refs else str(labels.get("question_type") or raw.get("question_format") or "course_exam_import"),
            "labels": labels,
            "generation_mode": "course_exam_import",
        })

    source_slug = f"course_exam_{course_exam_slugify(source_exam)}"
    archive_question_set(
        source_slug,
        {
            "source_name": exam.get("source_file") or source_exam,
            "subject": exam.get("course_name") or "과정시험",
            "unit": " · ".join(str(value) for value in (exam.get("round_label"), exam.get("period_label")) if value) or "가져온 시험지",
            "provider": "course_exam_import",
            "model": exam.get("parser_version") or "structured_import",
            "question_type": "course_exam_import",
            "reference_policy": "imported_exam_review",
            "generation_mode": "course_exam_import",
            "source_exam": source_exam,
        },
        records,
    )
    return load_question_set(source_slug)


def load_course_exam_record(exam_id: str) -> tuple[Path, dict]:
    safe_name = Path(exam_id).name
    if not safe_name.endswith(".json"):
        safe_name = f"{safe_name}.json"
    record_path = (COURSE_EXAM_EXTRACTED_DIR / safe_name).resolve()
    extracted_root = COURSE_EXAM_EXTRACTED_DIR.resolve()
    if extracted_root not in record_path.parents or not record_path.exists():
        raise FileNotFoundError(exam_id)
    return record_path, json.loads(record_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=16)
def _load_json_snapshot(path_value: str, mtime_ns: int, size_bytes: int) -> dict:
    del mtime_ns, size_bytes
    path = Path(path_value)
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_snapshot(path: Path) -> dict:
    if not path.exists():
        return {}
    stat = path.stat()
    return _load_json_snapshot(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=8)
def _file_sha256_snapshot(path_value: str, mtime_ns: int, size_bytes: int) -> str:
    del mtime_ns, size_bytes
    return file_sha256(Path(path_value))


def file_sha256_snapshot(path: Path) -> str:
    stat = path.stat()
    return _file_sha256_snapshot(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def evaluate_practice_release(exam_id: str, question: dict, surface: str) -> dict:
    """Evaluate an external Trust Kernel release; inline flags never bypass it."""

    registry = load_release_registry(ONTOLOGY_TRUST_KERNEL_RELEASES_PATH)
    question_id = str(question.get("question_id") or question.get("question_number") or "")
    has_candidate = any(
        str(item.get("exam_id")) == str(exam_id)
        and str(item.get("question_id")) == question_id
        for release in registry.get("releases") or []
        for item in release.get("questions") or []
        if isinstance(item, dict)
    )
    if not has_candidate:
        return evaluate_release(
            registry=registry,
            exam_id=exam_id,
            question=question,
            surface=surface,
            concept_registry={},
            axis_registry={},
            source_hashes=None,
        )
    return evaluate_release(
        registry=registry,
        exam_id=exam_id,
        question=question,
        surface=surface,
        concept_registry=load_json_snapshot(ONTOLOGY_CONCEPT_REGISTRY_PATH),
        axis_registry=load_json_snapshot(ONTOLOGY_AXIS_REGISTRY_PATH),
        source_hashes={
            "axis_registry_sha256": file_sha256_snapshot(ONTOLOGY_AXIS_REGISTRY_PATH),
            "review_decisions_sha256": file_sha256_snapshot(ONTOLOGY_REVIEW_DECISIONS_PATH),
        },
    )


def course_exam_media_url(asset: dict) -> str | None:
    file_path_value = asset.get("file_path")
    if not file_path_value:
        return None
    file_path = Path(file_path_value)
    if not file_path.is_absolute():
        file_path = (ROOT / file_path).resolve()
    if file_path.suffix.lower() not in VIEWABLE_COURSE_MEDIA_EXTS or not file_path.exists():
        return None

    relative_path = asset.get("relative_path")
    if relative_path:
        relative = Path(relative_path)
    else:
        try:
            relative = file_path.relative_to(COURSE_EXAM_MEDIA_DIR.resolve())
        except ValueError:
            return None
    source_dir = Path(relative).parent.name
    filename = Path(relative).name
    return f"/api/course-exams/media/{quote(source_dir)}/{quote(filename)}"


def course_exam_answer_values(question: dict) -> list[str]:
    source = question.get("generated_answer")
    if not source:
        source = question.get("answer")
    values = source if isinstance(source, list) else [source]
    return [str(value).strip() for value in values if str(value or "").strip()]


def course_exam_choice_count(question: dict) -> int:
    choices = question.get("choices") or {}
    if isinstance(choices, dict):
        return sum(1 for value in choices.values() if str(value or "").strip())
    if isinstance(choices, list):
        return sum(1 for value in choices if str(value or "").strip())
    return 0


def course_exam_is_practice_ready(question: dict) -> bool:
    if not str(question.get("stem") or "").strip():
        return False
    if not course_exam_answer_values(question):
        return False
    if course_exam_choice_count(question) < 2:
        return False
    choice_text = " ".join(
        str(value)
        for value in (question.get("choices") or {}).values()
        if str(value or "").strip()
    )
    malformed_markers = ("<문제해설>", "<-케이스->", "@")
    return not any(marker in choice_text for marker in malformed_markers)


def _nonempty_string_list(value) -> list[str]:
    values = value if isinstance(value, list) else [value]
    normalized = []
    for item in values:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return list(dict.fromkeys(normalized))


def _axis_type_from_id(axis_id: str | None) -> str:
    parts = str(axis_id or "").split(":", 2)
    return parts[1] if len(parts) == 3 and parts[0] == "a" else ""


def course_exam_question_blueprint(question: dict) -> dict:
    """Return the authored blueprint unchanged so it remains schema-valid."""
    raw = question.get("question_blueprint") or question.get("QuestionBlueprint") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def course_exam_ontology_target(question: dict) -> dict:
    """Normalize only the analytics target, separately from the blueprint.

    A blueprint may list every candidate axis available to the generator. Those
    candidates are not all assessed by one item, so claim-level IDs are retained
    only when the question explicitly selected them, when there is exactly one
    candidate, or when the source anchor names one candidate axis.
    """
    raw = course_exam_question_blueprint(question)
    target = raw.get("target") if isinstance(raw.get("target"), dict) else {}
    target_axis = raw.get("target_axis")
    target_axis = target_axis if isinstance(target_axis, dict) else {}
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    grounding_trace = question.get("grounding_trace") if isinstance(question.get("grounding_trace"), dict) else {}
    selection = raw.get("selection") if isinstance(raw.get("selection"), dict) else {}

    disease_concept_id = str(
        raw.get("disease_concept_id")
        or target.get("disease_concept_id")
        or question.get("disease_concept_id")
        or labels.get("disease_concept_id")
        or grounding_trace.get("disease_concept_id")
        or ""
    ).strip()
    assessment_domain = str(
        raw.get("assessment_domain")
        or target.get("assessment_domain")
        or question.get("assessment_domain")
        or labels.get("assessment_domain")
        or ""
    ).strip()

    explicit_axis_ids: list[str] = []
    for container in (question, raw, target_axis):
        if not isinstance(container, dict):
            continue
        for key in ("target_axis_ids", "axis_ids", "target_axis_id", "axis_id"):
            explicit_axis_ids.extend(_nonempty_string_list(container.get(key)))
    axis_ids = list(dict.fromkeys(explicit_axis_ids))

    blueprint_candidate_ids = _nonempty_string_list(target.get("axis_ids"))
    ids_source = str(selection.get("target_axis_ids_source") or "").strip()
    if not axis_ids and ids_source == "explicit_axis_ids":
        axis_ids = blueprint_candidate_ids
    elif not axis_ids and len(blueprint_candidate_ids) == 1:
        axis_ids = blueprint_candidate_ids

    # The generation pipeline currently stores its selected target axis here.
    # Only accept a syntactically recognisable axis id; prose source anchors are
    # evidence notes and must not silently become ontology identifiers.
    pma_solution = question.get("pma_solution") if isinstance(question.get("pma_solution"), dict) else {}
    source_anchor = str(pma_solution.get("source_anchor") or "").strip()
    if _axis_type_from_id(source_anchor) and (
        not blueprint_candidate_ids or source_anchor in blueprint_candidate_ids
    ):
        axis_ids = []
        axis_ids.append(source_anchor)
    axis_ids = list(dict.fromkeys(axis_ids))

    axis_type = str(
        raw.get("target_axis_type")
        or raw.get("axis_type")
        or target.get("target_axis_type")
        or target.get("axis_type")
        or target_axis.get("axis_type")
        or question.get("target_axis_type")
        or question.get("axis_type")
        or ""
    ).strip()
    if not axis_type and axis_ids:
        inferred = {_axis_type_from_id(axis_id) for axis_id in axis_ids}
        inferred.discard("")
        if len(inferred) == 1:
            axis_type = next(iter(inferred))

    return {
        "disease_concept_id": disease_concept_id or None,
        "assessment_domain": assessment_domain or None,
        "target_axis_type": axis_type or None,
        "target_axis_ids": axis_ids,
        "target_axis_resolution": (
            "explicit_or_single" if axis_ids else "axis_type_only"
        ),
    }


def course_exam_choice_ontology(question: dict) -> dict[str, dict]:
    """Normalize the choice provenance needed for feedback snapshots."""
    explanations = question.get("choice_explanations") or question.get("explanations_by_choice")
    if not isinstance(explanations, dict):
        pma_solution = question.get("pma_solution") if isinstance(question.get("pma_solution"), dict) else {}
        explanations = pma_solution.get("choice_explanations")
    if not isinstance(explanations, dict):
        return {}

    result: dict[str, dict] = {}
    for raw_key, raw_value in explanations.items():
        if not isinstance(raw_value, dict):
            continue
        normalized_key = normalize_attempt_choices(raw_key)
        choice_key = normalized_key[0] if normalized_key else str(raw_key).strip()
        if not choice_key:
            continue
        result[choice_key] = {
            "source_id": str(raw_value.get("source_id") or "").strip(),
            "misconception_id": str(raw_value.get("misconception_id") or "").strip(),
            "misconception": str(raw_value.get("misconception") or "").strip(),
            "why_attractive": str(raw_value.get("why_attractive") or "").strip(),
            "provenance": str(raw_value.get("provenance") or "").strip(),
        }
    return result


def course_exam_practice_question(question: dict, media_by_id: dict[str, dict]) -> dict:
    question_blueprint = course_exam_question_blueprint(question)
    ontology_target = course_exam_ontology_target(question)
    choice_ontology = course_exam_choice_ontology(question)
    media_refs = []
    for ref in question.get("media", {}).get("media_refs") or []:
        asset = media_by_id.get(ref.get("media_id"), {})
        media_refs.append(
            {
                **ref,
                "url": course_exam_media_url(asset),
                "filename": Path(asset.get("file_path") or "").name,
                "caption": asset.get("caption"),
                "modality": asset.get("modality"),
                "needs_review": ref.get("needs_review", asset.get("needs_review", True)),
            }
        )
    return {
        "question_id": question.get("question_id"),
        "question_number": question.get("question_number"),
        "stem": question.get("stem"),
        "stimulus": question.get("stimulus"),
        "lab_values": question.get("lab_values") or [],
        "choices": question.get("choices") or {},
        "answer": question.get("answer"),
        "generated_answer": question.get("generated_answer"),
        "explanation": question.get("explanation"),
        "key_info": question.get("key_info"),
        "answer_rationale": question.get("answer_rationale"),
        "choice_explanations": question.get("choice_explanations") or question.get("explanations_by_choice"),
        "key_learning_points": question.get("key_learning_points") or [],
        "anki_cards": question.get("anki_cards") or question.get("anki_card_candidates") or [],
        "question_format": question.get("question_format"),
        "sub_format": question.get("sub_format"),
        "labels": question.get("labels") or {},
        "disease_concept_id": ontology_target.get("disease_concept_id"),
        "assessment_domain": ontology_target.get("assessment_domain"),
        "question_blueprint": question_blueprint,
        "target_axis_type": ontology_target.get("target_axis_type"),
        "target_axis_ids": ontology_target.get("target_axis_ids") or [],
        "target_axis_resolution": ontology_target.get("target_axis_resolution"),
        "choice_ontology": choice_ontology,
        "grounding_trace": question.get("grounding_trace") or {},
        "review_status": question.get("review_status"),
        "ontology_analytics_approved": bool(question.get("ontology_analytics_approved")),
        "needs_review": question.get("needs_review", True),
        "review_reasons": question.get("review_reasons") or [],
        "media_refs": media_refs,
        "evidence": question.get("evidence") or [],
        "evidence_status": question.get("evidence_status"),
        "evidence_note": question.get("evidence_note"),
    }


def course_exam_attempt_question(question: dict, media_by_id: dict[str, dict]) -> dict:
    """Build the server-only question snapshot used after an answer is submitted.

    ``course_exam_practice_question`` is also returned by the pre-answer course
    exam endpoint.  Draft ``ontology_grounding`` often contains the diagnosis,
    so copying it into that public payload would leak the target before the
    learner answers.  This resolver runs only on the server-owned raw question
    after submission and restores the deterministic draft concept for audit and
    future review without making it analytics-eligible or student-visible.
    """

    stored = course_exam_practice_question(question, media_by_id)
    grounding = (
        question.get("ontology_grounding")
        if isinstance(question.get("ontology_grounding"), dict)
        else {}
    )
    blueprint = course_exam_question_blueprint(question)
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    grounding_trace = (
        question.get("grounding_trace")
        if isinstance(question.get("grounding_trace"), dict)
        else {}
    )

    mapping_source = None
    if blueprint and stored.get("disease_concept_id"):
        mapping_source = "question_blueprint"
    elif question.get("disease_concept_id"):
        mapping_source = "question_field"
    elif labels.get("disease_concept_id"):
        mapping_source = "question_labels"
    elif grounding_trace.get("disease_concept_id"):
        mapping_source = "grounding_trace"
    elif grounding.get("disease_concept_id"):
        mapping_source = "ontology_grounding"
        stored["disease_concept_id"] = str(grounding["disease_concept_id"]).strip() or None

    if mapping_source == "ontology_grounding":
        mapping_needs_review = bool(grounding.get("needs_review", True))
        mapping_review_status = str(
            grounding.get("review_status") or "draft_unreviewed"
        ).strip()
    elif mapping_source == "question_blueprint":
        mapping_needs_review = bool(blueprint.get("needs_review", True))
        mapping_review_status = str(
            blueprint.get("review_status") or "draft_unreviewed"
        ).strip()
    else:
        # A bare concept field has no independent medical-review contract.
        mapping_needs_review = bool(mapping_source)
        mapping_review_status = "draft_unreviewed" if mapping_source else "unmapped"

    stored["ontology_mapping"] = {
        "source": mapping_source,
        "review_status": mapping_review_status,
        "needs_review": mapping_needs_review,
        "pre_answer_exposed": False,
    }
    return stored


def course_exam_student_question(question: dict, media_by_id: dict[str, dict]) -> dict:
    """Strict pre-answer allowlist for a Trust-Kernel-released item."""

    source = course_exam_practice_question(question, media_by_id)
    safe_media = []
    for row in source.get("media_refs") or []:
        safe_media.append(
            {
                "media_id": row.get("media_id"),
                "url": row.get("url"),
            }
        )
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    return {
        "question_id": source.get("question_id"),
        "question_number": source.get("question_number"),
        "stem": source.get("stem"),
        "stimulus": source.get("stimulus"),
        "lab_values": source.get("lab_values") or [],
        "choices": source.get("choices") or {},
        "question_format": source.get("question_format"),
        "sub_format": source.get("sub_format"),
        "course_name": labels.get("course_name") or labels.get("course_name_labeled"),
        "media_refs": safe_media,
        "item_version": question_content_sha256(source),
    }


def approved_set_attempt_question(set_id: str, question_id: str) -> dict:
    """Return a server-only snapshot for a faculty-approved Studio question."""

    try:
        packet = load_question_set(set_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    metadata = packet.get("metadata") if isinstance(packet.get("metadata"), dict) else {}
    questions = packet.get("questions") if isinstance(packet.get("questions"), list) else []
    for index, raw_question in enumerate(questions, start=1):
        if str(raw_question.get("question_id") or index) != str(question_id):
            continue
        if str(raw_question.get("review_status") or "") != "approved":
            break
        options = raw_question.get("options") if isinstance(raw_question.get("options"), list) else []
        choices = {str(choice_index): str(value) for choice_index, value in enumerate(options, start=1)}
        labels = {
            "course_name": str(raw_question.get("subject") or metadata.get("subject") or "").strip(),
            "unit": str(raw_question.get("unit") or metadata.get("unit") or "").strip(),
            "question_type": str(raw_question.get("question_type") or metadata.get("question_type") or "").strip(),
        }
        return {
            "question_id": str(raw_question.get("question_id") or index),
            "question_number": index,
            "stem": str(raw_question.get("problem") or "").strip(),
            "stimulus": str(raw_question.get("stimulus") or "").strip() or None,
            "lab_values": raw_question.get("lab_values") if isinstance(raw_question.get("lab_values"), list) else [],
            "choices": choices,
            "answer": raw_question.get("answer"),
            "generated_answer": None,
            "explanation": str(raw_question.get("explanation") or "").strip(),
            "choice_explanations": raw_question.get("choice_explanations") or {},
            "question_format": str(raw_question.get("question_type") or metadata.get("question_type") or "single_choice"),
            "sub_format": None,
            "labels": labels,
            "review_status": "approved",
            "needs_review": False,
            "review_reasons": [],
            "media_refs": [
                {
                    "media_id": ref.get("id") or ref.get("asset_id"),
                    "url": ref.get("url"),
                }
                for ref in (raw_question.get("image_refs") or [])
                if isinstance(ref, dict) and ref.get("url")
            ],
            "evidence": raw_question.get("evidence") or raw_question.get("reference_notes") or [],
            "evidence_status": "faculty_approved",
            "ontology_mapping": {
                "source": "faculty_approved_question_set",
                "review_status": "approved",
                "needs_review": False,
                "pre_answer_exposed": False,
            },
            "source_set_id": set_id,
        }
    raise HTTPException(status_code=404, detail="풀이 가능한 승인 문항을 찾을 수 없습니다.")


def approved_set_student_question(set_id: str, question_id: str) -> dict:
    """Strict pre-answer allowlist for a faculty-approved Studio question."""

    source = approved_set_attempt_question(set_id, question_id)
    answer_count = max(1, len(normalize_attempt_choices(source.get("answer"))))
    return {
        "question_id": source["question_id"],
        "question_number": source["question_number"],
        "stem": source["stem"],
        "stimulus": source.get("stimulus"),
        "lab_values": source.get("lab_values") or [],
        "choices": source.get("choices") or {},
        "question_format": source.get("question_format"),
        "course_name": (source.get("labels") or {}).get("course_name"),
        "unit": (source.get("labels") or {}).get("unit"),
        "selection_mode": "multiple" if answer_count > 1 else "single",
        "required_selection_count": answer_count,
        "media_refs": source.get("media_refs") or [],
        "item_version": question_content_sha256(source),
    }


def student_set_release(set_id: str) -> dict | None:
    """Return the active assignment for a set; approval alone is not release."""

    if not STUDENT_RELEASES_PATH.exists():
        return None
    try:
        payload = json.loads(STUDENT_RELEASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    assignments = payload.get("assignments") if isinstance(payload, dict) else []
    if not isinstance(assignments, list):
        return None
    return next(
        (
            assignment
            for assignment in assignments
            if isinstance(assignment, dict)
            and str(assignment.get("set_id") or "") == str(set_id)
            and str(assignment.get("status") or "") == "released"
        ),
        None,
    )


def load_stored_practice_question(exam_id: str, question_id: str) -> dict:
    """Resolve an attempt target from the server-owned extracted exam record."""
    if str(exam_id).startswith("set:"):
        set_id = str(exam_id).split(":", 1)[1]
        if not student_set_release(set_id):
            raise HTTPException(status_code=404, detail="학생에게 공개된 문항 세트가 아닙니다.")
        return approved_set_attempt_question(set_id, question_id)
    try:
        _, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다.") from None

    raw_question = next(
        (
            question
            for question in record.get("questions", [])
            if str(question.get("question_id") or question.get("question_number") or "") == str(question_id)
        ),
        None,
    )
    if raw_question is None or not course_exam_is_practice_ready(raw_question):
        raise HTTPException(status_code=404, detail="풀이 가능한 문항을 찾을 수 없습니다.")
    media_by_id = {
        asset.get("media_id"): asset
        for asset in record.get("media_assets", [])
        if asset.get("media_id")
    }
    return course_exam_attempt_question(raw_question, media_by_id)


def _practice_choice_texts(question: dict) -> dict[str, str]:
    raw_choices = question.get("choices") or {}
    if isinstance(raw_choices, dict):
        return {str(key): str(value) for key, value in raw_choices.items()}
    if isinstance(raw_choices, list):
        return {str(index + 1): str(value) for index, value in enumerate(raw_choices)}
    return {}


def attach_stored_question_snapshot(
    event: dict,
    question: dict,
    *,
    analytics_release: dict | None = None,
    feedback_release: dict | None = None,
) -> dict:
    """Attach trusted question and ontology metadata to an attempt event.

    The client is authoritative only for the student's selected choices and
    timing.  Correctness, target concept/axis, and selected distractor provenance
    are reconstructed from the stored question to prevent metadata spoofing or
    drift when analytics are computed later.
    """
    blueprint = question.get("question_blueprint") if isinstance(question.get("question_blueprint"), dict) else {}
    choice_ontology = question.get("choice_ontology") if isinstance(question.get("choice_ontology"), dict) else {}
    answer_keys = normalize_attempt_choices(
        question.get("generated_answer") or question.get("answer")
    )
    item_version = question_content_sha256(question)
    selected_choices = normalize_attempt_choices(event.get("selected_choices"))
    selected_set = set(selected_choices)
    answer_set = set(answer_keys)

    selected_choice_ontology = []
    for choice in selected_choices:
        metadata = choice_ontology.get(choice) if isinstance(choice_ontology.get(choice), dict) else {}
        selected_choice_ontology.append(
            {
                "choice": choice,
                "is_correct_choice": choice in answer_set,
                "source_id": str(metadata.get("source_id") or "").strip(),
                "misconception_id": str(metadata.get("misconception_id") or "").strip(),
                "misconception": str(metadata.get("misconception") or "").strip(),
                "why_attractive": str(metadata.get("why_attractive") or "").strip(),
                "provenance": str(metadata.get("provenance") or "").strip(),
            }
        )

    _ontology_grounding = question.get("ontology_grounding") if isinstance(question.get("ontology_grounding"), dict) else {}
    disease_concept_id = str(
        question.get("disease_concept_id")
        or blueprint.get("disease_concept_id")
        or _ontology_grounding.get("disease_concept_id")  # 추출문항의 결정론 라벨(attach_hemeonc_ontology)
        or ""
    ).strip()
    target = blueprint.get("target") if isinstance(blueprint.get("target"), dict) else {}
    if not disease_concept_id:
        disease_concept_id = str(target.get("disease_concept_id") or "").strip()
    _stored_labels_ad = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    assessment_domain = str(
        question.get("assessment_domain")
        or blueprint.get("assessment_domain")
        or _stored_labels_ad.get("assessment_domain")  # 팀 라벨링(평가요소)
        or ""
    ).strip()
    target_axis_type = str(
        question.get("target_axis_type")
        or blueprint.get("target_axis_type")
        or target.get("axis_type")
        or ""
    ).strip()
    target_axis_ids = _nonempty_string_list(
        question.get("target_axis_ids")
        or blueprint.get("target_axis_ids")
        or target.get("axis_ids")
    )
    misconception_ids = list(
        dict.fromkeys(
            item["misconception_id"]
            for item in selected_choice_ontology
            if item["misconception_id"] and not item["is_correct_choice"]
        )
    )
    distractor_source_ids = list(
        dict.fromkeys(
            item["source_id"]
            for item in selected_choice_ontology
            if item["source_id"] and not item["is_correct_choice"]
        )
    )

    source_contract = (
        blueprint.get("source_contract")
        if isinstance(blueprint.get("source_contract"), dict)
        else {}
    )
    grounding_trace = (
        question.get("grounding_trace")
        if isinstance(question.get("grounding_trace"), dict)
        else {}
    )
    source_review_policy = str(
        grounding_trace.get("review_policy")
        or source_contract.get("grounding_review_policy")
        or ""
    ).strip()
    blueprint_ready = bool(
        blueprint
        and blueprint.get("status") == "draft_blueprint"
        and not (blueprint.get("block_reasons") or [])
        and disease_concept_id
        and target_axis_type
    )
    question_review_approved = str(question.get("review_status") or "").strip() == "approved"
    exam_id = str(event.get("exam_id") or "").strip()
    analytics_release = analytics_release or evaluate_practice_release(
        exam_id, question, "analytics"
    )
    feedback_release = feedback_release or evaluate_practice_release(
        exam_id, question, "post_answer_feedback"
    )
    ontology_analytics_eligible = bool(
        blueprint_ready
        and question_review_approved
        and analytics_release.get("allowed")
    )
    ontology_student_visible = bool(
        blueprint_ready
        and question_review_approved
        and feedback_release.get("allowed")
    )
    analytics_exclusion_reasons = []
    if not blueprint_ready:
        analytics_exclusion_reasons.append("blueprint_not_ready")
    if not question_review_approved:
        analytics_exclusion_reasons.append("question_not_faculty_approved")
    if not analytics_release.get("allowed"):
        analytics_exclusion_reasons.append("trust_kernel_analytics_not_released")
        analytics_exclusion_reasons.extend(
            f"trust_kernel:{reason}"
            for reason in analytics_release.get("reasons") or []
        )

    stored_labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    ontology_mapping = (
        question.get("ontology_mapping")
        if isinstance(question.get("ontology_mapping"), dict)
        else {}
    )
    event.update(
        {
            "question_number": safe_int(question.get("question_number")),
            "stem_preview": str(question.get("stem") or "").strip()[:240],
            "question_type": str(
                question.get("question_format")
                or stored_labels.get("question_type_labeled")
                or stored_labels.get("question_type")
                or ""
            ),
            "choice_texts": _practice_choice_texts(question),
            "answer_keys": answer_keys,
            "item_version": item_version,
            "is_correct": bool(answer_set) and selected_set == answer_set,
            "labels": stored_labels,
            "disease_concept_id": disease_concept_id or None,
            "assessment_domain": assessment_domain or None,
            "question_blueprint": blueprint,
            "target_axis_type": target_axis_type or None,
            "target_axis_ids": target_axis_ids,
            "selected_choice_ontology": selected_choice_ontology,
            "misconception_ids": misconception_ids,
            "distractor_source_ids": distractor_source_ids,
            "ontology_snapshot_status": "resolved_from_stored_question",
            "ontology_analytics_eligible": ontology_analytics_eligible,
            "ontology_analytics_exclusion_reasons": analytics_exclusion_reasons,
        }
    )
    event["ontology_snapshot"] = {
        "schema_version": "attempt_ontology_snapshot.v1",
        "source": "stored_exam_question",
        "item_version": item_version,
        "blueprint_id": blueprint.get("blueprint_id"),
        "disease_concept_id": disease_concept_id or None,
        "assessment_domain": assessment_domain or None,
        "target_axis_type": target_axis_type or None,
        "target_axis_ids": target_axis_ids,
        "selected_choices": selected_choice_ontology,
        "misconception_ids": misconception_ids,
        "distractor_source_ids": distractor_source_ids,
        "source_review_policy": source_review_policy or None,
        "question_review_status": question.get("review_status"),
        "mapping_source": ontology_mapping.get("source"),
        "mapping_review_status": ontology_mapping.get("review_status"),
        "mapping_needs_review": bool(ontology_mapping.get("needs_review", True)),
        "analytics_release_id": analytics_release.get("release_id"),
        "feedback_release_id": feedback_release.get("release_id"),
        "release_digest": feedback_release.get("release_digest") or analytics_release.get("release_digest"),
        "target_claim_ids": (
            (feedback_release.get("question_release") or {}).get("target_claim_ids")
            or (analytics_release.get("question_release") or {}).get("target_claim_ids")
            or []
        ),
        "student_visible": ontology_student_visible,
        "analytics_eligible": ontology_analytics_eligible,
        "analytics_exclusion_reasons": analytics_exclusion_reasons,
    }
    return event


def public_attempt_event(event: dict) -> dict:
    """Return the minimum learner-facing receipt; omit answers and source text."""
    snapshot = event.get("ontology_snapshot") if isinstance(event.get("ontology_snapshot"), dict) else {}
    ontology_student_visible = bool(snapshot.get("student_visible"))
    ontology_status = (
        "available"
        if ontology_student_visible
        else "withheld_unapproved"
        if snapshot.get("disease_concept_id")
        else "unavailable"
    )
    return {
        "event_id": event.get("event_id"),
        "exam_id": event.get("exam_id"),
        "question_id": event.get("question_id"),
        "question_number": event.get("question_number"),
        "selected_choices": event.get("selected_choices") or [],
        "is_correct": bool(event.get("is_correct")),
        "time_ms": event.get("time_ms"),
        "answered_at": event.get("answered_at"),
        "labels": event.get("labels") or {},
        "course_name": event.get("course_name"),
        "ontology_snapshot_status": event.get("ontology_snapshot_status"),
        "ontology": {
            "status": ontology_status,
            "blueprint_id": snapshot.get("blueprint_id") if ontology_student_visible else None,
            "disease_concept_id": snapshot.get("disease_concept_id") if ontology_student_visible else None,
            "target_axis_type": snapshot.get("target_axis_type") if ontology_student_visible else None,
            "target_axis_ids": (snapshot.get("target_axis_ids") or []) if ontology_student_visible else [],
            "student_visible": ontology_student_visible,
            "analytics_eligible": bool(snapshot.get("analytics_eligible")),
        },
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "paccine-studio"}


@app.get("/api/models")
def models() -> dict:
    return get_model_catalog()


@app.get("/api/ontology/context")
def ontology_context(
    topic: str = "",
    disease_concept_id: str = "",
    review_policy: str = "faculty_draft",
) -> dict:
    try:
        grounding = build_generation_grounding(
            topic,
            disease_concept_id=disease_concept_id,
            review_policy=review_policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pack = grounding.get("pack") if isinstance(grounding.get("pack"), dict) else {}
    return {
        "status": "blocked" if grounding.get("blocked") else "matched" if pack else "unmatched",
        "topic": grounding.get("topic"),
        "review_policy": grounding.get("review_policy"),
        "policy_requirements": grounding.get("policy_requirements") or {},
        "review_decisions": grounding.get("review_decisions") or {},
        "concept_review": grounding.get("concept_review") or {},
        "blocked": bool(grounding.get("blocked")),
        "block_reasons": grounding.get("block_reasons") or [],
        "excluded_counts": grounding.get("excluded_counts") or {},
        "match": grounding.get("match"),
        "missing": grounding.get("missing") or [],
        "ontology_used": bool(pack),
        "disease_concept_id": pack.get("disease_concept_id"),
        "label": pack.get("label"),
        "evidence": pack.get("evidence") or {},
        "inherited_edges": pack.get("inherited_edges") or {},
        "distractor_pool": pack.get("distractor_pool") or [],
        "axis_context": pack.get("axis_context") or {},
        "needs_review": True,
    }


def _normalized_ontology_search_text(value: object) -> str:
    """Normalize Korean/English labels without exposing private source text."""

    return "".join(char.lower() for char in str(value or "") if char.isalnum())


def _faculty_ontology_search_records() -> list[dict]:
    registry_payload = load_json_snapshot(ONTOLOGY_CONCEPT_REGISTRY_PATH)
    registry = registry_payload.get("concepts") if isinstance(registry_payload.get("concepts"), dict) else {}
    index_payload = load_json_snapshot(ONTOLOGY_REGISTRY_INDEX_PATH)
    index_rows = index_payload.get("concepts") if isinstance(index_payload.get("concepts"), list) else []
    query_map = load_json_snapshot(ONTOLOGY_QUERY_MAP_PATH)
    question_links = load_json_snapshot(STUDENT_QUESTION_LINKS_PATH)

    index_by_id = {
        str(item.get("id")): item
        for item in index_rows
        if isinstance(item, dict) and item.get("id")
    }
    labels_by_id: dict[str, Counter] = defaultdict(Counter)
    questions = question_links.get("questions") if isinstance(question_links.get("questions"), dict) else {}
    for item in questions.values():
        if not isinstance(item, dict):
            continue
        concept_id = str(item.get("concept") or "").strip()
        label = str(item.get("label") or "").strip()
        if concept_id and label:
            labels_by_id[concept_id][label] += 1
    concept_index = question_links.get("concept_index") if isinstance(question_links.get("concept_index"), dict) else {}

    concept_ids = set(registry) | set(index_by_id) | set(query_map)
    rows: list[dict] = []
    for concept_id in concept_ids:
        concept = registry.get(concept_id) if isinstance(registry.get(concept_id), dict) else {}
        index_item = index_by_id.get(concept_id) or {}
        label_counts = labels_by_id.get(concept_id) or Counter()
        korean_label = label_counts.most_common(1)[0][0] if label_counts else ""
        title = str(index_item.get("title") or query_map.get(concept_id) or concept_id.replace("_", " ")).strip()
        aliases = [
            str(alias).strip()
            for alias in (concept.get("aliases") or [])
            if str(alias).strip()
        ]
        if korean_label and korean_label not in aliases:
            aliases.insert(0, korean_label)
        edges = concept.get("edges") if isinstance(concept.get("edges"), dict) else {}
        relation_count = sum(len(values) for values in edges.values() if isinstance(values, list))
        clinical_axes = concept.get("clinical_axes") if isinstance(concept.get("clinical_axes"), dict) else {}
        axis_count = sum(
            1
            for key, value in clinical_axes.items()
            if key not in {"source", "evidence_refs", "needs_review"} and value
        )
        rows.append(
            {
                "disease_concept_id": concept_id,
                "label": korean_label or title,
                "title": title,
                "aliases": aliases[:8],
                "node_type": concept.get("node_type") or index_item.get("node_type") or "concept",
                "relation_count": relation_count,
                "axis_count": axis_count,
                "question_count": len(concept_index.get(concept_id) or []),
                "has_harrison": bool(((concept.get("evidence") or {}).get("harrison"))),
                "needs_review": True,
                "gen_ready": bool(concept.get("gen_ready", False)),
            }
        )
    return rows


@app.get("/api/ontology/search")
def ontology_search(q: str = "", limit: int = 8) -> dict:
    """Search faculty-facing concept labels/IDs while keeping all claims review-gated."""

    query = str(q or "").strip()
    normalized_query = _normalized_ontology_search_text(query)
    if not normalized_query:
        return {"query": query, "results": [], "total": 0, "needs_review": True}
    safe_limit = max(1, min(20, int(limit or 8)))
    ranked: list[tuple[int, int, str, dict]] = []
    for item in _faculty_ontology_search_records():
        fields = [
            item.get("disease_concept_id"),
            item.get("label"),
            item.get("title"),
            *(item.get("aliases") or []),
        ]
        normalized_fields = [_normalized_ontology_search_text(field) for field in fields if field]
        if normalized_query in normalized_fields:
            rank = 0
        elif any(field.startswith(normalized_query) for field in normalized_fields):
            rank = 1
        elif any(normalized_query in field for field in normalized_fields):
            rank = 2
        else:
            continue
        ranked.append((rank, -int(item.get("question_count") or 0), str(item.get("label") or ""), item))
    ranked.sort(key=lambda row: row[:3])
    results = [row[3] for row in ranked[:safe_limit]]
    return {
        "query": query,
        "results": results,
        "total": len(ranked),
        "needs_review": True,
        "message": "검색 결과는 교수 검토용이며 의학 승인 상태가 아닙니다.",
    }


@app.get("/api/faculty/item-intents/departments")
def faculty_item_intent_departments() -> dict:
    """Return department choices and current Ontology recommendation availability."""

    payload = load_json_snapshot(ONTOLOGY_CONCEPT_REGISTRY_PATH)
    concepts = payload.get("concepts") if isinstance(payload.get("concepts"), dict) else {}
    return build_department_catalog(concepts)


@app.post("/api/faculty/item-intents/recommendations")
def faculty_item_intent_recommendations(payload: Annotated[dict, Body()]) -> dict:
    """Recommend review-gated item intents after a professor chooses a department."""

    registry_payload = load_json_snapshot(ONTOLOGY_CONCEPT_REGISTRY_PATH)
    concepts = (
        registry_payload.get("concepts")
        if isinstance(registry_payload.get("concepts"), dict)
        else {}
    )
    search_records = {
        str(item.get("disease_concept_id")): item
        for item in _faculty_ontology_search_records()
        if isinstance(item, dict) and item.get("disease_concept_id")
    }
    question_links = load_json_snapshot(STUDENT_QUESTION_LINKS_PATH)
    concept_index = (
        question_links.get("concept_index")
        if isinstance(question_links.get("concept_index"), dict)
        else {}
    )
    question_counts = {
        str(concept_id): len(question_ids or [])
        for concept_id, question_ids in concept_index.items()
        if isinstance(question_ids, list)
    }
    try:
        requested_item_count = int(payload.get("requested_item_count") or 3)
        candidate_count = int(payload.get("candidate_count") or max(6, requested_item_count * 2))
        return recommend_item_intents(
            concepts,
            search_records,
            department=str(payload.get("department") or payload.get("department_id") or "").strip(),
            requested_item_count=requested_item_count,
            candidate_count=candidate_count,
            priority_tasks=normalized_metadata_values(payload.get("priority_tasks")),
            exclude_concept_ids=normalized_metadata_values(payload.get("exclude_concept_ids")),
            question_counts=question_counts,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ontology/review-status")
def ontology_review_status() -> dict:
    """Return aggregate review readiness without exposing private source text."""

    def read_object(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    readiness = read_object(ONTOLOGY_READINESS_PATH)
    hardening = read_object(ONTOLOGY_HARDENING_PATH)
    review_worklist = read_object(ONTOLOGY_REVIEW_WORKLIST_PATH)
    finding_endpoint_worklist = read_object(ONTOLOGY_FINDING_ENDPOINT_WORKLIST_PATH)
    decisions = read_object(ONTOLOGY_REVIEW_DECISIONS_PATH)
    decision_counts = {
        key: len(decisions.get(key) or [])
        for key in ("concepts", "axis_nodes", "axis_relationships")
    }
    return {
        "status": readiness.get("status") or "review_status_unavailable",
        "medical_approval": bool(readiness.get("medical_approval")),
        "counts": readiness.get("counts") or {},
        "generation_gates": readiness.get("generation_gates") or {},
        "hardening": hardening.get("summary") or {},
        "review_worklist": review_worklist.get("summary") or {},
        "finding_endpoint_worklist": finding_endpoint_worklist.get("summary") or {},
        "review_decisions": {
            "schema_version": decisions.get("schema_version"),
            "counts": decision_counts,
            "total": sum(decision_counts.values()),
        },
        "student_approved_policy": {
            "mode": "fail_closed",
            "available": bool((readiness.get("generation_gates") or {}).get("medical_review_policy_enforced")),
            "approved_claim_subset_available": bool(
                (readiness.get("generation_gates") or {}).get("approved_claim_subset_available")
            ),
        },
    }


@app.get("/api/ontology/external-validation")
def ontology_external_validation(
    profile: str = "core20",
    priority: str = "",
    classification: str = "",
    evaluation_status: str = "",
    polarity: str = "",
    q: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Read-only faculty queue for external KG candidates.

    This endpoint is deliberately disconnected from generation grounding,
    student feedback, analytics, and canonical ontology promotion.
    """
    try:
        return list_external_kg_review(
            profile=profile,
            priority=priority,
            classification=classification,
            evaluation_status=evaluation_status,
            polarity=polarity,
            query=q,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ontology/question-blueprint")
def ontology_question_blueprint(payload: Annotated[dict, Body()]) -> dict:
    """Preview the assessment target without calling a generation model."""
    try:
        grounding = build_generation_grounding(
            str(payload.get("topic") or "").strip(),
            disease_concept_id=str(payload.get("disease_concept_id") or "").strip(),
            review_policy=str(payload.get("review_policy") or "faculty_draft").strip(),
        )
        blueprint = build_question_blueprint(
            grounding,
            question_type=str(payload.get("question_type") or "").strip(),
            target_axis_type=str(payload.get("target_axis_type") or "").strip(),
            target_axis_ids=normalized_metadata_values(payload.get("target_axis_ids")),
            supporting_axis_types=(
                normalized_metadata_values(payload.get("supporting_axis_types")) or None
            ),
            option_domain=str(payload.get("option_domain") or "").strip(),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": blueprint.get("status"),
        "question_blueprint": blueprint,
        "grounding": {
            "review_policy": grounding.get("review_policy"),
            "blocked": bool(grounding.get("blocked")),
            "block_reasons": grounding.get("block_reasons") or [],
            "match": grounding.get("match") or {},
            "disease_concept_id": ((grounding.get("pack") or {}).get("disease_concept_id")),
        },
    }


@app.get("/api/rag/status")
def rag_status(course_id: str = DEFAULT_RAG_COURSE_ID) -> dict:
    return get_rag_index_status(course_id)


@app.get("/api/student/guidelines/status")
def student_guideline_status() -> dict:
    """Read-only readiness and safety boundary for the student guideline library."""

    try:
        return get_guideline_library_status()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/student/guidelines")
def student_guidelines(
    q: str = "",
    specialty: str = "",
    axis: str = "",
    currentness: str = "verified_current",
    concept_id: str = "",
    offset: int = 0,
    limit: int = 20,
) -> dict:
    """Browse source metadata; this endpoint never releases guideline claims."""

    normalized_currentness = str(currentness or "verified_current").strip()
    current_only = normalized_currentness in {"current", "verified_current", "verified_latest"}
    latest_status = ""
    if normalized_currentness not in {"", "all", "current", "verified_current", "verified_latest"}:
        latest_status = normalized_currentness
    try:
        library = search_guideline_library(
            q,
            specialty=specialty,
            clinical_axes=axis,
            latest_status=latest_status,
            concept_id=concept_id,
            current_only=current_only,
            offset=offset,
            limit=limit,
        )
        status = get_guideline_library_status()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    known_statuses = set((status.get("facets") or {}).get("latest_statuses") or [])
    if latest_status and latest_status not in known_statuses:
        raise HTTPException(status_code=400, detail="지원하지 않는 currentness 값입니다.")
    student_results = [
        sanitize_student_guideline_source(source) for source in library.get("results") or []
    ]
    return {
        "status": "ready",
        "summary": {
            "total_matches": library.get("total", 0),
            "returned": len(student_results),
            "verified_current_sources": (status.get("counts") or {}).get(
                "verified_current_sources", 0
            ),
            "approved_claims_connected": 0,
            "answer_status": "catalog_preview_only",
            "message": (
                "출처·버전·최신성 확인용 문서 목록입니다. 개별 진단·치료 claim은 아직 학생 배포 승인을 받지 않았습니다."
            ),
        },
        "counts": status.get("counts") or {},
        "facets": status.get("facets") or {},
        "filters": library.get("filters") or {},
        "offset": library.get("offset", 0),
        "limit": library.get("limit", 20),
        "total": library.get("total", 0),
        "pagination": {
            "offset": library.get("offset", 0),
            "limit": library.get("limit", 20),
            "total": library.get("total", 0),
            "has_more": (
                int(library.get("offset", 0)) + len(student_results) < int(library.get("total", 0))
            ),
        },
        "ontology_routing": library.get("ontology_routing") or {},
        "results": student_results,
        "needs_review": True,
    }


@app.post("/api/student/clinical-assistant")
def student_clinical_assistant(payload: Annotated[dict, Body()]) -> dict:
    """Build a stateless evidence packet and study/case-presentation template.

    No model is called and case text is not persisted. Patient-specific diagnosis
    and treatment are withheld while approved student-visible claims are absent.
    """

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 객체가 필요합니다.")
    query = str(payload.get("query") or payload.get("q") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query가 필요합니다.")
    mode = str(payload.get("mode") or "study_qa").strip()
    case_text = str(payload.get("case_text") or "")
    try:
        assistant = build_guideline_study_assistant(
            query,
            mode=mode,
            concept_id=str(payload.get("concept_id") or "").strip(),
            specialty=str(payload.get("specialty") or "").strip(),
            clinical_axes=(payload.get("clinical_axes") or payload.get("axis")),
            case_text=case_text,
            include_uncertain=form_bool(payload.get("include_uncertain", False)),
            # Student release is metadata-only until reviewed, student-visible claims exist.
            # Raw local excerpts remain available only to internal review services.
            include_passages=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    packet = assistant.get("evidence_packet") or {}
    student_sources = [
        sanitize_student_guideline_source(source) for source in packet.get("sources") or []
    ]
    if packet:
        packet = {**packet, "sources": student_sources, "passages": []}
    blocked = assistant.get("answer_status") in {
        "blocked_direct_identifiers",
        "retrieval_only_approved_claims_unavailable",
    }
    reasons = []
    if assistant.get("answer_status") == "blocked_direct_identifiers":
        reasons.append("direct_identifiers_detected")
    else:
        reasons.append("approved_student_visible_claims_unavailable")
    return {
        "status": assistant.get("status"),
        "mode": assistant.get("mode"),
        "answer_status": assistant.get("answer_status"),
        "grounding_state": assistant.get("grounding_state"),
        "message": assistant.get("message"),
        "detected_intents": assistant.get("detected_intents") or [],
        "detected_concepts": assistant.get("detected_concepts") or [],
        "ontology_matches": assistant.get("detected_concepts") or [],
        "guidelines": student_sources,
        "evidence": [],
        "evidence_packet": packet or None,
        "workspace_template": assistant.get("workspace_template"),
        "case_presentation": assistant.get("workspace_template"),
        "privacy_status": assistant.get("privacy_status") or {},
        "blocked": blocked,
        "blocked_scope": "patient_specific_diagnosis_and_treatment",
        "reasons": reasons,
        "needs_review": True,
        "safety": assistant.get("safety") or {},
    }


@app.get("/api/student/medical-copilot/status")
def student_medical_copilot_status() -> dict:
    """Return local Harrison/Ontology chatbot readiness without exposing private text."""

    try:
        return get_medical_copilot_status()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/student/medical-copilot")
def student_medical_copilot(payload: Annotated[dict, Body()]) -> dict:
    """Build a stateless, citation-checked medical-learning chat response.

    Harrison text remains server-side. Guideline metadata may route the question,
    but unreleased guideline claims cannot become diagnosis or treatment advice.
    """

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 객체가 필요합니다.")
    query = str(payload.get("query") or payload.get("q") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query가 필요합니다.")
    history = payload.get("history")
    if history is not None and not isinstance(history, list):
        raise HTTPException(status_code=400, detail="history는 배열이어야 합니다.")
    try:
        return build_medical_copilot_response(
            query,
            mode=str(payload.get("mode") or "concept").strip(),
            concept_id=str(payload.get("concept_id") or "").strip(),
            specialty=str(payload.get("specialty") or "").strip(),
            case_text=str(payload.get("case_text") or ""),
            history=history,
            generate_answer=form_bool(payload.get("generate_answer", True)),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/student/medical-copilot/jobs")
def create_student_medical_copilot_job(
    request: Request,
    payload: Annotated[dict, Body()],
) -> dict:
    """Start a reload-recoverable, memory-only medical-learning response job."""

    normalized = dict(payload) if isinstance(payload, dict) else payload
    if isinstance(normalized, dict):
        normalized["generate_answer"] = form_bool(normalized.get("generate_answer", True))
    try:
        return {"job": create_medical_copilot_job(normalized, owner_id=_student_identity(request))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/student/medical-copilot/jobs/{job_id}")
def read_student_medical_copilot_job(job_id: str, request: Request) -> dict:
    try:
        return get_medical_copilot_job(job_id, owner_id=_student_identity(request))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="답변 작업을 찾을 수 없습니다.") from None


@app.post("/api/student/medical-copilot/jobs/{job_id}/cancel")
def cancel_student_medical_copilot_job(job_id: str, request: Request) -> dict:
    try:
        return cancel_medical_copilot_job(job_id, owner_id=_student_identity(request))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="답변 작업을 찾을 수 없습니다.") from None


@app.post("/api/student/medical-copilot/jobs/{job_id}/retry")
def retry_student_medical_copilot_job(job_id: str, request: Request) -> dict:
    try:
        return retry_medical_copilot_job(job_id, owner_id=_student_identity(request))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="답변 작업을 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/faculty/guideline-map/status")
def faculty_guideline_map_status() -> dict:
    """Return the integrity-checked KR/US source-map status without medical claims."""

    try:
        return get_guideline_agent_map_status()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/faculty/guideline-map/route")
def faculty_guideline_map_route(
    query: str = "",
    concept_id: str = "",
    clinical_axis: str = "",
    mode: str = "korean_clinical_learning",
    include_candidate_claims: bool = False,
    limit: int = 12,
) -> dict:
    """Preview where an agent should look; never produce a clinical answer."""

    try:
        return route_guideline_sources(
            query,
            concept_id=concept_id,
            clinical_axis=clinical_axis,
            mode=mode,
            include_candidate_claims=include_candidate_claims,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/faculty/guideline-claims/tasks")
def faculty_guideline_claim_tasks(
    query: str = "",
    priority: str = "",
    readiness: str = "",
    clinical_axis: str = "",
    offset: int = 0,
    limit: int = 30,
) -> dict:
    """List local source-review tasks without creating or approving medical claims."""

    try:
        return list_claim_review_tasks(
            query=query,
            priority=priority,
            readiness=readiness,
            clinical_axis=clinical_axis,
            offset=offset,
            limit=limit,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/faculty/guideline-claims/drafts")
def faculty_guideline_claim_drafts(task_id: str = "") -> dict:
    try:
        items = list_claim_drafts(task_id=task_id)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "schema_version": "paccine.faculty_guideline_claim_drafts.v1",
        "task_id": task_id or None,
        "total": len(items),
        "items": items,
        "automatic_medical_approvals": 0,
    }


@app.get("/api/faculty/guideline-claims/tasks/{task_id}/source/{attachment_id}")
def faculty_guideline_claim_source_document(task_id: str, attachment_id: str) -> FileResponse:
    """Open a locally stored guideline source for human review."""

    try:
        path = get_claim_source_document(task_id, attachment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline")


@app.post("/api/faculty/guideline-claims/drafts")
def faculty_create_guideline_claim_draft(payload: Annotated[dict, Body()]) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 객체가 필요합니다.")
    try:
        draft = create_claim_draft(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "draft_saved",
        "claim": draft,
        "medical_approval": False,
        "student_visible": False,
    }


@app.post("/api/faculty/guideline-claims/{claim_id}/decision")
def faculty_decide_guideline_claim(claim_id: str, payload: Annotated[dict, Body()]) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 객체가 필요합니다.")
    try:
        return {"status": "decision_saved", **decide_claim(claim_id, payload)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        status_code = 404 if "찾을 수 없습니다" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/rag/search")
def rag_search(q: str, course_id: str = DEFAULT_RAG_COURSE_ID, limit: int = 8) -> dict:
    try:
        return search_rag_evidence(q, course_id=course_id, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/rag/anki-draft")
def rag_anki_draft(payload: Annotated[dict, Body()]) -> dict:
    query = str(payload.get("query") or payload.get("q") or "").strip()
    course_id = str(payload.get("course_id") or DEFAULT_RAG_COURSE_ID).strip()
    limit = int(payload.get("limit") or 5)
    try:
        return draft_anki_cards_from_evidence(query, course_id=course_id, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/questions/choice-explanations/draft")
def choice_explanation_draft(payload: Annotated[dict, Body()]) -> dict:
    question = payload.get("question") if isinstance(payload.get("question"), dict) else payload
    if not isinstance(question, dict):
        raise HTTPException(status_code=400, detail="question 객체가 필요합니다.")
    course_id = payload.get("course_id") if isinstance(payload, dict) else None
    use_rag = form_bool(payload.get("use_rag", True)) if isinstance(payload, dict) else True
    return build_choice_explanation_draft(question, course_id=course_id, use_rag=use_rag)


@app.get("/api/studio/images/{filename}")
def studio_image(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    image_path = (IMAGE_DIR / safe_name).resolve()
    image_root = IMAGE_DIR.resolve()
    if image_root not in image_path.parents or not image_path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(image_path)


@app.get("/api/media")
def media_assets() -> dict:
    return {"assets": list_media_assets()}


@app.get("/api/media/assets/{filename}")
def media_asset_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    asset_path = (MEDIA_ASSET_DIR / safe_name).resolve()
    asset_root = MEDIA_ASSET_DIR.resolve()
    if asset_root not in asset_path.parents or not asset_path.exists():
        raise HTTPException(status_code=404, detail="미디어 파일을 찾을 수 없습니다.")
    return FileResponse(asset_path)


@app.delete("/api/media/{asset_id}")
def remove_media_asset(asset_id: str) -> dict:
    try:
        return {"deleted": delete_media_asset(asset_id)}
    except MediaAssetInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"이 제시자료는 문항 세트 {len(exc.references)}곳에 연결되어 있어 삭제할 수 없습니다. "
                "먼저 문항에서 연결을 해제하세요."
            ),
        ) from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="제시자료를 찾을 수 없습니다.") from None


@app.get("/api/course-exams")
def course_exam_list(limit: int = 50) -> dict:
    ensure_course_exam_dirs()
    exams = []
    for record_path in sorted(
        COURSE_EXAM_EXTRACTED_DIR.glob("*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:limit]:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = course_exam_summary(record)
        questions = record.get("questions", [])
        review_set_id = f"course_exam_{course_exam_slugify(summary.get('source_exam') or record_path.stem)}"
        try:
            load_question_set(review_set_id)
            review_set_exists = True
        except (FileNotFoundError, ValueError):
            review_set_exists = False
        summary.update(
            {
                "exam_id": record_path.stem,
                "updated_at": datetime.fromtimestamp(record_path.stat().st_mtime).isoformat(timespec="seconds"),
                "preview_url": (
                    f"/api/course-exams/previews/{quote(record_path.stem, safe='')}.html"
                    if (COURSE_EXAM_PREVIEW_DIR / f"{record_path.stem}.html").exists()
                    else None
                ),
                "review_set_id": review_set_id,
                "review_set_exists": review_set_exists,
                "answer_key_source": (record.get("answer_key") or {}).get("source_file"),
                "practice_ready_count": sum(
                    1
                    for question in questions
                    if course_exam_is_practice_ready(question)
                ),
            }
        )
        exams.append(summary)
    return {"exams": exams}


@app.get("/api/course-exams/extracted/{exam_id}")
def course_exam_detail(exam_id: str, limit: int | None = None) -> dict:
    try:
        record_path, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="구조화된 시험지를 찾을 수 없습니다.") from None

    media_by_id = {
        asset.get("media_id"): asset
        for asset in record.get("media_assets", [])
        if asset.get("media_id")
    }
    questions = [
        course_exam_practice_question(question, media_by_id)
        for question in record.get("questions", [])
        if course_exam_is_practice_ready(question)
    ]
    if limit and limit > 0:
        questions = questions[:limit]
    return {
        "exam_id": record_path.stem,
        "exam": record.get("exam", {}),
        "summary": course_exam_summary(record),
        "questions": questions,
        "question_index": record.get("question_index") or [],
        "subjective_questions": record.get("subjective_questions") or [],
        "final_review_summary": record.get("final_review_summary") or {},
    }


@app.post("/api/course-exams/{exam_id}/review-set")
def ensure_course_exam_review_set(exam_id: str) -> dict:
    try:
        _, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="구조화된 시험지를 찾을 수 없습니다.") from None

    source_exam = str((record.get("exam") or {}).get("source_exam") or exam_id)
    set_id = f"course_exam_{course_exam_slugify(source_exam)}"
    try:
        review_set = load_question_set(set_id)
        created = False
    except FileNotFoundError:
        review_set = archive_course_exam_review_set(record)
        created = True
    return {
        "set_id": review_set.get("set_id") or set_id,
        "summary": review_set.get("summary") or {},
        "created": created,
    }


@app.get("/api/practice/exams/{exam_id}/questions")
def student_practice_question_list(exam_id: str, limit: int | None = None) -> dict:
    """Return only externally released items and a pre-answer-safe field allowlist."""

    try:
        record_path, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="구조화된 시험지를 찾을 수 없습니다.") from None
    media_by_id = {
        asset.get("media_id"): asset
        for asset in record.get("media_assets", [])
        if asset.get("media_id")
    }
    questions = []
    excluded = Counter()
    for raw_question in record.get("questions", []):
        if not course_exam_is_practice_ready(raw_question):
            excluded["not_practice_ready"] += 1
            continue
        stored_question = course_exam_attempt_question(raw_question, media_by_id)
        gate = evaluate_practice_release(
            record_path.stem,
            stored_question,
            "practice_pre_answer",
        )
        if not gate.get("allowed"):
            reason = (gate.get("reasons") or ["trust_kernel_release_missing"])[0]
            excluded[str(reason)] += 1
            continue
        questions.append(course_exam_student_question(raw_question, media_by_id))
        if limit and limit > 0 and len(questions) >= limit:
            break
    return {
        "exam_id": record_path.stem,
        "questions": questions,
        "released_count": len(questions),
        "excluded_counts": dict(sorted(excluded.items())),
        "release_policy": "ontology_trust_kernel_releases.v1",
    }


@lru_cache(maxsize=1)
def load_student_qbank() -> dict:
    """Load the canonical student question bank supplied with the UI handoff."""

    if not STUDENT_QBANK_PATH.exists():
        raise FileNotFoundError(STUDENT_QBANK_PATH)
    payload = json.loads(STUDENT_QBANK_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise ValueError("학생 문항 데이터 형식이 올바르지 않습니다.")
    return payload


def canonical_student_course(question: dict) -> str:
    exam = str(question.get("exam") or "")
    for course in ("신경 및 특수감각기학", "혈액종양내과", "임상종합평가"):
        if exam.startswith(f"{course} ·"):
            return course
    return ""


def canonical_student_course_id(question: dict) -> str | None:
    """Return the curriculum course id without treating an assessment as a course."""

    course_name = canonical_student_course(question)
    for course in STUDENT_COURSE_CATALOG:
        if course.get("qbank_course") == course_name:
            return str(course["id"])
    return None


def _student_identity(request: Request) -> str:
    return _request_identity(request) or "local_student"


def _latest_course_preferences(user_id: str) -> list[str]:
    favorites = list(DEFAULT_STUDENT_FAVORITE_COURSE_IDS)
    valid_ids = {str(course["id"]) for course in STUDENT_COURSE_CATALOG}
    for event in _iter_private_jsonl(STUDENT_COURSE_PREFERENCES_LOG_PATH):
        if event.get("user_id") != user_id or event.get("event_type") != "course_favorite_changed":
            continue
        course_id = str(event.get("course_id") or "")
        if course_id not in valid_ids:
            continue
        if event.get("on") and course_id not in favorites:
            favorites.append(course_id)
        if not event.get("on") and course_id in favorites:
            favorites.remove(course_id)
    return favorites


def _latest_qbank_bookmarks(user_id: str) -> dict[str, bool]:
    state: dict[str, bool] = {}
    for event in _iter_private_jsonl(PRACTICE_BOOKMARKS_LOG_PATH):
        if event.get("user_id") != user_id or event.get("event_type") != "qbank_bookmark_changed":
            continue
        question_id = str(event.get("question_id") or "")
        if question_id:
            state[question_id] = bool(event.get("on"))
    return state


def _load_student_question_links() -> dict[str, dict]:
    try:
        payload = json.loads(STUDENT_QUESTION_LINKS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    questions = payload.get("questions") if isinstance(payload, dict) else {}
    return questions if isinstance(questions, dict) else {}


def _load_student_concept_notes() -> list[dict]:
    try:
        payload = json.loads(STUDENT_CONCEPT_NOTES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    notes = payload.get("notes") if isinstance(payload, dict) else []
    return [note for note in notes if isinstance(note, dict)] if isinstance(notes, list) else []


def _student_learning_context(question_id: str) -> dict:
    """Expose only faculty-approved concept content; draft ontology remains fail-closed."""

    link = _load_student_question_links().get(question_id)
    if not isinstance(link, dict):
        return {
            "ontology": {"status": "fallback", "message": "승인된 개념 연결이 아직 없습니다."},
            "concept_note": {"status": "unavailable", "message": "연결된 개념 노트가 없습니다."},
        }
    concept_id = str(link.get("concept") or "")
    note = next(
        (item for item in _load_student_concept_notes() if str(item.get("disease_concept_id") or "") == concept_id),
        None,
    )
    if note and not note.get("needs_review") and note.get("gen_ready"):
        return {
            "ontology": {"status": "ready", "label": link.get("label"), "assessment_domain": link.get("assessment_domain")},
            "concept_note": {
                "status": "ready",
                "title": note.get("title"),
                "sections": note.get("sections") or {},
            },
        }
    return {
        "ontology": {"status": "reviewing", "message": "Ontology 연결을 교수 검수 중입니다."},
        "concept_note": {"status": "reviewing", "message": "개념 노트를 교수 검수 중입니다."},
    }


def _latest_fsrs_cards(user_id: str) -> dict[str, dict]:
    cards: dict[str, dict] = {}
    for event in _iter_private_jsonl(STUDENT_FSRS_LOG_PATH):
        if event.get("user_id") != user_id or event.get("event_type") != "fsrs_reviewed":
            continue
        question_id = str(event.get("question_id") or "")
        if question_id and isinstance(event.get("card"), dict):
            cards[question_id] = event
    return cards


def _latest_claim_fsrs_cards(user_id: str) -> dict[str, dict]:
    cards: dict[str, dict] = {}
    for event in _iter_private_jsonl(STUDENT_CLAIM_FSRS_LOG_PATH):
        if event.get("user_id") != user_id or event.get("event_type") != "guideline_claim_fsrs_reviewed":
            continue
        claim_id = str(event.get("claim_id") or "")
        if claim_id and isinstance(event.get("card"), dict):
            cards[claim_id] = event
    return cards


def _claim_fsrs_card_summary(claim: dict, event: dict | None, now: datetime) -> dict:
    due_at = None
    status = "new"
    if event:
        due_at = str((event.get("card") or {}).get("due") or "") or None
        if due_at:
            try:
                due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                delta = (due_dt - now).total_seconds()
                status = "overdue" if delta < -86400 else "due" if delta <= 0 else "scheduled"
            except ValueError:
                status = "scheduled"
    return {
        "claim_id": claim.get("claim_id"),
        "concept_id": claim.get("subject_concept_id"),
        "clinical_axis": claim.get("clinical_axis"),
        "source_title": claim.get("source_title"),
        "population": claim.get("population"),
        "prompt": f"{claim.get('subject_concept_id') or '핵심 개념'} · {claim.get('clinical_axis') or '권고'}",
        "answer": claim.get("object_text"),
        "status": status,
        "due_at": due_at,
        "last_rating": event.get("rating") if event else None,
        "review_due_at": (claim.get("release") or {}).get("review_due_at"),
    }


def _fsrs_card_summary(question: dict, event: dict | None, now: datetime) -> dict:
    due_at = None
    status = "new"
    if event:
        due_at = str((event.get("card") or {}).get("due") or "") or None
        if due_at:
            try:
                due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                delta = (due_dt - now).total_seconds()
                status = "overdue" if delta < -86400 else "due" if delta <= 0 else "scheduled"
            except ValueError:
                status = "scheduled"
    return {
        "question_id": question.get("id"),
        "course_id": canonical_student_course_id(question),
        "course": canonical_student_course(question),
        "exam": question.get("exam"),
        "topic": question.get("topic") or question.get("major") or question.get("subject"),
        "stem_preview": str(question.get("stem") or "")[:160],
        "status": status,
        "due_at": due_at,
        "last_rating": event.get("rating") if event else None,
    }


_QBank_VISUAL_REFERENCE_RE = re.compile(
    r"(?:아래|다음|위의).{0,30}(?:그림|사진|영상)|"
    r"(?:그림|사진|영상).{0,20}(?:관찰|소견|제시|같)",
    re.IGNORECASE,
)

STUDENT_QBANK_MEDIA_ALIASES = {
    "media/neuro_": "COURSE_2_20251103_NEURO_SPECIAL_SENSES_2차",
}


def resolve_student_qbank_image(image: object) -> tuple[str, bool]:
    """Resolve legacy qbank image aliases to the protected media endpoint.

    The rebuilt student UI is served from a different directory than the old
    Reader, so legacy ``media/neuro_*`` relative URLs otherwise resolve to a
    non-existent frontend folder after deployment.
    """

    raw = str(image or "").strip()
    if not raw:
        return "", False
    if raw.startswith(("/", "https://", "http://", "data:")):
        return raw, True
    normalized = raw.replace("\\", "/")
    for prefix, source_exam in STUDENT_QBANK_MEDIA_ALIASES.items():
        if not normalized.startswith(prefix):
            continue
        filename = Path(normalized.removeprefix(prefix)).name
        media_path = COURSE_EXAM_MEDIA_DIR / source_exam / filename
        if not filename or not media_path.is_file():
            return raw, False
        return (
            f"/api/course-exams/media/{quote(source_exam, safe='')}/{quote(filename, safe='')}",
            True,
        )
    return raw, True


def _visible_qbank_enrichment_releases() -> dict[str, dict]:
    try:
        from src.services import qbank_enrichment

        return qbank_enrichment.load_releases()
    except Exception:
        return {}


def qbank_question_practice_readiness(
    question: dict,
    enrichment_release: dict | None = None,
) -> dict[str, object]:
    """Fail closed when a question requires a visual that is not connected."""

    images = [item for item in (question.get("imgs") or []) if item]
    resolved_images = [resolve_student_qbank_image(item) for item in images]
    connected_images = [url for url, connected in resolved_images if url and connected]
    if isinstance(enrichment_release, dict):
        connected_images.extend(
            str(item.get("url") or "").strip()
            for item in (enrichment_release.get("connected_media") or [])
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        )
    stimulus = str(question.get("stimulus") or "")
    stem = str(question.get("stem") or "")
    requires_visual = any(token in stimulus for token in ("<그림>", "<사진>", "<영상>")) or bool(
        _QBank_VISUAL_REFERENCE_RE.search(stem)
    )
    text_sufficient = bool(
        isinstance(enrichment_release, dict)
        and enrichment_release.get("media_requirement_satisfied_by_text") is True
    )
    missing_required_media = requires_visual and not connected_images and not text_sufficient
    return {
        "practice_ready": not missing_required_media,
        "readiness_reason": "required_media_missing" if missing_required_media else None,
        "media_requirement": (
            "connected" if connected_images else "described_in_stem" if text_sufficient else "not_required"
        ),
    }


def public_qbank_question(question: dict, enrichment_release: dict | None = None) -> dict:
    """Return the strict pre-answer allowlist used by the student shell and Reader."""

    images: list[object] = [
        resolved
        for image in (question.get("imgs") or [])
        if (resolved_pair := resolve_student_qbank_image(image))
        for resolved, connected in (resolved_pair,)
        if resolved and connected
    ]
    if isinstance(enrichment_release, dict):
        images.extend(
            {
                "url": str(item.get("url") or ""),
                "caption": str(item.get("caption") or "제시자료"),
            }
            for item in (enrichment_release.get("connected_media") or [])
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        )

    return {
        "id": question.get("id"),
        "exam": question.get("exam"),
        "course": canonical_student_course(question),
        "course_id": canonical_student_course_id(question),
        "course_name": next(
            (course["name"] for course in STUDENT_COURSE_CATALOG if course["id"] == canonical_student_course_id(question)),
            None,
        ),
        "subject": question.get("subject"),
        "major": question.get("major"),
        "topic": question.get("topic"),
        "subtopic": question.get("subtopic"),
        "qtype": question.get("qtype"),
        "tags": question.get("tags") or [],
        "faculty": question.get("faculty"),
        "stem": question.get("stem"),
        "stimulus": question.get("stimulus"),
        "choices": [
            {"n": str(choice.get("n") or ""), "text": choice.get("text") or ""}
            for choice in (question.get("choices") or [])
            if isinstance(choice, dict)
        ],
        "imgs": images,
        **qbank_question_practice_readiness(question, enrichment_release),
    }


@app.get("/api/faculty/qbank-enrichment/review-queue")
def faculty_qbank_enrichment_review_queue(request: Request) -> dict:
    """실제 교수 검수 큐. 학생 workspace에서는 접근할 수 없다."""
    _require_faculty_reviewer(request)
    from src.services import qbank_enrichment

    return qbank_enrichment.build_faculty_review_queue()


@app.post("/api/faculty/qbank-enrichment/{question_id}/review")
def faculty_qbank_enrichment_review(
    question_id: str,
    request: Request,
    payload: Annotated[dict, Body()],
) -> dict:
    """교수의 명시적 medical approval 또는 거절을 기록한다."""
    reviewer_id = _require_faculty_reviewer(request)
    from src.services import qbank_enrichment

    try:
        entry = qbank_enrichment.record_faculty_review(
            question_id,
            decision=str(payload.get("decision") or ""),
            reviewer_id=reviewer_id,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            medical_approval=payload.get("medical_approval") is True,
            review_note=str(payload.get("review_note") or "").strip(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="검수 초안을 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "question_id": question_id,
        "review_status": entry.get("review_status"),
        "student_release_approved": qbank_enrichment.is_student_release_approved(entry),
        "reviewer_id": entry.get("reviewer_id"),
        "reviewed_at": entry.get("reviewed_at"),
    }


@app.get("/api/student/qbank")
def student_qbank_catalog() -> dict:
    """Serve canonical qbank metadata and questions without truth fields."""

    try:
        questions = load_student_qbank()["questions"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="학생 문항 데이터를 불러올 수 없습니다.") from exc
    enrichment_releases = _visible_qbank_enrichment_releases()
    course_names = ("신경 및 특수감각기학", "혈액종양내과", "임상종합평가")
    courses = []
    for name in course_names:
        course_questions = [question for question in questions if canonical_student_course(question) == name]
        categories = []
        for category_name in sorted({str(question.get("major") or "기타") for question in course_questions}):
            category_questions = [question for question in course_questions if str(question.get("major") or "기타") == category_name]
            topics = [
                {
                    "name": topic_name,
                    "count": sum(1 for question in category_questions if str(question.get("topic") or "기타") == topic_name),
                }
                for topic_name in sorted({str(question.get("topic") or "기타") for question in category_questions})
            ]
            categories.append({"name": category_name, "total": len(category_questions), "topics": topics})
        ready_count = sum(
            bool(qbank_question_practice_readiness(question, enrichment_releases.get(str(question.get("id") or "")))["practice_ready"])
            for question in course_questions
        )
        courses.append(
            {
                "name": name,
                "total": len(course_questions),
                "practice_ready_count": ready_count,
                "media_review_count": len(course_questions) - ready_count,
                "categories": categories,
            }
        )
    ready_count = sum(
        bool(qbank_question_practice_readiness(question, enrichment_releases.get(str(question.get("id") or "")))["practice_ready"])
        for question in questions
    )
    return {
        "schema_version": "paccine.student_qbank.pre_answer.v1",
        "subjects": courses,
        "questions": [
            public_qbank_question(question, enrichment_releases.get(str(question.get("id") or "")))
            for question in questions
        ],
        "question_count": len(questions),
        "practice_ready_count": ready_count,
        "media_review_count": len(questions) - ready_count,
    }


@app.get("/api/student/catalog")
def student_course_catalog(request: Request) -> dict:
    """Return the official curriculum catalog and separate assessment collections."""

    try:
        questions = load_student_qbank()["questions"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="학생 문항 데이터를 불러올 수 없습니다.") from exc
    enrichment_releases = _visible_qbank_enrichment_releases()
    favorites = set(_latest_course_preferences(_student_identity(request)))
    courses = []
    for configured in STUDENT_COURSE_CATALOG:
        qbank_course = configured.get("qbank_course")
        items = [question for question in questions if qbank_course and canonical_student_course(question) == qbank_course]
        ready_count = sum(
            bool(qbank_question_practice_readiness(question, enrichment_releases.get(str(question.get("id") or "")))["practice_ready"])
            for question in items
        )
        topics = Counter(str(question.get("topic") or question.get("major") or "기타") for question in items)
        courses.append(
            {
                "id": configured["id"],
                "name": configured["name"],
                "status": configured["status"],
                "is_favorite": configured["id"] in favorites,
                "question_count": len(items),
                "practice_ready_count": ready_count,
                "media_review_count": len(items) - ready_count,
                "topics": [{"name": name, "count": count} for name, count in topics.most_common()],
            }
        )
    assessment_groups: dict[str, list[dict]] = defaultdict(list)
    for question in questions:
        if canonical_student_course(question) == "임상종합평가":
            assessment_groups[str(question.get("exam") or "")].append(question)
    assessments = [
        {
            "id": f"assessment:{index + 1}",
            "name": name,
            "question_count": len(items),
            "practice_ready_count": sum(
                bool(qbank_question_practice_readiness(question, enrichment_releases.get(str(question.get("id") or "")))["practice_ready"])
                for question in items
            ),
            "media_review_count": sum(
                not bool(qbank_question_practice_readiness(question, enrichment_releases.get(str(question.get("id") or "")))["practice_ready"])
                for question in items
            ),
            "status": "released",
        }
        for index, (name, items) in enumerate(sorted(assessment_groups.items()))
    ]
    ready_count = sum(
        bool(qbank_question_practice_readiness(question, enrichment_releases.get(str(question.get("id") or "")))["practice_ready"])
        for question in questions
    )
    return {
        "schema_version": "paccine.student_catalog.v1",
        "courses": courses,
        "assessments": assessments,
        "released_question_count": len(questions),
        "practice_ready_question_count": ready_count,
        "media_review_question_count": len(questions) - ready_count,
        "model": "questions_keep_source_assessment_and_link_to_courses_by_question_id",
    }


@app.get("/api/student/preferences")
def student_preferences(request: Request) -> dict:
    return {"favorite_course_ids": _latest_course_preferences(_student_identity(request))}


@app.patch("/api/student/courses/{course_id}/favorite")
def save_student_course_favorite(course_id: str, request: Request, payload: Annotated[dict, Body()]) -> dict:
    valid_ids = {str(course["id"]) for course in STUDENT_COURSE_CATALOG}
    if course_id not in valid_ids:
        raise HTTPException(status_code=404, detail="과목을 찾을 수 없습니다.")
    event = {
        "event_type": "course_favorite_changed",
        "user_id": _student_identity(request),
        "course_id": course_id,
        "on": bool(payload.get("on")),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_private_jsonl(STUDENT_COURSE_PREFERENCES_LOG_PATH, event)
    return {"course_id": course_id, "on": event["on"], "status": "saved"}


@app.get("/api/student/bookmarks")
def student_qbank_bookmarks(request: Request) -> dict:
    state = _latest_qbank_bookmarks(_student_identity(request))
    return {"question_ids": sorted(question_id for question_id, on in state.items() if on)}


@app.patch("/api/student/questions/{question_id}/bookmark")
def save_student_qbank_bookmark(question_id: str, request: Request, payload: Annotated[dict, Body()]) -> dict:
    try:
        questions = load_student_qbank()["questions"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="학생 문항 데이터를 불러올 수 없습니다.") from exc
    if not any(str(question.get("id") or "") == question_id for question in questions):
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.")
    event = {
        "event_type": "qbank_bookmark_changed",
        "user_id": _student_identity(request),
        "question_id": question_id,
        "on": bool(payload.get("on")),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_private_jsonl(PRACTICE_BOOKMARKS_LOG_PATH, event)
    return {"question_id": question_id, "on": event["on"], "status": "saved"}


@app.get("/api/student/concepts")
def student_concepts() -> dict:
    notes = _load_student_concept_notes()
    approved = [note for note in notes if not note.get("needs_review") and note.get("gen_ready")]
    return {
        "schema_version": "paccine.student_concepts.v1",
        "approved": [
            {
                "concept_id": note.get("disease_concept_id"),
                "title": note.get("title"),
                "sections": note.get("sections") or {},
                "status": "ready",
            }
            for note in approved
        ],
        "reviewing_count": len(notes) - len(approved),
        "release_policy": "faculty_approved_fail_closed",
    }


@app.get("/api/student/review")
def student_fsrs_review_queue(request: Request, limit: int = 20) -> dict:
    try:
        questions = load_student_qbank()["questions"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="학생 문항 데이터를 불러올 수 없습니다.") from exc
    now = datetime.now(timezone.utc)
    latest = _latest_fsrs_cards(_student_identity(request))
    enrichment_releases = _visible_qbank_enrichment_releases()
    ready_questions = [
        question
        for question in questions
        if qbank_question_practice_readiness(
            question,
            enrichment_releases.get(str(question.get("id") or "")),
        )["practice_ready"]
    ]
    rows = [
        _fsrs_card_summary(question, latest.get(str(question.get("id") or "")), now)
        for question in ready_questions
    ]
    priority = {"overdue": 0, "due": 1, "new": 2, "scheduled": 3}
    rows.sort(key=lambda row: (priority[row["status"]], row.get("due_at") or "", row["question_id"] or ""))
    counts = Counter(row["status"] for row in rows)
    return {
        "schema_version": "paccine.student_fsrs_queue.v1",
        "algorithm": "FSRS-6",
        "desired_retention": 0.9,
        "counts": {key: counts.get(key, 0) for key in ("overdue", "due", "new", "scheduled")},
        "items": rows[: max(1, min(limit, 100))],
    }


@app.get("/api/student/medical-copilot/review")
def student_guideline_claim_fsrs_queue(request: Request, limit: int = 20) -> dict:
    """Return only currently valid claims released explicitly to the Anki surface."""

    try:
        claims = list_valid_released_claims(surface="anki")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    latest = _latest_claim_fsrs_cards(_student_identity(request))
    rows = [_claim_fsrs_card_summary(claim, latest.get(str(claim.get("claim_id") or "")), now) for claim in claims]
    priority = {"overdue": 0, "due": 1, "new": 2, "scheduled": 3}
    rows.sort(key=lambda row: (priority[row["status"]], row.get("due_at") or "", row["claim_id"] or ""))
    counts = Counter(row["status"] for row in rows)
    return {
        "schema_version": "paccine.student_guideline_claim_fsrs_queue.v1",
        "algorithm": "FSRS-6",
        "desired_retention": 0.9,
        "release_surface": "anki",
        "fail_closed": True,
        "counts": {key: counts.get(key, 0) for key in ("overdue", "due", "new", "scheduled")},
        "items": rows[: max(1, min(limit, 100))],
    }


@app.post("/api/student/medical-copilot/claims/{claim_id}/fsrs")
def save_student_guideline_claim_fsrs_review(
    claim_id: str,
    request: Request,
    payload: Annotated[dict, Body()],
) -> dict:
    try:
        from fsrs import Card, Rating, Scheduler
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="FSRS 모듈을 불러올 수 없습니다.") from exc
    rating_value = safe_int(payload.get("rating"))
    if rating_value not in {1, 2, 3, 4}:
        raise HTTPException(status_code=400, detail="rating은 1(Again)~4(Easy)여야 합니다.")
    try:
        valid_claims = list_valid_released_claims(surface="anki")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not any(str(claim.get("claim_id") or "") == claim_id for claim in valid_claims):
        raise HTTPException(status_code=404, detail="현재 Anki 복습용으로 승인된 claim을 찾을 수 없습니다.")
    user_id = _student_identity(request)
    event_id = str(payload.get("event_id") or f"claim_fsrs_{user_id}_{claim_id}_{int(time.time() * 1000)}")
    for existing in _iter_private_jsonl(STUDENT_CLAIM_FSRS_LOG_PATH):
        if existing.get("user_id") == user_id and existing.get("event_id") == event_id:
            return {"status": "already_saved", "claim_id": claim_id, "card": existing.get("card")}
    previous = _latest_claim_fsrs_cards(user_id).get(claim_id)
    card = Card.from_json(json.dumps(previous["card"])) if previous else Card()
    scheduler = Scheduler(desired_retention=0.9, maximum_interval=3650, enable_fuzzing=False)
    now = datetime.now(timezone.utc)
    card, review_log = scheduler.review_card(card, Rating(rating_value), review_datetime=now)
    card_payload = json.loads(card.to_json())
    event = {
        "event_type": "guideline_claim_fsrs_reviewed",
        "event_id": event_id,
        "user_id": user_id,
        "claim_id": claim_id,
        "rating": rating_value,
        "reviewed_at": now.isoformat(),
        "card": card_payload,
        "review_log": json.loads(review_log.to_json()),
        "algorithm": "FSRS-6",
        "desired_retention": 0.9,
    }
    _append_private_jsonl(STUDENT_CLAIM_FSRS_LOG_PATH, event)
    return {"status": "saved", "claim_id": claim_id, "card": card_payload, "algorithm": "FSRS-6"}


@app.post("/api/student/fsrs/reviews")
def save_student_fsrs_review(request: Request, payload: Annotated[dict, Body()]) -> dict:
    try:
        from fsrs import Card, Rating, Scheduler
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="FSRS 모듈을 불러올 수 없습니다.") from exc
    question_id = str(payload.get("question_id") or "").strip()
    rating_value = safe_int(payload.get("rating"))
    if rating_value not in {1, 2, 3, 4}:
        raise HTTPException(status_code=400, detail="rating은 1(Again)~4(Easy)여야 합니다.")
    try:
        questions = load_student_qbank()["questions"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="학생 문항 데이터를 불러올 수 없습니다.") from exc
    if not any(str(question.get("id") or "") == question_id for question in questions):
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.")
    user_id = _student_identity(request)
    event_id = str(payload.get("event_id") or f"fsrs_{user_id}_{question_id}_{int(time.time() * 1000)}")
    for existing in _iter_private_jsonl(STUDENT_FSRS_LOG_PATH):
        if existing.get("user_id") == user_id and existing.get("event_id") == event_id:
            return {"status": "already_saved", "question_id": question_id, "card": existing.get("card")}
    previous = _latest_fsrs_cards(user_id).get(question_id)
    card = Card.from_json(json.dumps(previous["card"])) if previous else Card()
    scheduler = Scheduler(desired_retention=0.9, maximum_interval=3650, enable_fuzzing=False)
    now = datetime.now(timezone.utc)
    card, review_log = scheduler.review_card(card, Rating(rating_value), review_datetime=now)
    card_payload = json.loads(card.to_json())
    event = {
        "event_type": "fsrs_reviewed",
        "event_id": event_id,
        "user_id": user_id,
        "question_id": question_id,
        "rating": rating_value,
        "reviewed_at": now.isoformat(),
        "card": card_payload,
        "review_log": json.loads(review_log.to_json()),
        "algorithm": "FSRS-6",
        "desired_retention": 0.9,
    }
    _append_private_jsonl(STUDENT_FSRS_LOG_PATH, event)
    return {"status": "saved", "question_id": question_id, "card": card_payload, "algorithm": "FSRS-6"}


def _apply_qbank_enrichment_release(response: dict, question_id: str) -> None:
    """제출 후 응답에 실제 교수 승인 enrichment release만 병합한다.

    - draft overlay는 절대 병합하지 않는다(승인 release만).
    - load_releases()가 checksum + medical approval + non-demo를 강제한다.
    - 원본에 해설이 있으면 원본 우선, 비어있을 때만 release로 채운다.
    """
    try:
        from src.services import qbank_enrichment
    except Exception:
        return
    try:
        entry = qbank_enrichment.load_releases().get(str(question_id))
    except Exception:
        return
    if not isinstance(entry, dict):
        return
    if entry.get("explanation") and not str(response.get("explanation") or "").strip():
        response["explanation"] = entry["explanation"]
    if entry.get("points") and not response.get("points"):
        response["points"] = entry["points"]
    if entry.get("choice_explanations"):
        existing = response.get("choice_explanations") or {}
        filled = {
            str(c.get("n") or ""): str(c.get("expl") or "")
            for c in entry["choice_explanations"]
            if isinstance(c, dict)
        }
        # 원본 선지풀이가 비었거나 플레이스홀더일 때만 release로 채운다.
        for key, value in filled.items():
            current = str(existing.get(key) or "")
            if not current.strip() or "저장된 해설에는" in current or "근거가 부족" in current:
                existing[key] = value
        response["choice_explanations"] = existing
    for field in (
        "concept_id",
        "concept_label",
        "concept_registry_status",
        "target_axis_type",
        "target_axis_label",
        "target_axis_ids",
        "target_axis_resolution",
        "anki_cards",
        "connected_media",
        "media_requirement_satisfied_by_text",
        "evidence",
    ):
        if field in entry:
            response[field] = entry[field]
    faculty_approved = qbank_enrichment.is_student_release_approved(entry)
    response["ontology_analytics_approved"] = bool(entry.get("target_axis_type"))
    response["enrichment_source"] = "faculty_release" if faculty_approved else "owner_curated_demo_release"
    response["enrichment_needs_review"] = not faculty_approved
    response["enrichment_release"] = {
        "release_mode": "faculty_approved" if faculty_approved else "owner_curated_demo",
        "medical_approval": faculty_approved,
        "needs_real_faculty_review": not faculty_approved,
        "reviewer_id": entry.get("reviewer_id"),
        "reviewed_at": entry.get("reviewed_at"),
    }


@app.post("/api/student/questions/{question_id}/answer")
def submit_student_qbank_answer(question_id: str, request: Request, payload: Annotated[dict, Body()]) -> dict:
    """Verify one qbank answer server-side, then release its feedback."""

    selected = normalize_attempt_choices(payload.get("selected_choices") or payload.get("selected"))
    if not selected:
        raise HTTPException(status_code=400, detail="답안을 선택하세요.")
    try:
        questions = load_student_qbank()["questions"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="학생 문항 데이터를 불러올 수 없습니다.") from exc
    question = next((item for item in questions if str(item.get("id") or "") == question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.")
    visible_release = _visible_qbank_enrichment_releases().get(str(question_id))
    if not qbank_question_practice_readiness(question, visible_release)["practice_ready"]:
        raise HTTPException(status_code=409, detail="필수 제시자료 연결을 검토 중인 문항입니다.")
    valid = {str(choice.get("n") or "") for choice in question.get("choices") or [] if isinstance(choice, dict)}
    if not set(selected).issubset(valid):
        raise HTTPException(status_code=400, detail="유효하지 않은 선택지가 포함되어 있습니다.")
    answer_keys = normalize_attempt_choices(question.get("answer"))
    is_correct = set(selected) == set(answer_keys)
    user_id = _student_identity(request)
    event = normalize_attempt_payload(
        {
            "event_id": payload.get("event_id"),
            "session_id": payload.get("session_id") or "qbank_session",
            "user_id": user_id,
            "question_id": question_id,
            "question_type": question.get("qtype"),
            "selected_choices": selected,
            "answer_keys": answer_keys,
            "is_correct": is_correct,
            "time_ms": payload.get("time_ms"),
            "is_bookmarked": payload.get("is_bookmarked"),
            "course_name": canonical_student_course(question),
            "stem_preview": question.get("stem"),
            "labels": {
                "subject": question.get("subject"),
                "major": question.get("major"),
                "topic": question.get("topic"),
                "subtopic": question.get("subtopic"),
            },
            "source_meta": {"source_file": "qbank.json", "exam": question.get("exam")},
        }
    )
    event["answer_keys"] = answer_keys
    event["is_correct"] = is_correct
    event["ontology_snapshot_status"] = "qbank_server_verified"
    try:
        from src.services import qbank_enrichment

        approved_snapshot = qbank_enrichment.student_release_snapshot(question_id)
    except Exception:
        approved_snapshot = None
    if approved_snapshot:
        event["qbank_enrichment_snapshot"] = approved_snapshot
        event["ontology_snapshot_status"] = "qbank_server_verified_with_approved_enrichment"
    already_saved = any(
        existing.get("event_id") == event["event_id"]
        for existing in iter_attempt_events(user_id=user_id)
    )
    if not already_saved:
        ensure_course_exam_dirs()
        with ATTEMPTS_LOG_PATH.open("a", encoding="utf-8") as file:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX)
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        os.chmod(ATTEMPTS_LOG_PATH, 0o600)
    response = {
        "status": "already_saved" if already_saved else "saved",
        "is_correct": is_correct,
        "selected_choices": selected,
        "answer_keys": answer_keys,
        "explanation": question.get("explanation") or "",
        "points": question.get("points") or [],
        "choice_explanations": {
            str(choice.get("n") or ""): str(choice.get("expl") or "")
            for choice in (question.get("choices") or [])
            if isinstance(choice, dict)
        },
        "learning_context": _student_learning_context(question_id),
    }
    _apply_qbank_enrichment_release(response, question_id)
    return response


@app.get("/api/practice/catalog")
def student_practice_catalog(limit: int = 100) -> dict:
    """List only faculty-approved question sets that learners may practice."""

    rows = []
    for summary in list_question_sets(limit=max(1, min(limit, 500))):
        approved_count = safe_int(summary.get("approved_count"), 0) or 0
        if approved_count <= 0:
            continue
        release = student_set_release(str(summary.get("set_id") or ""))
        if not release:
            continue
        subject = str(summary.get("subject") or "").strip()
        unit = str(summary.get("unit") or "").strip()
        source_name = str(summary.get("source_name") or "").strip()
        try:
            packet = load_question_set(str(summary.get("set_id") or ""), include_summary=False)
        except (FileNotFoundError, ValueError):
            packet = {}
        metadata = packet.get("metadata") if isinstance(packet.get("metadata"), dict) else {}
        title = " · ".join(value for value in (subject, unit) if value) or source_name or str(summary.get("set_id"))
        rows.append(
            {
                "source_id": f"set:{summary.get('set_id')}",
                "set_id": summary.get("set_id"),
                "title": title,
                "source_name": source_name,
                "subject": subject,
                "unit": unit,
                "question_type": summary.get("question_type"),
                # Set-level, faculty-authored labels are safe to expose before an
                # attempt. Question-level answer, explanation, diagnosis and
                # ontology target fields remain excluded from this endpoint.
                "exam_year": metadata.get("exam_year") or metadata.get("year"),
                "instructor": metadata.get("instructor") or metadata.get("professor"),
                "major_category": metadata.get("major_category") or metadata.get("department"),
                "topic": metadata.get("topic") or metadata.get("subtopic"),
                "assessment_domain": metadata.get("assessment_domain"),
                "difficulty": metadata.get("difficulty"),
                "approved_count": approved_count,
                "has_media": bool(summary.get("image_question_count")),
                "updated_at": summary.get("updated_at"),
                "release_id": release.get("assignment_id"),
            }
        )
    return {
        "sets": rows,
        "available_question_count": sum(row["approved_count"] for row in rows),
        "release_policy": "student_release_assignments.v1",
    }


@app.get("/api/practice/sets/{set_id}/questions")
def student_approved_set_question_list(set_id: str, limit: int | None = None) -> dict:
    """Return faculty-approved questions without answer or explanation fields."""

    if not student_set_release(set_id):
        raise HTTPException(status_code=404, detail="학생에게 공개된 문항 세트가 아닙니다.")

    try:
        packet = load_question_set(set_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raw_questions = packet.get("questions") if isinstance(packet.get("questions"), list) else []
    questions = []
    for index, raw_question in enumerate(raw_questions, start=1):
        if str(raw_question.get("review_status") or "") != "approved":
            continue
        question_id = str(raw_question.get("question_id") or index)
        questions.append(approved_set_student_question(set_id, question_id))
        if limit and limit > 0 and len(questions) >= limit:
            break
    metadata = packet.get("metadata") if isinstance(packet.get("metadata"), dict) else {}
    return {
        "source_id": f"set:{set_id}",
        "set_id": set_id,
        "title": " · ".join(
            value for value in (
                str(metadata.get("subject") or "").strip(),
                str(metadata.get("unit") or "").strip(),
            ) if value
        ) or str(metadata.get("source_name") or set_id),
        "questions": questions,
        "released_count": len(questions),
        "release_policy": "student_release_assignments.v1",
    }


@app.post("/api/practice/sessions")
def start_student_practice_session(request: Request, payload: Annotated[dict, Body()]) -> dict:
    """Create a server-owned session only after every requested item resolves."""

    requested = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    if not 1 <= len(requested) <= 100:
        raise HTTPException(status_code=400, detail="1~100개의 공개 문항을 선택하세요.")
    resolved = []
    for item in requested:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="문항 참조 형식이 올바르지 않습니다.")
        exam_id = str(item.get("exam_id") or "").strip()
        question_id = str(item.get("question_id") or "").strip()
        if not exam_id or not question_id:
            raise HTTPException(status_code=400, detail="exam_id와 question_id가 필요합니다.")
        load_stored_practice_question(exam_id, question_id)
        resolved.append({"exam_id": exam_id, "question_id": question_id})

    session_id = f"practice_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    event = {
        "event_type": "session_started",
        "session_id": session_id,
        "user_id": _request_identity(request) or "local_student",
        "title": str(payload.get("title") or "공개 문항 학습 세트")[:200],
        "mode": "exam" if str(payload.get("mode") or "") == "exam" else "learning",
        "question_count": len(resolved),
        "questions": resolved,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _append_private_jsonl(PRACTICE_SESSIONS_LOG_PATH, event)
    return {"session_id": session_id, "status": "started", "question_count": len(resolved)}


@app.get("/api/practice/sessions/{session_id}/questions/{question_index}")
def student_practice_session_question(session_id: str, question_index: int) -> dict:
    """Return a strict pre-answer allowlist for one server-owned session item."""

    session = _practice_session_started(session_id)
    questions = session.get("questions") if isinstance(session.get("questions"), list) else []
    if question_index < 0 or question_index >= len(questions):
        raise HTTPException(status_code=404, detail="세션 문항을 찾을 수 없습니다.")
    ref = questions[question_index]
    stored = load_stored_practice_question(str(ref.get("exam_id") or ""), str(ref.get("question_id") or ""))
    return {
        "session_id": session_id,
        "index": question_index,
        "question": {
            "question_id": stored.get("question_id"),
            "question_number": stored.get("question_number"),
            "stem": stored.get("stem"),
            "stimulus": stored.get("stimulus"),
            "lab_values": stored.get("lab_values") or [],
            "choices": stored.get("choices") or {},
            "question_format": stored.get("question_format"),
            "course_name": stored.get("course_name") or (stored.get("labels") or {}).get("course_name"),
            "unit": stored.get("unit") or (stored.get("labels") or {}).get("unit"),
            "selection_mode": "multiple" if len(course_exam_answer_values(stored)) > 1 else "single",
            "required_selection_count": max(1, len(course_exam_answer_values(stored))),
            "media_refs": [
                {
                    "media_id": item.get("media_id") or item.get("asset_id"),
                    "url": item.get("url"),
                    "caption": item.get("caption"),
                }
                for item in (stored.get("media_refs") or [])
                if isinstance(item, dict) and item.get("url")
            ],
            "item_version": question_content_sha256(stored),
        },
    }


@app.patch("/api/questions/{question_id}/bookmark")
def save_student_bookmark(question_id: str, request: Request, payload: Annotated[dict, Body()]) -> dict:
    """Persist an optimistic learner bookmark event without exposing question truth."""

    session_id = str(payload.get("session_id") or "").strip()
    exam_id = str(payload.get("exam_id") or "").strip()
    if not session_id.startswith("practice_") or not exam_id:
        raise HTTPException(status_code=400, detail="session_id와 exam_id가 필요합니다.")
    _practice_session_started(session_id)
    load_stored_practice_question(exam_id, question_id)
    event = {
        "event_type": "bookmark_changed",
        "session_id": session_id,
        "user_id": _request_identity(request) or "local_student",
        "exam_id": exam_id,
        "question_id": question_id,
        "on": bool(payload.get("on")),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _append_private_jsonl(PRACTICE_BOOKMARKS_LOG_PATH, event)
    return {"question_id": question_id, "on": event["on"], "status": "saved"}


@app.put("/api/practice/sessions/{session_id}/snapshot")
def save_student_practice_snapshot(session_id: str, request: Request, payload: Annotated[dict, Body()]) -> dict:
    """Store the resumable learner state; failures can remain in local browser storage."""

    _practice_session_started(session_id)
    answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
    flags = payload.get("flags") if isinstance(payload.get("flags"), dict) else {}
    event = {
        "event_type": "session_snapshot",
        "session_id": session_id,
        "user_id": _request_identity(request) or "local_student",
        "index": max(0, safe_int(payload.get("index"), 0) or 0),
        "answers": answers,
        "elapsed_ms": max(0, safe_int(payload.get("elapsed_ms"), 0) or 0),
        "flags": flags,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _append_private_jsonl(PRACTICE_SNAPSHOTS_LOG_PATH, event)
    return {"session_id": session_id, "status": "saved", "saved_at": event["saved_at"]}


@app.post("/api/practice/sessions/{session_id}/finalize")
def finalize_student_practice_session(session_id: str, request: Request, payload: Annotated[dict, Body()]) -> dict:
    """Append a compact completion record; detailed answers remain in attempt events."""

    if not session_id.startswith("practice_"):
        raise HTTPException(status_code=400, detail="유효하지 않은 세션입니다.")
    event = {
        "event_type": "session_finalized",
        "session_id": session_id,
        "user_id": _request_identity(request) or "local_student",
        "answered_count": max(0, safe_int(payload.get("answered_count"), 0) or 0),
        "correct_count": max(0, safe_int(payload.get("correct_count"), 0) or 0),
        "elapsed_ms": max(0, safe_int(payload.get("elapsed_ms"), 0) or 0),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    }
    _practice_session_started(session_id)
    _append_private_jsonl(PRACTICE_SESSIONS_LOG_PATH, event)
    return {"session_id": session_id, "status": "saved"}


@app.get("/api/practice/sessions/{session_id}/result")
def student_practice_session_result(session_id: str) -> dict:
    """Return a post-session aggregate without private source text or unsubmitted answers."""

    session = _practice_session_started(session_id)
    question_refs = session.get("questions") if isinstance(session.get("questions"), list) else []
    attempts = [event for event in iter_attempt_events() if event.get("session_id") == session_id]
    by_question = {str(event.get("question_id") or ""): event for event in attempts}
    finalized = next(
        (
            event
            for event in reversed(_iter_private_jsonl(PRACTICE_SESSIONS_LOG_PATH))
            if event.get("event_type") == "session_finalized" and event.get("session_id") == session_id
        ),
        None,
    )
    rows = []
    for index, ref in enumerate(question_refs):
        question_id = str(ref.get("question_id") or "")
        attempt = by_question.get(question_id)
        rows.append(
            {
                "index": index,
                "question_id": question_id,
                "answered": bool(attempt),
                "is_correct": bool(attempt.get("is_correct")) if attempt else None,
                "elapsed_seconds": round((safe_int(attempt.get("time_ms"), 0) or 0) / 1000) if attempt else 0,
                "bookmarked": bool(attempt.get("is_bookmarked")) if attempt else False,
            }
        )
    answered_count = len(attempts)
    correct_count = sum(1 for event in attempts if event.get("is_correct"))
    total_ms = safe_int((finalized or {}).get("elapsed_ms"), 0) or sum(safe_int(event.get("time_ms"), 0) or 0 for event in attempts)
    return {
        "session_id": session_id,
        "status": "completed" if finalized else "active",
        "score_percent": round(correct_count / max(1, len(question_refs)) * 100),
        "correct_count": correct_count,
        "answered_count": answered_count,
        "question_count": len(question_refs),
        "total_seconds": round(total_ms / 1000),
        "average_seconds": round(total_ms / max(1, len(question_refs)) / 1000),
        "rows": rows,
        "weak_areas": [],
    }


@app.get("/api/evidence/review")
def evidence_review_list(status: str = "all", limit: int = 60, offset: int = 0) -> dict:
    """근거(citation) 검토 대상 목록. status: draft | needs_review | verified | rejected | all."""
    wanted = {"draft", "needs_review", "verified", "rejected"} if status == "all" else {status}
    items = []
    counts = {"draft": 0, "needs_review": 0, "verified": 0, "rejected": 0}
    for path in sorted(COURSE_EXAM_EXTRACTED_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        exam = record.get("exam", {})
        for q in record.get("questions", []):
            st = q.get("evidence_status")
            if st not in counts:
                continue
            counts[st] += 1
            if st not in wanted:
                continue
            labels = q.get("labels") or {}
            items.append({
                "exam_id": path.stem,
                "source_name": exam.get("source_exam") or path.stem,
                "question_id": q.get("question_id"),
                "question_number": q.get("question_number"),
                "stem": (q.get("stem") or "")[:160],
                "concept_tags": labels.get("concept_tags") or [],
                "evidence": q.get("evidence") or [],
                "evidence_status": st,
                "evidence_note": q.get("evidence_note"),
            })
    total = len(items)
    return {"total": total, "counts": counts, "items": items[offset:offset + max(1, limit)]}


@app.post("/api/evidence/review")
def evidence_review_update(payload: Annotated[dict, Body()]) -> dict:
    """근거 검토 액션. action: approve | reject | flag | edit."""
    exam_id = str(payload.get("exam_id") or "").strip()
    question_id = str(payload.get("question_id") or "").strip()
    action = str(payload.get("action") or "").strip()
    if not exam_id or not question_id:
        raise HTTPException(status_code=400, detail="exam_id와 question_id가 필요합니다.")
    try:
        record_path, record = load_course_exam_record(exam_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다.") from None
    q = next((x for x in record.get("questions", []) if x.get("question_id") == question_id), None)
    if q is None:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.")
    if action == "approve":
        if not q.get("evidence"):
            raise HTTPException(status_code=400, detail="부착된 근거가 없어 승인할 수 없습니다.")
        q["evidence_status"] = "verified"
        for ev in q["evidence"]:
            ev["status"] = "verified"
    elif action == "reject":
        q["evidence"] = []
        q["evidence_status"] = "rejected"
        q["evidence_note"] = str(payload.get("note") or "검토자 반려")
    elif action == "flag":
        q["evidence_status"] = "needs_review"
    elif action == "edit":
        new_ev = payload.get("evidence")
        if not isinstance(new_ev, list):
            raise HTTPException(status_code=400, detail="evidence 배열이 필요합니다.")
        q["evidence"] = new_ev
        q["evidence_status"] = "verified" if new_ev else "needs_review"
    else:
        raise HTTPException(status_code=400, detail="action은 approve/reject/flag/edit 중 하나여야 합니다.")
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "question_id": question_id, "evidence_status": q["evidence_status"]}


@app.post("/api/practice/attempts")
def save_practice_attempt(request: Request, payload: Annotated[dict, Body()]) -> dict:
    event = normalize_attempt_payload(payload)
    authenticated_user = _request_identity(request)
    if authenticated_user:
        event["user_id"] = authenticated_user
        event["role"] = "authenticated_user"
    if not event["question_id"]:
        raise HTTPException(status_code=400, detail="question_id가 필요합니다.")
    if not event["selected_choices"]:
        raise HTTPException(status_code=400, detail="선택한 답안이 필요합니다.")
    if any(
        existing.get("event_id") == event["event_id"]
        for existing in iter_attempt_events(user_id=event["user_id"])
    ):
        raise HTTPException(status_code=409, detail="이미 저장된 풀이 이벤트입니다.")
    stored_question = None
    feedback_release = {
        "allowed": False,
        "release_id": None,
        "reasons": ["stored_question_unresolved"],
        "item_version": None,
    }
    if event["exam_id"]:
        stored_question = load_stored_practice_question(event["exam_id"], event["question_id"])
        valid_choices = set(_practice_choice_texts(stored_question))
        if not set(event["selected_choices"]).issubset(valid_choices):
            raise HTTPException(status_code=400, detail="유효하지 않은 선택지가 포함되어 있습니다.")
        is_approved_set = event["exam_id"].startswith("set:")
        if is_approved_set:
            analytics_release = {
                "allowed": False,
                "release_id": None,
                "reasons": ["ontology_not_used_for_faculty_question_set"],
                "item_version": question_content_sha256(stored_question),
            }
            feedback_release = dict(analytics_release)
        else:
            analytics_release = evaluate_practice_release(
                event["exam_id"], stored_question, "analytics"
            )
            feedback_release = evaluate_practice_release(
                event["exam_id"], stored_question, "post_answer_feedback"
            )
        attach_stored_question_snapshot(
            event,
            stored_question,
            analytics_release=analytics_release,
            feedback_release=feedback_release,
        )
    else:
        # Historical/imported clients did not always send exam_id. Keep those
        # events writable, but never accept client-supplied ontology metadata as
        # a substitute for a server-resolved question.
        event["ontology_snapshot_status"] = "unresolved_legacy_missing_exam_id"
    ensure_course_exam_dirs()
    with ATTEMPTS_LOG_PATH.open("a", encoding="utf-8") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
        file.flush()
        os.fsync(file.fileno())
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    os.chmod(ATTEMPTS_LOG_PATH, 0o600)
    if event["exam_id"].startswith("set:") and stored_question:
        feedback_packet = {
            "schema_version": "feedback_packet.v1",
            "feedback_id": f"fb:{event['event_id']}",
            "attempt_event_id": event["event_id"],
            "question_id": event["question_id"],
            "item_version": event.get("item_version"),
            "status": "released",
            "release_mode": "immediate",
            "result": {
                "is_correct": bool(event.get("is_correct")),
                "selected_choices": event.get("selected_choices") or [],
                "correct_choices": event.get("answer_keys") or [],
            },
            "explanation": stored_question.get("explanation") or "",
            "choice_explanations": stored_question.get("choice_explanations") or {},
            "safe_message": "교수 검토가 완료된 해설입니다.",
        }
    else:
        feedback_packet = build_feedback_packet(
            question=stored_question,
            event=event,
            gate=feedback_release,
        )
    return {
        "status": "saved",
        "attempt": public_attempt_event(event),
        "feedback": feedback_packet,
    }


@app.post("/api/practice/reports")
def save_practice_question_report(request: Request, payload: Annotated[dict, Body()]) -> dict:
    """Store a learner report for a server-owned, released practice item."""

    exam_id = str(payload.get("exam_id") or "").strip()
    question_id = str(payload.get("question_id") or "").strip()
    reason = str(payload.get("reason") or "").strip()[:1000]
    if not exam_id or not question_id or not reason:
        raise HTTPException(status_code=400, detail="exam_id, question_id, reason이 필요합니다.")
    # Resolve from server truth so draft or invented question IDs cannot be
    # reported as though they were learner-released items.
    load_stored_practice_question(exam_id, question_id)
    report = {
        "report_id": f"report_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}",
        "session_id": str(payload.get("session_id") or "local_session"),
        "user_id": _request_identity(request) or "local_student",
        "exam_id": exam_id,
        "question_id": question_id,
        "reason": reason,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "received",
    }
    LEARNING_ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = LEARNING_ANALYTICS_DIR / "question_reports.jsonl"
    with report_path.open("a", encoding="utf-8") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        file.write(json.dumps(report, ensure_ascii=False) + "\n")
        file.flush()
        os.fsync(file.fileno())
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    os.chmod(report_path, 0o600)
    return {"report_id": report["report_id"], "status": report["status"]}


@app.post("/api/practice/anki-export")
def export_practice_session_anki(request: Request, payload: Annotated[dict, Body()]) -> dict:
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id가 필요합니다.")
    user_id = _request_identity(request) or str(payload.get("user_id") or "local_student")
    session_events = [
        event
        for event in iter_attempt_events(user_id=user_id)
        if str(event.get("session_id") or "") == session_id
    ]
    if not session_events:
        raise HTTPException(status_code=404, detail="내보낼 풀이 기록을 찾을 수 없습니다.")

    requested = payload.get("items") if isinstance(payload.get("items"), list) else []
    attempted_pairs = {
        (str(event.get("exam_id") or ""), str(event.get("question_id") or ""))
        for event in session_events
    }
    selected_pairs = []
    if requested:
        for item in requested:
            if not isinstance(item, dict):
                continue
            pair = (str(item.get("exam_id") or ""), str(item.get("question_id") or ""))
            if pair not in attempted_pairs:
                raise HTTPException(status_code=403, detail="이 세션에서 풀이하지 않은 문항은 내보낼 수 없습니다.")
            selected_pairs.append(pair)
    else:
        selected_pairs = sorted(attempted_pairs)
    selected_pairs = list(dict.fromkeys(selected_pairs))
    if not selected_pairs:
        raise HTTPException(status_code=400, detail="내보낼 문항을 선택하세요.")

    questions = []
    for exam_id, question_id in selected_pairs:
        if not exam_id.startswith("set:"):
            raise HTTPException(status_code=400, detail="현재 Anki 내보내기는 교수 승인 문항 세트에서 지원합니다.")
        questions.append(load_stored_practice_question(exam_id, question_id))
    try:
        artifact = build_practice_anki_export(
            questions,
            session_id=session_id,
            export_dir=ANKI_EXPORT_DIR,
            deck_name=str(payload.get("deck_name") or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anki export 생성 실패: {exc}") from exc
    return artifact


@app.post("/api/feedback")
def save_feedback(payload: Annotated[dict, Body()]) -> dict:
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        rating = None
    if rating is None or not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="rating은 1~5 사이 정수여야 합니다.")
    event = {
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "rating": rating,
        "comment": str(payload.get("comment") or "").strip(),
        "page": str(payload.get("page") or "").strip(),
        "exam_id": str(payload.get("exam_id") or "").strip(),
    }
    ensure_course_exam_dirs()
    with FEEDBACK_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"status": "saved"}


@app.get("/api/feedback/summary")
def feedback_summary() -> dict:
    if not FEEDBACK_LOG_PATH.exists():
        return {"count": 0, "avg_rating": 0, "recent": []}
    events = []
    for line in FEEDBACK_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    count = len(events)
    avg_rating = round(sum(event.get("rating", 0) for event in events) / count, 2) if count else 0
    return {"count": count, "avg_rating": avg_rating, "recent": list(reversed(events))[:30]}


def _event_date(event: dict) -> str | None:
    """answered_at(ISO)에서 YYYY-MM-DD만 추출. 없거나 파싱 실패 시 None."""
    raw = str(event.get("answered_at") or "").strip()
    if not raw:
        return None
    return raw[:10] if len(raw) >= 10 else None


def build_practice_heatmap(events: list[dict], days: int = 119) -> dict:
    """최근 days일 동안 날짜별 풀이 수/정답 수를 집계해 잔디 히트맵용 데이터로 반환."""
    from datetime import timedelta

    today = datetime.now().date()
    start = today - timedelta(days=days)
    per_day: dict[str, dict] = {}
    dated_total = 0
    for event in events:
        day = _event_date(event)
        if not day:
            continue
        bucket = per_day.setdefault(day, {"attempts": 0, "correct": 0})
        bucket["attempts"] += 1
        if event.get("is_correct"):
            bucket["correct"] += 1
        dated_total += 1

    cells = []
    max_attempts = 0
    for offset in range((today - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        bucket = per_day.get(day, {"attempts": 0, "correct": 0})
        max_attempts = max(max_attempts, bucket["attempts"])
        cells.append({"date": day, "attempts": bucket["attempts"], "correct": bucket["correct"]})

    active_days = sum(1 for cell in cells if cell["attempts"] > 0)
    return {
        "cells": cells,
        "max_attempts": max_attempts,
        "active_days": active_days,
        "dated_attempt_count": dated_total,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
    }


def build_question_history(events: list[dict], limit: int = 40) -> list[dict]:
    """문항별 풀이 이력(회차·정오답 시퀀스)을 최근 시도 순으로 반환."""
    by_question: dict[str, dict] = {}
    for event in events:
        qid = str(event.get("question_id") or "")
        if not qid:
            continue
        key = f"{event.get('exam_id', '')}::{qid}"
        entry = by_question.setdefault(key, {
            "question_id": qid,
            "exam_id": event.get("exam_id", ""),
            "question_number": event.get("question_number"),
            "label_summary": attempt_label_path(event),
            "results": [],
            "last_answered_at": None,
        })
        entry["results"].append(bool(event.get("is_correct")))
        entry["last_answered_at"] = event.get("answered_at") or entry["last_answered_at"]

    rows = []
    for entry in by_question.values():
        results = entry["results"]
        attempts = len(results)
        correct = sum(1 for r in results if r)
        rows.append({
            "question_id": entry["question_id"],
            "exam_id": entry["exam_id"],
            "question_number": entry["question_number"],
            "label_summary": entry["label_summary"],
            "attempt_count": attempts,
            "correct_count": correct,
            "correct_rate_pct": round(correct / attempts * 100, 1) if attempts else 0,
            "results": results,
            "last_correct": results[-1] if results else None,
            "last_answered_at": entry["last_answered_at"],
        })
    rows.sort(key=lambda r: (r["last_answered_at"] or ""), reverse=True)
    return rows[:limit]


@app.get("/api/practice/analytics/student")
def student_practice_analytics(request: Request, user_id: str = "local_student") -> dict:
    user_id = _request_identity(request) or user_id
    events = iter_attempt_events(user_id=user_id)
    total = len(events)
    correct = sum(1 for event in events if event.get("is_correct"))
    return {
        "user_id": user_id,
        "summary": {
            "attempt_count": total,
            "correct_count": correct,
            "correct_rate_pct": round(correct / total * 100, 1) if total else 0,
            "avg_time_sec": round(
                sum(safe_int(event.get("time_ms"), 0) or 0 for event in events) / max(total, 1) / 1000,
                1,
            ),
        },
        "weakness": aggregate_student_weakness(events),
        "ontology_weakness": aggregate_student_ontology_weakness(events),
        "recent_attempts": [public_attempt_event(event) for event in events[-20:][::-1]],
        "heatmap": build_practice_heatmap(events),
        "question_history": build_question_history(events),
    }


def build_distractor_analysis(events: list[dict], *, min_attempts: int = 1, limit: int = 40) -> list[dict]:
    """문항별로 학생들이 고른 선지 분포를 집계 → 어느 오답에 몰리는지(막힘 지점) 반환.

    한 오답 선지에 응답이 몰릴수록 '특정 오개념'이 강함. concentration(최다 오답 비율)로 정렬.
    """
    from collections import defaultdict as _dd

    by_q: dict[str, dict] = {}
    for event in events:
        qid = str(event.get("question_id") or "")
        if not qid:
            continue
        key = f"{event.get('exam_id', '')}::{qid}"
        entry = by_q.get(key)
        if entry is None:
            entry = {
                "question_id": qid,
                "exam_id": event.get("exam_id", ""),
                "question_number": event.get("question_number"),
                "stem_preview": event.get("stem_preview", ""),
                "label_summary": attempt_label_path(event),
                "answer_keys": [str(k) for k in (event.get("answer_keys") or [])],
                "choice_texts": {},
                "choice_counts": _dd(int),
                "attempts": 0,
                "correct": 0,
                "time_ms_sum": 0,
            }
            by_q[key] = entry
        entry["attempts"] += 1
        if event.get("is_correct"):
            entry["correct"] += 1
        entry["time_ms_sum"] += safe_int(event.get("time_ms"), 0) or 0
        # 선지 텍스트는 가장 완전한 것으로 갱신
        texts = event.get("choice_texts") or {}
        if isinstance(texts, dict) and len(texts) > len(entry["choice_texts"]):
            entry["choice_texts"] = {str(k): str(v) for k, v in texts.items()}
        if not entry["answer_keys"] and event.get("answer_keys"):
            entry["answer_keys"] = [str(k) for k in event["answer_keys"]]
        for choice in (event.get("selected_choices") or []):
            entry["choice_counts"][str(choice)] += 1

    rows = []
    for entry in by_q.values():
        attempts = entry["attempts"]
        if attempts < min_attempts:
            continue
        answer_keys = set(entry["answer_keys"])
        choices = []
        top_wrong = None
        for choice_key, count in sorted(entry["choice_counts"].items(), key=lambda kv: kv[1], reverse=True):
            is_answer = choice_key in answer_keys
            pct = round(count / attempts * 100, 1) if attempts else 0
            row = {
                "choice": choice_key,
                "text": entry["choice_texts"].get(choice_key, ""),
                "count": count,
                "pct": pct,
                "is_answer": is_answer,
            }
            choices.append(row)
            if not is_answer and top_wrong is None:
                top_wrong = row
        rows.append({
            "question_id": entry["question_id"],
            "exam_id": entry["exam_id"],
            "question_number": entry["question_number"],
            "stem_preview": entry["stem_preview"],
            "label_summary": entry["label_summary"],
            "attempt_count": attempts,
            "correct_count": entry["correct"],
            "correct_rate_pct": round(entry["correct"] / attempts * 100, 1) if attempts else 0,
            "avg_time_sec": round(entry["time_ms_sum"] / attempts / 1000, 1) if attempts else 0,
            "choices": choices,
            "top_distractor": top_wrong,
            "distractor_concentration_pct": top_wrong["pct"] if top_wrong else 0,
        })
    # 신호 강도 = 오답 몰림 × 응답자 수(10명에서 포화). 1명 100%보다 8명 62%가 위로.
    for r in rows:
        weight = min(r["attempt_count"], 10) / 10
        r["signal_score"] = round(r["distractor_concentration_pct"] * weight, 1)
    rows.sort(key=lambda r: (r["signal_score"], 100 - r["correct_rate_pct"]), reverse=True)
    return rows[:limit]


@app.get("/api/practice/analytics/distractors")
def distractor_analysis(exam_id: str | None = None, min_attempts: int = 1) -> dict:
    events = iter_attempt_events(exam_id=exam_id)
    rows = build_distractor_analysis(events, min_attempts=max(1, min_attempts))
    return {
        "exam_id": exam_id,
        "min_attempts": max(1, min_attempts),
        "question_count": len(rows),
        "questions": rows,
    }


@app.post("/api/practice/weakness-targeting")
def weakness_targeting(payload: Annotated[dict | None, Body()] = None) -> dict:
    """모드 C — 코호트 약점(label_path) → 같은 라벨의 기출 부모 → 변형 생성 프롬프트 묶음.

    프라이버시: prompt-only(외부 전송 없음). 실제 생성은 승인된 제공자(Claude Code 계정)로.
    """
    from collections import defaultdict as _dd
    from scripts.generate_kichul_variants import build_prompt, VARIANT_TYPES

    payload = payload or {}
    user_id = payload.get("user_id")
    exam_id = payload.get("exam_id")
    max_areas = safe_int(payload.get("max_areas"), 3) or 3
    parents_per_area = safe_int(payload.get("parents_per_area"), 2) or 2
    n_each = safe_int(payload.get("n_each"), 1) or 1
    min_attempts = safe_int(payload.get("min_attempts"), 1) or 1
    max_correct_rate = float(payload.get("max_correct_rate", 80))
    types = [t for t in (payload.get("variant_types") or ["numeric", "distractor", "vignette"]) if t in VARIANT_TYPES]

    events = iter_attempt_events(exam_id=exam_id, user_id=user_id)
    weakness = aggregate_student_weakness(events)
    weak_areas = [
        row for row in weakness
        if row["attempt_count"] >= min_attempts and row["correct_rate_pct"] <= max_correct_rate
    ][:max_areas]

    # 라벨 뱅크를 label_path로 색인
    by_path: dict[str, list] = _dd(list)
    for ex_id, question in iter_all_labeled_questions():
        by_path[question_label_path(question)].append((ex_id, question))

    out_dir = COURSE_EXAM_ROOT / "variants" / "weakness"
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = []
    for area in weak_areas:
        parents = by_path.get(area["label_path"], [])
        # 폴백: topic 토큰 부분일치
        if not parents:
            tokens = [t.strip() for t in area["label_path"].split(">") if t.strip()]
            topic = tokens[2] if len(tokens) > 2 else (tokens[-1] if tokens else "")
            if topic:
                parents = [
                    (ex_id, q) for ex_id, q in iter_all_labeled_questions()
                    if topic and topic in question_label_path(q)
                ]
        packets = []
        for ex_id, question in parents[:parents_per_area]:
            prompt = build_prompt({"exam_title": ex_id}, question, types, n_each)
            slug = f"{question.get('question_id', 'q')}_weakness.prompt.txt"
            (out_dir / slug).write_text(prompt, encoding="utf-8")
            packets.append({
                "parent_question_id": question.get("question_id"),
                "exam_id": ex_id,
                "stem_preview": str(question.get("stem") or "")[:120],
                "variant_types": types,
                "n_each": n_each,
                "expected_variants": len(types) * n_each,
                "prompt_file": str(out_dir / slug),
            })
        plan.append({
            "label_path": area["label_path"],
            "correct_rate_pct": area["correct_rate_pct"],
            "attempt_count": area["attempt_count"],
            "parent_candidate_count": len(parents),
            "packets": packets,
        })

    return {
        "mode": "kichul_variant_weakness_targeting",
        "provider": "prompt-only",
        "user_id": user_id,
        "exam_id": exam_id,
        "weak_area_count": len(weak_areas),
        "total_packets": sum(len(p["packets"]) for p in plan),
        "total_expected_variants": sum(pk["expected_variants"] for p in plan for pk in p["packets"]),
        "plan": plan,
        "next": "각 packet 프롬프트를 승인된 제공자로 생성 → 검토 큐(needs_review=true) → 승인 → cbt_docx_export",
    }


@app.get("/api/practice/analytics/faculty")
def faculty_practice_analytics(exam_id: str | None = None) -> dict:
    events = iter_attempt_events(exam_id=exam_id)
    item_reports, summary = aggregate_faculty_items(events, exam_id)
    high_signal = [
        row
        for row in item_reports
        if row.get("attempt_count", 0) >= 1
        and row.get("top_wrong_choice")
        and row["top_wrong_choice"].get("selected_count", 0) > 0
    ]
    high_signal.sort(
        key=lambda row: (
            -(row["top_wrong_choice"]["selected_pct"] if row.get("top_wrong_choice") else 0),
            row.get("correct_rate_pct", 0),
        )
    )
    return {
        "exam_id": exam_id,
        "summary": summary,
        "attempt_count": len(events),
        "item_reports": item_reports,
        "high_signal_misconceptions": high_signal[:10],
    }


@app.get("/api/course-exams/previews/{filename}")
def course_exam_preview_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    preview_path = (COURSE_EXAM_PREVIEW_DIR / safe_name).resolve()
    preview_root = COURSE_EXAM_PREVIEW_DIR.resolve()
    if preview_root not in preview_path.parents or not preview_path.exists():
        raise HTTPException(status_code=404, detail="검수 미리보기를 찾을 수 없습니다.")
    return FileResponse(preview_path, media_type="text/html")


@app.get("/api/course-exams/media/{source_exam}/{filename}")
def course_exam_media_file(source_exam: str, filename: str) -> FileResponse:
    safe_source = Path(source_exam).name
    safe_name = Path(filename).name
    media_path = (COURSE_EXAM_MEDIA_DIR / safe_source / safe_name).resolve()
    media_root = COURSE_EXAM_MEDIA_DIR.resolve()
    if media_root not in media_path.parents or not media_path.exists():
        raise HTTPException(status_code=404, detail="시험지 제시자료를 찾을 수 없습니다.")
    return FileResponse(media_path)


@app.post("/api/course-exams/import")
async def import_course_exam(
    exam_file: Annotated[UploadFile, File(description="기출/과정시험 HWP 또는 PDF")],
    answer_key_file: Annotated[UploadFile | None, File(description="정답지 XLSX")] = None,
    subject: Annotated[str, Form()] = "",
    unit: Annotated[str, Form()] = "",
) -> dict:
    ensure_course_exam_dirs()
    content = await exam_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="시험지 파일이 비어 있습니다.")

    original_name = exam_file.filename or "course_exam"
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".hwp", ".pdf"}:
        raise HTTPException(status_code=400, detail="현재 HWP/PDF 시험지만 구조화할 수 있습니다.")

    safe_stem = course_exam_slugify(Path(original_name).stem)
    saved_path = COURSE_EXAM_UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_{safe_stem}{suffix}"
    saved_path.write_bytes(content)

    try:
        if suffix == ".pdf":
            record = extract_course_exam_pdf_file(saved_path, media_root=COURSE_EXAM_MEDIA_DIR)
        else:
            record = extract_course_exam_hwp_file(saved_path, media_root=COURSE_EXAM_MEDIA_DIR)
        if answer_key_file and answer_key_file.filename:
            key_content = await answer_key_file.read()
            if key_content:
                key_suffix = Path(answer_key_file.filename).suffix.lower()
                if key_suffix not in {".xlsx", ".xlsm"}:
                    raise HTTPException(status_code=400, detail="정답지는 XLSX 파일만 지원합니다.")
                key_stem = course_exam_slugify(Path(answer_key_file.filename).stem)
                key_path = COURSE_EXAM_UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_answer_key_{key_stem}{key_suffix}"
                key_path.write_bytes(key_content)
                record = apply_answer_key_to_record(record, parse_answer_key_xlsx(key_path))
        exam_meta = record.setdefault("exam", {})
        exam_meta["source_file"] = original_name
        if subject.strip():
            exam_meta["course_name"] = subject.strip()
        if unit.strip():
            exam_meta["round_label"] = unit.strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"시험지 구조화 실패: {exc}") from exc

    output_name = f"{course_exam_slugify(record['exam']['source_exam'])}.json"
    markdown_name = f"{course_exam_slugify(record['exam']['source_exam'])}.md"
    preview_name = f"{course_exam_slugify(record['exam']['source_exam'])}.html"
    output_path = COURSE_EXAM_EXTRACTED_DIR / output_name
    markdown_path = COURSE_EXAM_MARKDOWN_DIR / markdown_name
    preview_path = COURSE_EXAM_PREVIEW_DIR / preview_name

    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_course_exam_markdown(record), encoding="utf-8")
    preview_path.write_text(render_course_exam_preview(record, preview_path), encoding="utf-8")

    review_set = archive_course_exam_review_set(record)

    summary = course_exam_summary(record)
    summary["exam_id"] = output_path.stem
    return {
        "status": "imported",
        "exam_id": output_path.stem,
        "set_id": review_set.get("set_id"),
        "review_summary": review_set.get("summary") or {},
        "summary": summary,
        "paths": {
            "json": str(output_path),
            "markdown": str(markdown_path),
            "preview": str(preview_path),
        },
        "answer_key": record.get("answer_key"),
        "preview_url": f"/api/course-exams/previews/{preview_name}",
    }


@app.post("/api/media")
async def upload_media_asset(
    media_file: Annotated[UploadFile, File(description="환자 사진/영상/병리/검사 이미지")],
    asset_type: Annotated[str, Form()] = "clinical_photo",
    modality: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    unit: Annotated[str, Form()] = "",
    diagnosis: Annotated[str, Form()] = "",
    caption: Annotated[str, Form()] = "",
    key_findings: Annotated[str, Form()] = "",
    deidentified: Annotated[str, Form()] = "false",
    approved_for_question_use: Annotated[str, Form()] = "false",
    faculty_note: Annotated[str, Form()] = "",
) -> dict:
    content = await media_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="미디어 파일이 비어 있습니다.")
    asset = save_media_asset(
        content,
        media_file.filename or "media.png",
        asset_type=asset_type,
        modality=modality.strip(),
        subject=subject.strip(),
        unit=unit.strip(),
        diagnosis=diagnosis.strip(),
        caption=caption.strip(),
        key_findings=key_findings,
        deidentified=form_bool(deidentified),
        approved_for_question_use=form_bool(approved_for_question_use),
        faculty_note=faculty_note.strip(),
    )
    return {"asset": asset}


@app.get("/api/question-sets")
def question_sets(limit: int = 20) -> dict:
    return {"sets": list_question_sets(limit=limit)}


@app.get("/api/question-sets/{set_id}")
def question_set_detail(set_id: str) -> dict:
    try:
        return load_question_set(set_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/notebooklm/import")
def import_notebooklm(payload: Annotated[dict, Body()]) -> dict:
    try:
        return import_notebooklm_question_set(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/medlegal/cases")
def medlegal_cases(track: str | None = None) -> dict:
    return {"cases": list_medlegal_cases(track=track)}


@app.get("/api/medlegal/cases/{case_id}")
def medlegal_case_detail(case_id: str) -> dict:
    try:
        return load_medlegal_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="의료법/EMR 교육 케이스를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/medlegal/cases/{case_id}/submit")
def submit_medlegal_case_note(
    case_id: str,
    payload: Annotated[dict, Body()],
) -> dict:
    try:
        return submit_medlegal_note(
            case_id,
            str(payload.get("note_text") or ""),
            learner_role=str(payload.get("learner_role") or "student"),
            note_type=str(payload.get("note_type") or ""),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="의료법/EMR 교육 케이스를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/medlegal/submissions/{submission_id}")
def medlegal_submission_detail(submission_id: str) -> dict:
    try:
        return load_medlegal_submission(submission_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="제출 기록을 찾을 수 없습니다.") from None


@app.post("/api/question-sets/{set_id}/export/anki")
def export_question_set_anki(
    set_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return build_anki_export(
            set_id,
            deck_name=str(payload.get("deck_name") or "").strip() or None,
            include_unapproved=form_bool(payload.get("include_unapproved")),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anki export 생성 실패: {exc}") from exc


@app.post("/api/question-sets/{set_id}/export/cbt-hwp")
def export_question_set_cbt_hwp(
    set_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return build_cbt_hwp_export(
            set_id,
            include_unapproved=form_bool(payload.get("include_unapproved")),
            include_answers=payload.get("include_answers", True) is not False,
            include_explanations=payload.get("include_explanations", True) is not False,
            include_references=payload.get("include_references", True) is not False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CBT HWP 양식 생성 실패: {exc}") from exc


@app.post("/api/question-sets/{set_id}/export/cbt-docx")
def export_question_set_cbt_docx(
    set_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    """의학교육실 과정시험 HWP 양식(.docx). 한글에서 열어 .hwp로 저장·제출."""
    payload = payload or {}
    try:
        return build_studio_cbt_docx_export(
            set_id,
            include_unapproved=form_bool(payload.get("include_unapproved")),
            include_explanation=payload.get("include_explanations", True) is not False,
            group_by=str(payload.get("group_by") or "course_name"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"의학교육실 HWP(.docx) 양식 생성 실패: {exc}") from exc


@app.get("/api/exports/{filename}")
def export_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    export_path = (EXPORT_SET_DIR / safe_name).resolve()
    export_root = EXPORT_SET_DIR.resolve()
    if export_root not in export_path.parents or not export_path.exists():
        raise HTTPException(status_code=404, detail="내보내기 파일을 찾을 수 없습니다.")
    return FileResponse(export_path, filename=safe_name, media_type="application/octet-stream")


@app.get("/api/anki-exports/{filename}")
def anki_export_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    export_path = (ANKI_EXPORT_DIR / safe_name).resolve()
    export_root = ANKI_EXPORT_DIR.resolve()
    if export_root not in export_path.parents or not export_path.exists():
        raise HTTPException(status_code=404, detail="Anki 내보내기 파일을 찾을 수 없습니다.")
    return FileResponse(export_path, filename=safe_name, media_type="application/octet-stream")


@app.patch("/api/question-sets/{set_id}/questions/{question_id}")
def update_question_detail(
    set_id: str,
    question_id: str,
    payload: Annotated[dict, Body()],
) -> dict:
    try:
        updates = payload.get("updates", payload)
        comment = str(payload.get("comment") or "")
        actor_id = str(payload.get("actor_id") or "local_faculty")
        return update_question_review(
            set_id,
            question_id,
            updates,
            action="edited",
            actor_id=actor_id,
            comment=comment,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/question-sets/{set_id}/questions/{question_id}/approve")
def approve_question(
    set_id: str,
    question_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return update_question_review(
            set_id,
            question_id,
            payload.get("updates", {}),
            action="approved",
            actor_id=str(payload.get("actor_id") or "local_faculty"),
            comment=str(payload.get("comment") or "교수 검수 승인"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.") from None


@app.post("/api/question-sets/{set_id}/questions/{question_id}/reject")
def reject_question(
    set_id: str,
    question_id: str,
    payload: Annotated[dict | None, Body()] = None,
) -> dict:
    payload = payload or {}
    try:
        return update_question_review(
            set_id,
            question_id,
            payload.get("updates", {}),
            action="rejected",
            actor_id=str(payload.get("actor_id") or "local_faculty"),
            comment=str(payload.get("comment") or "교수 검수 반려"),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="문항 세트를 찾을 수 없습니다.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.") from None


@app.post("/api/generate-from-topic")
def generate_questions_from_topic(payload: Annotated[dict, Body()]) -> dict:
    """강의파일 없이 '주제 + 교수 강조점'만으로 문항 생성.

    교재(Harrison 등) 원문은 프롬프트에 넣지 않는다(저작권 경계). 교수가 적어준 주제·강조점
    텍스트만 근거로 쓰고, 교재 참고는 학생 열람용 표기로만 남긴다.
    """
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="출제 주제를 입력하세요.")
    teaching_points = str(payload.get("teaching_points") or "").strip()
    set_name = str(payload.get("set_name") or "").strip()
    textbook_reference = str(payload.get("textbook_reference") or "").strip()
    subject = str(payload.get("subject") or "General").strip() or "General"
    unit = str(payload.get("unit") or topic).strip() or topic
    num_questions = safe_int(payload.get("num_questions"), 5) or 5
    num_questions = max(1, min(30, num_questions))
    difficulty = str(payload.get("difficulty") or "보통").strip() or "보통"
    question_type = str(payload.get("question_type") or "clinical_case").strip() or "clinical_case"
    item_type = str(payload.get("item_type") or "A").strip() or "A"
    reveal_specialty = form_bool(payload.get("reveal_specialty", False))
    reasoning_hops = max(1, min(3, safe_int(payload.get("reasoning_hops"), 2) or 2))
    provider = str(payload.get("provider") or "auto").strip() or "auto"
    model = str(payload.get("model") or "auto").strip() or "auto"
    ontology_review_policy = str(payload.get("ontology_review_policy") or "faculty_draft").strip() or "faculty_draft"
    target_axis_type = str(payload.get("target_axis_type") or "").strip()
    target_axis_ids = normalized_metadata_values(payload.get("target_axis_ids"))
    supporting_axis_types = normalized_metadata_values(payload.get("supporting_axis_types"))
    option_domain = str(payload.get("option_domain") or "").strip()
    generation_profile = str(payload.get("generation_profile") or "standard").strip().lower()
    if generation_profile not in {"standard", "fast"}:
        generation_profile = "standard"

    # 교수 입력만으로 가상 강의노트 텍스트를 만든다(교재 원문 미포함).
    lines = [f"# 출제 주제: {topic}", f"과목: {subject} / 단원: {unit}", ""]
    if teaching_points:
        lines += ["## 교수 강조점 / 출제 의도", teaching_points, ""]
    if textbook_reference:
        lines += [
            "## 참고 교재 (학생 열람용 — 원문은 문항에 복사하지 말 것)",
            textbook_reference,
            "",
        ]
    lines += [
        "위 주제와 강조점을 바탕으로 KMLE/국시형 5지선다 문항을 새로 작성한다.",
        "교재 원문을 그대로 옮기지 말고, 개념을 재구성해 임상 추론형 문항으로 만든다.",
    ]
    synthetic_text = "\n".join(lines)

    try:
        lecture = save_upload_bytes(
            synthetic_text.encode("utf-8"),
            filename=f"topic_{course_exam_slugify(topic) or 'seed'}.txt",
            kind="lecture",
        )
        result = generate_studio_questions(
            lecture,
            set_name=set_name,
            subject=subject,
            unit=unit,
            num_questions=num_questions,
            difficulty=difficulty,
            question_type=question_type,
            item_type=item_type,
            reveal_specialty=reveal_specialty,
            reasoning_hops=reasoning_hops,
            grounding_topic=topic,
            grounding_concept_id=str(payload.get("disease_concept_id") or "").strip(),
            ontology_review_policy=ontology_review_policy,
            target_axis_type=target_axis_type,
            target_axis_ids=target_axis_ids,
            supporting_axis_types=supporting_axis_types or None,
            option_domain=option_domain,
            generation_profile=generation_profile,
            reference_policy="local_open",
            provider=provider,
            model=model,
        )
        if textbook_reference:
            result["textbook_reference"] = textbook_reference
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print("[studio.generate_topic.error]", datetime.now().isoformat(timespec="seconds"), repr(exc), flush=True)
        raise HTTPException(status_code=500, detail=f"주제 기반 생성 실패: {exc}") from exc


def normalized_generation_job_request(payload: dict) -> dict:
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="출제 주제를 입력하세요.")
    num_questions = max(1, min(30, safe_int(payload.get("num_questions"), 1) or 1))
    return {
        "topic": topic,
        "set_name": str(payload.get("set_name") or "새 Ontology 문항 세트").strip()
        or "새 Ontology 문항 세트",
        "teaching_points": str(payload.get("teaching_points") or "").strip(),
        "textbook_reference": str(payload.get("textbook_reference") or "").strip(),
        "subject": str(payload.get("subject") or "General").strip() or "General",
        "unit": str(payload.get("unit") or topic).strip() or topic,
        "num_questions": num_questions,
        "difficulty": str(payload.get("difficulty") or "보통").strip() or "보통",
        "question_type": str(payload.get("question_type") or "clinical_case").strip()
        or "clinical_case",
        "item_type": str(payload.get("item_type") or "A").strip() or "A",
        "reveal_specialty": form_bool(payload.get("reveal_specialty", False)),
        "reasoning_hops": max(1, min(3, safe_int(payload.get("reasoning_hops"), 2) or 2)),
        "provider": str(payload.get("provider") or "auto").strip() or "auto",
        "model": str(payload.get("model") or "auto").strip() or "auto",
        "ontology_review_policy": str(
            payload.get("ontology_review_policy") or "faculty_draft"
        ).strip()
        or "faculty_draft",
        "disease_concept_id": str(payload.get("disease_concept_id") or "").strip(),
        "target_axis_type": str(payload.get("target_axis_type") or "").strip(),
        "target_axis_ids": normalized_metadata_values(payload.get("target_axis_ids")),
        "supporting_axis_types": normalized_metadata_values(payload.get("supporting_axis_types")),
        "option_domain": str(payload.get("option_domain") or "").strip(),
        "selected_media_ids": normalized_metadata_values(payload.get("selected_media_ids")),
        "faculty_question_intent": payload.get("faculty_question_intent")
        if isinstance(payload.get("faculty_question_intent"), dict)
        else {},
    }


def normalized_faculty_intent_generation_request(payload: dict) -> dict:
    selected = payload.get("selected_intents")
    if not isinstance(selected, list) or len(selected) not in {2, 3}:
        raise HTTPException(status_code=400, detail="출제 의도 후보를 2개 또는 3개 선택하세요.")

    item_intents: list[dict] = []
    seen_intent_ids: set[str] = set()
    for index, raw_item in enumerate(selected, start=1):
        if not isinstance(raw_item, dict):
            raise HTTPException(status_code=400, detail=f"{index}번 출제 의도 형식이 올바르지 않습니다.")
        selection = raw_item.get("selection_contract")
        selection = selection if isinstance(selection, dict) and selection else raw_item
        target = raw_item.get("target") if isinstance(raw_item.get("target"), dict) else selection.get("target")
        claim = (
            raw_item.get("assessment_claim")
            if isinstance(raw_item.get("assessment_claim"), dict)
            else selection.get("assessment_claim")
        )
        task_model = (
            raw_item.get("task_model")
            if isinstance(raw_item.get("task_model"), dict)
            else selection.get("task_model")
        )
        target = target if isinstance(target, dict) else {}
        claim = claim if isinstance(claim, dict) else {}
        task_model = task_model if isinstance(task_model, dict) else {}
        evidence_contract = (
            raw_item.get("evidence_contract")
            if isinstance(raw_item.get("evidence_contract"), dict)
            else selection.get("evidence_contract")
        )
        evidence_contract = evidence_contract if isinstance(evidence_contract, dict) else {}

        intent_id = str(raw_item.get("intent_id") or "").strip()
        concept_id = str(target.get("concept_id") or target.get("id") or "").strip()
        label = str(target.get("label") or concept_id.replace("_", " ")).strip()
        task = str(claim.get("task") or "").strip()
        faculty_claim = str(claim.get("faculty_claim") or "").strip()
        target_axis_type = str(raw_item.get("target_axis_type") or target_axis_for_task(task)).strip()
        if not intent_id or not concept_id or not label or not task or not target_axis_type:
            raise HTTPException(
                status_code=400,
                detail=f"{index}번 출제 의도에 intent_id, 대상 개념, 평가 과업 또는 Ontology 축이 없습니다.",
            )
        if intent_id in seen_intent_ids:
            raise HTTPException(status_code=400, detail="같은 출제 의도를 중복 선택할 수 없습니다.")
        seen_intent_ids.add(intent_id)

        normalized_intent = {
            "intent_id": intent_id,
            "intent_title": str(raw_item.get("title") or f"{label} · {claim.get('task_label') or task}").strip(),
            "topic": label,
            "unit": label,
            "teaching_points": faculty_claim,
            "disease_concept_id": concept_id,
            "target_axis_type": target_axis_type,
            "question_type": str(task_model.get("format") or "clinical_case").strip() or "clinical_case",
            "reasoning_hops": max(1, min(3, safe_int(task_model.get("reasoning_hops"), 2) or 2)),
            "selected_media_ids": normalized_metadata_values(evidence_contract.get("selected_media_ids")),
            "faculty_question_intent": selection,
        }
        item_intents.append(normalized_intent)

    department = payload.get("department")
    if isinstance(department, dict):
        department_label = str(department.get("label") or department.get("id") or "").strip()
    else:
        department_label = str(department or payload.get("department_id") or "").strip()
    return {
        "topic": f"{department_label or '임상의학'} 교수 선택 출제 의도 {len(item_intents)}개",
        "set_name": str(payload.get("set_name") or f"{department_label or '임상의학'} 임종평 문항 세트").strip(),
        "subject": department_label or "임상의학종합평가",
        "unit": "임상의학종합평가",
        "num_questions": len(item_intents),
        "difficulty": str(payload.get("difficulty") or "국가고시형").strip() or "국가고시형",
        "question_type": "clinical_case",
        "item_type": "A",
        "reveal_specialty": False,
        "reasoning_hops": 2,
        "provider": str(payload.get("provider") or "auto").strip() or "auto",
        "model": str(payload.get("model") or "auto").strip() or "auto",
        "ontology_review_policy": "faculty_draft",
        "reference_policy": "local_open",
        "item_intents": item_intents,
        "faculty_assignment": {
            "faculty_id": str(payload.get("faculty_id") or "local_faculty").strip() or "local_faculty",
            "department": department_label or None,
            "assigned_item_count": len(item_intents),
            "exam_profile": "clinical_comprehensive",
        },
    }


@app.post("/api/generation-jobs")
def create_studio_generation_job(payload: Annotated[dict, Body()]) -> dict:
    """다문항을 한 문항씩 안전하게 생성하는 지속형 작업을 시작한다."""
    request = normalized_generation_job_request(payload)
    job, duplicate = create_generation_job(request)
    return {"job": job, "duplicate": duplicate}


@app.post("/api/faculty/item-intents/generation-jobs")
def create_faculty_item_intent_generation_job(payload: Annotated[dict, Body()]) -> dict:
    """Create one review set from 2-3 distinct faculty-selected item intents."""

    request = normalized_faculty_intent_generation_request(payload)
    job, duplicate = create_generation_job(request)
    return {
        "job": job,
        "duplicate": duplicate,
        "review_contract": {
            "needs_review": True,
            "gen_ready": False,
            "student_auto_release": False,
        },
    }


@app.get("/api/generation-jobs/{job_id}")
def read_studio_generation_job(job_id: str) -> dict:
    try:
        return get_generation_job(job_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.") from None


@app.post("/api/generation-jobs/{job_id}/retry")
def retry_studio_generation_job(job_id: str) -> dict:
    try:
        return retry_failed_generation_job(job_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.") from None


@app.post("/api/generation-jobs/{job_id}/cancel")
def cancel_studio_generation_job(job_id: str) -> dict:
    try:
        return cancel_generation_job(job_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.") from None


@app.post("/api/generation-jobs/{job_id}/resume")
def resume_studio_generation_job(job_id: str) -> dict:
    try:
        return resume_generation_job(job_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.") from None


@app.post("/api/generate")
async def generate_questions(
    lecture_file: Annotated[UploadFile | None, File(description="강의자료 PDF/DOCX/PPTX/HWP/TXT/MD")] = None,
    topic: Annotated[str, Form()] = "",
    set_name: Annotated[str, Form()] = "",
    disease_concept_id: Annotated[str, Form()] = "",
    ontology_review_policy: Annotated[str, Form()] = "faculty_draft",
    target_axis_type: Annotated[str, Form()] = "",
    target_axis_ids: Annotated[str, Form()] = "",
    supporting_axis_types: Annotated[str, Form()] = "",
    option_domain: Annotated[str, Form()] = "",
    style_files: Annotated[list[UploadFile] | None, File(description="기출문항 유형 참고 자료")] = None,
    evidence_files: Annotated[list[UploadFile] | None, File(description="승인 근거자료")] = None,
    image_files: Annotated[list[UploadFile] | None, File(description="사진/영상/검사 이미지 자료")] = None,
    subject: Annotated[str, Form()] = "General",
    unit: Annotated[str, Form()] = "미분류",
    num_questions: Annotated[int, Form(ge=1, le=30)] = 5,
    difficulty: Annotated[str, Form()] = "보통",
    question_type: Annotated[str, Form()] = "clinical_case",
    item_type: Annotated[str, Form()] = "A",
    reveal_specialty: Annotated[str, Form()] = "false",
    reasoning_hops: Annotated[int, Form(ge=1, le=3)] = 2,
    generation_profile: Annotated[str, Form()] = "standard",
    reference_policy: Annotated[str, Form()] = "local_open",
    image_policy: Annotated[str, Form()] = "none",
    selected_media_ids: Annotated[str, Form()] = "",
    image_description: Annotated[str, Form()] = "",
    include_tables: Annotated[str, Form()] = "false",
    provider: Annotated[str, Form()] = "auto",
    model: Annotated[str, Form()] = "auto",
) -> dict:
    try:
        started_at = datetime.now().isoformat(timespec="seconds")
        print(
            "[studio.generate.start]",
            started_at,
            {
                "lecture": lecture_file.filename if (lecture_file and lecture_file.filename) else f"topic:{topic.strip()[:40]}",
                "style_count": len([f for f in (style_files or []) if f and f.filename]),
                "evidence_count": len([f for f in (evidence_files or []) if f and f.filename]),
                "image_count": len([f for f in (image_files or []) if f and f.filename]),
                "provider": provider,
                "model": model,
                "question_type": question_type,
                "item_type": item_type,
                "reveal_specialty": form_bool(reveal_specialty),
                "reasoning_hops": reasoning_hops,
                "generation_profile": generation_profile,
                "reference_policy": reference_policy,
                "image_policy": image_policy,
                "selected_media_ids": split_metadata_values(selected_media_ids),
                "has_image_description": bool(image_description.strip()),
                "include_tables": form_bool(include_tables),
                "disease_concept_id": disease_concept_id.strip() or None,
                "ontology_review_policy": ontology_review_policy.strip() or "faculty_draft",
                "target_axis_type": target_axis_type.strip() or None,
                "target_axis_ids": split_metadata_values(target_axis_ids),
            },
            flush=True,
        )
        has_lecture = bool(lecture_file and lecture_file.filename)
        topic_seed = topic.strip()
        if has_lecture:
            lecture = await save_upload_file(lecture_file, kind="lecture")
        elif topic_seed:
            # 강의파일 없이 주제만으로 생성(간단 생성 모드). 교재 원문은 넣지 않고 주제 텍스트만 근거로 사용.
            synthetic_lecture = "\n".join(
                [
                    f"# 출제 주제: {topic_seed}",
                    f"과목: {subject.strip() or 'General'} / 단원: {unit.strip() or topic_seed}",
                    "",
                    "위 주제를 바탕으로 KMLE/국시형 5지선다 문항을 새로 작성한다.",
                    "교재 원문을 그대로 옮기지 말고 개념을 재구성해 임상 추론형 문항으로 만든다.",
                ]
            )
            lecture = save_upload_bytes(
                synthetic_lecture.encode("utf-8"),
                filename=f"topic_{course_exam_slugify(topic_seed) or 'seed'}.txt",
                kind="lecture",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="강의자료 파일 또는 출제 주제 중 하나는 입력해야 합니다.",
            )
        style_uploads = [
            await save_upload_file(upload, kind="style")
            for upload in (style_files or [])
            if upload and upload.filename
        ]
        evidence_uploads = [
            await save_upload_file(upload, kind="evidence")
            for upload in (evidence_files or [])
            if upload and upload.filename
        ]
        image_uploads = [
            await save_upload_file(upload, kind="image")
            for upload in (image_files or [])
            if upload and upload.filename
        ]

        result = generate_studio_questions(
            lecture,
            set_name=set_name.strip(),
            subject=subject.strip() or "General",
            unit=unit.strip() or "미분류",
            num_questions=num_questions,
            difficulty=difficulty.strip() or "보통",
            question_type=question_type,
            item_type=item_type.strip() or "A",
            reveal_specialty=form_bool(reveal_specialty),
            reasoning_hops=reasoning_hops,
            grounding_topic=topic_seed or unit.strip() or subject.strip(),
            grounding_concept_id=disease_concept_id.strip(),
            ontology_review_policy=ontology_review_policy.strip() or "faculty_draft",
            target_axis_type=target_axis_type.strip(),
            target_axis_ids=split_metadata_values(target_axis_ids),
            supporting_axis_types=split_metadata_values(supporting_axis_types) or None,
            option_domain=option_domain.strip(),
            generation_profile=generation_profile.strip().lower() or "standard",
            reference_policy=reference_policy,
            image_policy=image_policy,
            selected_media_ids=split_metadata_values(selected_media_ids),
            image_description=image_description.strip(),
            include_tables=form_bool(include_tables),
            provider=provider,
            model=model,
            style_uploads=style_uploads,
            evidence_uploads=evidence_uploads,
            image_uploads=image_uploads,
        )
        print(
            "[studio.generate.done]",
            datetime.now().isoformat(timespec="seconds"),
            {
                "status": result.get("status"),
                "question_count": result.get("question_count"),
                "output": result.get("paths", {}).get("output"),
            },
            flush=True,
        )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print("[studio.generate.error]", datetime.now().isoformat(timespec="seconds"), repr(exc), flush=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/")
@app.get("/index.html")
def index(request: Request) -> RedirectResponse:
    destination = "/faculty-studio-v2/" if request.cookies.get(_ROLE_COOKIE) == "faculty" else "/student/"
    return RedirectResponse(url=destination, status_code=307)


@app.get("/cpx-osce")
@app.get("/cpx-osce/")
def cpx_osce_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "cpx-osce" / "index.html")


@app.get("/faculty-studio-v2")
@app.get("/faculty-studio-v2/")
def faculty_studio_v2_index() -> FileResponse:
    """Serve the Ontology authoring workspace while preserving the V2 implementation."""

    return FileResponse(
        FRONTEND_DIR / "faculty-studio-v3" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/faculty-studio-v3")
@app.get("/faculty-studio-v3/")
@app.get("/faculty-studio-v3/index.html")
def faculty_studio_v3_index() -> RedirectResponse:
    return RedirectResponse(url="/faculty-studio-v2/", status_code=307)


@app.get("/faculty-studio-v2/legacy")
@app.get("/faculty-studio-v2/index.html")
def faculty_studio_v2_legacy() -> RedirectResponse:
    return RedirectResponse(url="/faculty-studio-v2/", status_code=307)


@app.get("/student")
@app.get("/student/")
def student_v3_index() -> FileResponse:
    """Keep the previous student files intact while making V3 the default student shell."""

    return FileResponse(
        FRONTEND_DIR / "student-v3" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/student/reader.html")
def student_v3_reader() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "student-v3" / "reader.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/student/index.html")
def student_legacy_index() -> RedirectResponse:
    return RedirectResponse(url="/student/", status_code=307)


@app.get("/student-v2")
@app.get("/student-v2/")
@app.get("/student-v2/{legacy_path:path}")
def student_v2_legacy(legacy_path: str = "") -> RedirectResponse:
    destination = "/student/#report" if legacy_path == "result.html" else "/student/"
    return RedirectResponse(url=destination, status_code=307)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
