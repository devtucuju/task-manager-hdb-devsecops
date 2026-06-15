#!/usr/bin/env bash
# =============================================================================
# compare-sast-dast.sh — Resumo lado a lado: relatórios SAST vs DAST (ZAP)
# =============================================================================
# Uso:
#   ./scripts/validate-security.sh
#   ./scripts/zap-baseline-local.sh
#   ./scripts/compare-sast-dast.sh
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SAST_DIR="${SAST_DIR:-$ROOT/reports/after}"
DAST_JSON="${DAST_JSON:-$ROOT/reports/zap/zap-report.json}"

if [ ! -f "$DAST_JSON" ] && [ -f "$ROOT/reports/zap/zap-baseline-report.json" ]; then
  DAST_JSON="$ROOT/reports/zap/zap-baseline-report.json"
fi
if [ -L "$ROOT/reports/zap/latest" ] && [ -f "$ROOT/reports/zap/latest/zap-report.json" ]; then
  DAST_JSON="$ROOT/reports/zap/latest/zap-report.json"
fi

echo "=============================================="
echo " SAST vs DAST — Task Manager DevSecOps"
echo "=============================================="
echo "SAST: $SAST_DIR"
echo "DAST: $DAST_JSON"
echo ""

if ! command -v jq &>/dev/null; then
  echo "ERRO: jq não instalado (sudo apt-get install -y jq)"
  exit 1
fi

echo "=== SAST — Bandit ==="
if [ -f "$SAST_DIR/bandit-report.json" ]; then
  jq -r '
    [.results[]? | .issue_severity] | group_by(.) | .[]
    | "\(.[0]): \(length)"
  ' "$SAST_DIR/bandit-report.json"
  TOTAL=$(jq '[.results[]?] | length' "$SAST_DIR/bandit-report.json")
  echo "Total: $TOTAL"
else
  echo "(sem $SAST_DIR/bandit-report.json — rode ./scripts/validate-security.sh)"
fi

echo ""
echo "=== SAST — Dependency-Check ==="
if [ -f "$SAST_DIR/dependency-check-report.json" ]; then
  jq -r '
    [.dependencies[]?.vulnerabilities[]? | .severity] | group_by(.) | .[]
    | "\(.[0]): \(length)"
  ' "$SAST_DIR/dependency-check-report.json" 2>/dev/null || echo "(formato inesperado)"
  CRIT=$(jq '[.dependencies[]?.vulnerabilities[]? | select(.severity=="CRITICAL")] | length' \
    "$SAST_DIR/dependency-check-report.json" 2>/dev/null || echo 0)
  echo "CRITICAL: $CRIT"
else
  echo "(sem dependency-check-report.json)"
fi

echo ""
echo "=== SAST — Safety ==="
if [ -f "$SAST_DIR/safety-report.json" ]; then
  COUNT=$(jq 'if type == "array" then length else (.vulnerabilities // [] | length) end' \
    "$SAST_DIR/safety-report.json" 2>/dev/null || echo 0)
  echo "Vulnerabilidades em pacotes: $COUNT"
else
  echo "(sem safety-report.json)"
fi

echo ""
echo "=== DAST — OWASP ZAP ==="
if [ -f "$DAST_JSON" ]; then
  jq -r '
    [.site[]?.alerts[]? | .riskdesc | split(" ")[0]] | group_by(.) | .[]
    | "\(.[0]): \(length)"
  ' "$DAST_JSON"
  HIGH=$(jq '[.site[]?.alerts[]? | select(.riskcode == "3" or .riskcode == "4")] | length' \
    "$DAST_JSON")
  echo "High/Critical: $HIGH"
  echo ""
  echo "Top alertas (qualquer risco):"
  jq -r '
    .site[]?.alerts[]?
    | "\(.riskdesc | split(" ")[0]) | [\(.pluginid)] \(.name) (x\(.count))"
  ' "$DAST_JSON" | head -15
else
  echo "(sem relatório ZAP — rode ./scripts/zap-baseline-local.sh)"
  exit 1
fi

echo ""
echo "Matriz detalhada: docs/SAST_vs_DAST.md"
