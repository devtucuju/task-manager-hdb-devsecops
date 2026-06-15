# Guia de Validação — Correções de Segurança (DevSecOps)

Este guia descreve como validar que as correções de segurança funcionam corretamente, sem regressão funcional, usando as ferramentas do pipeline SAST/DAST e a suite `tests/`.

> **Nota sobre caminhos:** neste repositório o código da aplicação Flask está em `todo_project/todo_project/` (equivalente ao `app/` em projetos genéricos).

---

## Pré-requisitos

```bash
pip install -r requirements.txt
pip install bandit "safety>=2.3,<3" pytest pytest-cov
# Opcional: Docker para Dependency-Check
```

---

## Fluxo recomendado (antes → depois)

```bash
# 1. Snapshot ANTES das correções
./scripts/validate-security.sh
cp -r reports/after/* reports/before/

# 2. Aplicar correções de segurança no código

# 3. Snapshot DEPOIS das correções
./scripts/validate-security.sh

# 4. Comparar relatórios
./scripts/validate-security.sh --compare
```

Ou execute tudo de uma vez via script automatizado:

```bash
chmod +x scripts/validate-security.sh
./scripts/validate-security.sh
```

---

## 1. Re-executar Bandit após correções

### Comando manual

```bash
# Equivalente a app/ neste projeto:
APP_SOURCE=todo_project/todo_project

# Relatório anterior (baseline)
bandit -r "$APP_SOURCE" -f json -o bandit-report-before.json

# Após correções
bandit -r "$APP_SOURCE" -f json -o bandit-report-after.json
```

### Comparar relatórios

```bash
python3 scripts/compare-bandit.py bandit-report-before.json bandit-report-after.json
```

### O que verificar

| Verificação | Critério de sucesso |
|-------------|---------------------|
| Issues HIGH/CRITICAL | Quantidade **reduzida ou zero** |
| Novas regras | Nenhuma regra HIGH nova introduzida |
| Regressão | Total de issues não aumentou |

### Exemplo de saída esperada

```
=== Comparação Bandit (antes → depois) ===

Severidade      Antes   Depois        Δ
----------------------------------------
LOW                 1        0       -1
----------------------------------------
TOTAL               1        0       -1

Melhoria: 1 issue(s) a menos.
```

---

## 2. Re-executar OWASP Dependency-Check

### Comando manual (Docker)

> O parâmetro `--out` é um **diretório**, não um arquivo. O JSON gerado será `dependency-check-report.json` dentro desse diretório.

```bash
mkdir -p reports/dc-after

docker run --rm \
  -v "$(pwd)":/src:ro \
  -v "$(pwd)/reports/dc-after":/report:rw \
  owasp/dependency-check:latest \
  --project "Task Manager" \
  --scan /src/requirements.txt \
  --scan /src/todo_project/todo_project \
  --format JSON \
  --out /report \
  --noupdate

cp reports/dc-after/dependency-check-report.json dependency-check-report-after.json
```

### Comparar CVEs

```bash
python3 scripts/compare-dependency-check.py \
  dependency-check-report-before.json \
  dependency-check-report-after.json
```

### O que verificar

| Verificação | Critério de sucesso |
|-------------|---------------------|
| Dependências atualizadas | `requirements.txt` com versões corrigidas |
| CVEs CRITICAL | **0** no relatório `after` |
| CVEs HIGH | Redução ou eliminação |
| Funcionalidade | `pip install -r requirements.txt` sem conflitos |

### Safety (complementar — dependências pip)

```bash
safety check -r requirements.txt --json > safety-report-after.json
python3 -m json.tool safety-report-after.json
```

---

## 3. Executar testes funcionais (sem regressão)

```bash
export FLASK_ENV=testing
export SECRET_KEY=validate-local-key
export SYSLOG_ENABLED=false
export BOOTSTRAP_ADMIN_ENABLED=false

pytest tests/ -v
```

### Com cobertura

```bash
pytest tests/ -v \
  --cov=todo_project \
  --cov-report=term-missing \
  --cov-report=html:reports/coverage-html
```

### Critérios de sucesso

| Métrica | Esperado |
|---------|----------|
| Testes | **100% passed** (29 testes na suite atual) |
| Cobertura | Sem queda significativa vs. baseline |
| CI | Job `Test` verde no GitHub Actions |

### Via Docker

```bash
docker compose exec app pytest /app/tests -v \
  --cov=todo_project --cov-report=term-missing
```

---

## 4. Testes de segurança específicos

Arquivo: `tests/test_security.py`

```bash
pytest tests/test_security.py::test_password_hashing -v
pytest tests/test_security.py::test_jwt_token_generation -v
pytest tests/test_security.py::test_xss_protection -v
pytest tests/test_security.py::test_sql_injection_protection -v
```

Ou todos de uma vez:

```bash
pytest tests/test_security.py -v -k "password_hashing or jwt_token or xss or sql_injection"
```

### O que cada teste valida

| Teste | Validação |
|-------|-----------|
| `test_password_hashing` | Senhas armazenadas com bcrypt (`$2b$`), nunca em texto plano; `check_password` funciona |
| `test_jwt_token_generation` | JWT contém `user_id`, `email` e claim `exp` válido |
| `test_jwt_token_expiration` | Token expirado é rejeitado |
| `test_xss_protection` | Payload `<script>` escapado no HTML (`&lt;script&gt;`) |
| `test_sql_injection_protection` | Payload SQL no login não autentica; queries parametrizadas |
| `test_csrf_token_validation` | POST sem CSRF retorna 400 |
| `test_password_strength_validation` | Regex de senha forte aplicada |
| `test_rate_limiting` | Login bloqueado com HTTP 429 após limite |

