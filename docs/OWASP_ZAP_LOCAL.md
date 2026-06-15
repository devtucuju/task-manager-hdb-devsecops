# Guia Prático — Executar OWASP ZAP no Task Manager

Este guia mostra como rodar o **OWASP ZAP** contra o Task Manager Flask em `http://localhost:5000`, interpretar relatórios e comparar achados com **SAST**.

> **Imagem Docker:** `owasp/zap2docker-stable` foi **descontinuada**. Use:
>
> ```bash
> docker pull ghcr.io/zaproxy/zaproxy:stable
> ```
>
> Os comandos abaixo usam a imagem atual. A sintaxe antiga é mostrada apenas como referência.

**Scripts prontos:** `scripts/zap-baseline-local.sh`, `scripts/dast-run.sh`

---

## 1. Pré-requisitos

### Aplicação rodando

```bash
# Na raiz do repositório
cp .env.example .env
docker compose up -d --build

# Verificar
curl -sf http://localhost:5000/about && echo " OK"
```

### Docker instalado

```bash
docker --version
docker compose version
docker pull ghcr.io/zaproxy/zaproxy:stable
```

### Relatórios SAST para comparação

Gere (ou reutilize) relatórios SAST antes do DAST:

```bash
./scripts/validate-security.sh
# Saída em reports/after/:
#   bandit-report.json
#   dependency-check-report.json
#   safety-report.json
```

Para comparar antes/depois de correções:

```bash
cp -r reports/after reports/before   # snapshot "antes"
# ... aplicar correções ...
./scripts/validate-security.sh --compare
```

| Relatório SAST | Caminho típico | O que contém |
|----------------|----------------|--------------|
| Bandit | `reports/after/bandit-report.json` | Issues no código Python |
| Dependency-Check | `reports/after/dependency-check-report.json` | CVEs em dependências |
| Safety | `reports/after/safety-report.json` | Pacotes pip vulneráveis |

### Diretório de relatórios DAST

```bash
mkdir -p reports/zap reports/dast
```

---

## 2. Executar Baseline Scan (recomendado para começar)

Scan **passivo/rápido** (~5–10 min). Ideal para CI e primeira varredura.

### Comando (imagem atual — use este)

```bash
docker run --rm --network host \
  -v "$(pwd)/reports/zap":/zap/wrk:rw \
  -t ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py \
    -t http://localhost:5000 \
    -r zap-baseline-report.html \
    -J zap-baseline-report.json
```

### Comando legado (não funciona mais)

```bash
# ❌ DESCONTINUADO — pull negado no Docker Hub
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t http://localhost:5000 \
  -r zap-baseline-report.html \
  -J zap-baseline-report.json
```

### Explicação das flags

| Flag | Significado |
|------|-------------|
| `-t` | URL alvo (`http://localhost:5000`) |
| `-r` | Relatório HTML (leitura humana) |
| `-J` | Relatório JSON (automação, `jq`, CI) |
| `-I` | (opcional) Não falha com exit 1 em warnings — útil localmente |
| `-x` | (opcional) Relatório XML |

> **Linux/WSL:** `--network host` permite ao container acessar `localhost:5000`.  
> **macOS/Windows:** substitua por `http://host.docker.internal:5000` e remova `--network host`.

### Atalho do projeto

```bash
chmod +x scripts/zap-baseline-local.sh
./scripts/zap-baseline-local.sh
```

---

## 3. Executar Full Scan (mais completo)

Scan **ativo** com spider + fuzzing (~30–60 min). Use em homolog/staging, nunca em produção sem autorização.

### Comando

```bash
docker run --rm --network host \
  -v "$(pwd)/reports/zap":/zap/wrk:rw \
  -t ghcr.io/zaproxy/zaproxy:stable \
  zap-full-scan.py \
    -t http://localhost:5000 \
    -r zap-full-report.html \
    -J zap-full-report.json
```

### Via script

```bash
./scripts/dast-prepare.sh          # opcional: seed de dados
./scripts/dast-run.sh full
# Relatórios em reports/zap/latest/
```

---

## 4. Interpretar resultados

### Estrutura do relatório JSON

O ZAP gera um JSON com esta hierarquia principal:

```json
{
  "@version": "2.14.0",
  "@generated": "Mon, 15 Jun 2026 10:30:00",
  "site": [
    {
      "@name": "http://localhost:5000",
      "@host": "localhost",
      "@port": "5000",
      "alerts": [ "..." ],
      "instances": [ "..." ]
    }
  ]
}
```

