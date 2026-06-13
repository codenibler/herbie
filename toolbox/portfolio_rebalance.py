from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values


REPO_ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_REBALANCE_DIR = REPO_ROOT / "portfolio_rebalance"
PORTFOLIO_REBALANCE_ENV_FILE = PORTFOLIO_REBALANCE_DIR / ".env"
PORTFOLIO_REBALANCE_MAIN = PORTFOLIO_REBALANCE_DIR / "main.py"
PORTFOLIO_REBALANCE_PRIMARY_PYTHON = PORTFOLIO_REBALANCE_DIR / "venv" / "bin" / "python"
PORTFOLIO_REBALANCE_LINUX_PYTHON = PORTFOLIO_REBALANCE_DIR / "venv_linux" / "bin" / "python"
PORTFOLIO_REBALANCE_TIMEOUT_SECONDS = int(
    os.getenv("PORTFOLIO_REBALANCE_TIMEOUT_SECONDS", "1800")
)
PORTFOLIO_REBALANCE_PYTHON_PATH_OVERRIDE = os.getenv(
    "PORTFOLIO_REBALANCE_PYTHON_PATH",
    "",
).strip()
REQUIRED_PORTFOLIO_REBALANCE_ENV_VARS = (
    "TRADING212_DATA_FETCH_API_KEY",
    "TRADING212_DATA_FETCH_API_SECRET",
)


def _tail_non_empty_lines(text: str, *, max_lines: int = 3) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return " ".join(lines[-max_lines:])


def _candidate_python_paths() -> list[Path]:
    candidates: list[Path] = []

    if PORTFOLIO_REBALANCE_PYTHON_PATH_OVERRIDE:
        candidates.append(Path(PORTFOLIO_REBALANCE_PYTHON_PATH_OVERRIDE).expanduser())

    candidates.extend(
        [
            PORTFOLIO_REBALANCE_PRIMARY_PYTHON,
            PORTFOLIO_REBALANCE_LINUX_PYTHON,
        ]
    )

    unique_candidates: list[Path] = []
    seen_paths: set[Path] = set()
    for candidate in candidates:
        resolved_candidate = candidate.resolve(strict=False)
        if resolved_candidate in seen_paths:
            continue
        seen_paths.add(resolved_candidate)
        unique_candidates.append(candidate)

    return unique_candidates


