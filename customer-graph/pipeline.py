"""End-to-end graph build pipeline (README Steps 6 -> 7 -> 8 -> 9).

Runs the full ingestion sequence in the correct order so the graph can be
built unattended (e.g. inside Docker). Each step is an existing standalone
script, so you can still run them individually for the manual workflow.

Usage:
    python pipeline.py
"""

import subprocess
import sys

STEPS = [
    ("Step 6 — Unstructured PDF ingestion", ["python", "unstructured_ingest.py"]),
    ("Step 7 — Structured CSV import", ["python", "load_structured.py"]),
    ("Step 8 — Cross-link structured & unstructured", ["python", "create_cross_links.py"]),
    ("Step 9 — Post-processing (embeddings + vector index)", ["python", "ingest_post_processing.py"]),
]


def main():
    for title, command in STEPS:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70, flush=True)
        result = subprocess.run(command)
        if result.returncode != 0:
            print(f"\nFAILED: {' '.join(command)} (exit code {result.returncode})")
            sys.exit(result.returncode)

    print("\n" + "=" * 70)
    print("Graph build complete. Run the agent with:")
    print("  docker compose run --rm agent")
    print("or manually:")
    print("  cd graphrag && python cli_agent.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
