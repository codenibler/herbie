from __future__ import annotations

import csv
import logging
import os
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_portfolio_state_csv(
    *,
    log_dir: str,
    positions: Iterable[dict],
    account_summary: dict[str, Any] | None,
) -> str:
    output_path = os.path.join(log_dir, "portfolio_state.csv")

    cash_available = 0.0
    if isinstance(account_summary, dict):
        cash_available = _to_float((account_summary.get("cash") or {}).get("availableToTrade")) or 0.0

    holdings_rows: list[dict[str, Any]] = []
    skipped = 0
    for position in positions:
        instrument = position.get("instrument", {}) if isinstance(position, dict) else {}
        ticker = instrument.get("ticker")
        name = instrument.get("shortName") or instrument.get("name") or ""
        quantity = _to_float(position.get("quantityAvailableForTrading")) if isinstance(position, dict) else None
        if not ticker or quantity is None or quantity <= 0:
            skipped += 1
            continue

        current_price = _to_float(position.get("currentPrice"))
        wallet_impact = position.get("walletImpact", {}) if isinstance(position, dict) else {}
        wallet_current_value = _to_float(wallet_impact.get("currentValue"))

        if current_price is None and wallet_current_value is not None and quantity > 0:
            current_price = wallet_current_value / quantity

        position_value = wallet_current_value
        if position_value is None:
            position_value = (current_price or 0.0) * quantity

        holdings_rows.append({
            "ticker": str(ticker),
            "name": str(name),
            "quantity": quantity,
            "current_price": current_price,
            "position_value": position_value,
        })

    holdings_rows.sort(key=lambda row: (-float(row["position_value"]), row["ticker"]))
    holdings_total = sum(float(row["position_value"]) for row in holdings_rows)
    total_portfolio_value = holdings_total + cash_available

    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "row_type",
                "ticker",
                "name",
                "quantity_available_for_trading",
                "current_share_price",
                "position_value",
                "holdings_total",
                "available_to_trade_cash",
                "total_portfolio_value",
            ]
        )
        for row in holdings_rows:
            writer.writerow(
                [
                    "HOLDING",
                    row["ticker"],
                    row["name"],
                    f"{float(row['quantity']):.6f}",
                    f"{float(row['current_price']):.6f}" if row["current_price"] is not None else "",
                    f"{float(row['position_value']):.2f}",
                    "",
                    "",
                    "",
                ]
            )

        writer.writerow(
            [
                "TOTAL",
                "",
                "",
                "",
                "",
                "",
                f"{holdings_total:.2f}",
                f"{cash_available:.2f}",
                f"{total_portfolio_value:.2f}",
            ]
        )

    logger.info(
        "Saved portfolio state CSV: %s (holdings=%s skipped=%s holdings_total=%.2f cash=%.2f total=%.2f)",
        output_path,
        len(holdings_rows),
        skipped,
        holdings_total,
        cash_available,
        total_portfolio_value,
    )
    return output_path
