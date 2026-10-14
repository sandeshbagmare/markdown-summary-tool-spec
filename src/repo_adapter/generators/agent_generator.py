"""Generate an agent definition for the adapted tool."""

from __future__ import annotations

import textwrap
from pathlib import Path

from repo_adapter.models import RepoProfile


def generate_agent(profile: RepoProfile, output_dir: str | Path, agent_name: str = "repo-adapter-agent") -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    extra_list = ", ".join(a.name for a in profile.extra_arguments) or "none"

    content = textwrap.dedent(f"""\
        ---
        name: {agent_name}
        description: Adapt Markdown Summary / Visualization tools to {profile.repo_name}
        tools: [create_markdown_summary, create_visualization]
        ---

        # Agent: {agent_name}

        > Auto-generated for **{profile.repo_name}** — adapts tools to this repo's data shape.

        ## Purpose

        This agent knows how to reshape the Markdown Summary and Visualization tools
        for the current repository:

        - **Sampling:** `{profile.sampling.strategy}` — {profile.sampling.description}
        - **Extra args:** {extra_list}
        - **Connectors:** {", ".join(profile.connectors_needed)}
        - **Datasets:** {len(profile.datasets)} detected

        ## Instructions

        1. Run `RepoAnalyzer` on the target repo to get a fresh `RepoProfile`.
        2. Use `ToolAdapter.from_profile(profile)` to generate the adapted tool.
        3. Wire the adapted tool into DeepAgent:

        ```python
        from deepagents import create_deep_agent
        from adapted_tool import create_markdown_summary  # generated

        agent = create_deep_agent(
            model="claude-fable-5.1",
            tools=[create_markdown_summary],
            system_prompt="You are a data assistant for {profile.repo_name}.",
        )
        ```

        4. Verify with `pytest -q` and `python examples/demo.py`.

        ## When to Re-adapt

        - New data files added
        - Sampling requirements changed (e.g., data grew 10x)
        - New columns needing extra arguments (e.g., `lm_count`, `discount`)
        - Connector changes (new API, DB)

        Re-run:

        ```python
        from repo_adapter import RepoAnalyzer, ToolAdapter
        profile = RepoAnalyzer("{profile.repo_path}").analyze()
        ToolAdapter.from_profile(profile).write("./adapted")
        ```
        """)
    path = out / f"{agent_name}.md"
    path.write_text(content, encoding="utf-8")
    return path
