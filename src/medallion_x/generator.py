"""Synthetic event stream; every row and fault is synthetic."""
from __future__ import annotations
import csv
from pathlib import Path

FIELDS = ["event_id", "transaction_id", "event_at", "ingested_at", "status", "amount_cents", "gross_amount_cents", "currency", "payload_schema_version", "customer_id"]


def _row(eid: str, tx: str, minute: int, state: str, amount: int, *, version: int = 1, ingested: int | None = None) -> dict[str, str]:
    def ts(m: int) -> str:
        return f"2026-10-01T08:{m:02d}:00Z"
    return {
        "event_id": eid, "transaction_id": tx, "event_at": ts(minute),
        "ingested_at": ts(minute if ingested is None else ingested),
        "status": state, "amount_cents": str(amount) if version == 1 else "",
        "gross_amount_cents": str(amount) if version == 2 else "",
        "currency": "MXN", "payload_schema_version": str(version),
        "customer_id": f"synthetic-{tx}",
    }


def make_events(scenario: str = "clean") -> list[dict[str, str]]:
    if scenario not in {"clean", "regression", "poisoned", "late"}:
        raise ValueError(f"Unknown scenario {scenario!r}")
    rows = [
        _row("e01", "tx-001", 0, "authorized", 10000),
        _row("e02", "tx-001", 2, "settled", 10000),
        _row("e03", "tx-002", 3, "settled", 17500),
        _row("e04", "tx-003", 4, "authorized", 20000),
        _row("e05", "tx-003", 8, "chargeback", 20000),
        _row("e06", "tx-004", 6, "authorized", 5000),
        _row("e07", "tx-005", 7, "settled", 12000, version=2),
        _row("e08", "tx-006", 9, "settled", 5000),
        _row("e09", "tx-006", 11, "refunded", 5000),
        _row("e10", "tx-007", 13, "refunded", 30000),
        # Arrives late but has an earlier event time: must not undo refund.
        _row("e11", "tx-007", 10, "settled", 30000, ingested=20),
        _row("e12", "tx-008", 14, "authorized", 11000),
    ]
    rows.insert(5, dict(rows[1]))  # exact duplicate of e02
    if scenario == "late":
        # A late-arriving correction with newer EVENT time changes true current state.
        rows.append(_row("e13", "tx-002", 18, "refunded", 17500, ingested=28))
    if scenario == "poisoned":
        rows += [
            _row("bad01", "tx-009", 22, "settled", 9000, version=3),
            _row("bad02", "tx-010", 23, "settled", -4000),
            {**dict(rows[1]), "amount_cents": "999999"},  # same event ID with different payload
        ]
    return rows


def write_csv(events: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)