def _is_usable_python_executable(python_path: Path) -> bool:
    if not python_path.is_file():
        logging.info("Portfolio rebalance interpreter not found: %s", python_path)
        return False

    if not os.access(python_path, os.X_OK):
        logging.info(
            "Portfolio rebalance interpreter is not executable on this machine: %s",
            python_path,
        )
        return False

    try:
        probe = subprocess.run(
            [str(python_path), "--version"],
            cwd=PORTFOLIO_REBALANCE_DIR,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as error:
        logging.info(
            "Portfolio rebalance interpreter probe failed for %s: %s",
            python_path,
            error,
        )
        return False

    if probe.returncode != 0:
        logging.info(
            "Portfolio rebalance interpreter probe returned %s for %s. stderr=%r",
            probe.returncode,
            python_path,
            probe.stderr.strip(),
        )
        return False

    return True


def _select_python_path() -> Path | None:
    for candidate in _candidate_python_paths():
        if _is_usable_python_executable(candidate):
            return candidate
    return None


def _load_portfolio_rebalance_env_overrides() -> dict[str, str]:
    if not PORTFOLIO_REBALANCE_ENV_FILE.is_file():
        logging.info(
            "Portfolio rebalance env file not found: %s",
            PORTFOLIO_REBALANCE_ENV_FILE,
        )
        return {}

    overrides: dict[str, str] = {}
    for env_var, value in dotenv_values(PORTFOLIO_REBALANCE_ENV_FILE).items():
        if value is None:
            continue
        overrides[env_var] = value.strip()

    logging.info(
        "Loaded %s portfolio rebalance env override(s) from %s",
        len(overrides),
        PORTFOLIO_REBALANCE_ENV_FILE,
    )
    return overrides


def _build_portfolio_rebalance_env() -> dict[str, str]:
    merged_env = os.environ.copy()
    merged_env.update(_load_portfolio_rebalance_env_overrides())
    return merged_env


def _missing_required_env_vars(env: dict[str, str]) -> list[str]:
    return [
        env_var
        for env_var in REQUIRED_PORTFOLIO_REBALANCE_ENV_VARS
        if not env.get(env_var, "").strip()
    ]


def rebalance_portfolio() -> str:
    if not PORTFOLIO_REBALANCE_DIR.is_dir():
        logging.error(
            "Portfolio rebalance directory does not exist: %s",
            PORTFOLIO_REBALANCE_DIR,
        )
        return "I could not find the portfolio rebalance project."

    if not PORTFOLIO_REBALANCE_MAIN.is_file():
        logging.error(
            "Portfolio rebalance entrypoint does not exist: %s",
            PORTFOLIO_REBALANCE_MAIN,
        )
        return "I found the portfolio rebalance folder, but main.py is missing."

    python_path = _select_python_path()
    if python_path is None:
        logging.error(
            "No usable portfolio rebalance interpreter was found. Tried: %s",
            [str(candidate) for candidate in _candidate_python_paths()],
        )
        return (
            "I found the rebalance project, but none of its configured Python environments "
            "are usable on this machine."
        )

    command_env = _build_portfolio_rebalance_env()
    missing_env_vars = _missing_required_env_vars(command_env)
    if missing_env_vars:
        logging.error(
            "Portfolio rebalance cannot start because required environment variables are missing: %s",
            missing_env_vars,
        )
        missing_env_vars_text = ", ".join(missing_env_vars)
        return (
            "I can run the portfolio rebalance tool now, but the required configuration is still missing. "
            f"Please add these environment variables first: {missing_env_vars_text}."
        )

    command = [str(python_path), "main.py"]
    logging.info(
        "Running portfolio rebalance command: %s (cwd=%s)",
        command,
        PORTFOLIO_REBALANCE_DIR,
    )

    try:
        completed_process = subprocess.run(
            command,
            cwd=PORTFOLIO_REBALANCE_DIR,
            env=command_env,
            capture_output=True,
            text=True,
            timeout=PORTFOLIO_REBALANCE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logging.error(
            "Portfolio rebalance timed out after %s seconds.",
            PORTFOLIO_REBALANCE_TIMEOUT_SECONDS,
        )
        return "The portfolio rebalance run timed out before it finished."
    except Exception as error:
        logging.exception("Portfolio rebalance run crashed before completion.")
        return f"I hit an error while starting the portfolio rebalance run: {error}."

    stdout_tail = _tail_non_empty_lines(completed_process.stdout)
    stderr_tail = _tail_non_empty_lines(completed_process.stderr)

    if completed_process.returncode == 0:
        logging.info("Portfolio rebalance finished successfully.")
        if stdout_tail:
            logging.info("Portfolio rebalance output tail: %s", stdout_tail)
            return f"Portfolio rebalance finished successfully. Final update: {stdout_tail}"
        return "Portfolio rebalance finished successfully."

    logging.error(
        "Portfolio rebalance failed with exit code %s. stdout tail=%r stderr tail=%r",
        completed_process.returncode,
        stdout_tail,
        stderr_tail,
    )

    if stderr_tail:
        return (
            f"Portfolio rebalance failed with exit code {completed_process.returncode}. "
            f"Final error: {stderr_tail}"
        )
    if stdout_tail:
        return (
            f"Portfolio rebalance failed with exit code {completed_process.returncode}. "
            f"Final update: {stdout_tail}"
        )
    return f"Portfolio rebalance failed with exit code {completed_process.returncode}."
