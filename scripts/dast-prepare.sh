#!/usr/bin/env bash
# =============================================================================
# dast-prepare.sh — Prepara ambiente para testes DAST
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET="${TARGET:-http://localhost:5000}"
HEALTH_PATH="${HEALTH_PATH:-/about}"   # /health não existe; /about é o health check atual

echo "=============================================="
echo " DAST — Preparação do ambiente de teste"
echo "=============================================="

# 1. Garantir .env adequado para DAST
if [ ! -f .env ]; then
  echo ">>> Criando .env a partir de .env.example"
  cp .env.example .env
fi
echo ">>> Aplicando overrides DAST em .env"
sed -i 's/^SECRET_KEY=.*/SECRET_KEY=dast-local-secret-key-not-for-production/' .env
sed -i 's/^FLASK_ENV=.*/FLASK_ENV=production/' .env
sed -i 's/^SYSLOG_ENABLED=.*/SYSLOG_ENABLED=false/' .env
sed -i 's/^BOOTSTRAP_ADMIN_ENABLED=.*/BOOTSTRAP_ADMIN_ENABLED=true/' .env
sed -i 's/^REGISTRATION_ENABLED=.*/REGISTRATION_ENABLED=true/' .env
sed -i 's/^LOGIN_RATE_LIMIT=.*/LOGIN_RATE_LIMIT=100 per minute/' .env

echo ">>> Subindo stack (docker compose)..."
docker compose up -d --build

echo ">>> Aguardando aplicação ($TARGET$HEALTH_PATH)..."
for attempt in $(seq 1 40); do
  if curl -sf "${TARGET}${HEALTH_PATH}" > /dev/null; then
    echo "Health check OK (tentativa $attempt)."
    break
  fi
  if [ "$attempt" -eq 40 ]; then
    echo "FALHA: aplicação não respondeu."
    docker compose ps
    docker compose logs app --tail 50
    exit 1
  fi
  sleep 3
done

echo ">>> Verificando endpoint raiz..."
curl -sf -o /dev/null -w "HTTP %{http_code}\n" "$TARGET/" || true

# 2. Dados de teste via API + seed Python
echo ">>> Registrando usuários de teste via API..."
for payload in \
  '{"username":"dast_user","email":"dast-user@example.com","password":"DastUser1!"}' \
  '{"username":"dast_peer","email":"dast-peer@example.com","password":"DastPeer1!"}'; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${TARGET}/api/auth/register" \
    -H "Content-Type: application/json" -d "$payload" || echo "000")
  echo "   POST /api/auth/register → HTTP $code"
done

echo ">>> Seed de tarefas (banco)..."
docker compose exec -T app python /app/scripts/seed-dast-data.py

echo ">>> Obtendo token JWT para scans autenticados..."
TOKEN=$(curl -s -X POST "${TARGET}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"dast-user@example.com","password":"DastUser1!"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || true)

mkdir -p reports/dast
if [ -n "$TOKEN" ]; then
  echo "$TOKEN" > reports/dast/.jwt-token
  echo "Token salvo em reports/dast/.jwt-token"
else
  echo "AVISO: não foi possível obter JWT (scan seguirá sem auth)."
fi

cat > reports/dast/context.txt << EOF
# Contexto DAST — Task Manager
TARGET=$TARGET
HEALTH=$TARGET$HEALTH_PATH
PUBLIC_URLS=$TARGET/ $TARGET/about $TARGET/login $TARGET/register
API_URLS=$TARGET/api/auth/login $TARGET/api/auth/register $TARGET/api/me $TARGET/api/tasks
TEST_USER=dast-user@example.com
TEST_PEER=dast-peer@example.com
JWT_FILE=reports/dast/.jwt-token
EOF

echo ""
echo "=============================================="
echo " Ambiente DAST pronto."
echo " Próximo passo: ./scripts/dast-run.sh baseline"
echo "=============================================="