| Campo raiz | Conteúdo |
|------------|----------|
| `site` | Lista de sites testados (normalmente um) |
| `site[].alerts` | Vulnerabilidades agrupadas por tipo |
| `site[].instances` | URLs concretas onde o alerta apareceu |

### Estrutura de cada alerta

```json
{
  "pluginid": "10038",
  "alertRef": "10038-1",
  "name": "Content Security Policy (CSP) Header Not Set",
  "riskcode": "1",
  "confidence": "3",
  "riskdesc": "Low (Medium)",
  "desc": "Content Security Policy (CSP) is an added layer of security...",
  "solution": "Ensure that your web server, application server, load balancer, etc. is configured to set the Content-Security-Policy header.",
  "reference": "https://developer.mozilla.org/...",
  "cweid": "693",
  "wascid": "15",
  "count": "3",
  "instances": [
    {
      "uri": "http://localhost:5000/login",
      "method": "GET",
      "param": "",
      "attack": "",
      "evidence": ""
    }
  ]
}
```

| Campo | Significado |
|-------|-------------|
| `pluginid` | ID do teste ZAP (usado em `.zap/rules.tsv` para ignorar) |
| `name` | Nome da vulnerabilidade |
| `riskcode` | `0`=Info, `1`=Low, `2`=Medium, `3`=High, `4`=Critical |
| `confidence` | `0`=Low, `1`=Medium, `2`=High, `3`=Confirmed |
| `desc` | Descrição detalhada |
| `solution` | Como corrigir |
| `instances` | Onde foi encontrado (URL, método, parâmetro, evidência) |

### Exemplo de relatório HTML

O HTML lista alertas em tabela com cores por risco:

```
┌──────────────────────────────────────────────────────────────┐
│ OWASP ZAP Report — http://localhost:5000                     │
├──────────┬────────────────────────────────────┬──────────────┤
│ Risk     │ Alert                              │ Instances    │
├──────────┼────────────────────────────────────┼──────────────┤
│ Low      │ CSP Header Not Set [10038]         │ 3            │
│ Low      │ X-Frame-Options Header Not Set     │ 5            │
│ Info     │ Information Disclosure - Suspicious│ 1            │
└──────────┴────────────────────────────────────┴──────────────┘
```

Abrir localmente:

```bash
xdg-open reports/zap/zap-baseline-report.html   # Linux/WSL
```

### Comandos `jq` para análise

```bash
# Contagem por severidade
jq -r '
  [.site[]?.alerts[]?]
  | group_by(.riskdesc)
  | .[] | "\(.[0].riskdesc): \(length)"
' reports/zap/zap-baseline-report.json

# Listar todos os alertas (nome + risco + contagem)
jq -r '
  .site[]?.alerts[]?
  | "\(.riskdesc | split(" ")[0]) | \(.name) | instances: \(.count)"
' reports/zap/zap-baseline-report.json

# Apenas High (riskcode 3)
jq -r '
  .site[]?.alerts[]? | select(.riskcode == "3")
  | "[HIGH] \(.name)\n  pluginid: \(.pluginid)\n  urls: \([.instances[]?.uri] | join(", "))\n"
' reports/zap/zap-baseline-report.json

# Detalhe de um plugin específico (ex.: CSP 10038)
jq '.site[]?.alerts[]? | select(.pluginid == "10038")' \
  reports/zap/zap-baseline-report.json
```

### Códigos de saída do baseline

| Exit code | Significado |
|-----------|-------------|
| `0` | Nenhum alerta novo |
| `1` | Warnings encontrados |
| `2` | Erro de configuração / scan falhou |
| `3` | Outro erro |

### Exemplo de saída no terminal (resumo)

```
PASS: Directory Browsing [0]
WARN-NEW: Content Security Policy (CSP) Header Not Set [10038] x 3
WARN-NEW: X-Frame-Options Header Not Set [10020] x 5
WARN-NEW: Strict-Transport-Security Header Not Set [10035] x 4
FAIL-NEW: 0     FAIL-INPROG: 0     WARN-NEW: 8     WARN-INPROG: 0
```

---

## 5. Vulnerabilidades comuns encontradas

### a) Missing Security Headers (Low Risk)

**O que o ZAP reporta no Task Manager:**

