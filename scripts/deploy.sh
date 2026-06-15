#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Deploy automatizado para staging (Task Manager DevSecOps)
# =============================================================================
# Fluxo: validar pré-requisitos → build → push Docker Hub → deploy staging →
#        health check → smoke tests (pytest) → notificações (Slack/email).
# Em caso de falha após deploy: rollback para a imagem anterior.
#
# Uso:
#   ./scripts/deploy.sh
#   APP_VERSION=v1.0.0 ./scripts/deploy.sh
#   SKIP_PUSH=1 ./scripts/deploy.sh          # apenas build + deploy local
#   SKIP_ROLLBACK=1 ./scripts/deploy.sh      # não reverter em falha
#
# Variáveis de ambiente (obrigatórias — carregadas de .env se existir):
#   DOCKER_USERNAME      — usuário Docker Hub
#   DOCKER_PASSWORD      — token de acesso Docker Hub
#   SECRET_KEY           — chave secreta Flask
#   DB_USER, DB_PASSWORD, DB_NAME — credenciais PostgreSQL
#
# Variáveis opcionais:
#   APP_VERSION          — tag de versão (padrão: v1.0.0)
#   IMAGE_NAME           — nome da imagem (padrão: task-manager)
#   DOCKER_IMAGE         — imagem completa para staging (sobrescreve padrão)
#   APP_PORT             — porta exposta (padrão: 5000)
#   SLACK_WEBHOOK_URL    — webhook Slack para notificações
#   DEPLOY_NOTIFY_EMAIL  — destinatários de email (separados por vírgula)
#   MAIL_FROM            — remetente do email (padrão: deploy@task-manager.local)
#   SMOKE_BASE_URL       — URL base para pytest (padrão: http://localhost:5000)
#   DEPLOY_STATE_DIR     — diretório de estado/rollback (padrão: .deploy)
#   SKIP_PUSH            — 1 para pular push ao registry
#   SKIP_ROLLBACK        — 1 para pular rollback automático
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
readonly IMAGE_NAME="${IMAGE_NAME:-task-manager}"
readonly APP_VERSION="${APP_VERSION:-v1.0.0}"
readonly APP_PORT="${APP_PORT:-5000}"
readonly COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"
readonly DEPLOY_STATE_DIR="${DEPLOY_STATE_DIR:-.deploy}"
readonly PREVIOUS_IMAGE_FILE="${DEPLOY_STATE_DIR}/previous_image"
readonly SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost:${APP_PORT}}"
readonly MAIL_FROM="${MAIL_FROM:-deploy@task-manager.local}"
readonly SKIP_PUSH="${SKIP_PUSH:-0}"
readonly SKIP_ROLLBACK="${SKIP_ROLLBACK:-0}"

DEPLOY_STARTED=0
ROLLBACK_IMAGE=""
CURRENT_IMAGE=""
COMPOSE_CMD=()

# ---------------------------------------------------------------------------
# Logging e utilitários
# ---------------------------------------------------------------------------
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  log "ERRO: $*"
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Comando obrigatório não encontrado: $cmd"
}

load_env_file() {
  if [[ -f "$ROOT/.env" ]]; then
    log "Carregando variáveis de $ROOT/.env"
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  else
    log "AVISO: arquivo .env não encontrado — usando apenas variáveis do ambiente"
  fi
}

resolve_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
  else
    die "Docker Compose não encontrado (docker compose ou docker-compose)"
  fi
}

resolve_full_image() {
  if [[ -n "${DOCKER_IMAGE:-}" ]]; then
    CURRENT_IMAGE="$DOCKER_IMAGE"
    return
  fi

  if [[ -z "${DOCKER_USERNAME:-}" ]]; then
    die "DOCKER_USERNAME não definido (necessário para montar a imagem no registry)"
  fi

  CURRENT_IMAGE="${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
}

resolve_rollback_image() {
  if [[ -n "${ROLLBACK_IMAGE:-}" ]]; then
    return
  fi

  if [[ -f "$PREVIOUS_IMAGE_FILE" ]]; then
    ROLLBACK_IMAGE="$(tr -d '[:space:]' < "$PREVIOUS_IMAGE_FILE")"
    [[ -n "$ROLLBACK_IMAGE" ]] && return
  fi

  if [[ -n "${DOCKER_USERNAME:-}" ]]; then
    ROLLBACK_IMAGE="${DOCKER_USERNAME}/${IMAGE_NAME}:${APP_VERSION}"
  else
    ROLLBACK_IMAGE="${IMAGE_NAME}:${APP_VERSION}"
  fi
}

