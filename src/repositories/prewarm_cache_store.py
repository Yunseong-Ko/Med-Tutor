from .json_store import load_json_file, save_json_file


def load_prewarm_cache_file(path):
    data = load_json_file(path, {})
    return data if isinstance(data, dict) else {}


def save_prewarm_cache_file(path, data):
    payload = data if isinstance(data, dict) else {}
    return save_json_file(path, payload)
