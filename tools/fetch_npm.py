import json
import os
import pathlib
import sys
from typing import Any, Dict, List

import requests
import yaml

try:
    from packaging.version import Version
except Exception:  # pragma: no cover
    try:  # fallback when packaging is unavailable
        from distutils.version import LooseVersion as Version  # type: ignore
    except Exception:  # pragma: no cover
        Version = None  # type: ignore

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "index" / "plugins"
REGISTRY_DEFAULT = "https://registry.npmjs.org"
AUTO_REMOVE_INVALID = os.getenv("AUTO_REMOVE_INVALID", "false").lower() in {"1", "true", "yes"}


def log(*args):
    print("[fetch-npm]", *args)


def load_manifest(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_manifest(path: pathlib.Path, data: Dict[str, Any]):
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def fetch_registry(pkg: str, registry: str = REGISTRY_DEFAULT) -> Dict[str, Any]:
    url = f"{registry.rstrip('/')}/{pkg}"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 404:
        raise FileNotFoundError(f"package {pkg} not found")
    resp.raise_for_status()
    return resp.json()


def build_version_entry(pkg: str, meta: Dict[str, Any], version: str, registry: str) -> Dict[str, Any]:
    versions = meta.get("versions", {})
    vinfo = versions.get(version, {})
    dist = vinfo.get("dist", {})
    entry = {
        "version": version,
        "desktopCompat": vinfo.get("desktopCompat") or vinfo.get("desktop", ">=0.0.0"),
        "sdkCompat": vinfo.get("sdkCompat") or vinfo.get("sdk", ">=0.0.0"),
        "targets": vinfo.get("targets") or ["main"],
        "dist": {
            "npm": pkg,
            "tag": version,
            "registry": registry,
        },
    }
    if dist.get("integrity"):
        entry["dist"]["integrity"] = dist["integrity"]
    if dist.get("shasum"):
        entry["dist"]["shasum"] = dist["shasum"]
    tarball = dist.get("tarball")
    if tarball:
        entry["dist"]["tarball"] = tarball
    readme = meta.get("readmeFilename")
    if readme:
        entry["readme"] = readme
    return entry

def _is_prerelease_version(ver: str) -> bool:
    """排除 stage/staged/beta/alpha/rc 等预发布版本。"""
    lowered = ver.lower()
    return any(tag in lowered for tag in ("stage", "staged", "alpha", "beta", "rc", "pre"))


def _sort_versions(available_versions: List[str]) -> List[str]:
    """
    安全地按版本号从大到小排序：
    - 过滤掉预发布版本
    - 过滤掉 Version 无法解析的字符串（避免 InvalidVersion 崩溃）
    - 若无 Version 解析器，则退回字符串排序
    """
    # 1) 先过滤预发布
    cleaned = [v for v in available_versions if not _is_prerelease_version(v)]

    if not cleaned:
        return []

    if Version is None:
        # 没有版本解析器，直接字符串排序
        return sorted(cleaned, reverse=True)

    # 2) 逐个尝试解析，无法解析的跳过
    parsed: List[tuple] = []
    for ver in cleaned:
        try:
            parsed.append((Version(ver), ver))
        except Exception:
            log("skip unparsable version:", ver)
            continue

    if not parsed:
        return []

    # 3) 按解析后的版本倒序
    parsed.sort(key=lambda item: item[0], reverse=True)
    return [ver for _, ver in parsed]

def main():
    if not INDEX_DIR.exists():
        log("plugins directory not found", INDEX_DIR)
        sys.exit(1)

    files = [p for p in INDEX_DIR.iterdir() if p.suffix in {".yml", ".yaml", ".json"}]
    invalid: List[pathlib.Path] = []

    for path in files:
        try:
            data = load_manifest(path)
            pkg = data.get("package") or data.get("npm")
            if not pkg:
                log("skip (no package field)", path.name)
                continue
            registry = data.get("registry", REGISTRY_DEFAULT)
            try:
                meta = fetch_registry(pkg, registry)
            except FileNotFoundError:
                log("NOT FOUND, mark invalid", pkg)
                invalid.append(path)
                continue
            except Exception as exc:  # noqa: BLE001
                log("failed", pkg, exc)
                continue

            latest = meta.get("dist-tags", {}).get("latest")
            if not latest:
                log("no latest tag", pkg)
                continue

            available_versions = list(meta.get("versions", {}).keys())
            sorted_versions = _sort_versions(available_versions)

            if latest in available_versions and not _is_prerelease_version(latest):
                chosen = latest
            elif sorted_versions:
                chosen = sorted_versions[0]
            else:
                log("no usable version found", pkg)
                continue

            entry = build_version_entry(pkg, meta, chosen, registry)
            data["latestVersion"] = chosen
            data["versions"] = [entry]
            save_manifest(path, data)
            log("updated", pkg, "->", chosen)
        except Exception as exc:  # noqa: BLE001
            log("unexpected error for", path.name, exc)
            continue

    if invalid and AUTO_REMOVE_INVALID:
        for path in invalid:
            try:
                path.unlink()
                log("removed invalid", path.name)
            except Exception as exc:  # noqa: BLE001
                log("failed to remove", path.name, exc)

    if invalid and not AUTO_REMOVE_INVALID:
        log("invalid packages (not removed):", ", ".join(p.name for p in invalid))


if __name__ == "__main__":
    main()