# ---------------------------------------------------------------------------
# 1. Validar pré-requisitos
# ---------------------------------------------------------------------------
validate_prerequisites() {
  log "=== 1/7 Validando pré-requisitos ==="

  require_cmd docker
  resolve_compose_cmd
  require_cmd curl
  require_cmd pytest

  if ! docker info >/dev/null 2>&1; then
    die "Docker daemon não está acessível — inicie o Docker e tente novamente"
  fi

  load_env_file

  local missing=()
  [[ -n "${DOCKER_USERNAME:-}" ]] || missing+=("DOCKER_USERNAME")
  [[ -n "${DOCKER_PASSWORD:-}" ]] || missing+=("DOCKER_PASSWORD")
  [[ -n "${SECRET_KEY:-}" ]] || missing+=("SECRET_KEY")
  [[ -n "${DB_USER:-}" ]] || missing+=("DB_USER")
  [[ -n "${DB_PASSWORD:-}" ]] || missing+=("DB_PASSWORD")
  [[ -n "${DB_NAME:-}" ]] || missing+=("DB_NAME")

  if ((${#missing[@]} > 0)); then
    die "Variáveis de ambiente obrigatórias ausentes: ${missing[*]}"
  fi

  [[ -f "$ROOT/Dockerfile" ]] || die "Dockerfile não encontrado em $ROOT"
  [[ -f "$ROOT/$COMPOSE_FILE" ]] || die "Arquivo $COMPOSE_FILE não encontrado"

  if [[ ! -f "$ROOT/tests/test_smoke.py" ]]; then
    die "Arquivo de smoke tests não encontrado: tests/test_smoke.py"
  fi

  resolve_full_image
  resolve_rollback_image

  mkdir -p "$DEPLOY_STATE_DIR"

  log "Pré-requisitos OK"
  log "  Imagem alvo:    $CURRENT_IMAGE"
  log "  Versão:         $APP_VERSION"
  log "  Rollback:       $ROLLBACK_IMAGE"
  log "  Compose:        ${COMPOSE_CMD[*]} -f $COMPOSE_FILE"
}

# ---------------------------------------------------------------------------
# 2. Build da imagem Docker
# ---------------------------------------------------------------------------
build_image() {
  log "=== 2/7 Build da imagem Docker ==="

  local build_latest build_version
  if [[ -n "${DOCKER_USERNAME:-}" ]]; then
    build_latest="${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
    build_version="${DOCKER_USERNAME}/${IMAGE_NAME}:${APP_VERSION}"
  else
    build_latest="${IMAGE_NAME}:latest"
    build_version="${IMAGE_NAME}:${APP_VERSION}"
  fi

  log "Executando: docker build -t $build_latest -t $build_version ."

  if ! docker build \
    -t "$build_latest" \
    -t "$build_version" \
    .; then
    die "Falha no build da imagem Docker"
  fi

  if ! docker image inspect "$build_latest" >/dev/null 2>&1; then
    die "Build concluído, mas imagem $build_latest não encontrada localmente"
  fi

  CURRENT_IMAGE="$build_latest"
  export DOCKER_IMAGE="$CURRENT_IMAGE"

  log "Build concluído com sucesso: $build_latest (+ tag $APP_VERSION)"
}

# ---------------------------------------------------------------------------
# 3. Push para Docker Hub
# ---------------------------------------------------------------------------
push_image() {
  if [[ "$SKIP_PUSH" == "1" ]]; then
    log "=== 3/7 Push ao Docker Hub (SKIP_PUSH=1 — ignorado) ==="
    return
  fi

  log "=== 3/7 Push para Docker Hub ==="

  local push_latest push_version
  if [[ -n "${DOCKER_USERNAME:-}" ]]; then
    push_latest="${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
    push_version="${DOCKER_USERNAME}/${IMAGE_NAME}:${APP_VERSION}"
  else
    push_latest="${IMAGE_NAME}:latest"
    push_version="${IMAGE_NAME}:${APP_VERSION}"
  fi

  log "Autenticando no Docker Hub (usuário: $DOCKER_USERNAME)"
  if ! echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin; then
    die "Falha no docker login"
  fi

  log "Executando: docker push $push_latest"
  if ! docker push "$push_latest"; then
    die "Falha no push de $push_latest"
  fi

  log "Executando: docker push $push_version"
  if ! docker push "$push_version"; then
    die "Falha no push de $push_version"
  fi

  log "Push concluído: $push_latest e $push_version"
}

# ---------------------------------------------------------------------------
# Estado para rollback
# ---------------------------------------------------------------------------
save_previous_image() {
  if [[ -f "$PREVIOUS_IMAGE_FILE" ]]; then
    ROLLBACK_IMAGE="$(tr -d '[:space:]' < "$PREVIOUS_IMAGE_FILE")"
    log "Imagem anterior para rollback: $ROLLBACK_IMAGE"
  else
    log "Nenhuma imagem anterior registrada — rollback usará: $ROLLBACK_IMAGE"
  fi
}

persist_current_image() {
  echo "$CURRENT_IMAGE" > "$PREVIOUS_IMAGE_FILE"
  log "Imagem atual registrada para rollback futuro: $CURRENT_IMAGE"
}

# ---------------------------------------------------------------------------
# 4. Deploy em staging
# ---------------------------------------------------------------------------
compose_staging() {
  DOCKER_IMAGE="$1" "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" "${@:2}"
}

deploy_staging() {
  log "=== 4/7 Deploy em staging ==="

  export DOCKER_IMAGE="$CURRENT_IMAGE"

  log "Executando: ${COMPOSE_CMD[*]} -f $COMPOSE_FILE pull"
  compose_staging "$CURRENT_IMAGE" pull

  log "Executando: ${COMPOSE_CMD[*]} -f $COMPOSE_FILE up -d"
  if ! compose_staging "$CURRENT_IMAGE" up -d; then
    die "Falha ao subir stack de staging"
  fi

  DEPLOY_STARTED=1
  log "Stack de staging iniciada"
}

wait_for_health() {
  log "Aguardando health check (container + endpoint HTTP)..."

  local max_attempts=60
  local attempt=1
  local health_url="${SMOKE_BASE_URL}/about"

  while (( attempt <= max_attempts )); do
    local container_health=""
    container_health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      task-manager-staging-app 2>/dev/null || echo "missing")"

    if curl -sf "$health_url" >/dev/null 2>&1; then
      log "Health check OK (tentativa $attempt) — HTTP 200 em $health_url"
      if [[ "$container_health" == "healthy" || "$container_health" == "none" ]]; then
        return 0
      fi
      log "Endpoint responde; status Docker health: $container_health"
      return 0
    fi

    if [[ "$container_health" == "unhealthy" ]]; then
      log "Container reportou unhealthy (tentativa $attempt)"
    fi

    if (( attempt == max_attempts )); then
      log "Logs recentes do app:"
      compose_staging "$CURRENT_IMAGE" logs app --tail 40 || true
      die "Health check falhou após $max_attempts tentativas ($health_url)"
    fi

    sleep 5
    (( attempt++ )) || true
  done
}

# ---------------------------------------------------------------------------
# 5. Smoke tests (pytest)
# ---------------------------------------------------------------------------
run_smoke_tests() {
  log "=== 5/7 Executando smoke tests ==="

  export SMOKE_BASE_URL

  log "Executando: pytest tests/test_smoke.py -v (SMOKE_BASE_URL=$SMOKE_BASE_URL)"

  if ! pytest tests/test_smoke.py -v; then
    die "Smoke tests falharam — deploy abortado"
  fi

  log "Smoke tests passaram"
}

# ---------------------------------------------------------------------------
# 6. Notificações
# ---------------------------------------------------------------------------
notify_slack() {
  local status="$1"
  local message="$2"

  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    log "SLACK_WEBHOOK_URL não configurado — notificação Slack ignorada"
    return 0
  fi

  local emoji payload
  if [[ "$status" == "success" ]]; then
    emoji=":white_check_mark:"
  else
    emoji=":x:"
  fi

  payload=$(cat <<EOF
{"text":"${emoji} *Deploy Task Manager — ${status}*\n${message}"}
EOF
)

  if curl -sf -X POST -H 'Content-type: application/json' \
    --data "$payload" "$SLACK_WEBHOOK_URL" >/dev/null; then
    log "Notificação Slack enviada ($status)"
  else
    log "AVISO: falha ao enviar notificação Slack"
  fi
}

notify_email() {
  local subject="$1"
  local body="$2"

  if [[ -z "${DEPLOY_NOTIFY_EMAIL:-}" ]]; then
    log "DEPLOY_NOTIFY_EMAIL não configurado — notificação por email ignorada"
    return 0
  fi

  if ! command -v mail >/dev/null 2>&1; then
    log "AVISO: comando 'mail' não disponível — email não enviado"
    return 0
  fi

  local recipient
  IFS=',' read -ra recipients <<< "$DEPLOY_NOTIFY_EMAIL"
  for recipient in "${recipients[@]}"; do
    recipient="$(echo "$recipient" | xargs)"
    [[ -z "$recipient" ]] && continue
    if echo "$body" | mail -s "$subject" -r "$MAIL_FROM" "$recipient" 2>/dev/null; then
      log "Email enviado para $recipient"
    else
      log "AVISO: falha ao enviar email para $recipient"
    fi
  done
}

notify_success() {
  log "=== 6/7 Notificando sucesso ==="

  local msg
  msg="Imagem: \`${CURRENT_IMAGE}\`
Versão: \`${APP_VERSION}\`
Ambiente: staging
Smoke tests: OK"

  notify_slack "sucesso" "$msg"
  notify_email "[Task Manager] Deploy staging — SUCESSO" \
    "Deploy concluído com sucesso.

Imagem: ${CURRENT_IMAGE}
Versão: ${APP_VERSION}
URL: ${SMOKE_BASE_URL}
Data: $(date -Iseconds)"
}

notify_failure() {
  local reason="$1"

  log "=== Notificando falha ==="

  local msg
  msg="Motivo: ${reason}
Imagem tentada: \`${CURRENT_IMAGE:-desconhecida}\`
Rollback: ${ROLLBACK_IMAGE:-não aplicado}"

  notify_slack "FALHA" "$msg"
  notify_email "[Task Manager] Deploy staging — FALHA" \
    "Deploy falhou.

Motivo: ${reason}
Imagem tentada: ${CURRENT_IMAGE:-desconhecida}
Rollback aplicado: ${DEPLOY_STARTED:-0}
Data: $(date -Iseconds)"
}

# ---------------------------------------------------------------------------
# 7. Rollback
# ---------------------------------------------------------------------------
perform_rollback() {
  if [[ "$SKIP_ROLLBACK" == "1" ]]; then
    log "SKIP_ROLLBACK=1 — rollback automático ignorado"
    return 0
  fi

  if [[ "$DEPLOY_STARTED" != "1" ]]; then
    log "Deploy de staging não iniciou — rollback não necessário"
    return 0
  fi

  if [[ -z "$ROLLBACK_IMAGE" ]]; then
    log "AVISO: imagem anterior desconhecida — rollback manual necessário"
    return 1
  fi

  log "=== 7/7 Rollback para versão anterior ==="
  log "Revertendo para: $ROLLBACK_IMAGE"

  export DOCKER_IMAGE="$ROLLBACK_IMAGE"

  log "Executando: ${COMPOSE_CMD[*]} -f $COMPOSE_FILE down"
  compose_staging "$ROLLBACK_IMAGE" down || log "AVISO: docker compose down retornou erro"

  log "Executando: ${COMPOSE_CMD[*]} -f $COMPOSE_FILE up -d (versão anterior)"
  if ! compose_staging "$ROLLBACK_IMAGE" up -d; then
    log "ERRO CRÍTICO: rollback falhou ao subir stack anterior"
    return 1
  fi

  local rollback_url="${SMOKE_BASE_URL}/about"
  local attempt=1
  while (( attempt <= 24 )); do
    if curl -sf "$rollback_url" >/dev/null 2>&1; then
      log "Rollback concluído — aplicação anterior respondendo em $rollback_url"
      notify_slack "rollback" "Rollback aplicado para \`${ROLLBACK_IMAGE}\` após falha no deploy."
      return 0
    fi
    sleep 5
    (( attempt++ )) || true
  done

  log "AVISO: rollback executado, mas health check da versão anterior não confirmou HTTP 200"
  return 1
}

# ---------------------------------------------------------------------------
# Tratamento global de erros
# ---------------------------------------------------------------------------
cleanup_on_error() {
  local exit_code=$?
  if (( exit_code == 0 )); then
    return 0
  fi

  log "Deploy interrompido (código de saída: $exit_code)"

  notify_failure "Pipeline abortado — verifique os logs acima"
  perform_rollback || true

  exit "$exit_code"
}

trap cleanup_on_error ERR

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "Iniciando deploy Task Manager → staging"
  log "Diretório: $ROOT"

  validate_prerequisites
  save_previous_image
  build_image
  push_image
  deploy_staging
  wait_for_health
  run_smoke_tests
  persist_current_image
  notify_success

  log "Deploy concluído com sucesso."
}

main "$@"
