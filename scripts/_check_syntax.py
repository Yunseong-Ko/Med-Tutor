"""Run syntax checks on key pipeline files and exit non-zero on failure."""
import ast
import pathlib
import sys

FILES = [
    "src/services/rag_library.py",
    "src/services/choice_explanations.py",
    "scripts/enrich_course_exam_choice_explanations.py",
    "scripts/build_neuro_rag_index.py",
]

ok = True
for f in FILES:
    try:
        ast.parse(pathlib.Path(f).read_text(encoding="utf-8"))
        print(f"  OK  {f}")
    except SyntaxError as exc:
        print(f"  FAIL {f}: {exc}", file=sys.stderr)
        ok = False

sys.exit(0 if ok else 1)
