"""Sampling strategies — pluggable, deterministic, repo-adaptable.

Strategies:
- full: no sampling
- random: uniform random sample
- stratified: sample per group (stratify_by column)
- reservoir: reservoir sampling (streaming-friendly)
- window: sliding window (most recent N)
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from repo_adapter.models import SamplingConfig


def apply_sampling(rows: list[dict[str, Any]], config: SamplingConfig) -> list[dict[str, Any]]:
    if not rows:
        return rows
    strategy = config.strategy
    n = config.sample_size
    if strategy == "full" or n is None or len(rows) <= n:
        return rows
    if strategy == "random":
        return _random_sample(rows, n, config.seed)
    if strategy == "stratified":
        return _stratified_sample(rows, n, config.stratify_by, config.seed)
    if strategy == "reservoir":
        return _reservoir_sample(rows, n, config.seed)
    if strategy == "window":
        return _window_sample(rows, n, config.window_size)
    return _random_sample(rows, n, config.seed)


def _random_sample(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return rng.sample(rows, n)


def _stratified_sample(rows: list[dict[str, Any]], n: int, stratify_by: str | None, seed: int) -> list[dict[str, Any]]:
    if not stratify_by:
        return _random_sample(rows, n, seed)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = str(r.get(stratify_by, "__null__"))
        groups[key].append(r)
    rng = random.Random(seed)
    per_group = max(1, n // len(groups))
    out: list[dict[str, Any]] = []
    for grp_rows in groups.values():
        k = min(per_group, len(grp_rows))
        out.extend(rng.sample(grp_rows, k))
    if len(out) > n:
        out = rng.sample(out, n)
    elif len(out) < n:
        remaining = [r for r in rows if r not in out]
        need = min(n - len(out), len(remaining))
        if need > 0:
            out.extend(rng.sample(remaining, need))
    return out


def _reservoir_sample(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    reservoir = rows[:n]
    for i, row in enumerate(rows[n:], start=n):
        j = rng.randint(0, i)
        if j < n:
            reservoir[j] = row
    return reservoir


def _window_sample(rows: list[dict[str, Any]], n: int, window_size: int | None) -> list[dict[str, Any]]:
    if window_size is not None and window_size < n:
        return rows[-window_size:]
    return rows[-n:]
