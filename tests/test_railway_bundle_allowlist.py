"""배포 allow-list 정합성 — build_railway_bundle.DATA_PATHS ⊆ .dockerignore 재포함 목록.

2026-09-05 감사에서 발견: 번들에는 실렸지만 .dockerignore가 professor_items/ 전체를 빌드 컨텍스트에서 제거해
Railway 볼륨에 AI 생성 세트·검토 집계가 영원히 시딩되지 않았다(교수 콘솔 큐 0건·학생 배지 None).
Docker의 .dockerignore 평가(moby/patternmatcher MatchesOrParentMatches)를 그대로 흉내 내어
allow-list의 모든 경로가 살아남는지, 금지 파일은 계속 제외되는지 검사한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERIGNORE = ROOT / ".dockerignore"


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.strip().rstrip("/")
    out = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
                out += "(?:/)?"
            continue
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch == "\\" and i + 1 < len(pattern):
            out += re.escape(pattern[i + 1])
            i += 1
        else:
            out += re.escape(ch)
        i += 1
    return re.compile("^" + out + "$")


def load_patterns(text: str) -> list[tuple[bool, re.Pattern[str]]]:
    rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        exclusion = line.startswith("!")
        if exclusion:
            line = line[1:]
        rules.append((exclusion, _pattern_to_regex(line)))
    return rules


def is_ignored(path: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """moby/patternmatcher.MatchesOrParentMatches 와 같은 규칙: 순서대로 평가, 부모 디렉터리 매치 포함."""
    parts = path.split("/")
    parents = ["/".join(parts[: i + 1]) for i in range(len(parts) - 1)]
    matched = False
    for exclusion, regex in rules:
        if exclusion != matched:
            # 이미 제외된 상태에서 제외 패턴, 포함 상태에서 예외 패턴은 건너뛴다(moby 구현과 동일)
            continue
        hit = bool(regex.match(path)) or any(regex.match(parent) for parent in parents)
        if hit:
            matched = not exclusion
    return matched


def _bundle_data_paths() -> list[str]:
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_railway_bundle", ROOT / "scripts" / "build_railway_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return list(module.DATA_PATHS)


def test_dockerignore_keeps_every_bundle_data_path():
    rules = load_patterns(DOCKERIGNORE.read_text(encoding="utf-8"))
    leaked = []
    for relative in _bundle_data_paths():
        if relative.endswith((".json", ".csv", ".jsonl", ".md", ".txt", ".png", ".jpg")):
            if is_ignored(f"data_private/{relative}", rules):
                leaked.append(relative)
            continue
        # 디렉터리 항목: 대표 자식(직계 md/json, 하위 이미지) 중 하나라도 살아남아야 한다
        # (markdown/ 처럼 확장자 한 종류만 싣는 디렉터리가 있으므로 '전부'가 아니라 '하나 이상')
        candidates = [f"data_private/{relative}/sample.md", f"data_private/{relative}/sample.json", f"data_private/{relative}/sub/sample.png"]
        if all(is_ignored(candidate, rules) for candidate in candidates):
            leaked.append(relative)
    assert not leaked, f".dockerignore 가 번들 allow-list 경로를 제외한다: {leaked}"


def test_dockerignore_still_excludes_private_and_original_files():
    rules = load_patterns(DOCKERIGNORE.read_text(encoding="utf-8"))
    must_be_ignored = [
        "data_private/professor_items/review/roster_credentials.csv",
        "data_private/professor_items/review/roster.txt",
        "data_private/professor_items/review/faculty_edits.jsonl",
        "data_private/professor_items/review/v2_batches/batch_01.json",
        "data_private/professor_items/generated/_backup_pre_v2_20260905/set_1.json",
        "data_private/professor_items/generated/set_1.security_report.json",
        "data_private/professor_items/originals/1cha.pdf",
        "data_private/professor_items/originals_text/1cha.txt",
        "data_private/professor_items/originals_text_pma/2023.txt",
        "data_private/professor_items/seeds/seed.csv",
        "data_private/student/signup_requests.json",
        "data_private/student/approved_accounts.json",
        "data_private/course_exams/analytics/attempts.jsonl",
        "data_private/textbook_grounding/harrison/harrison.pdf",
    ]
    exposed = [path for path in must_be_ignored if not is_ignored(path, rules)]
    assert not exposed, f"빌드 컨텍스트에 실리면 안 되는 파일이 재포함된다: {exposed}"


def test_dockerignore_emulator_matches_known_conventions():
    rules = load_patterns("data_private/*\n!data_private/student/\ndata_private/student/*\n!data_private/student/qbank.json\n")
    assert not is_ignored("data_private/student/qbank.json", rules)
    assert is_ignored("data_private/student/other.json", rules)
    assert is_ignored("data_private/elsewhere/x.json", rules)
    assert not is_ignored("api_server.py", rules)


def test_local_only_textbooks_never_enter_the_bundle():
    """과별 교과서 쪽 텍스트는 로컬 전용(manifest policy) — 번들 allow-list·.dockerignore 어디에도 들어가면 안 된다."""
    assert not [p for p in _bundle_data_paths() if "textbooks" in p.split("/")[0]]
    assert "data_private/textbooks" not in (ROOT / "scripts" / "build_railway_bundle.py").read_text(encoding="utf-8")
    rules = load_patterns(DOCKERIGNORE.read_text(encoding="utf-8"))
    for path in ("data_private/textbooks/nelson_21e/pages.jsonl", "data_private/textbooks/sabiston_21e/manifest.json", "data_private/textbooks/x/sub/y.json"):
        assert is_ignored(path, rules), path
