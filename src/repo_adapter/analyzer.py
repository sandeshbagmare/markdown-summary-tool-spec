"""RepoAnalyzer — inspect any repo and produce a RepoProfile.

Handles:
- File-system scan (data files, configs, schemas)
- Sampling detection (how the repo samples / paginates data)
- Extra-argument detection (what extra knobs the repo needs)
- Framework / language detection
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from repo_adapter.models import ArgumentSpec, ColumnInfo, DatasetInfo, RepoProfile, SamplingConfig

DATA_EXTENSIONS = {".csv", ".json", ".jsonl", ".parquet", ".tsv", ".xlsx", ".db", ".sqlite"}
CONFIG_FILES = {"pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "pom.xml"}
SAMPLING_KEYWORDS = re.compile(r"sample|sampling|reservoir|stratified|window|batch|chunk|paginate|cursor|offset|limit", re.I)
ARG_KEYWORDS = re.compile(r"(extra|additional|custom)\s*(arg|param|option|field|column)", re.I)


def _infer_type(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None and v != ""]
    if not non_null:
        return "string"
    has_int = has_float = has_bool = False
    for v in non_null:
        if isinstance(v, bool):
            has_bool = True
        elif isinstance(v, int):
            has_int = True
        elif isinstance(v, float):
            has_float = True
        elif isinstance(v, str):
            try:
                int(v)
                has_int = True
            except ValueError:
                try:
                    float(v)
                    has_float = True
                except ValueError:
                    return "string"
    if has_bool and not (has_int or has_float):
        return "boolean"
    if has_float:
        return "float"
    if has_int:
        return "integer"
    return "string"


def _profile_rows(rows: list[dict[str, Any]], name: str, source_kind: str = "inline_json", file_path: str | None = None) -> DatasetInfo:
    if not rows:
        return DatasetInfo(name=name, row_count=0, source_kind=source_kind, file_path=file_path)
    all_cols: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                all_cols.append(k)
    columns: list[ColumnInfo] = []
    for col in all_cols:
        vals = [r.get(col) for r in rows]
        non_null = [v for v in vals if v is not None and v != ""]
        null_rate = 1 - len(non_null) / len(rows) if rows else 0
        distinct = len(set(str(v) for v in non_null)) if non_null else 0
        columns.append(ColumnInfo(
            name=col, inferred_type=_infer_type(vals),
            sample_values=non_null[:3], null_rate=round(null_rate, 4), distinct_count=distinct,
        ))
    return DatasetInfo(name=name, row_count=len(rows), columns=columns, sample_rows=rows[:5], source_kind=source_kind, file_path=file_path)


def _count_file_rows(path: Path) -> int | None:
    """Fast row count without loading full data (for sampling decisions)."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".csv", ".tsv"):
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                # count lines minus header
                n = sum(1 for _ in f) - 1
                return max(n, 0)
        elif suffix == ".json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        return len(v)
                return 1
            return 0
        elif suffix == ".jsonl":
            with open(path, encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
    except Exception:
        return None
    return None


def _load_rows_from_file(path: Path, max_rows: int = 5000) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv" or suffix == ".tsv":
            delim = "\t" if suffix == ".tsv" else ","
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=delim)
                return [dict(r) for _, r in zip(range(max_rows), reader)]
        elif suffix == ".json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [r for r in data[:max_rows] if isinstance(r, dict)]
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        return v[:max_rows]
                return [data]
            return []
        elif suffix == ".jsonl":
            rows: list[dict[str, Any]] = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
                        if len(rows) >= max_rows:
                            break
            return rows
    except Exception:
        return []
    return []


