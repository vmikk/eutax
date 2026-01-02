"""
Reference database validation utilities.

On startup we want to *fail fast* if reference databases are not available,
because jobs will otherwise fail later in confusing ways.

Validation checks:
- uniqueness of database paths (files)
- existence of database paths (files)
- uniqueness of database names (aliases from YAML)
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


@dataclass(frozen=True)
class DuplicateRefDbName:
    refdb_name: str
    duplicate_refdb_ids: list[str]
    details: str


@dataclass(frozen=True)
class DuplicateRefDbPath:
    path: str
    refdb_ids: list[str]
    path_keys: list[str]
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


def validate_refdb_name_uniqueness_raw(yaml_content: str) -> list[DuplicateRefDbName]:
    """
    Check for duplicate database names by parsing raw YAML content.
    This catches duplicates that YAML parser would silently resolve.

    Returns a list of DuplicateRefDbName instances for any names that appear more than once.
    """
    import re

    # Find all database names under refdbs: section
    # This regex looks for lines like "  database_name:" under refdbs:
    refdb_pattern = re.compile(r'^refdbs:\s*$', re.MULTILINE)
    db_name_pattern = re.compile(r'^\s{2}([^:\s]+):', re.MULTILINE)

    refdb_match = refdb_pattern.search(yaml_content)
    if not refdb_match:
        return []

    # Extract content after refdbs:
    content_after_refdbs = yaml_content[refdb_match.end():]

    # Find all database names (non-indented keys)
    db_names = []
    for match in db_name_pattern.finditer(content_after_refdbs):
        db_name = match.group(1)
        db_names.append(db_name)

    # Check for duplicates
    name_counts = {}
    for name in db_names:
        name_counts[name] = name_counts.get(name, 0) + 1

    duplicates = []
    for name, count in name_counts.items():
        if count > 1:
            duplicates.append(DuplicateRefDbName(
                refdb_name=name,
                duplicate_refdb_ids=[name] * count,  # List with name repeated 'count' times
                details=f"Database name '{name}' appears {count} times in the YAML file"
            ))

    return duplicates


def validate_refdb_path_uniqueness(refdb_config: RefDbConfig) -> list[DuplicateRefDbPath]:
    """
    Check for duplicate paths across different databases in refdb configuration.

    Returns a list of DuplicateRefDbPath instances for any paths that appear in multiple databases.
    """
    path_to_usage: dict[str, list[tuple[str, str]]] = {}

    for refdb_id, entry in refdb_config.refdbs.items():
        paths = entry.paths
        for key in ("blast", "vsearch_global", "vsearch_exact"):
            value = getattr(paths, key, None)
            if value:
                path_to_usage.setdefault(value, []).append((refdb_id, key))

    duplicates = []
    for path, usages in path_to_usage.items():
        if len(usages) > 1:
            refdb_ids = [refdb_id for refdb_id, _ in usages]
            path_keys = [key for _, key in usages]
            duplicates.append(DuplicateRefDbPath(
                path=path,
                refdb_ids=refdb_ids,
                path_keys=path_keys,
                details=f"Path '{path}' is used by databases {', '.join(refdb_ids)} (keys: {', '.join(path_keys)})"
            ))

    return duplicates


def validate_refdb_files(config_path: str | None = None) -> tuple[str, list[MissingRefDbPath], list[DuplicateRefDbName], list[DuplicateRefDbPath]]:
    """
    Validate refdb configuration including:
    - All refdb paths referenced in refdb.yaml exist on disk
    - Database names are unique (fatal error)
    - Paths are unique across databases (warning)

    Returns:
    - resolved_config_path
    - list of missing paths (empty when OK)
    - list of duplicate names (fatal, should exit)
    - list of duplicate paths (warning, continue)
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
            [],  # no duplicate names
            [],  # no duplicate paths
        )

    # Read raw YAML content for duplicate name validation
    try:
        with open(resolved, "r") as f:
            yaml_content = f.read()
    except Exception as e:
        return (
            resolved,
            [
                MissingRefDbPath(
                    refdb_id="__config__",
                    path_key="refdb.yaml",
                    configured_path=resolved,
                    details=f"failed to read YAML file: {type(e).__name__}: {e}",
                )
            ],
            [],  # no duplicate names
            [],  # no duplicate paths
        )

    # Check for duplicate names in raw YAML (fatal - catches duplicates before parsing)
    duplicate_names = validate_refdb_name_uniqueness_raw(yaml_content)

    try:
        raw = yaml.safe_load(yaml_content) or {}
    except Exception as e:
        return (
            resolved,
            [
                MissingRefDbPath(
                    refdb_id="__config__",
                    path_key="refdb.yaml",
                    configured_path=resolved,
                    details=f"failed to parse YAML: {type(e).__name__}: {e}",
                )
            ],
            duplicate_names,  # include any duplicate names found
            [],  # no duplicate paths
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
            duplicate_names,  # include any duplicate names found
            [],  # no duplicate paths
        )

    # Check for duplicate paths (warning)
    duplicate_paths = validate_refdb_path_uniqueness(parsed)

    # Check for missing paths
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

    return resolved, missing, duplicate_names, duplicate_paths


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
    Validate refdb availability and exit the process if missing or invalid.
    Intended to be called during API startup.
    """
    # Allow being called without importing main.py (colors is optional).
    class _NoColors:
        RED = ""
        RESET = ""

    colors = colors or _NoColors()

    resolved, missing, duplicate_names, duplicate_paths = validate_refdb_files()

    # Handle duplicate names (fatal error)
    if duplicate_names:
        print(f"{colors.RED}FATAL: Reference database configuration contains duplicate names — refusing to start.{colors.RESET}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Duplicate database names found:", file=sys.stderr)
        for item in duplicate_names:
            print(f"  - {item.details}", file=sys.stderr)
        print("", file=sys.stderr)
        print("How to fix:", file=sys.stderr)
        print("  - Edit refdb.yaml to ensure all database names are unique.", file=sys.stderr)
        print("", file=sys.stderr)

        if logger is not None:
            logger.error(
                "Reference DB validation failed - duplicate names; exiting",
                event_type="startup_refdb_validation_failed",
                refdb_config_path=resolved,
                duplicate_names=[item.__dict__ for item in duplicate_names],
            )
        os._exit(2)

    # Handle duplicate paths (warning only)
    if duplicate_paths:
        print(f"{colors.RED}WARNING: Reference database configuration contains duplicate paths.{colors.RESET}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Duplicate paths found:", file=sys.stderr)
        for item in duplicate_paths:
            print(f"  - {item.details}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Note: This may be intentional but could indicate configuration errors.", file=sys.stderr)
        print("", file=sys.stderr)

        if logger is not None:
            logger.warning(
                "Reference DB validation - duplicate paths detected",
                event_type="startup_refdb_validation_duplicate_paths",
                refdb_config_path=resolved,
                duplicate_paths=[item.__dict__ for item in duplicate_paths],
            )

    # Handle missing paths (fatal error)
    if missing:
        msg = _format_startup_failure(colors=colors, resolved_config_path=resolved, missing=missing)
        print(msg, file=sys.stderr)
        try:
            sys.stderr.flush()
        except Exception:
            pass

        if logger is not None:
            logger.error(
                "Reference DB validation failed - missing files; exiting",
                event_type="startup_refdb_validation_failed",
                refdb_config_path=resolved,
                missing=[item.__dict__ for item in missing],
            )

        # In FastAPI/Starlette lifespan, raising SystemExit/Exception causes an
        # "ERROR: Traceback ..." log which looks like an application crash.
        # We intentionally terminate the process *without* raising, to keep logs clean.
        os._exit(2)


def main() -> None:
    resolved, missing, duplicate_names, duplicate_paths = validate_refdb_files()

    # Check for fatal errors first
    if duplicate_names:
        print(f"refdb validation FAILED - duplicate names (config: {resolved})", file=sys.stderr)
        for item in duplicate_names:
            print(f"- {item.details}", file=sys.stderr)
        raise SystemExit(2)

    if duplicate_paths:
        print(f"refdb validation WARNING - duplicate paths (config: {resolved})", file=sys.stderr)
        for item in duplicate_paths:
            print(f"- WARNING: {item.details}", file=sys.stderr)

    if missing:
        print(f"refdb validation FAILED - missing files (config: {resolved})", file=sys.stderr)
        for item in missing:
            print(f"- {item.refdb_id}:{item.path_key} -> {item.configured_path} ({item.details})", file=sys.stderr)
        raise SystemExit(2)

    if duplicate_paths:
        print(f"refdb validation OK with warnings (config: {resolved})")
    else:
        print(f"refdb validation OK (config: {resolved})")


if __name__ == "__main__":
    main()

