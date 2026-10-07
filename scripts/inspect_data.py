#!/usr/bin/env python3
"""Inspect JSON datasets without modifying them or importing training dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


LABEL_KEYS = {"label", "labels", "class", "is_injected", "is_injection"}
POSITION_KEYS = {"position", "side", "injection_position", "injection_side"}
ATTACK_KEYS = {"attack", "attack_type", "category", "injection_type"}
MAX_DISTRIBUTION_VALUES = 50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and summarize every JSON file in a dataset directory."
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--sample-chars", type=int, default=240)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def truncate(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, list):
        return [truncate(item, limit) for item in value[:10]]
    if isinstance(value, dict):
        return {str(key): truncate(item, limit) for key, item in value.items()}
    return value


def select_records(document: Any) -> tuple[list[Any], str]:
    if isinstance(document, list):
        return document, "array"
    if isinstance(document, dict):
        for key in ("data", "examples", "records", "train", "test"):
            candidate = document.get(key)
            if isinstance(candidate, list):
                return candidate, f"object containing array at key '{key}'"
        if document and all(isinstance(value, dict) for value in document.values()):
            return list(document.values()), "object mapping IDs to records"
        return [document], "single object"
    return [document], type(document).__name__


def scalar_distribution(records: Iterable[dict[str, Any]], keys: set[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in sorted(keys):
        values = [record[key] for record in records if key in record]
        if not values or any(isinstance(value, (dict, list)) for value in values):
            continue
        rendered = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
        counts = Counter(rendered)
        if len(counts) <= MAX_DISTRIBUTION_VALUES:
            output[key] = {
                "present_count": len(values),
                "distribution": dict(sorted(counts.items())),
            }
        else:
            output[key] = {
                "present_count": len(values),
                "unique_count": len(counts),
                "distribution": "omitted because the field has more than 50 unique values",
            }
    return output


def representative_indices(count: int) -> list[int]:
    if count == 0:
        return []
    return sorted({0, count // 2, count - 1})


def inspect_file(path: Path, data_dir: Path, sample_chars: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "file": path.relative_to(data_dir).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "valid_json": False,
    }
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        base["error"] = f"{type(error).__name__}: {error}"
        return base

    records, structure = select_records(document)
    mapping_records = [record for record in records if isinstance(record, dict)]
    malformed_indices = [index for index, record in enumerate(records) if not isinstance(record, dict)]
    key_counts: Counter[str] = Counter()
    signature_counts: Counter[tuple[str, ...]] = Counter()
    for record in mapping_records:
        keys = tuple(sorted(str(key) for key in record))
        signature_counts[keys] += 1
        key_counts.update(keys)

    modal_keys: tuple[str, ...] = ()
    if signature_counts:
        modal_keys = signature_counts.most_common(1)[0][0]
    missing_from_modal: dict[str, list[int]] = {}
    for key in modal_keys:
        missing = [index for index, record in enumerate(records) if not isinstance(record, dict) or key not in record]
        if missing:
            missing_from_modal[key] = missing[:20]

    observed_keys = set(key_counts)
    samples = [
        {"index": index, "record": truncate(records[index], sample_chars)}
        for index in representative_indices(len(records))
    ]
    base.update(
        {
            "valid_json": True,
            "top_level_type": type(document).__name__,
            "record_structure": structure,
            "example_count": len(records),
            "mapping_record_count": len(mapping_records),
            "malformed_record_count": len(malformed_indices),
            "malformed_record_indices_first_20": malformed_indices[:20],
            "observed_keys": sorted(observed_keys),
            "key_presence_counts": dict(sorted(key_counts.items())),
            "modal_keys": list(modal_keys),
            "modal_schema_count": signature_counts.get(modal_keys, 0),
            "missing_modal_fields_first_20": missing_from_modal,
            "label_fields": scalar_distribution(mapping_records, observed_keys & LABEL_KEYS),
            "position_fields": scalar_distribution(mapping_records, observed_keys & POSITION_KEYS),
            "attack_fields": scalar_distribution(mapping_records, observed_keys & ATTACK_KEYS),
            "representative_samples": samples,
        }
    )
    return base


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Dataset inspection summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Data directory: `{summary['data_directory']}`",
        f"- Git revision: `{summary.get('git_revision') or 'not detected'}`",
        f"- JSON files: {summary['json_file_count']}",
        f"- Total examples: {summary['total_examples']}",
        "",
        "The script only read and hashed the source datasets; it did not modify them.",
        "",
    ]
    for item in summary["files"]:
        lines.extend([f"## `{item['file']}`", ""])
        if not item["valid_json"]:
            lines.extend([f"- JSON error: `{item['error']}`", ""])
            continue
        lines.extend(
            [
                f"- Size: {item['bytes']:,} bytes",
                f"- SHA-256: `{item['sha256']}`",
                f"- Top level: {item['record_structure']}",
                f"- Examples: {item['example_count']:,}",
                f"- Keys: {', '.join(f'`{key}`' for key in item['observed_keys']) or 'none'}",
                f"- Malformed/non-object records: {item['malformed_record_count']}",
                f"- Records missing modal fields: {sum(len(v) for v in item['missing_modal_fields_first_20'].values())}",
                f"- Label fields: `{json.dumps(item['label_fields'], ensure_ascii=False)}`",
                f"- Position fields: `{json.dumps(item['position_fields'], ensure_ascii=False)}`",
                f"- Attack/category fields: `{json.dumps(item['attack_fields'], ensure_ascii=False)}`",
                "",
                "Representative records (text is truncated):",
                "",
                "```json",
                json.dumps(item["representative_samples"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "data_summary.json"
    markdown_path = output_dir / "data_summary.md"

    files = sorted(data_dir.rglob("*.json")) if data_dir.is_dir() else []
    inspected = [inspect_file(path, data_dir, args.sample_chars) for path in files]
    valid = bool(files) and all(item["valid_json"] for item in inspected)
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if valid else "failed",
        "data_directory": args.data_dir.as_posix(),
        "git_revision": git_revision(data_dir),
        "json_file_count": len(files),
        "total_examples": sum(item.get("example_count", 0) for item in inspected),
        "files": inspected,
    }
    if not data_dir.is_dir():
        summary["error"] = f"Data directory does not exist: {data_dir}"
    elif not files:
        summary["error"] = f"No JSON files found under: {data_dir}"

    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(summary) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    print(f"Status: {summary['status']}; files: {len(files)}; examples: {summary['total_examples']}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
