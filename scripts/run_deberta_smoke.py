#!/usr/bin/env python3
"""Run a bounded DeBERTa/DeepSpeed smoke test without changing upstream code."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL = "microsoft/deberta-v3-base"
SEED = 42
CONTEXT_COUNT = 16
INSTRUCTION_COUNT = 64


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def stream_command(
    command: list[str], log_path: Path, repo: Path, env: dict[str, str] | None = None
) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=repo,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        return process.wait()


def tail(path: Path, line_count: int = 80) -> str:
    if not path.exists():
        return ""
    return "".join(path.read_text(encoding="utf-8", errors="replace").splitlines(True)[-line_count:])


def prepare_subset(source: Path, destination: Path, count: int) -> None:
    records = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) < count:
        raise ValueError(f"{source} must contain at least {count} records")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records[:count], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install the minimal pinned user-space dependencies before training.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    os.chdir(repo)
    results = repo / "results" / "deberta_smoke"
    results.mkdir(parents=True, exist_ok=True)
    error_path = results / "error.txt"
    if error_path.exists():
        error_path.unlink()

    requirements = repo / "configs" / "kaggle-smoke-requirements.txt"
    source_instructions = repo / "data" / "crafted_instruction_data_alpaca.json"
    source_contexts = repo / "data" / "crafted_instruction_data_context_squad.json"
    smoke_data = repo / "artifacts" / "smoke_data"
    instructions = smoke_data / "alpaca_64.json"
    contexts = smoke_data / "squad_16.json"
    model_dir = repo / "artifacts" / "models" / "deberta_smoke"
    train_log = results / "training_log.txt"

    config: dict[str, Any] = {
        "experiment": "deberta_squad_smoke",
        "scientific_result": False,
        "created_at_utc": utc_now(),
        "git_commit": git_commit(repo),
        "model": MODEL,
        "tokenizer": MODEL,
        "seed": SEED,
        "train_dataset": str(source_contexts.relative_to(repo)),
        "instruction_dataset": str(source_instructions.relative_to(repo)),
        "train_sample_count": CONTEXT_COUNT,
        "instruction_pool_count": INSTRUCTION_COUNT,
        "epochs": 1,
        "train_batch_size": 4,
        "micro_train_batch_size": 4,
        "gradient_accumulation": 1,
        "expected_optimizer_steps": 4,
        "learning_rate": 1e-5,
        "inject_rate": 0.6,
        "head_rate": 0.25,
        "tail_rate": 0.25,
        "precision": "bf16",
        "zero_stage": 1,
        "adam_offload": True,
        "gpu_selection": "localhost:0",
        "install_dependencies": args.install_deps,
        "dependency_file": str(requirements.relative_to(repo)),
        "dependency_file_sha256": sha256(requirements),
        "source_data_sha256": {
            str(source_instructions.relative_to(repo)): sha256(source_instructions),
            str(source_contexts.relative_to(repo)): sha256(source_contexts),
        },
        "notes": "Smoke test only; no TPR, FPR, or scientific accuracy is computed.",
    }
    write_json(results / "config.json", config)

    def fail(stage: str, return_code: int, message: str, log: Path | None = None) -> int:
        detail = message
        if log is not None:
            log_tail = tail(log)
            if log_tail:
                detail += f"\n\nLast log lines:\n{log_tail}"
        error_path.write_text(detail.rstrip() + "\n", encoding="utf-8")
        write_json(
            results / "metrics.json",
            {
                "experiment": "deberta_squad_smoke",
                "status": "failed",
                "scientific_result": False,
                "failed_stage": stage,
                "return_code": return_code,
                "finished_at_utc": utc_now(),
                "metrics_computed": [],
            },
        )
        print(detail, file=sys.stderr)
        return return_code or 1

    try:
        prepare_subset(source_instructions, instructions, INSTRUCTION_COUNT)
        prepare_subset(source_contexts, contexts, CONTEXT_COUNT)
    except Exception as error:
        return fail("prepare_smoke_data", 1, f"{type(error).__name__}: {error}")

    before_command = [
        sys.executable,
        "scripts/check_environment.py",
        "--output",
        str(results / "environment_before.txt"),
    ]
    before = subprocess.run(before_command, cwd=repo, check=False)
    if before.returncode != 0:
        return fail("environment_before", before.returncode, "Initial environment capture failed.")

    if args.install_deps:
        install_command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements),
        ]
        install_log = results / "dependency_install_log.txt"
        install_code = stream_command(install_command, install_log, repo)
        if install_code != 0:
            return fail(
                "dependency_install",
                install_code,
                "Minimal Kaggle smoke dependencies failed to install.",
                install_log,
            )

    after_command = [
        sys.executable,
        "scripts/check_environment.py",
        "--output",
        str(results / "environment.txt"),
    ]
    after = subprocess.run(after_command, cwd=repo, check=False)
    if after.returncode != 0:
        return fail("environment_after", after.returncode, "Post-install environment capture failed.")

    if model_dir.exists():
        return fail(
            "preflight",
            1,
            f"Generated model directory already exists: {model_dir}. Start a fresh Kaggle session before rerunning.",
        )

    command = [
        sys.executable,
        "-m",
        "deepspeed.launcher.runner",
        "--include",
        "localhost:0",
        "--master_port",
        "1113",
        "train_head.py",
        "--model_name_or_path",
        MODEL,
        "--instruction_train_data_path",
        str(instructions),
        "--context_train_data_path",
        str(contexts),
        "--eval_data_path",
        "data/crafted_instruction_data_squad_injection_qa.json",
        "--bf16",
        "--save_path",
        str(model_dir),
        "--max_epochs",
        "1",
        "--train_batch_size",
        "4",
        "--micro_train_batch_size",
        "4",
        "--learning_rate",
        "1e-5",
        "--l2",
        "0",
        "--lr_scheduler",
        "cosine",
        "--logging_steps",
        "1",
        "--adam_offload",
        "--zero_stage",
        "1",
        "--seed",
        str(SEED),
        "--inject_rate",
        "0.6",
        "--log_file",
        str(results / "upstream_args.log"),
    ]
    command_text = "DS_SKIP_CUDA_CHECK=1 " + shlex.join(command)
    (results / "command.txt").write_text(command_text + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["DS_SKIP_CUDA_CHECK"] = "1"
    train_code = stream_command(command, train_log, repo, env)
    if train_code != 0:
        return fail("training", train_code, "DeBERTa smoke training failed.", train_log)

    checkpoint_config = model_dir / "config.json"
    weight_files = sorted(path.name for path in model_dir.glob("*.safetensors"))
    weight_files.extend(sorted(path.name for path in model_dir.glob("*.bin")))
    if not checkpoint_config.exists() or not weight_files:
        return fail(
            "checkpoint_validation",
            1,
            "Training exited successfully but the expected Hugging Face config/weight files were not saved.",
            train_log,
        )

    write_json(
        results / "metrics.json",
        {
            "experiment": "deberta_squad_smoke",
            "status": "success",
            "scientific_result": False,
            "finished_at_utc": utc_now(),
            "train_sample_count": CONTEXT_COUNT,
            "expected_optimizer_steps": 4,
            "checkpoint_config_present": True,
            "checkpoint_weight_files": weight_files,
            "metrics_computed": [],
            "notes": "Pipeline smoke test passed; no detection metrics were computed.",
        },
    )
    print("DeBERTa smoke test completed and checkpoint files were validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
