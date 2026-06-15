#!/usr/bin/env bash
# =============================================================================
# dast-cleanup.sh — Limpeza após testes DAST
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ARCHIVE_DIR="${ARCHIVE_DIR:-$ROOT/reports/archive}"
REMOVE_VOLUMES="${REMOVE_VOLUMES:-false}"

echo ">>> Arquivando relatórios ZAP..."
if [ -d reports/zap ]; then
  mkdir -p "$ARCHIVE_DIR"
  STAMP=$(date +%Y%m%d-%H%M%S)
  tar -czf "$ARCHIVE_DIR/zap-$STAMP.tar.gz" -C reports zap 2>/dev/null || true
  echo "Arquivo: $ARCHIVE_DIR/zap-$STAMP.tar.gz"
fi

echo ">>> Removendo tokens e contexto temporário..."
rm -f reports/dast/.jwt-token

echo ">>> Removendo usuários/tarefas DAST (opcional via seed reverso)..."
docker compose exec -T app python - << 'PY' 2>/dev/null || echo "Stack já parada — pulando limpeza DB."
import os, sys
sys.path.insert(0, "/app/todo_project")
os.environ.setdefault("SYSLOG_ENABLED", "false")
from todo_project.factory import create_app
from todo_project.extensions import db
from todo_project.models import Task, User

app = create_app()
emails = ["dast-user@example.com", "dast-peer@example.com"]
with app.app_context():
    for email in emails:
        user = db.session.query(User).filter_by(email=email).first()
        if user:
            db.session.query(Task).filter_by(user_id=user.id).delete()
            db.session.delete(user)
            print(f"Removido: {email}")
    db.session.commit()
PY

echo ">>> Parando containers..."
if [ "$REMOVE_VOLUMES" = "true" ]; then
  docker compose down -v --remove-orphans
  echo "Volumes removidos (banco resetado)."
else
  docker compose down --remove-orphans
fi

echo "Limpeza DAST concluída."
