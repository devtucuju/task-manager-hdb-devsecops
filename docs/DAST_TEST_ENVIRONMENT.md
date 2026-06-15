# Guia — Preparar Ambiente de Teste para DAST

Este guia descreve como preparar o Task Manager Flask para varreduras **DAST** (OWASP ZAP), executar testes, analisar resultados, remediar e limpar o ambiente.

**Scripts de automação:** `scripts/dast-*.sh` e `scripts/seed-dast-data.py`

---

## Visão do fluxo

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐    ┌──────────┐
│ 1. Preparar │ →  │ 2. Seed    │ →  │ 3. ZAP scan │ →  │ 4. Analisar│ →  │ 5. Limpar│
│ docker up   │    │ usuários/  │    │ baseline/   │    │ relatórios │    │ down     │
│ health OK   │    │ tarefas    │    │ full/api    │    │ remediar   │    │ arquivar │
└─────────────┘    └──────────────┘    └─────────────┘    └────────────┘    └──────────┘
```

**Ciclo automatizado (uma linha):**

```bash
chmod +x scripts/dast-*.sh
./scripts/dast-full-cycle.sh baseline
```

---

## 1. Iniciar aplicação em modo teste

### Passo a passo manual

```bash
# Na raiz do repositório
cp .env.example .env

# Overrides recomendados para DAST (produção simulada, sem syslog)
sed -i 's/^SECRET_KEY=.*/SECRET_KEY=dast-local-secret-key/' .env
sed -i 's/^FLASK_ENV=.*/FLASK_ENV=production/' .env
sed -i 's/^SYSLOG_ENABLED=.*/SYSLOG_ENABLED=false/' .env
sed -i 's/^REGISTRATION_ENABLED=.*/REGISTRATION_ENABLED=true/' .env
sed -i 's/^LOGIN_RATE_LIMIT=.*/LOGIN_RATE_LIMIT=100 per minute/' .env

docker compose up -d --build
```

### Verificar se a aplicação está rodando

```bash
# Endpoint raiz (redireciona / → /about)
curl -i http://localhost:5000

# Health check — rota pública usada pelo Dockerfile e pela CI
curl -sf http://localhost:5000/about && echo " OK"
```

> **Nota:** não existe rota `/health` nesta versão. O health check oficial é **`/about`** (HTTP 200).  
> Se precisar de `/health` no futuro, adicione uma rota leve que retorne `{"status":"ok"}`.

### Verificar serviços Docker

```bash
docker compose ps
docker compose logs app --tail 30
docker compose logs db --tail 10
```

### Automatizado

```bash
./scripts/dast-prepare.sh
```

---

## 2. Criar dados de teste

### Usuários de teste (cenários DAST)

| Usuário | Email | Senha | Cenário |
|---------|-------|-------|---------|
| `dast_user` | `dast-user@example.com` | `DastUser1!` | Usuário principal autenticado |
| `dast_peer` | `dast-peer@example.com` | `DastPeer1!` | Segundo usuário (teste IDOR) |
| Bootstrap | `admin@example.com` | `Change-me1!` | Admin padrão (se bootstrap ativo) |

### Registrar via API

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "dast_user",
    "email": "dast-user@example.com",
    "password": "DastUser1!"
  }'
# Esperado: HTTP 201
```

### Obter token JWT (scan autenticado)

```bash
curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dast-user@example.com","password":"DastUser1!"}' | jq .

# Salvar token
curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dast-user@example.com","password":"DastUser1!"}' \
  | jq -r .token > reports/dast/.jwt-token
```

### Criar tarefas de teste

```bash
docker compose exec app python /app/scripts/seed-dast-data.py
```

Tarefas criadas:

| Título | Usuário | Status |
|--------|---------|--------|
| DAST Task — pending | dast-user | pending |
| DAST Task — in progress | dast-user | in_progress |
| DAST Peer Task — private | dast-peer | done |

### Cenários preparados para o ZAP

