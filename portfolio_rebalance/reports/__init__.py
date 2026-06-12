from __future__ import annotations

from typing import Any

__all__ = ["generate_rebalance_report", "save_portfolio_state_csv"]


def generate_rebalance_report(*args: Any, **kwargs: Any) -> str:
    from .rebalance_report import generate_rebalance_report as _generate_rebalance_report

    return _generate_rebalance_report(*args, **kwargs)


def save_portfolio_state_csv(*args: Any, **kwargs: Any) -> str:
    from .portfolio_state import save_portfolio_state_csv as _save_portfolio_state_csv

    return _save_portfolio_state_csv(*args, **kwargs)
