"""
tracks <cache_dir>/build_artifacts/ so `kernel-sandbox list-cache` can tell a caller which (commit, arch, config)
combinations are ready to boot, and in which mode
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from libs.console import get_logger

logger = get_logger(__name__)

META_FILENAME = ".cache_meta.json"


def write_cache_metadata(artifacts_dir, mode, arch, config_flavor, commit_hash, kernel_image_name=None, rpm_arch=None):
    """Writes/refreshes the metadata file for one build_artifacts/<commit>/<arch>/<flavor>/ directory."""
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "mode": mode,
        "arch": arch,
        "config_flavor": config_flavor,
        "commit_hash": commit_hash,
        "kernel_image_name": kernel_image_name,
        "rpm_arch": rpm_arch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(artifacts_dir / META_FILENAME, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def read_cache_metadata(artifacts_dir):
    """Returns the parsed metadata dict, or None if missing/corrupt"""
    meta_path = Path(artifacts_dir) / META_FILENAME
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Ignoring unreadable cache metadata at {meta_path}: {e}")
        return None


def _rpm_cow_image_path(cache_dir, commit_hash, config_flavor, rpm_arch):
    return Path(cache_dir) / "base-images" / f"temp-sandbox-g{commit_hash[:7]}-{config_flavor}.{rpm_arch}.qcow2"


def discover_cached_builds(cache_dir):
    """scans build_artifacts/*<commit>/*<arch>/*<flavor>/.cache_meta.json and
    returns a list of metadata dicts, each augmented with `artifacts_dir` and `boot_ready`
    """
    cache_dir = Path(cache_dir)
    build_artifacts_root = cache_dir / "build_artifacts"
    if not build_artifacts_root.exists():
        return []

    discovered = []
    for meta_path in build_artifacts_root.glob("*/*/*/" + META_FILENAME):
        artifacts_dir = meta_path.parent
        metadata = read_cache_metadata(artifacts_dir)
        if metadata is None:
            continue

        if metadata.get("mode") == "fast":
            kernel_image_name = metadata.get("kernel_image_name")
            boot_ready = bool(kernel_image_name) and \
                (artifacts_dir / kernel_image_name).exists() and \
                (artifacts_dir / "initrd_custom.gz").exists()
        elif metadata.get("mode") == "rpm":
            rpm_arch = metadata.get("rpm_arch")
            boot_ready = bool(rpm_arch) and _rpm_cow_image_path(
                cache_dir, metadata.get("commit_hash", ""), metadata.get("config_flavor", ""), rpm_arch
            ).exists()
        else:
            boot_ready = False

        entry = dict(metadata)
        entry["artifacts_dir"] = artifacts_dir
        entry["boot_ready"] = boot_ready
        discovered.append(entry)

    discovered.sort(key=lambda entry: entry.get("updated_at", ""), reverse=True)
    return discovered