| Header ausente | pluginid típico | URLs comuns |
|----------------|-----------------|-------------|
| `Content-Security-Policy` | 10038 | `/login`, `/about`, `/register` |
| `X-Frame-Options` | 10020 | todas as páginas HTML |
| `X-Content-Type-Options` | 10021 | todas as páginas HTML |
| `Strict-Transport-Security` | 10035 | todas (esperado em HTTP local) |

**Exemplo de alerta JSON:**

```json
{
  "pluginid": "10020",
  "name": "X-Frame-Options Header Not Set",
  "riskcode": "1",
  "riskdesc": "Low (Medium)",
  "instances": [{ "uri": "http://localhost:5000/login", "method": "GET" }]
}
```

**Solução (Flask):**

```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response
```

---

### b) Insecure Direct Object References — IDOR (High Risk)

Usuário acessa recurso de outro usuário alterando ID na URL.

**Teste manual:**

```bash
# Login como dast-user
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dast-peer@example.com","password":"DastPeer1!"}' | jq -r .token)

# Tentar tarefa de outro usuário (substitua ID real)
curl -i -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/tasks/1
```

**Esperado seguro:** `403` ou `404` — nunca dados de outro usuário.

**Exemplo de alerta ZAP (se confirmado):**

```json
{
  "name": "Insecure Direct Object References",
  "riskcode": "3",
  "riskdesc": "High (Medium)",
  "instances": [{
    "uri": "http://localhost:5000/api/tasks/42",
    "method": "GET",
    "evidence": "Response contains data belonging to another user"
  }]
}
```

**Solução:** validar `task.user_id == current_user.id` em cada requisição.

---

### c) Broken Authentication (High Risk)

| Problema | Como testar | Esperado seguro |
|----------|-------------|-----------------|
| Sessão não expira | JWT sem `exp` ou TTL muito longo | Token rejeitado após TTL |
| Token não validado | `Authorization: Bearer fake` | `401` em `/api/me` |
| Sem rate limit | 10+ `POST /api/auth/login` falhos | `429` |
| Senha fraca aceita | `POST /api/auth/register` com `"password":"123"` | `400` |

```bash
curl -i -H "Authorization: Bearer token-invalido" http://localhost:5000/api/me
# HTTP/1.1 401 Unauthorized
```

**Solução:** expiração JWT (`JWT_ACCESS_TOKEN_EXPIRES`), `token_required`, rate limiting.

---

### d) Sensitive Data Exposure (High Risk)

| Vetor | Exemplo | Risco |
|-------|---------|-------|
| Dados em URL | `GET /login?password=secret` | Senha em logs/proxy |
| Stack trace em 500 | Erro não tratado | Caminhos internos, versões |
| Hash de senha na API | `GET /api/me` retorna `password_hash` | Offline cracking |

```bash
# Verificar que /api/me não expõe campos internos
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/me | jq 'keys'
# Esperado: id, username, email — NÃO password_hash
```

**Solução:** HTTPS em produção, erros genéricos (`DEBUG=False`), serialização segura da API.

---

## 6. Comparação com SAST

SAST e DAST cobrem camadas diferentes. Use ambos.

```
┌─────────────────────┐     ┌─────────────────────┐
│       SAST          │     │       DAST          │
│  Código + deps      │     │  App em execução    │
│  (sem rodar app)    │     │  (HTTP real)        │
└─────────┬───────────┘     └─────────┬───────────┘
          │                           │
          ▼                           ▼
  bandit-report.json          zap-baseline-report.json
  dependency-check.json       (headers, auth, runtime)
```

| Vulnerabilidade | SAST encontra? | DAST encontra? | Exemplo no Task Manager |
|-----------------|----------------|----------------|-------------------------|
| CVE em `requirements.txt` | ✅ Dependency-Check | ❌ | `requests` com CVE |
| `hardcoded_password` no `.py` | ✅ Bandit B105 | ❌ | `SECRET_KEY` no código |
| CSP header ausente | ❌ | ✅ ZAP 10038 | `/login` sem CSP |
| Cookie sem SameSite | ❌ | ✅ ZAP | cookie de sessão |
| SQLi (código concatenado) | ✅ Bandit | ✅* se explorável | SQLAlchemy parametrizado → SAST ok, DAST não acha bypass |
| IDOR em `/api/tasks/{id}` | Parcial (revisão manual) | ✅ se vulnerável | teste com dois usuários |
| Rate limit no login | Parcial (código) | ✅ | 429 após N tentativas |

\* DAST só confirma SQLi se a injeção funcionar em runtime.

### Script de comparação SAST + DAST

