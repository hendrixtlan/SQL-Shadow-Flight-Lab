"""Small reference replay oracle. NOT the Fabric SQL execution engine."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

SUPPORTED_VERSIONS = {"1": "amount_cents", "2": "gross_amount_cents"}
STATUSES = {"authorized", "settled", "refunded", "chargeback"}


def _timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp_missing")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp_invalid") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamp_timezone_missing")
    return dt.astimezone(timezone.utc).isoformat()


def normalize(raw: dict[str, str]) -> dict[str, Any]:
    version = raw.get("payload_schema_version")
    if version not in SUPPORTED_VERSIONS:
        raise ValueError("unapproved_schema_version")
    status = raw.get("status")
    if status not in STATUSES:
        raise ValueError("unknown_status")
    if raw.get("currency") != "MXN":
        raise ValueError("unsupported_currency")
    event_id, tx_id = raw.get("event_id", ""), raw.get("transaction_id", "")
    if not event_id or not tx_id:
        raise ValueError("missing_business_key")
    value = raw.get(SUPPORTED_VERSIONS[version], "")
    if not isinstance(value, str) or not value.lstrip("-").isdecimal():
        raise ValueError("invalid_amount_cents")
    cents = int(value)
    if cents <= 0 or cents > 10**12:
        raise ValueError("amount_out_of_range")
    return {
        "event_id": event_id, "transaction_id": tx_id,
        "event_at": _timestamp(raw.get("event_at")),
        "ingested_at": _timestamp(raw.get("ingested_at")),
        "status": status, "amount_cents": cents, "currency": "MXN",
    }


def replay(raw_events: list[dict[str, str]], *, model_version: str = "stable") -> dict[str, Any]:
    """Deterministic last-event-wins CDC and business metrics.

    model_version='buggy-authorized-as-settled' is a deliberately injected semantic regression.
    """
    if model_version not in {"stable", "buggy-authorized-as-settled"}:
        raise ValueError("unknown_model_version")
    accepted: dict[str, dict[str, Any]] = {}
    quarantined: list[dict[str, str]] = []
    duplicates = 0
    for i, raw in enumerate(raw_events):
        try:
            item = normalize(raw)
        except ValueError as exc:
            quarantined.append({"source_index": i, "event_id": raw.get("event_id", ""), "reason": str(exc)})
            continue
        earlier = accepted.get(item["event_id"])
        if earlier is not None:
            if item == earlier:
                duplicates += 1
            else:
                quarantined.append({"source_index": i, "event_id": item["event_id"], "reason": "conflicting_event_id"})
            continue
        accepted[item["event_id"]] = item
    current: dict[str, dict[str, Any]] = {}
    for item in accepted.values():
        tx = item["transaction_id"]
        old = current.get(tx)
        key = (item["event_at"], item["ingested_at"], item["event_id"])
        if old is None or key > (old["event_at"], old["ingested_at"], old["event_id"]):
            current[tx] = item

    settled_states = {"settled"}
    if model_version == "buggy-authorized-as-settled":
        settled_states.add("authorized")
    settled = [r for r in current.values() if r["status"] in settled_states]
    authorized = [r for r in current.values() if r["status"] == "authorized"]
    canonical_state = {
        tx: {"status": row["status"], "amount_cents": row["amount_cents"], "event_id": row["event_id"]}
        for tx, row in sorted(current.items())
    }
    encoded = json.dumps(canonical_state, sort_keys=True, separators=(",", ":"))
    return {
        "model_version": model_version,
        "accepted_count": len(accepted), "duplicate_count": duplicates,
        "quarantine": sorted(quarantined, key=lambda x: (x["event_id"], x["reason"], x["source_index"])),
        "current_state": canonical_state,
        "state_hash": hashlib.sha256(encoded.encode()).hexdigest(),
        "state_counts": dict(sorted(Counter(r["status"] for r in current.values()).items())),
        "metrics": {
            "current_settled_amount_cents": sum(r["amount_cents"] for r in settled),
            "currently_settled_transactions": len(settled),
            "authorized_exposure_cents": sum(r["amount_cents"] for r in authorized),
        },
    }


def snapshot_hash(raw_events: list[dict[str, str]]) -> str:
    """Permutation-invariant but duplicate-sensitive source identifier."""
    rows = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in raw_events]
    return hashlib.sha256(("\n".join(sorted(rows))).encode()).hexdigest()
