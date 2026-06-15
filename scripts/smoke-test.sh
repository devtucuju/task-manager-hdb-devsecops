#!/usr/bin/env bash
# =============================================================================
# smoke-test.sh — Smoke tests pós-deploy (Task Manager)
# =============================================================================
# Uso:
#   ./scripts/smoke-test.sh
#   ./scripts/smoke-test.sh https://homolog.exemplo.com
# =============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:5000}"

echo ">>> Smoke tests em: $BASE_URL"

# Health / página pública
code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/about")
[ "$code" = "200" ] || { echo "FAIL: GET /about → $code"; exit 1; }
echo "OK: GET /about → 200"

# Login page
code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/login")
[ "$code" = "200" ] || { echo "FAIL: GET /login → $code"; exit 1; }
echo "OK: GET /login → 200"

# API protegida sem token
code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/api/me" || true)
[ "$code" = "401" ] || { echo "FAIL: GET /api/me sem auth → $code (esperado 401)"; exit 1; }
echo "OK: GET /api/me sem auth → 401"

# Register page (se habilitado)
code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/register" || echo "000")
if [ "$code" = "200" ] || [ "$code" = "302" ]; then
  echo "OK: GET /register → $code"
else
  echo "WARN: GET /register → $code (pode estar desabilitado)"
fi

echo ""
echo "Smoke tests concluídos com sucesso."