| # | Cenário | URLs / ações |
|---|---------|--------------|
| 1 | Rotas públicas | `/`, `/about`, `/login`, `/register` |
| 2 | Auth API | `POST /api/auth/login`, `POST /api/auth/register` |
| 3 | Rotas protegidas | `/all_tasks`, `/api/me`, `/api/tasks` (com JWT) |
| 4 | IDOR | Token de `dast-user` vs tarefas de `dast-peer` |
| 5 | Rate limit | Múltiplos `POST /api/auth/login` falhos |
| 6 | CSRF | `POST /login` sem `csrf_token` |

---

## 3. Configurar ZAP para teste

### Imagem Docker (oficial)

```bash
docker pull ghcr.io/zaproxy/zaproxy:stable
```

### Contexto — URLs a testar

Arquivo gerado por `dast-prepare.sh`: `reports/dast/context.txt`

```
TARGET=http://localhost:5000
PUBLIC_URLS=/ /about /login /register
API_URLS=/api/auth/login /api/auth/register /api/me /api/tasks
```

### Autenticação JWT no ZAP

Variáveis suportadas pelo ZAP Docker:

```bash
export ZAP_AUTH_HEADER="Authorization"
export ZAP_AUTH_HEADER_VALUE="Bearer $(cat reports/dast/.jwt-token)"

docker run --rm --network host \
  -e ZAP_AUTH_HEADER -e ZAP_AUTH_HEADER_VALUE \
  -v "$(pwd)/reports/zap":/zap/wrk:rw \
  -t ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://localhost:5000 \
    -r zap-report.html -J zap-report.json
```

### Limites de teste

| Parâmetro | Recomendação DAST local |
|-----------|-------------------------|
| Modo | `baseline` para iterar; `full` antes de release |
| Rate limit app | `100 per minute` no `.env` (evita 429 durante scan) |
| Escopo | Apenas `localhost:5000` — nunca scan em produção sem autorização |
| Regras ignoradas | `.zap/rules.tsv` para falsos positivos documentados |

Exemplo `.zap/rules.tsv`:

```tsv
10038	IGNORE	(CSP — backlog sprint X)
10021	IGNORE	(X-Content-Type-Options — dev HTTP)
```

---

## 4. Executar testes

### a) Baseline scan (rápido — 5–10 min)

```bash
./scripts/dast-run.sh baseline
```

Manual:

```bash
docker run --rm --network host \
  -v "$(pwd)/reports/zap":/zap/wrk:rw \
  -t ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://localhost:5000 \
    -r zap-report.html -J zap-report.json -I
```

### b) Full scan (completo — 30–60 min)

```bash
./scripts/dast-run.sh full
```

> Use apenas em homolog/staging — envia payloads ativos.

### c) API scan (se houver OpenAPI)

```bash
# Requer http://localhost:5000/openapi.json
./scripts/dast-run.sh api
```

**Alternativa manual (sem OpenAPI):**

```bash
TOKEN=$(cat reports/dast/.jwt-token)
curl -i -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/me
curl -i -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/tasks
```

---

## 5. Analisar resultados

### Localizar relatórios

```bash
ls -la reports/zap/latest/
# zap-report.html  zap-report.json
```

### Classificar por severidade

```bash
# Resumo
jq -r '[.site[]?.alerts[]?] | group_by(.riskdesc) | .[] | "\(.[0].riskdesc): \(length)"' \
  reports/zap/latest/zap-report.json

# Apenas High
jq -r '[.site[]?.alerts[]? | select(.riskcode == "3")] | .[] | "\(.name) — \(.url)"' \
  reports/zap/latest/zap-report.json
```

### Tabela de classificação

| Risk | riskcode | Ação |
|------|----------|------|
| High | 3 | Corrigir antes do deploy |
| Medium | 2 | Planejar correção |
| Low | 1 | Avaliar / aceitar com justificativa |
| Informational | 0 | Documentar |

### Documentar achados (modelo)

Crie `reports/dast/findings.md`:

