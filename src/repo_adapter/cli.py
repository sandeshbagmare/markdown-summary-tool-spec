"""CLI for repo_adapter — analyze any repo and generate an adapted tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adapt Markdown Summary / Visualization tools to any repo")
    parser.add_argument("--repo", required=True, help="Path to target repository")
    parser.add_argument("--out", default="./adapted", help="Output directory for adapted tool")
    parser.add_argument("--tool-name", default="create_markdown_summary", help="Tool function name")
    parser.add_argument("--module", default="adapted_tool", help="Output module name")
    parser.add_argument("--profile-out", default=None, help="Also write RepoProfile JSON to this path")
    parser.add_argument("--sampling", default=None, choices=["full", "random", "stratified", "reservoir", "window"], help="Override sampling strategy")
    parser.add_argument("--sample-size", type=int, default=None, help="Override sample size")
    args = parser.parse_args(argv)

    from repo_adapter import RepoAnalyzer, ToolAdapter

    print(f"Analyzing {args.repo} ...")
    profile = RepoAnalyzer(args.repo).analyze()
    print(profile.raw_notes)
    print(f"Sampling: {profile.sampling.strategy} — {profile.sampling.description}")
    if profile.extra_arguments:
        print(f"Extra args: {', '.join(a.name for a in profile.extra_arguments)}")
    if profile.warnings:
        for w in profile.warnings:
            print(f"Warning: {w}")

    if args.sampling:
        profile.sampling.strategy = args.sampling  # type: ignore[assignment]
    if args.sample_size:
        profile.sampling.sample_size = args.sample_size

    adapter = ToolAdapter.from_profile(profile, tool_name=args.tool_name, target_module=args.module)
    out_path = adapter.write(args.out)
    print(f"Adapted tool written to {out_path}")

    from repo_adapter.generators import generate_agent, generate_skill
    skill_path = generate_skill(profile, args.out)
    agent_path = generate_agent(profile, args.out)
    print(f"Skill written to {skill_path}")
    print(f"Agent written to {agent_path}")

    if args.profile_out:
        p = Path(args.profile_out)
        p.write_text(json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"Profile written to {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
