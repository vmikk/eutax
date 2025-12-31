"""
Reference database validation utilities.

On startup we want to *fail fast* if reference databases are not available,
because jobs will otherwise fail later in confusing ways.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Iterable

import yaml

from app.models.models import RefDbConfig


DEFAULT_CONTAINER_REFDB_CONFIG_PATH = "/app/app/config/refdb.yaml"


@dataclass(frozen=True)
class MissingRefDbPath:
    refdb_id: str
    path_key: str
    configured_path: str
    details: str


def get_refdb_config_path() -> str:
    """
    Resolve the refdb config path.

    Priority:
    - REFDB_CONFIG_PATH env var
    - container default if it exists
    - repo-local default (app/config/refdb.yaml)
    """
    env = os.getenv("REFDB_CONFIG_PATH")
    if env:
        return env
    if os.path.exists(DEFAULT_CONTAINER_REFDB_CONFIG_PATH):
        return DEFAULT_CONTAINER_REFDB_CONFIG_PATH
    return os.path.join(os.path.dirname(__file__), "config", "refdb.yaml")


def _blast_prefix_exists(prefix: str) -> tuple[bool, str]:
    """
    BLAST DBs are typically a set of files named <prefix>.<ext>.
    We treat the DB as "present" if any of the common index files exist.
    """
    if os.path.exists(prefix):
        return True, "prefix path exists"

    # Common BLAST nucleotide db files (legacy and volumes)
    candidates = [
        f"{prefix}.nhr",
        f"{prefix}.nin",
        f"{prefix}.nsq",
        f"{prefix}.00.nhr",
        f"{prefix}.00.nin",
        f"{prefix}.00.nsq",
    ]
    existing = [p for p in candidates if os.path.exists(p)]
    if existing:
        return True, f"found BLAST index file(s): {', '.join(existing[:3])}" + ("..." if len(existing) > 3 else "")

    return False, f"missing BLAST DB prefix and expected files like: {', '.join(candidates[:3])}, ..."


def _iter_configured_paths(refdb_config: RefDbConfig) -> Iterable[tuple[str, str, str]]:
    for refdb_id, entry in refdb_config.refdbs.items():
        paths = entry.paths
        # Include all non-empty configured paths
        for key in ("blast", "vsearch_global", "vsearch_exact"):
            value = getattr(paths, key, None)
            if value:
                yield refdb_id, key, value


def validate_refdb_files(config_path: str | None = None) -> tuple[str, list[MissingRefDbPath]]:
    """
    Validate that all refdb paths referenced in refdb.yaml exist on disk.

    Returns:
    - resolved_config_path
    - list of missing paths (empty when OK)
    """
    resolved = config_path or get_refdb_config_path()

    if not os.path.exists(resolved):
        return (
            resolved,
            [
                MissingRefDbPath(
                    refdb_id="__config__",
                    path_key="refdb.yaml",
                    configured_path=resolved,
                    details="refdb config file not found",
                )
            ],
        )

    try:
        with open(resolved, "r") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        return (
            resolved,
            [
                MissingRefDbPath(
                    refdb_id="__config__",
                    path_key="refdb.yaml",
                    configured_path=resolved,
                    details=f"failed to read/parse YAML: {type(e).__name__}: {e}",
                )
            ],
        )

    try:
        parsed = RefDbConfig.model_validate(raw)
    except Exception as e:
        return (
            resolved,
            [
                MissingRefDbPath(
                    refdb_id="__config__",
                    path_key="refdb.yaml",
                    configured_path=resolved,
                    details=f"invalid refdb.yaml structure: {type(e).__name__}: {e}",
                )
            ],
        )

    missing: list[MissingRefDbPath] = []
    for refdb_id, key, path in _iter_configured_paths(parsed):
        if key == "blast":
            ok, details = _blast_prefix_exists(path)
            if not ok:
                missing.append(MissingRefDbPath(refdb_id=refdb_id, path_key=key, configured_path=path, details=details))
            continue

        if not os.path.exists(path):
            missing.append(
                MissingRefDbPath(
                    refdb_id=refdb_id,
                    path_key=key,
                    configured_path=path,
                    details="path does not exist",
                )
            )

    return resolved, missing


def _format_startup_failure(
    *,
    colors,
    resolved_config_path: str,
    missing: list[MissingRefDbPath],
) -> str:
    lines: list[str] = []
    lines.append(f"{colors.RED}FATAL: Reference databases are not available — refusing to start.{colors.RESET}")
    lines.append("")
    lines.append("Reference database configuration:")
    lines.append(f"  - REFDB_CONFIG_PATH env: {os.getenv('REFDB_CONFIG_PATH', '(not set)')}")
    lines.append(f"  - resolved config path: {resolved_config_path}")
    lines.append("")
    lines.append("Missing/invalid items:")
    for item in missing:
        lines.append(f"  - {item.refdb_id}:{item.path_key} -> {item.configured_path}")
        lines.append(f"    {item.details}")
    lines.append("")
    lines.append("How to fix:")
    lines.append("  - Ensure the host database directory is mounted into the container at the expected location (often /data).")
    lines.append("  - Or update REFDB_CONFIG_PATH to point at the correct refdb.yaml.")
    lines.append("  - Or edit refdb.yaml so all referenced paths match your filesystem.")
    lines.append("")
    return "\n".join(lines)


def ensure_refdbs_available_or_exit(*, logger=None, colors=None) -> None:
    """
    Validate refdb availability and exit the process if missing.
    Intended to be called during API startup.
    """
    # Allow being called without importing main.py (colors is optional).
    class _NoColors:
        RED = ""
        RESET = ""

    colors = colors or _NoColors()

    resolved, missing = validate_refdb_files()
    if not missing:
        return

    msg = _format_startup_failure(colors=colors, resolved_config_path=resolved, missing=missing)
    print(msg, file=sys.stderr)

    if logger is not None:
        logger.error(
            "Reference DB validation failed; exiting",
            event_type="startup_refdb_validation_failed",
            refdb_config_path=resolved,
            missing=[item.__dict__ for item in missing],
        )

    raise SystemExit(2)


def main() -> None:
    resolved, missing = validate_refdb_files()
    if missing:
        # Minimal plain output for CLI usage
        print(f"refdb validation FAILED (config: {resolved})", file=sys.stderr)
        for item in missing:
            print(f"- {item.refdb_id}:{item.path_key} -> {item.configured_path} ({item.details})", file=sys.stderr)
        raise SystemExit(2)
    print(f"refdb validation OK (config: {resolved})")


if __name__ == "__main__":
    main()

