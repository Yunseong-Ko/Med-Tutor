import json
from copy import deepcopy
from pathlib import Path


def _clone_default(default):
    try:
        return deepcopy(default)
    except Exception:
        return default


def load_json_file(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return _clone_default(default)
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _clone_default(default)

    if isinstance(default, dict) and not isinstance(data, dict):
        return _clone_default(default)
    if isinstance(default, list) and not isinstance(data, list):
        return _clone_default(default)
    return data


def save_json_file(path, data):
    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
