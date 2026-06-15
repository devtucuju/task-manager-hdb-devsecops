#!/usr/bin/env bash
# =============================================================================
# zap-baseline-local.sh — OWASP ZAP baseline contra Task Manager local
# =============================================================================
# Uso: ./scripts/zap-baseline-local.sh
# Pré-requisito: Docker + docker compose
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ZAP_IMG="${ZAP_IMG:-ghcr.io/zaproxy/zaproxy:stable}"
TARGET="${TARGET:-http://localhost:5000}"
REPORT_DIR="${REPORT_DIR:-$ROOT/reports/zap}"
FAIL_ON_HIGH="${FAIL_ON_HIGH:-true}"

mkdir -p "$REPORT_DIR"

echo ">>> Subindo stack..."
cp -n .env.example .env 2>/dev/null || true
docker compose up -d --build

echo ">>> Aguardando app em $TARGET ..."
for attempt in $(seq 1 36); do
  if curl -sf "${TARGET}/about" > /dev/null; then
    echo "App pronta (tentativa $attempt)."
    break
  fi
  if [ "$attempt" -eq 36 ]; then
    echo "Timeout aguardando aplicação."
    docker compose logs app --tail 40
    exit 1
  fi
  sleep 5
done

echo ">>> Executando ZAP baseline ($ZAP_IMG)..."
set +e
docker run --rm --network host \
  -v "$REPORT_DIR":/zap/wrk:rw \
  -t "$ZAP_IMG" \
  zap-baseline.py \
    -t "$TARGET" \
    -r zap-report.html \
    -J zap-report.json
ZAP_EXIT=$?
set -e
echo "ZAP exit code: $ZAP_EXIT"

if [ ! -f "$REPORT_DIR/zap-report.json" ]; then
  echo "ERRO: zap-report.json não gerado."
  exit 1
fi

if command -v jq &>/dev/null; then
  echo ""
  echo "=== Resumo ==="
  jq -r '
    [.site[]?.alerts[]?]
    | group_by(.riskdesc)
    | map({risk: .[0].riskdesc, count: length})
    | .[]
    | "\(.risk): \(.count)"
  ' "$REPORT_DIR/zap-report.json" || true
fi

if [ "$FAIL_ON_HIGH" = "true" ] && command -v jq &>/dev/null; then
  HIGH=$(jq '[.site[]?.alerts[]? | select(.riskcode == "3" or .riskcode == "4")] | length' \
    "$REPORT_DIR/zap-report.json")
  if [ "$HIGH" -gt 0 ]; then
    echo "FALHA: $HIGH alerta(s) High/Critical — ver $REPORT_DIR/zap-report.html"
    exit 1
  fi
fi

echo ""
echo "OK — relatórios em: $REPORT_DIR/"
echo "  HTML: $REPORT_DIR/zap-report.html"
echo "  JSON: $REPORT_DIR/zap-report.json"
