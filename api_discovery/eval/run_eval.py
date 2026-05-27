"""
Precision@1 and Precision@3 evaluation against the golden query set.

Usage (from api_discovery/):
    python eval/run_eval.py
    python eval/run_eval.py --top-k 5 --verbose
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.retrieval import search
from rich.console import Console
from rich.table import Table

console = Console()
GOLDEN_PATH = Path(__file__).parent / "golden.json"


def run(top_k: int = 5, verbose: bool = False) -> None:
    cases = json.loads(GOLDEN_PATH.read_text())

    hits_at_1 = 0
    hits_at_3 = 0
    total = len(cases)

    rows = []

    for case in cases:
        qid = case["id"]
        query = case["query"]
        expected = case["expected_capability_id"]
        expected_domain = case["expected_domain"]

        results = search(query, org_id="default", top_k=top_k)
        returned_ids = [r.capability.capability_id for r in results]
        returned_domains = [r.capability.domain for r in results]

        hit1 = expected in returned_ids[:1]
        hit3 = expected in returned_ids[:3]

        if hit1:
            hits_at_1 += 1
        if hit3:
            hits_at_3 += 1

        top_result = results[0] if results else None
        top_name = top_result.capability.tool_name if top_result else "—"
        top_score = f"{top_result.score:.4f}" if top_result else "—"
        domain_ok = expected_domain in returned_domains[:3]

        status = "[green]P@1[/green]" if hit1 else ("[yellow]P@3[/yellow]" if hit3 else "[red]MISS[/red]")
        rows.append((str(qid), query, top_name, top_score, status))

        if verbose and not hit1:
            console.print(f"\n  [dim]Q{qid}:[/dim] {query}")
            console.print(f"    expected:  {expected}")
            for i, r in enumerate(results[:3]):
                marker = "[green]✓[/green]" if r.capability.capability_id == expected else " "
                console.print(f"    [{i+1}] {marker} {r.capability.capability_id}  score={r.score:.4f}")

    # ── results table ──────────────────────────────────────────────────────────
    table = Table(title="Eval Results — Golden Set", show_lines=False, box=None, pad_edge=False)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("query", min_width=35)
    table.add_column("top match", style="cyan", min_width=38)
    table.add_column("score", justify="right", width=8)
    table.add_column("hit", justify="center", width=6)

    for row in rows:
        table.add_row(*row)

    console.print()
    console.print(table)

    p1 = hits_at_1 / total
    p3 = hits_at_3 / total

    console.print()
    console.print(f"  Precision@1  [bold]{'[green]' if p1 >= 0.8 else '[yellow]'}{p1:.0%}{'[/green]' if p1 >= 0.8 else '[/yellow]'}[/bold]   ({hits_at_1}/{total})")
    console.print(f"  Precision@3  [bold]{'[green]' if p3 >= 0.8 else '[yellow]'}{p3:.0%}{'[/green]' if p3 >= 0.8 else '[/yellow]'}[/bold]   ({hits_at_3}/{total})")
    console.print(f"\n  Phase 2 target: P@1 ≥ 80%  {'[green]PASS[/green]' if p1 >= 0.8 else '[red]FAIL[/red]'}")
    console.print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    run(top_k=args.top_k, verbose=args.verbose)
