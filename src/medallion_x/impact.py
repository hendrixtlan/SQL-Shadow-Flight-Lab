"""Computes blast radius using dbt manifest child_map, with declared-graph fallback."""
from __future__ import annotations
from collections import deque
import json
from pathlib import Path
from typing import Any

SOURCE = "source.medallion_x.bronze.raw_payment_events"


def traverse(graph: dict[str, list[str]], root: str = SOURCE) -> list[str]:
    seen = {root}
    affected: list[str] = []
    queue = deque([root])
    while queue:
        for child in graph.get(queue.popleft(), []):
            if child not in seen:
                seen.add(child)
                affected.append(child)
                queue.append(child)
    return affected


def compute_impact(*, graph_file: Path, manifest_file: Path | None = None) -> dict[str, Any]:
    graph: dict[str, list[str]] = json.loads(graph_file.read_text(encoding="utf-8"))
    provenance = "declared_fallback_graph"
    if manifest_file and manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        children = manifest.get("child_map")
        if not isinstance(children, dict) or SOURCE not in children:
            raise ValueError("manifest does not contain the expected dbt source or child_map")
        # Non-dbt consumer edges are maintained separately.
        graph = {k: list(v) for k, v in children.items()}
        graph["model.medallion_x.mart_daily_payments"] = list(set(graph.get("model.medallion_x.mart_daily_payments", [])) | {"consumer.powerbi.payment_exposure"})
        provenance = "dbt_manifest_plus_declared_consumers"
    return {"changed_node": SOURCE, "graph_provenance": provenance, "affected_nodes": traverse(graph)}