class RepoAnalyzer:
    """Analyze any repository and produce a RepoProfile."""

    def __init__(self, repo_path: str | Path, max_scan_depth: int = 4, max_rows_per_file: int = 5000) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.max_scan_depth = max_scan_depth
        self.max_rows_per_file = max_rows_per_file

    def analyze(self) -> RepoProfile:
        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repo path does not exist: {self.repo_path}")

        repo_name = self.repo_path.name
        language = self._detect_language()
        framework = self._detect_framework()
        datasets = self._scan_datasets()
        sampling = self._detect_sampling(datasets)
        extra_args = self._detect_extra_arguments(datasets)
        connectors = self._detect_connectors()
        warnings: list[str] = []
        if not datasets:
            warnings.append("No data files detected — tool will rely on inline_json / inline_csv / url connectors at runtime.")

        return RepoProfile(
            repo_path=str(self.repo_path),
            repo_name=repo_name,
            language=language,
            framework=framework,
            datasets=datasets,
            sampling=sampling,
            extra_arguments=extra_args,
            connectors_needed=connectors,
            warnings=warnings,
            raw_notes=self._build_notes(datasets, sampling, extra_args),
        )

    def _detect_language(self) -> str:
        ext_counts: dict[str, int] = {}
        for p in self.repo_path.rglob("*"):
            if p.is_file() and p.suffix:
                ext_counts[p.suffix] = ext_counts.get(p.suffix, 0) + 1
        if ext_counts.get(".py", 0) > 0:
            return "python"
        if ext_counts.get(".ts", 0) or ext_counts.get(".js", 0):
            return "typescript"
        if ext_counts.get(".go", 0):
            return "go"
        if ext_counts.get(".java", 0):
            return "java"
        return "unknown"

    def _detect_framework(self) -> str | None:
        if (self.repo_path / "pyproject.toml").exists():
            text = (self.repo_path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
            if "fastapi" in text.lower():
                return "fastapi"
            if "django" in text.lower():
                return "django"
            if "flask" in text.lower():
                return "flask"
        if (self.repo_path / "package.json").exists():
            return "node"
        return None

    def _scan_datasets(self) -> list[DatasetInfo]:
        datasets: list[DatasetInfo] = []
        for p in self.repo_path.rglob("*"):
            if not p.is_file():
                continue
            depth = len(p.relative_to(self.repo_path).parts)
            if depth > self.max_scan_depth:
                continue
            if any(part.startswith(".") or part in ("__pycache__", "node_modules", "venv", ".venv", "build", "dist") for part in p.parts):
                continue
            if p.suffix.lower() in DATA_EXTENSIONS:
                rows = _load_rows_from_file(p, self.max_rows_per_file)
                if rows:
                    name = p.stem.replace("-", "_").replace(" ", "_")
                    info = _profile_rows(rows, name=name, source_kind="file", file_path=str(p.relative_to(self.repo_path)))
                    # Use true file row count for sampling decisions (not capped sample)
                    true_count = _count_file_rows(p)
                    if true_count is not None and true_count > info.row_count:
                        info.row_count = true_count
                    datasets.append(info)
        return datasets

    def _detect_sampling(self, datasets: list[DatasetInfo]) -> SamplingConfig:
        total_rows = sum(d.row_count for d in datasets)
        if total_rows > 100_000:
            return SamplingConfig(strategy="reservoir", sample_size=10_000, description="Large repo — reservoir sampling recommended.")
        if total_rows > 10_000:
            return SamplingConfig(strategy="random", sample_size=5_000, description="Medium repo — random sampling with seed.")
        # Scan code for sampling hints
        for p in self.repo_path.rglob("*.py"):
            if any(part.startswith(".") for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if SAMPLING_KEYWORDS.search(text):
                    if "stratified" in text.lower():
                        return SamplingConfig(strategy="stratified", sample_size=5_000, description="Code mentions stratified sampling.")
                    if "reservoir" in text.lower():
                        return SamplingConfig(strategy="reservoir", sample_size=5_000, description="Code mentions reservoir sampling.")
                    if "window" in text.lower():
                        return SamplingConfig(strategy="window", window_size=1000, description="Code mentions window sampling.")
            except Exception:
                continue
        return SamplingConfig(strategy="full", description="Small repo — full scan (no sampling needed).")

    def _detect_extra_arguments(self, datasets: list[DatasetInfo]) -> list[ArgumentSpec]:
        args: list[ArgumentSpec] = []
        all_cols = {c.name for d in datasets for c in d.columns}
        # Common extra args inferred from column names
        if any("discount" in c.lower() for c in all_cols):
            args.append(ArgumentSpec(name="discount_column", type="str", required=False, default=None, description="Column containing discount values (if any).", example="discount"))
        if any("lm" in c.lower() or "model" in c.lower() or c.lower() == "llm" for c in all_cols):
            args.append(ArgumentSpec(name="lm_count_column", type="str", required=False, default=None, description="Column for LM / model counting.", example="model"))
        if any("date" in c.lower() or "time" in c.lower() for c in all_cols):
            args.append(ArgumentSpec(name="date_column", type="str", required=False, default=None, description="Date/time column for time-series facts.", example="created_at"))
        # Scan for TODO / extra arg hints in code
        for p in self.repo_path.rglob("*.py"):
            if any(part.startswith(".") for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r"extra_args\s*[:=]\s*\[([^\]]+)\]", text):
                    raw = m.group(1)
                    for token in re.findall(r'"([^"]+)"|\'([^\']+)\'', raw):
                        name = token[0] or token[1]
                        if name and name.isidentifier() and not any(a.name == name for a in args):
                            args.append(ArgumentSpec(name=name, type="str", required=False, description="Detected from code extra_args."))
            except Exception:
                continue
        return args

    def _detect_connectors(self) -> list[str]:
        connectors = ["inline_json", "inline_csv"]
        for p in self.repo_path.rglob("*.py"):
            if any(part.startswith(".") for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if "httpx" in text or "requests" in text or "http" in text.lower():
                    if "url" not in connectors:
                        connectors.append("url")
                if "connector" in text.lower():
                    if "connector" not in connectors:
                        connectors.append("connector")
            except Exception:
                continue
        return connectors

    def _build_notes(self, datasets: list[DatasetInfo], sampling: SamplingConfig, args: list[ArgumentSpec]) -> str:
        lines = [f"Datasets found: {len(datasets)}"]
        for d in datasets:
            lines.append(f"  - {d.name}: {d.row_count} rows, {len(d.columns)} cols ({d.source_kind})")
        lines.append(f"Sampling: {sampling.strategy} ({sampling.description})")
        if args:
            lines.append(f"Extra args: {', '.join(a.name for a in args)}")
        return "\n".join(lines)
