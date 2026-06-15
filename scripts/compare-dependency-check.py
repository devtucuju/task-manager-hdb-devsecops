#!/usr/bin/env python3
"""Compara relatórios JSON do OWASP Dependency-Check (CVEs críticas/altas)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_vulns(path: Path) -> dict[str, dict]:
    if not path.exists():
        print(f"Arquivo não encontrado: {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text())
    vulns: dict[str, dict] = {}
    for dep in data.get("dependencies", []):
        for v in dep.get("vulnerabilities", []) or []:
            name = v.get("name", "unknown")
            vulns[name] = {
                "severity": (v.get("severity") or "").upper(),
                "cvss": float((v.get("cvssv3") or {}).get("baseScore") or 0),
                "package": dep.get("fileName", ""),
            }
    return vulns


def is_critical(info: dict) -> bool:
    return info["severity"] == "CRITICAL" or info["cvss"] >= 9.0


def is_high(info: dict) -> bool:
    return info["severity"] == "HIGH" or info["cvss"] >= 7.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparar relatórios Dependency-Check")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()

    before = load_vulns(args.before)
    after = load_vulns(args.after)

    before_crit = {k for k, v in before.items() if is_critical(v)}
    after_crit = {k for k, v in after.items() if is_critical(v)}
    before_high = {k for k, v in before.items() if is_high(v)}
    after_high = {k for k, v in after.items() if is_high(v)}

    print("\n=== Comparação Dependency-Check (antes → depois) ===\n")
    print(f"{'Métrica':<28} {'Antes':>8} {'Depois':>8}")
    print("-" * 48)
    print(f"{'CVEs CRITICAL':<28} {len(before_crit):>8} {len(after_crit):>8}")
    print(f"{'CVEs HIGH+':<28} {len(before_high):>8} {len(after_high):>8}")
    print(f"{'Total CVEs únicas':<28} {len(before):>8} {len(after):>8}")

    resolved = before_crit - after_crit
    new_crit = after_crit - before_crit

    if resolved:
        print(f"\n✓ CVEs CRITICAL resolvidas: {', '.join(sorted(resolved))}")
    if new_crit:
        print(f"\n✗ Novas CVEs CRITICAL: {', '.join(sorted(new_crit))}")

    if len(after_crit) == 0 and len(before_crit) > 0:
        print("\nTodas as CVEs CRITICAL foram eliminadas.")
    elif len(after_crit) == 0:
        print("\nNenhuma CVE CRITICAL detectada.")


if __name__ == "__main__":
    main()
