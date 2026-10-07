#!/usr/bin/env python3
"""Convert the official evaluation scripts' text logs into structured files."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


DETECTION_START = re.compile(r"Attack Method (.*?), Side (.*?) Start")
REMOVAL_START = DETECTION_START
ASR_START = re.compile(r"Attack Method (.*?), Defense Method (.*?),\s*Side (.*?), Begin")
ACC = re.compile(r"ACC:\s*([0-9.eE+-]+)")
COST = re.compile(r"COST:\s*([0-9.eE+-]+)")
ASR = re.compile(r"ASR:\s*([0-9.eE+-]+)")
INJ_ACC = re.compile(r"INJ ACC:\s*([0-9.eE+-]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("detection", "removal", "asr"), required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--sample-count", type=int, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args()


def parse_blocks(text: str, mode: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in text.splitlines():
        start = (ASR_START if mode == "asr" else DETECTION_START).search(line)
        if start:
            if mode == "asr":
                current = {
                    "attack": start.group(1).strip(),
                    "defense": start.group(2).strip(),
                    "position": start.group(3).strip(),
                }
            else:
                current = {
                    "attack": start.group(1).strip(),
                    "position": start.group(2).strip(),
                }
            rows.append(current)
            continue
        if current is None:
            continue
        match = COST.search(line)
        if match:
            current["cost_seconds_per_sample"] = float(match.group(1))
        if mode in ("detection", "removal"):
            match = ACC.search(line)
            if match:
                current["score"] = float(match.group(1))
        else:
            match = ASR.search(line)
            if match:
                current["asr"] = float(match.group(1))
            match = INJ_ACC.search(line)
            if match:
                current["removal_rate"] = float(match.group(1))
    return rows


def normalize(rows: list[dict[str, object]], mode: str, dataset: str, sample_count: int) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        base = {
            "dataset": dataset,
            "attack": row["attack"],
            "position": row["position"],
            "sample_count": sample_count,
            "cost_seconds_per_sample": row.get("cost_seconds_per_sample"),
        }
        if mode == "detection":
            score = row.get("score")
            base["tpr"] = None if row["attack"] == "none" else score
            base["fpr"] = score if row["attack"] == "none" else None
        elif mode == "removal":
            base["removal_rate"] = row.get("score")
        else:
            base["defense"] = row.get("defense")
            base["asr"] = row.get("asr")
            base["removal_rate"] = row.get("removal_rate")
        normalized.append(base)
    return normalized


def main() -> int:
    args = parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    rows = normalize(parse_blocks(text, args.mode), args.mode, args.dataset, args.sample_count)
    if not rows:
        raise SystemExit(f"No {args.mode} result blocks found in {args.log}")

    required_metric = {"detection": ("tpr", "fpr"), "removal": ("removal_rate",), "asr": ("asr",)}[args.mode]
    incomplete = [row for row in rows if all(row.get(key) is None for key in required_metric)]
    if incomplete:
        raise SystemExit(f"Found {len(incomplete)} incomplete result blocks in {args.log}")

    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with args.csv_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    args.json_output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(f"Parsed {len(rows)} result rows into {args.csv_output} and {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
