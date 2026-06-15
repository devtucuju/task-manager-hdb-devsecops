#!/usr/bin/env bash
# =============================================================================
# dast-full-cycle.sh — Ciclo completo: preparar → scan → arquivar
# =============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-baseline}"
"$ROOT/scripts/dast-prepare.sh"
"$ROOT/scripts/dast-run.sh" "$MODE"
echo ""
echo ">>> Ciclo DAST concluído. Revise reports/zap/latest/"
echo ">>> Limpeza: ./scripts/dast-cleanup.sh"
