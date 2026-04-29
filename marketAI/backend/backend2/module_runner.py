from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable

from backend2.config import PROJECT_ROOT, PYTHON_EXECUTABLE


@dataclass
class CommandResult:
    module_name: str
    return_code: int
    duration_seconds: float
    stdout: str
    stderr: str


def run_python_module(module_name: str, extra_env: dict[str, str] | None = None) -> CommandResult:
    cmd = [PYTHON_EXECUTABLE or sys.executable, "-m", module_name]
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    started = time.time()
    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    duration = time.time() - started

    return CommandResult(
        module_name=module_name,
        return_code=completed.returncode,
        duration_seconds=round(duration, 3),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def truncate_text(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def summarize_result(result: CommandResult) -> dict[str, str | int | float]:
    return {
        "module_name": result.module_name,
        "return_code": result.return_code,
        "duration_seconds": result.duration_seconds,
        "stdout": truncate_text(result.stdout),
        "stderr": truncate_text(result.stderr),
    }


def ensure_success(result: CommandResult, accepted_codes: Iterable[int] = (0,)) -> None:
    if result.return_code in accepted_codes:
        return

    summary = summarize_result(result)
    raise RuntimeError(
        "Module execution failed: "
        f"module={summary['module_name']} "
        f"return_code={summary['return_code']} "
        f"stderr={summary['stderr']}"
    )
