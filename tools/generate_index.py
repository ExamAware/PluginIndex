import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "index" / "plugins"
BASE_PATH = ROOT / "base.json"
OUTPUT_PATH = ROOT / "index" / "index.json"


def log(*args):
    print("[generate-index]", *args)


def load_base() -> Dict[str, Any]:
    if not BASE_PATH.exists():
        return {}
    try:
        return json.loads(BASE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log("base.json parse failed, ignored:", exc)
        return {}


def load_manifest(path: pathlib.Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(raw)
    return yaml.safe_load(raw) or {}


def collect_items() -> List[Dict[str, Any]]:
    if not INDEX_DIR.exists():
        log("plugins directory not found", INDEX_DIR)
        sys.exit(1)

    files = [p for p in INDEX_DIR.iterdir() if p.suffix.lower() in {".yml", ".yaml", ".json"}]
    items: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = load_manifest(path)
            if not isinstance(data, dict):
                raise ValueError("manifest is not an object")
            data["__source"] = str(path.relative_to(ROOT))
            items.append(data)
        except Exception as exc:  # noqa: BLE001
            log("skip", path.name, exc)
    items.sort(key=lambda x: (x.get("id") or x.get("name") or x.get("__source") or "").lower())
    return items


def build_payload(items: List[Dict[str, Any]], base: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plugins": items,
    }
    mirrors = base.get("DownloadMirrors") if isinstance(base, dict) else None
    if mirrors:
        payload["mirrors"] = mirrors
    return payload


def write_output(payload: Dict[str, Any]):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log("written", OUTPUT_PATH)


def main():
    base = load_base()
    items = collect_items()
    payload = build_payload(items, base)
    write_output(payload)


if __name__ == "__main__":
    main()
