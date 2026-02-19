import sys
import traceback
from datetime import datetime
from pathlib import Path
from streamlit.web import cli as stcli


def resolve_app_path(file_path=None, executable_path=None, meipass_path=None, cwd_path=None, frozen=None):
    file_path = Path(file_path) if file_path is not None else Path(__file__)
    executable_path = Path(executable_path) if executable_path is not None else Path(sys.executable)
    cwd_path = Path(cwd_path) if cwd_path is not None else Path.cwd()
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if meipass_path is None:
        meipass_path = getattr(sys, "_MEIPASS", None)
    meipass_path = Path(meipass_path) if meipass_path else None

    candidates = [file_path.with_name("app.py")]
    if frozen:
        exe_dir = executable_path.parent
        candidates.extend(
            [
                exe_dir / "_internal" / "app.py",
                exe_dir / "app.py",
            ]
        )
        if meipass_path:
            candidates.append(meipass_path / "app.py")
    candidates.append(cwd_path / "app.py")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    checked = "\n".join(str(path) for path in candidates)
    raise FileNotFoundError(f"app.py not found. Checked:\n{checked}")


def write_error_log(detail):
    try:
        log_dir = Path.home() / "MedTutor"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "launcher_error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}]\n{detail}\n\n")
        return log_path
    except Exception:
        return None


def main():
    try:
        app_path = resolve_app_path()
        sys.argv = ["streamlit", "run", str(app_path), "--server.fileWatcherType=none"]
        sys.exit(stcli.main())
    except Exception as exc:
        detail = traceback.format_exc()
        log_path = write_error_log(detail)
        message = f"MedTutor launch failed: {exc}"
        if log_path is not None:
            message += f" (log: {log_path})"
        print(message, file=sys.stderr)
        print(detail, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
