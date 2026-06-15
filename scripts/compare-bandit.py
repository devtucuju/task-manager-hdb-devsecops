#!/usr/bin/env python3
"""Compara dois relatórios JSON do Bandit e exibe tabela antes/depois."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_report(path: Path) -> list[dict]:
    if not path.exists():
        print(f"Arquivo não encontrado: {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text())
    return data.get("results", [])


def summarize(results: list[dict]) -> Counter:
    return Counter(item.get("issue_severity", "UNDEFINED") for item in results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparar relatórios Bandit JSON")
    parser.add_argument("before", type=Path, help="Relatório anterior (ex.: bandit-report-before.json)")
    parser.add_argument("after", type=Path, help="Relatório atual (ex.: bandit-report-after.json)")
    args = parser.parse_args()

    before_results = load_report(args.before)
    after_results = load_report(args.after)
    before_counts = summarize(before_results)
    after_counts = summarize(after_results)

    severities = sorted(set(before_counts) | set(after_counts))

    print("\n=== Comparação Bandit (antes → depois) ===\n")
    print(f"{'Severidade':<12} {'Antes':>8} {'Depois':>8} {'Δ':>8}")
    print("-" * 40)
    for sev in severities:
        b = before_counts.get(sev, 0)
        a = after_counts.get(sev, 0)
        delta = a - b
        sign = "+" if delta > 0 else ""
        print(f"{sev:<12} {b:>8} {a:>8} {sign}{delta:>7}")

    total_before = len(before_results)
    total_after = len(after_results)
    print("-" * 40)
    print(f"{'TOTAL':<12} {total_before:>8} {total_after:>8} {total_after - total_before:>+8}")

    removed = {r["test_id"] for r in before_results} - {r["test_id"] for r in after_results}
    added = {r["test_id"] for r in after_results} - {r["test_id"] for r in before_results}

    if removed:
        print(f"\n✓ Regras eliminadas ({len(removed)}): {', '.join(sorted(removed))}")
    if added:
        print(f"\n✗ Novas regras ({len(added)}): {', '.join(sorted(added))}")

    if total_after < total_before:
        print(f"\nMelhoria: {total_before - total_after} issue(s) a menos.")
    elif total_after > total_before:
        print(f"\nAtenção: {total_after - total_before} issue(s) a mais.")
    else:
        print("\nSem alteração no total de issues.")


if __name__ == "__main__":
    main()
