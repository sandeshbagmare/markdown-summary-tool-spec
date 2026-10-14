import json
import tempfile
from pathlib import Path

from repo_adapter import RepoAnalyzer, ToolAdapter
from repo_adapter.models import SamplingConfig
from repo_adapter.sampling import apply_sampling


def test_analyzer_on_this_repo():
    profile = RepoAnalyzer(".").analyze()
    assert profile.repo_name != ""
    assert profile.language in ("python", "typescript", "go", "java", "unknown")
    assert profile.sampling.strategy in ("full", "random", "stratified", "reservoir", "window")


def test_analyzer_with_data_files():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "data.csv").write_text("name,amount\nAlice,100\nBob,200\n", encoding="utf-8")
        profile = RepoAnalyzer(tmp).analyze()
        assert len(profile.datasets) == 1
        assert profile.datasets[0].row_count == 2


def test_sampling_strategies():
    rows = [{"x": i} for i in range(100)]
    for strategy in ("random", "reservoir", "window"):
        cfg = SamplingConfig(strategy=strategy, sample_size=10, seed=42)
        out = apply_sampling(rows, cfg)
        assert len(out) == 10
    cfg = SamplingConfig(strategy="stratified", sample_size=10, stratify_by="x", seed=42)
    out = apply_sampling([{"x": i % 3, "y": i} for i in range(30)], cfg)
    assert len(out) == 10
    cfg = SamplingConfig(strategy="full")
    out = apply_sampling(rows, cfg)
    assert len(out) == 100


def test_adapter_generates_tool():
    profile = RepoAnalyzer(".").analyze()
    adapter = ToolAdapter.from_profile(profile)
    code = adapter.generate_tool_code()
    assert "def create_markdown_summary" in code
    assert "_apply_sampling" in code


def test_adapter_write_and_invoke():
    with tempfile.TemporaryDirectory() as tmp:
        profile = RepoAnalyzer(".").analyze()
        adapter = ToolAdapter.from_profile(profile)
        path = adapter.write(tmp)
        assert path.exists()
        # Import and invoke the generated tool
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("adapted_tool_test", str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["adapted_tool_test"] = mod
        spec.loader.exec_module(mod)
        tool = mod.create_markdown_summary
        ds = json.dumps([{"kind": "inline_json", "name": "t", "data": [{"x": 1}, {"x": 2}]}])
        raw = tool.invoke({"datasets_json": ds, "question": "Summarize"})
        parsed = json.loads(raw)
        assert "markdown" in parsed
        assert parsed["meta"]["verified"] is True


def test_extra_args_in_generated_tool():
    from repo_adapter.models import ArgumentSpec, RepoProfile
    profile = RepoAnalyzer(".").analyze()
    profile.extra_arguments.append(ArgumentSpec(name="lm_count_column", type="str", required=False, default=None, description="LM column"))
    adapter = ToolAdapter.from_profile(profile)
    code = adapter.generate_tool_code()
    assert "lm_count_column" in code
