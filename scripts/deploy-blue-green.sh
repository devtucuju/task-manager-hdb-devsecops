#!/usr/bin/env bash
# =============================================================================
# deploy-blue-green.sh — Blue-green deploy com Docker Compose
# =============================================================================
# Uso no servidor de produção:
#   ./scripts/deploy-blue-green.sh v1.3.0
#   ./scripts/deploy-blue-green.sh v1.2.0 --rollback
#
# Requer: docker, docker compose, arquivo docker-compose.prod.yml
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:?Informe a versão da imagem (ex.: v1.3.0 ou latest)}"
ROLLBACK=false
if [ "${2:-}" = "--rollback" ]; then
  ROLLBACK=true
fi

DOCKER_IMAGE="${DOCKER_IMAGE:-${DOCKER_USERNAME:-usuario}/task-manager:${VERSION}}"
STATE_FILE="${STATE_FILE:-/opt/task-manager/.active-slot}"
ACTIVE=$(cat "$STATE_FILE" 2>/dev/null || echo "blue")
NEXT=$([ "$ACTIVE" = "blue" ] && echo "green" || echo "blue")

echo ">>> Blue-green deploy"
echo "    Versão:  $VERSION"
echo "    Imagem:  $DOCKER_IMAGE"
echo "    Ativo:   $ACTIVE → subir $NEXT"
[ "$ROLLBACK" = true ] && echo "    Modo:    ROLLBACK"

export DOCKER_IMAGE
export SECRET_KEY="${SECRET_KEY:?SECRET_KEY obrigatório}"
export DATABASE_URL="${DATABASE_URL:?DATABASE_URL obrigatório}"

# Sobe slot inativo
export COMPOSE_PROFILES="$NEXT"
docker compose -f docker-compose.prod.yml pull "app-$NEXT"
docker compose -f docker-compose.prod.yml up -d "app-$NEXT" db

BASE_URL="http://127.0.0.1:$([ "$NEXT" = "blue" ] && echo 5001 || echo 5002)"
for i in $(seq 1 30); do
  if curl -sf "${BASE_URL}/about" > /dev/null; then
    echo "Health OK em $NEXT ($BASE_URL)"
    break
  fi
  [ "$i" -eq 30 ] && { echo "FAIL: health check $NEXT"; exit 1; }
  sleep 5
done

# Troca tráfego (nginx upstream ou symlink de porta)
if [ -f scripts/switch-traffic.sh ]; then
  ./scripts/switch-traffic.sh "$NEXT"
else
  echo "WARN: scripts/switch-traffic.sh ausente — atualize proxy manualmente para $NEXT"
fi

echo "$NEXT" > "$STATE_FILE"
echo ">>> Slot ativo: $NEXT"

# Drena slot antigo após troca
export COMPOSE_PROFILES="$ACTIVE"
docker compose -f docker-compose.prod.yml stop "app-$ACTIVE" || true

echo ">>> Deploy blue-green concluído."
