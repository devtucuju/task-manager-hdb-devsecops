#!/usr/bin/env bash
# =============================================================================
# deploy-monitoring.sh — Sobe stack de monitoramento (Prometheus/Grafana/Loki)
# =============================================================================
# Uso:
#   ./scripts/deploy-monitoring.sh
#   DEPLOY_PATH=/opt/task-manager ./scripts/deploy-monitoring.sh
#
# Equivalente GitLab CI:
#   deploy_monitoring:
#     stage: deploy
#     script:
#       - ./scripts/deploy-monitoring.sh
#     only:
#       - main
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.monitoring.yml}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo ">>> Deploy stack de monitoramento"
echo "    Compose: ${COMPOSE_FILE}"

# Rede compartilhada com a aplicação (app:5000 para scrape Prometheus)
if ! docker network inspect app-network >/dev/null 2>&1; then
  echo ">>> Criando rede app-network..."
  docker network create app-network
fi

docker compose -f "${COMPOSE_FILE}" pull --quiet 2>/dev/null || true
docker compose -f "${COMPOSE_FILE}" up -d

echo ">>> Aguardando Grafana..."
for i in $(seq 1 30); do
  if curl -sf "${GRAFANA_URL}/api/health" > /dev/null; then
    echo "Grafana pronto (tentativa ${i})."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERRO: Grafana não respondeu em ${GRAFANA_URL}"
    docker compose -f "${COMPOSE_FILE}" logs grafana --tail 30
    exit 1
  fi
  sleep 5
done

echo ">>> Aguardando Prometheus..."
for i in $(seq 1 24); do
  if curl -sf "${PROMETHEUS_URL}/-/healthy" > /dev/null; then
    echo "Prometheus pronto (tentativa ${i})."
    break
  fi
  sleep 5
done

echo ""
echo "Monitoramento iniciado:"
echo "  Grafana:    ${GRAFANA_URL}"
echo "  Prometheus: ${PROMETHEUS_URL}"
echo "  Alertmanager: http://localhost:9093"
echo "  Loki:       http://localhost:3100"
echo ""
docker compose -f "${COMPOSE_FILE}" ps