```markdown
# DAST Findings — 2026-06-15

| ID | Alerta ZAP | Severidade | URL | Status | Ação |
|----|------------|------------|-----|--------|------|
| 1 | CSP Header Not Set | Low | /login | Aberto | Adicionar CSP em after_request |
| 2 | Cookie without SameSite | Low | /login | Aberto | SameSite=Strict em produção |
```

### Abrir HTML

```bash
xdg-open reports/zap/latest/zap-report.html   # Linux/WSL
```

---

## 6. Remediação

### Ciclo de correção

```
1. Corrigir código/config (ex.: headers de segurança em factory.py)
2. Re-executar pytest:  pytest tests/ -v
3. Re-executar DAST:    ./scripts/dast-run.sh baseline
4. Comparar relatórios: diff de contagem High/Medium
5. Atualizar findings.md com status "Corrigido"
```

### Exemplo: adicionar security headers

```python
# todo_project/factory.py (exemplo)
@app.after_request
def security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response
```

### Validar correções

```bash
./scripts/validate-security.sh    # SAST + pytest
./scripts/dast-run.sh baseline      # DAST pós-fix
```

---

## 7. Limpeza

### Parar containers

```bash
docker compose down
```

### Remover volumes (reset completo do banco)

```bash
REMOVE_VOLUMES=true ./scripts/dast-cleanup.sh
# ou: docker compose down -v
```

### Remover dados de teste e arquivar relatórios

```bash
./scripts/dast-cleanup.sh
```

O script:

- Arquiva `reports/zap/` em `reports/archive/zap-YYYYMMDD-HHMMSS.tar.gz`
- Remove usuários `dast-user@example.com` e `dast-peer@example.com`
- Remove `reports/dast/.jwt-token`
- Para containers

---

## Scripts de automação — referência

| Script | Função |
|--------|--------|
| `scripts/dast-prepare.sh` | Sobe stack, health check, seed, JWT |
| `scripts/seed-dast-data.py` | Usuários e tarefas no banco |
| `scripts/dast-run.sh` | ZAP baseline / full / api |
| `scripts/dast-full-cycle.sh` | prepare + run |
| `scripts/dast-cleanup.sh` | Limpeza e arquivamento |
| `scripts/zap-baseline-local.sh` | Baseline simples (sem seed) |

### Fluxo completo recomendado

```bash
# 1. Preparar
./scripts/dast-prepare.sh

# 2. Scan
./scripts/dast-run.sh baseline

# 3. Analisar
jq '.site[].alerts[] | select(.riskcode=="3")' reports/zap/latest/zap-report.json

# 4. (Após correções) Re-testar
pytest tests/ -v
./scripts/dast-run.sh baseline

# 5. Limpar
./scripts/dast-cleanup.sh
```

### Variáveis de ambiente úteis

```bash
export TARGET=http://localhost:5000
export ZAP_IMG=ghcr.io/zaproxy/zaproxy:stable
export REPORT_DIR=./reports/zap
./scripts/dast-run.sh baseline
```

---

## Integração CI/CD

O workflow `.github/workflows/dast.yml` automatiza:

1. `docker compose up`
2. Health em `/about`
3. `zaproxy/action-baseline@v0.15.0`
4. Falha em alertas High/Critical

Para reproduzir localmente o mesmo comportamento:

```bash
./scripts/dast-full-cycle.sh baseline
```

---

## Checklist DAST

- [ ] `docker compose up -d` — todos os serviços healthy
- [ ] `curl http://localhost:5000/about` → 200
- [ ] Usuários DAST criados (`dast-user`, `dast-peer`)
- [ ] Tarefas de teste no banco
- [ ] JWT salvo em `reports/dast/.jwt-token` (opcional)
- [ ] Baseline executado; relatórios em `reports/zap/latest/`
- [ ] Achados High/Critical = 0 ou justificados
- [ ] `pytest tests/` verde após remediação
- [ ] `dast-cleanup.sh` executado

---

## Referências

- [OWASP ZAP local](OWASP_ZAP_LOCAL.md)
- [SAST vs DAST](SAST_vs_DAST.md)
- [Validação pós-correção](SECURITY_VALIDATION.md)
- Workflow: `.github/workflows/dast.yml`
