#!/usr/bin/env bash
# =============================================================================
# dast-run.sh — Executa varredura OWASP ZAP (baseline | full | api)
# =============================================================================
# Uso:
#   ./scripts/dast-prepare.sh
#   ./scripts/dast-run.sh baseline
#   ./scripts/dast-run.sh full
#   ./scripts/dast-run.sh api
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-baseline}"
TARGET="${TARGET:-http://localhost:5000}"
ZAP_IMG="${ZAP_IMG:-ghcr.io/zaproxy/zaproxy:stable}"
REPORT_DIR="${REPORT_DIR:-$ROOT/reports/zap}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$REPORT_DIR/run-$TIMESTAMP"
mkdir -p "$RUN_DIR"

EXTRA_ZAP_OPTS=()
if [ -f reports/dast/.jwt-token ]; then
  TOKEN=$(cat reports/dast/.jwt-token)
  export ZAP_AUTH_HEADER="Authorization"
  export ZAP_AUTH_HEADER_VALUE="Bearer $TOKEN"
  echo ">>> JWT configurado (ZAP_AUTH_HEADER*) para rotas autenticadas"
fi

echo ">>> Modo: $MODE | Alvo: $TARGET | Saída: $RUN_DIR"

case "$MODE" in
  baseline)
    ZAP_SCRIPT=zap-baseline.py
    HTML=zap-report.html
    JSON=zap-report.json
    ;;
  full)
    ZAP_SCRIPT=zap-full-scan.py
    HTML=zap-full-report.html
    JSON=zap-full-report.json
    ;;
  api)
    OPENAPI_URL="${OPENAPI_URL:-$TARGET/openapi.json}"
    if ! curl -sf "$OPENAPI_URL" > /dev/null; then
      echo "ERRO: OpenAPI não em $OPENAPI_URL — use baseline ou exponha openapi.json"
      exit 1
    fi
    ZAP_SCRIPT=zap-api-scan.py
    TARGET="$OPENAPI_URL"
    HTML=zap-api-report.html
    JSON=zap-api-report.json
    EXTRA_ZAP_OPTS+=(-f openapi)
    ;;
  *)
    echo "Uso: $0 {baseline|full|api}"
    exit 1
    ;;
esac

set +e
docker run --rm --network host \
  -v "$RUN_DIR":/zap/wrk:rw \
  -e ZAP_AUTH_HEADER \
  -e ZAP_AUTH_HEADER_VALUE \
  -t "$ZAP_IMG" \
  "$ZAP_SCRIPT" \
    -t "$TARGET" \
    -r "$HTML" \
    -J "$JSON" \
    -I \
    "${EXTRA_ZAP_OPTS[@]}"
ZAP_EXIT=$?
set -e

echo "ZAP exit code: $ZAP_EXIT"

if [ -f "$RUN_DIR/$JSON" ] && command -v jq &>/dev/null; then
  echo ""
  echo "=== Resumo ==="
  jq -r '[.site[]?.alerts[]?] | group_by(.riskdesc) | .[] | "\(.[0].riskdesc): \(length)"' \
    "$RUN_DIR/$JSON" 2>/dev/null || true
  HIGH=$(jq '[.site[]?.alerts[]? | select(.riskcode == "3" or .riskcode == "4")] | length' \
    "$RUN_DIR/$JSON")
  echo "High/Critical: $HIGH"
fi

ln -sfn "$RUN_DIR" "$REPORT_DIR/latest"
echo "Relatórios em: $RUN_DIR/"
