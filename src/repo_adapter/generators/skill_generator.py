"""Generate a SKILL.md for the adapted tool."""

from __future__ import annotations

import textwrap
from pathlib import Path

from repo_adapter.models import RepoProfile


def generate_skill(profile: RepoProfile, output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sampling = profile.sampling
    extra = ", ".join(f"`{a.name}` ({a.type}, default={a.default!r})" for a in profile.extra_arguments) or "none"
    datasets = "\n".join(f"- **{d.name}**: {d.row_count} rows, {len(d.columns)} cols — {', '.join(c.name for c in d.columns[:6])}" for d in profile.datasets) or "- No datasets detected — use inline_json / url at runtime."

    content = textwrap.dedent(f"""\
        ---
        name: adapt-tool
        description: Adapt the Markdown Summary / Visualization tools to this repo
        ---

        # Skill: Adapt Tool to This Repo

        > Auto-generated for **{profile.repo_name}** (`{profile.repo_path}`)

        ## Repo Profile

        - **Language:** {profile.language}  |  **Framework:** {profile.framework or "none"}
        - **Sampling:** `{sampling.strategy}` — {sampling.description}
        - **Connectors:** {", ".join(profile.connectors_needed)}
        - **Extra arguments:** {extra}

        ### Datasets Detected

        {datasets}

        ## How to Adapt

        ```python
        from repo_adapter import RepoAnalyzer, ToolAdapter

        profile = RepoAnalyzer("{profile.repo_path}").analyze()
        adapter = ToolAdapter.from_profile(profile)
        path = adapter.write("./adapted")
        print(f"Adapted tool written to {{path}}")
        ```

        ## Sampling

        Strategy `{sampling.strategy}` is configured for this repo.
        Override at call time via `options_json`:

        ```json
        {{"sampling_strategy": "random", "sample_size": 5000, "seed": 42}}
        ```

        Available strategies: `full`, `random`, `stratified`, `reservoir`, `window`.

        ## Extra Arguments

        These are injected into `options` and available in the pipeline:

        ```python
        # In adapted tool:
        # options["discount_column"], options["lm_count_column"], etc.
        ```

        ## Verification

        ```powershell
        pip install -e ".[dev]"
        pytest -q
        python examples/demo.py
        ```
        """)
    path = out / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path