---

## 5. Comparação antes/depois

### Tabela comparativa (modelo)

Preencha após executar `./scripts/validate-security.sh --compare`:

| Ferramenta | Métrica | Antes | Depois | Status |
|------------|---------|-------|--------|--------|
| Bandit | Issues HIGH | ? | ? | ✅ / ❌ |
| Bandit | Issues MEDIUM | ? | ? | ✅ / ❌ |
| Bandit | Total issues | ? | ? | ✅ / ❌ |
| Dependency-Check | CVEs CRITICAL | ? | ? | ✅ / ❌ |
| Dependency-Check | CVEs HIGH+ | ? | ? | ✅ / ❌ |
| Safety | Vulnerabilidades pip | ? | ? | ✅ / ❌ |
| Pytest | Testes passando | ? / 29 | 29 / 29 | ✅ |
| DAST (ZAP) | Alertas High/Critical | CI | 0 | ✅ |

### Exemplo preenchido (Etapa 1 DevSecOps)

| Ferramenta | Métrica | Antes | Depois | Status |
|------------|---------|-------|--------|--------|
| Bandit | Issues HIGH | 0 | 0 | ✅ |
| Bandit | Issues LOW | 1 | 0–1 | ✅ |
| Autenticação | Senha texto plano | Sim (legado) | Não (bcrypt) | ✅ |
| JWT | Token em cookie httpOnly | Não | Sim | ✅ |
| CSRF | Proteção WTForms | Parcial | Ativa | ✅ |
| Rate limit | Login sem limite | Sim | 5/15min | ✅ |
| Pytest segurança | 13 testes | — | 13 passed | ✅ |

---

## 6. Documentação de mudanças (Etapa 1 + DevSecOps)

### Arquivos modificados e justificativa

| Arquivo | Mudança | Justificativa |
|---------|---------|---------------|
| `todo_project/todo_project/auth.py` | JWT, bcrypt, `validate_password_strength`, `@token_required` | Autenticação segura sem senhas em claro |
| `todo_project/todo_project/routes.py` | Login JWT, rate limit, API `/api/auth/*`, audit | Endpoints protegidos + API testável |
| `todo_project/todo_project/audit.py` | `AuditLog` + syslog | Rastreabilidade de eventos de segurança |
| `todo_project/todo_project/forms.py` | Validação senha forte, CSRF | Prevenção de senhas fracas e CSRF |
| `todo_project/todo_project/config.py` | Variáveis via `.env` | Segredos fora do código |
| `todo_project/todo_project/factory.py` | Application factory | Configuração centralizada e testável |
| `tests/test_security.py` | Testes XSS, SQLi, JWT, bcrypt | Regressão automatizada de segurança |
| `tests/test_auth.py` | Testes API auth (201/401/409/429) | Contrato REST de autenticação |
| `.github/workflows/sast.yml` | Bandit + Dependency-Check + Safety | SAST contínuo na CI |
| `.github/workflows/dast.yml` | OWASP ZAP baseline | DAST dinâmico |
| `.github/workflows/ci.yml` | Pytest + flake8 + build | Integração contínua |
| `Dockerfile` | Usuário não-root, gunicorn | Redução de superfície de ataque |
| `.dockerignore` | Exclui `.env`, `tests/` | Segredos e testes fora da imagem |

---

## 7. Scripts de validação incluídos

| Script | Função |
|--------|--------|
| `scripts/validate-security.sh` | Orquestra Bandit, Dependency-Check, Safety e pytest |
| `scripts/compare-bandit.py` | Tabela comparativa de relatórios Bandit |
| `scripts/compare-dependency-check.py` | Compara CVEs CRITICAL/HIGH |

### Exemplo rápido (uma linha)

```bash
# Validação completa pós-correção
./scripts/validate-security.sh && echo "OK: validação concluída"
```

### Exemplo no CI (local, simulando pipeline)

```bash
# SAST (mesmos passos do GitHub Actions)
pip install bandit "safety>=2.3,<3"
bandit -r todo_project/todo_project -ll -f json -o bandit-report-after.json
safety check -r requirements.txt --json > safety-report-after.json

# Testes
FLASK_ENV=testing SECRET_KEY=ci-key SYSLOG_ENABLED=false \
  BOOTSTRAP_ADMIN_ENABLED=false pytest tests/ -v --cov=todo_project
```

---

## 8. Checklist final

- [ ] `bandit-report-after.json` sem issues HIGH/CRITICAL
- [ ] `dependency-check-report-after.json` sem CVEs CRITICAL
- [ ] `safety-report-after.json` sem vulnerabilidades conhecidas críticas
- [ ] `pytest tests/ -v` — todos passando
- [ ] `test_password_hashing`, `test_jwt_token_generation`, `test_xss_protection`, `test_sql_injection_protection` — pass
- [ ] Comparação before/after documentada na tabela
- [ ] PR com CI verde (SAST + DAST + Test)

---

## Referências

- [Bandit](https://bandit.readthedocs.io/)
- [OWASP Dependency-Check](https://jeremylong.github.io/DependencyCheck/)
- [OWASP ZAP](https://www.zaproxy.org/)
- [Safety](https://pypi.org/project/safety/)
- Workflows: `.github/workflows/sast.yml`, `.github/workflows/dast.yml`, `.github/workflows/ci.yml`