```bash
#!/usr/bin/env bash
# compare-sast-dast.sh — resumo lado a lado
set -euo pipefail

SAST_DIR="${SAST_DIR:-reports/after}"
DAST_JSON="${DAST_JSON:-reports/zap/zap-baseline-report.json}"

echo "=== SAST (Bandit) ==="
jq -r '
  [.results[]? | .issue_severity] | group_by(.) | .[]
  | "\(.[0]): \(length)"
' "$SAST_DIR/bandit-report.json" 2>/dev/null || echo "(sem relatório)"

echo ""
echo "=== SAST (Dependency-Check) ==="
jq -r '
  [.dependencies[]?.vulnerabilities[]? | .severity] | group_by(.) | .[]
  | "\(.[0]): \(length)"
' "$SAST_DIR/dependency-check-report.json" 2>/dev/null || echo "(sem relatório)"

echo ""
echo "=== DAST (ZAP) ==="
jq -r '
  [.site[]?.alerts[]? | .riskdesc | split(" ")[0]] | group_by(.) | .[]
  | "\(.[0]): \(length)"
' "$DAST_JSON" 2>/dev/null || echo "(sem relatório)"
```

Salve como `scripts/compare-sast-dast.sh` e execute após ambos os scans.

### Matriz de correlação (documentar achados)

Crie `reports/dast/sast-dast-matrix.md`:

```markdown
| Achado | SAST | DAST | Prioridade | Status |
|--------|------|------|------------|--------|
| CSP ausente | — | ZAP 10038 Low | Média | Aberto |
| CVE requests | Dep-Check HIGH | — | Alta | Corrigido |
| IDOR /api/tasks | — | ZAP High | Alta | Em análise |
```

---

## 7. Próximos passos

### 1. Documentar vulnerabilidades

```bash
mkdir -p reports/dast
cat > reports/dast/findings.md << 'EOF'
# DAST Findings — Task Manager

| ID | Alerta | pluginid | Risk | URL | Status |
|----|--------|----------|------|-----|--------|
| 1 | CSP Header Not Set | 10038 | Low | /login | Aberto |
EOF
```

### 2. Priorizar correções

| Prioridade | Critério |
|------------|----------|
| P0 | High/Critical no DAST ou SAST |
| P1 | Medium + dados sensíveis |
| P2 | Low (headers) — sprint de hardening |
| P3 | Informational — documentar |

### 3. Implementar remediações

```bash
# Editar código (ex.: security headers em factory.py)
pytest tests/ -v
./scripts/validate-security.sh
```

### 4. Re-executar testes e validar

```bash
./scripts/zap-baseline-local.sh
./scripts/compare-sast-dast.sh   # se criado

# Comparar contagem de High antes/depois
jq '[.site[]?.alerts[]? | select(.riskcode=="3")] | length' \
  reports/zap/zap-baseline-report.json
```

### 5. Integrar na CI

O workflow `.github/workflows/dast.yml` já executa baseline no PR e falha em High/Critical.

---

## Fluxo completo recomendado

```bash
# 1. SAST
./scripts/validate-security.sh

# 2. Subir app + DAST
docker compose up -d --build
./scripts/zap-baseline-local.sh

# 3. Analisar
jq '.site[]?.alerts[] | select(.riskcode=="3")' reports/zap/zap-baseline-report.json

# 4. (Opcional) Full scan antes de release
./scripts/dast-run.sh full

# 5. Limpar
./scripts/dast-cleanup.sh
```

---

## Checklist

- [ ] App em `http://localhost:5000` — `curl /about` → 200
- [ ] Imagem `ghcr.io/zaproxy/zaproxy:stable` disponível
- [ ] Relatórios SAST em `reports/after/`
- [ ] Baseline executado — HTML + JSON em `reports/zap/`
- [ ] Alertas High revisados
- [ ] Matriz SAST×DAST documentada
- [ ] Re-scan após correções

---

## Referências

- [ZAP Docker — baseline](https://www.zaproxy.org/docs/docker/baseline-scan/)
- [ZAP Docker — full scan](https://www.zaproxy.org/docs/docker/full-scan/)
- Comparativo detalhado: [`SAST_vs_DAST.md`](SAST_vs_DAST.md)
- Ambiente de teste DAST: [`DAST_TEST_ENVIRONMENT.md`](DAST_TEST_ENVIRONMENT.md)
- Validação pós-correção: [`SECURITY_VALIDATION.md`](SECURITY_VALIDATION.md)
