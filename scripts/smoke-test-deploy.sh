#!/usr/bin/env bash
# =============================================================================
# smoke-test-deploy.sh — Smoke tests pós-deploy com auth + CRUD de tarefas
# =============================================================================
# Uso:
#   ./scripts/smoke-test-deploy.sh
#   ./scripts/smoke-test-deploy.sh https://staging.exemplo.com
# =============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:5000}"
SUFFIX="${SMOKE_TEST_SUFFIX:-$(date +%s)}"
EMAIL="smoke-${SUFFIX}@example.com"
USERNAME="smoke_user_${SUFFIX}"
PASSWORD="SmokeTest1!"

echo ">>> Smoke tests (auth + CRUD) em: $BASE_URL"

# --- Endpoints públicos ---
code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/about")
[ "$code" = "200" ] || { echo "FAIL: GET /about → $code"; exit 1; }
echo "OK: GET /about → 200"

code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/login")
[ "$code" = "200" ] || { echo "FAIL: GET /login → $code"; exit 1; }
echo "OK: GET /login → 200"

code=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/api/me" || true)
[ "$code" = "401" ] || { echo "FAIL: GET /api/me sem auth → $code"; exit 1; }
echo "OK: GET /api/me sem auth → 401"

# --- Registro + login ---
register_code=$(curl -s -o /tmp/smoke-register.json -w "%{http_code}" \
  -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

if [ "$register_code" != "201" ]; then
  echo "FAIL: POST /api/auth/register → $register_code"
  cat /tmp/smoke-register.json
  exit 1
fi
echo "OK: POST /api/auth/register → 201"

TOKEN=$(curl -sf -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .token)

[ -n "$TOKEN" ] && [ "$TOKEN" != "null" ] || { echo "FAIL: login sem token"; exit 1; }
echo "OK: POST /api/auth/login → token obtido"

# --- /api/me autenticado ---
me_code=$(curl -s -o /tmp/smoke-me.json -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/me")
[ "$me_code" = "200" ] || { echo "FAIL: GET /api/me → $me_code"; exit 1; }
echo "OK: GET /api/me autenticado → 200"

# --- CRUD tarefas (rotas /tasks) ---
create_code=$(curl -s -o /tmp/smoke-task.json -w "%{http_code}" \
  -X POST "$BASE_URL/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Smoke Task","description":"CD smoke test","status":"pending"}')

[ "$create_code" = "201" ] || { echo "FAIL: POST /tasks → $create_code"; cat /tmp/smoke-task.json; exit 1; }
TASK_ID=$(jq -r .id /tmp/smoke-task.json)
echo "OK: POST /tasks → 201 (id=$TASK_ID)"

list_code=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/tasks")
[ "$list_code" = "200" ] || { echo "FAIL: GET /api/tasks → $list_code"; exit 1; }
echo "OK: GET /api/tasks → 200"

update_code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X PUT "$BASE_URL/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Smoke Task Updated","status":"done"}')
[ "$update_code" = "200" ] || { echo "FAIL: PUT /tasks/$TASK_ID → $update_code"; exit 1; }
echo "OK: PUT /tasks/$TASK_ID → 200"

delete_code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE "$BASE_URL/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN")
[ "$delete_code" = "200" ] || { echo "FAIL: DELETE /tasks/$TASK_ID → $delete_code"; exit 1; }
echo "OK: DELETE /tasks/$TASK_ID → 200"

echo ""
echo "Smoke tests (auth + CRUD) concluídos com sucesso."
