#!/usr/bin/env python3
"""Record the runtime information needed to judge Kaggle compatibility."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGES = ("torch", "transformers", "deepspeed", "accelerate", "datasets", "tokenizers")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write Python, package, CUDA, and GPU details.")
    parser.add_argument("--output", type=Path, default=Path("results/environment.txt"))
    return parser.parse_args()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        return f"unavailable ({type(error).__name__}: {error})"
    output = (result.stdout or result.stderr).strip()
    return output or f"no output (exit code {result.returncode})"


def git_revision() -> str:
    return command_output(["git", "rev-parse", "HEAD"]).splitlines()[0]


def torch_details() -> dict[str, Any]:
    details: dict[str, Any] = {}
    try:
        import torch
    except Exception as error:  # Import errors are environment evidence.
        details["import"] = f"failed ({type(error).__name__}: {error})"
        return details

    details["import"] = "ok"
    details["version"] = torch.__version__
    details["cuda_available"] = torch.cuda.is_available()
    details["compiled_cuda_version"] = torch.version.cuda
    details["cudnn_version"] = torch.backends.cudnn.version()
    details["device_count"] = torch.cuda.device_count()
    if torch.cuda.is_available():
        bf16_probe = getattr(torch.cuda, "is_bf16_supported", None)
        details["bf16_supported"] = bool(bf16_probe()) if bf16_probe else "unknown"
        devices = []
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": properties.name,
                    "total_memory_bytes": properties.total_memory,
                    "total_memory_gib": round(properties.total_memory / 1024**3, 2),
                    "compute_capability": f"{properties.major}.{properties.minor}",
                }
            )
        details["devices"] = devices
    else:
        details["bf16_supported"] = False
        details["devices"] = []
    return details


def render(details: dict[str, Any]) -> str:
    lines = [
        "Indirect PIA reproduction environment",
        "====================================",
        f"generated_at_utc: {details['generated_at_utc']}",
        f"git_commit: {details['git_commit']}",
        f"python: {details['python']}",
        f"python_executable: {details['python_executable']}",
        f"platform: {details['platform']}",
        f"kaggle_kernel_run_type: {details['kaggle_kernel_run_type']}",
        f"cuda_visible_devices: {details['cuda_visible_devices']}",
        "",
        "Package versions",
        "----------------",
    ]
    lines.extend(f"{name}: {version}" for name, version in details["packages"].items())
    lines.extend(["", "PyTorch / CUDA", "--------------"])
    lines.extend(f"{key}: {value}" for key, value in details["torch"].items())
    lines.extend(["", "nvidia-smi", "----------", details["nvidia_smi"], ""])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    details = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_revision(),
        "python": sys.version.replace("\n", " "),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "kaggle_kernel_run_type": os.environ.get("KAGGLE_KERNEL_RUN_TYPE", "not set"),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "not set"),
        "packages": {name: package_version(name) for name in PACKAGES},
        "torch": torch_details(),
        "nvidia_smi": command_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version,compute_cap",
                "--format=csv,noheader",
            ]
        ),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(details), encoding="utf-8")
    print(render(details))
    print(f"Saved environment report to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
