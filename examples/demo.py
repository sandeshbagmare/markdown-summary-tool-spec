"""Demo: run pipeline on sample data."""
from markdown_summary_tool.engine.pipeline import run
import json

req = {
    "datasets": [
        {"kind": "inline_json", "name": "orders", "data": [
            {"customer": "Alice", "amount": 120.5, "region": "East"},
            {"customer": "Bob", "amount": 80.0, "region": "West"},
            {"customer": "Alice", "amount": 200.0, "region": "East"},
            {"customer": "Carol", "amount": 50.0, "region": "West"},
        ]}
    ],
    "question": "Summarize total and average order amount by region",
}

result = run(req)
print("=== MARKDOWN ===")
print(result["markdown"])
print("\n=== FACTS ===")
print(json.dumps(result["facts"][:5], indent=2))
print("\n=== META ===")
print(result["meta"])
