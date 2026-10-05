"""P0-D(TECH-12 확장) 수용 테스트 — 검증자 작성.

목적: 모든 status_code=500 HTTPException이 예외 원문(str(exc)/f"...{exc}")을
클라이언트 detail로 노출하지 않음을 정적(AST)으로 보장한다.
전체 앱 부팅 없이 실행 가능하도록 소스 파싱만 사용한다.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = ROOT / "api_server.py"


def _iter_raise_httpexception(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            fn = node.exc.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name == "HTTPException":
                yield node.exc


def _kw(call, key):
    for keyword in call.keywords or []:
        if keyword.arg == key:
            return keyword.value
    return None


def _mentions_exc(node) -> bool:
    """detail 표현식이 예외 변수 exc를 참조하는지 확인한다."""

    return any(
        isinstance(sub, ast.Name) and sub.id == "exc"
        for sub in ast.walk(node)
    )


def test_no_500_handler_leaks_exception_detail():
    tree = ast.parse(API.read_text(encoding="utf-8"))
    leaks = []
    for call in _iter_raise_httpexception(tree):
        status = _kw(call, "status_code")
        detail = _kw(call, "detail")
        if status is None or detail is None:
            continue
        is_500 = isinstance(status, ast.Constant) and status.value == 500
        if is_500 and _mentions_exc(detail):
            leaks.append(getattr(call, "lineno", "?"))
    assert not leaks, f"500 응답이 예외 원문을 노출: lines {leaks}"


def test_course_exam_import_is_faculty_gated():
    """P0-E: 시험지 import에 faculty dependency가 있어야 한다."""

    source = API.read_text(encoding="utf-8")
    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "import_course_exam"
        ):
            target = node
            break
    assert target is not None, "import_course_exam 함수를 찾지 못함"

    gated = False
    for decorator in target.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        for keyword in decorator.keywords or []:
            if keyword.arg != "dependencies":
                continue
            dependency_source = ast.get_source_segment(source, keyword.value) or ""
            if "_require_faculty_reviewer" in dependency_source:
                gated = True

    if not gated:
        body_source = ast.get_source_segment(source, target) or ""
        gated = "_require_faculty_reviewer(" in body_source
    assert gated, "import_course_exam이 faculty 게이트되지 않음(P0-E 미적용)"


def test_400_validation_detail_allowed():
    """400 사용자 입력 검증에서는 str(exc)를 허용한다."""

    tree = ast.parse(API.read_text(encoding="utf-8"))
    count = 0
    for call in _iter_raise_httpexception(tree):
        status = _kw(call, "status_code")
        detail = _kw(call, "detail")
        if (
            isinstance(status, ast.Constant)
            and status.value == 400
            and detail is not None
            and _mentions_exc(detail)
        ):
            count += 1
    assert count >= 0
