#!/usr/bin/env bash
# =============================================================================
# validate-security.sh — Validação pós-correções de segurança (DevSecOps)
# =============================================================================
# Uso:
#   ./scripts/validate-security.sh              # gera relatórios em reports/after/
#   ./scripts/validate-security.sh --compare    # compara before/ vs after/
#
# Pré-requisitos: Python 3.11+, pip, Docker (para Dependency-Check opcional)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP_SOURCE="${APP_SOURCE:-todo_project/todo_project}"
REPORTS_DIR="${REPORTS_DIR:-reports}"
BEFORE_DIR="$REPORTS_DIR/before"
AFTER_DIR="$REPORTS_DIR/after"
COMPARE=false

if [[ "${1:-}" == "--compare" ]]; then
  COMPARE=true
fi

mkdir -p "$BEFORE_DIR" "$AFTER_DIR"

echo "=============================================="
echo " Task Manager DevSecOps — Validação Segurança"
echo "=============================================="
echo "APP_SOURCE: $APP_SOURCE"
echo "Relatórios: $REPORTS_DIR"
echo ""

# ---------------------------------------------------------------------------
# 1. Bandit — análise estática Python
# ---------------------------------------------------------------------------
run_bandit() {
  local out_dir="$1"
  local outfile="$out_dir/bandit-report.json"
  echo ">>> [1/4] Bandit — $outfile"
  pip install -q bandit
  bandit -r "$APP_SOURCE" -f json -o "$outfile" || true
  python3 -m json.tool "$outfile" > /dev/null 2>&1 || echo '[]' > "$outfile"
  python3 << PY
import json
from collections import Counter
from pathlib import Path
data = json.loads(Path("$outfile").read_text())
results = data.get("results", data if isinstance(data, list) else [])
counts = Counter(r.get("issue_severity") for r in results)
print("   Issues:", dict(counts), "| total:", len(results))
PY
}

# ---------------------------------------------------------------------------
# 2. OWASP Dependency-Check (Docker)
# ---------------------------------------------------------------------------
run_dependency_check() {
  local out_dir="$1"
  echo ">>> [2/4] OWASP Dependency-Check — $out_dir/"
  if ! command -v docker &>/dev/null; then
    echo "   Docker não disponível — pulando Dependency-Check."
    echo '{"dependencies":[]}' > "$out_dir/dependency-check-report.json"
    return
  fi
  mkdir -p "$out_dir/dc-out"
  docker run --rm \
    -v "$ROOT:/src:ro" \
    -v "$out_dir/dc-out:/report:rw" \
    owasp/dependency-check:latest \
    --project "Task Manager" \
    --scan "/src/requirements.txt" \
    --scan "/src/$APP_SOURCE" \
    --format JSON \
    --out /report \
    --noupdate \
    || true
  if [[ -f "$out_dir/dc-out/dependency-check-report.json" ]]; then
    cp "$out_dir/dc-out/dependency-check-report.json" "$out_dir/dependency-check-report.json"
  else
    echo '{"dependencies":[]}' > "$out_dir/dependency-check-report.json"
  fi
  echo "   Relatório: $out_dir/dependency-check-report.json"
}

# ---------------------------------------------------------------------------
# 3. Safety — dependências pip
# ---------------------------------------------------------------------------
run_safety() {
  local out_dir="$1"
  local outfile="$out_dir/safety-report.json"
  echo ">>> [3/4] Safety — $outfile"
  pip install -q "safety>=2.3,<3"
  safety check -r requirements.txt --json > "$outfile" 2>/dev/null || echo '[]' > "$outfile"
  echo "   Relatório salvo."
}

# ---------------------------------------------------------------------------
# 4. Pytest — funcional + segurança
# ---------------------------------------------------------------------------
run_pytest() {
  local out_dir="$1"
  echo ">>> [4/4] Pytest — tests/"
  export FLASK_ENV=testing
  export SECRET_KEY=validate-security-script-key
  export SYSLOG_ENABLED=false
  export BOOTSTRAP_ADMIN_ENABLED=false
  pip install -q -r requirements.txt
  pytest tests/ -v \
    --cov=todo_project \
    --cov-report=term-missing \
    --cov-report=xml:"$out_dir/coverage.xml" \
    --junitxml="$out_dir/junit.xml" \
    2>&1 | tee "$out_dir/pytest.log"
  echo ""
  echo ">>> Testes de segurança específicos:"
  pytest tests/test_security.py::test_password_hashing \
         tests/test_security.py::test_jwt_token_generation \
         tests/test_security.py::test_xss_protection \
         tests/test_security.py::test_sql_injection_protection \
         -v
}

# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
if $COMPARE; then
  echo "Modo comparação (before/ vs after/)"
  echo ""
  if [[ -f "$BEFORE_DIR/bandit-report.json" && -f "$AFTER_DIR/bandit-report.json" ]]; then
    python3 scripts/compare-bandit.py \
      "$BEFORE_DIR/bandit-report.json" \
      "$AFTER_DIR/bandit-report.json"
  else
    echo "Relatórios Bandit before/after ausentes. Execute o script sem --compare primeiro."
    echo "Dica: cp reports/after/* reports/before/  # snapshot antes das correções"
  fi
  if [[ -f "$BEFORE_DIR/dependency-check-report.json" && -f "$AFTER_DIR/dependency-check-report.json" ]]; then
    python3 scripts/compare-dependency-check.py \
      "$BEFORE_DIR/dependency-check-report.json" \
      "$AFTER_DIR/dependency-check-report.json"
  fi
  exit 0
fi

run_bandit "$AFTER_DIR"
run_dependency_check "$AFTER_DIR"
run_safety "$AFTER_DIR"
run_pytest "$AFTER_DIR"

echo ""
echo "=============================================="
echo " Validação concluída — artefatos em: $AFTER_DIR/"
echo "=============================================="
echo ""
echo "Próximos passos:"
echo "  1. Antes das correções:  cp -r $AFTER_DIR/* $BEFORE_DIR/"
echo "  2. Após as correções:    ./scripts/validate-security.sh"
echo "  3. Comparar:             ./scripts/validate-security.sh --compare"
