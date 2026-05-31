"""Module Runner - Execute Python modules as subprocesses with result summarization"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from backend2.config import PROJECT_ROOT, PYTHON_EXECUTABLE
from backend2.logging_utils import get_logger

logger = get_logger(__name__)


def run_python_module(module_name: str) -> dict[str, Any]:
    """
    Run a Python module as a subprocess.
    
    Args:
        module_name: Module name (e.g., 'etl.02_clean_and_transform')
    
    Returns:
        Dictionary with execution result, stdout, stderr, and return code
    """
    try:
        cmd = [sys.executable, "-m", module_name]
        
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )
        
        return {
            "module": module_name,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Module {module_name} execution timed out")
        return {
            "module": module_name,
            "return_code": -1,
            "stdout": "",
            "stderr": "Execution timed out",
            "success": False,
        }
    except Exception as e:
        logger.error(f"Error running module {module_name}: {str(e)}")
        return {
            "module": module_name,
            "return_code": -1,
            "stdout": "",
            "stderr": str(e),
            "success": False,
        }


def ensure_success(result: dict[str, Any]) -> None:
    """
    Ensure execution was successful, raise RuntimeError if not.
    
    Args:
        result: Result dictionary from run_python_module
    
    Raises:
        RuntimeError: If execution failed
    """
    if not result.get("success"):
        error_msg = f"Module {result.get('module')} failed\nstderr: {result.get('stderr')}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    Summarize module execution result for logging.
    
    Args:
        result: Result dictionary from run_python_module
    
    Returns:
        Simplified summary dictionary
    """
    return {
        "module": result.get("module"),
        "success": result.get("success"),
        "return_code": result.get("return_code"),
        "stdout_length": len(result.get("stdout", "")),
        "stderr_length": len(result.get("stderr", "")),
    }
