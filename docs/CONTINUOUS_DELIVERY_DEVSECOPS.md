# Guia Completo — Entrega Contínua (CD) em DevSecOps

Este documento explica **Continuous Delivery** no contexto DevSecOps, com exemplos práticos baseados no **Task Manager Flask** deste repositório.

---

## Visão geral do pipeline deste projeto

```
┌─────────┐   ┌───────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌─────────┐   ┌───────┐   ┌──────────┐   ┌─────────┐
│ Commit  │ → │ Build │ → │ Test │ → │ SAST │ → │ DAST │ → │ Staging │ → │ Smoke │ → │ Approval │ → │  Prod   │
│         │   │       │   │      │   │      │   │      │   │ Deploy  │   │ Tests │   │ (manual) │   │ Deploy  │
└─────────┘   └───────┘   └──────┘   └──────┘   └──────┘   └─────────┘   └───────┘   └──────────┘   └─────────┘
                                                                                                              │
                                                                                                              ▼
                                                                                                        ┌───────────┐
                                                                                                        │ Monitoring│
                                                                                                        └───────────┘
```

**Git Flow deste repositório:**

```
feat/<escopo>  →  develop  →  homolog  →  master/main
  (feature)      (integração)  (staging)   (produção)
```

| Etapa | Workflow / ferramenta | Branch típica |
|-------|----------------------|---------------|
| Build + Test + Lint | `.github/workflows/ci.yml` | `develop`, `homolog`, `main` |
| SAST | `.github/workflows/sast.yml` | `develop`, PR |
| DAST | `.github/workflows/dast.yml` | `homolog`, PR |
| Deploy | `.github/workflows/deploy.yml` | `main` (produção) |

---

## 1. O que é Continuous Delivery (CD)?

### Definição

**Continuous Delivery (Entrega Contínua)** é a prática de automatizar o caminho do código versionado até um ambiente onde ele pode ser implantado em produção **a qualquer momento**, com confiança.

Princípios centrais:

- **Automação do processo de deploy** — build, testes, segurança e publicação de artefatos sem intervenção manual repetitiva.
- **Código sempre pronto para produção** — cada commit na branch de integração passa por validações; o artefato (imagem Docker, pacote) é reproduzível.
- **Deploy manual ou automático** — a decisão de *quando* ir para produção pode ser humana (botão, aprovação) ou totalmente automatizada.

### CD vs Continuous Deployment

| Aspecto | Continuous Delivery | Continuous Deployment |
|---------|---------------------|----------------------|
| Artefato | Sempre deployável | Sempre deployável |
| Decisão de ir a produção | **Manual** (ou com aprovação) | **Automática** após gates |
| Exemplo | Merge em `homolog` → QA aprova → deploy `main` | Merge em `main` → deploy imediato |
| Risco operacional | Menor — humano no loop | Maior — exige gates muito confiáveis |
| Uso comum | Empresas reguladas, B2B, equipes em maturação | SaaS com feature flags e observabilidade forte |

**Analogia no Task Manager:**

```bash
# Continuous Delivery — imagem publicada, deploy decidido depois
git push origin main          # ci.yml + sast passam
# → deploy.yml publica imagem no Docker Hub
# → equipe clica "Deploy" no servidor de homolog/prod quando quiser

# Continuous Deployment — push em main já atualiza produção
git push origin main          # pipeline completo até kubectl apply / docker compose pull
# → usuários recebem nova versão sem ação manual
```

### Exemplo prático — artefato sempre pronto

O job `build` em `ci.yml` só roda após `test` e `lint` passarem:

```yaml
# .github/workflows/ci.yml (trecho)
build:
  needs: [test, lint]
  steps:
    - name: Build imagem Docker
      run: docker build -t task-manager:latest .
```

Se os testes falham, **não há imagem confiável** — isso é CD na prática.

---

## 2. Benefícios da CD

### Redução de tempo entre desenvolvimento e produção

**Antes (manual):** desenvolvedor envia ZIP → ops copia para servidor → configura `.env` → reinicia processo → 2–5 dias.

**Com CD (este projeto):**

```bash
# Desenvolvedor abre PR feat/auth-jwt → develop
# CI roda em ~5–10 min: pytest + flake8 + docker build
# Após merge: artefato pronto; homolog recebe mesma imagem
```

### Redução de erros manuais

Deploy manual comum: esquecer variável `SECRET_KEY`, versão errada do Python, dependência não instalada.

**Com CD:** mesma imagem Docker testada na CI:

```dockerfile
# Dockerfile — ambiente idêntico em dev, CI, staging e prod
FROM python:3.11-slim
WORKDIR /app/todo_project
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

### Feedback rápido sobre problemas

| Gate | Feedback | Tempo típico |
|------|----------|--------------|
| `pytest tests/` | Teste quebrado | ~1 min |
| Bandit (SAST) | Código inseguro | ~2 min |
| ZAP (DAST) | Header ausente, auth fraca | ~10 min |
| Smoke test pós-deploy | App não sobe | ~30 s |

Exemplo de falha rápida na CI:

```text
FAILED tests/test_auth.py::test_login_invalid_password_returns_401
→ PR bloqueado; nada chega a homolog
```

### Rollback rápido em caso de falhas

Com imagens versionadas (`deploy.yml`):

```bash
# Versão atual com problema
docker pull usuario/task-manager:latest   # tag latest quebrada

# Rollback para versão anterior conhecida
docker pull usuario/task-manager:v1.2.0
docker compose up -d   # com image: usuario/task-manager:v1.2.0
```

### Confiança no processo de deploy

Gates acumulados geram confiança:

```
29 testes pytest ✓  +  Bandit sem HIGH ✓  +  ZAP sem High/Critical ✓  +  smoke /about ✓
→ equipe aprova deploy em produção
```

---

## 3. Etapas do Pipeline CD

### a) Build — compilação/interpretação do código

**O que faz:** transforma código-fonte em artefato executável (imagem Docker, wheel, JAR).

**Neste projeto:**

```yaml
# ci.yml — build após test + lint
- name: Build imagem Docker
  run: docker build -t task-manager:latest .
```

**Local:**

```bash
docker compose build
docker build -t task-manager:latest .
```

---

### b) Test — testes automatizados

**O que faz:** valida comportamento funcional e regressões.

**Neste projeto:** 29 testes em `tests/` (auth, rotas, segurança).

```yaml
# ci.yml
- name: Executar testes
  env:
    FLASK_ENV: testing
    SECRET_KEY: ci-secret-key-not-for-production
  run: pytest tests/ -v --cov=todo_project --cov-report=xml
```

```bash
# Local
pytest tests/ -v
docker compose exec app pytest /app/tests -v
```

---

### c) Security Scan — SAST e DAST

**SAST** (código parado, sem rodar app):

| Ferramenta | Workflow | Falha em |
|------------|----------|----------|
| Bandit | `sast.yml` | Issues HIGH |
| Dependency-Check | `sast.yml` | CVE CRITICAL |
| Safety | `sast.yml` | Relatório (informativo) |

```bash
./scripts/validate-security.sh   # local
```

**DAST** (app em execução):

```yaml
# dast.yml — sobe stack + ZAP baseline
- name: OWASP ZAP Baseline Scan
  uses: zaproxy/action-baseline@v0.15.0
  with:
    target: http://localhost:5000
    docker_name: ghcr.io/zaproxy/zaproxy:stable
```

```bash
./scripts/zap-baseline-local.sh
```

**Gate DevSecOps:** deploy só prossegue se SAST e DAST estiverem verdes (ou exceções documentadas).

---

### d) Staging Deploy — deploy em ambiente de teste

**O que faz:** publica o artefato em ambiente que replica produção (`homolog` neste repo).

**Exemplo conceitual (homolog):**

```yaml
# deploy-homolog.yml (exemplo a expandir)
deploy-staging:
  needs: [test, sast, dast]
  environment: homolog
  steps:
    - name: Push imagem
      run: |
        docker tag task-manager:latest $REGISTRY/task-manager:homolog
        docker push $REGISTRY/task-manager:homolog
    - name: Deploy no servidor de homolog
      run: |
        ssh deploy@homolog.example.com \
          "cd /opt/task-manager && docker compose pull && docker compose up -d"
```

**Variáveis de homolog** (`.env` diferente de produção):

```bash
FLASK_ENV=production
SECRET_KEY=<secret-do-vault-homolog>
DATABASE_URL=postgresql://...@db-homolog:5432/taskmanager
SYSLOG_ENABLED=true
```

---

### e) Smoke Tests — testes rápidos pós-deploy

**O que faz:** confirma que o deploy “subiu” — não substitui testes completos.

**Exemplos para o Task Manager:**

```bash
#!/usr/bin/env bash
# smoke-test.sh
set -euo pipefail
BASE_URL="${1:-http://localhost:5000}"

curl -sf "$BASE_URL/about" | grep -qi "task" || { echo "FAIL: /about"; exit 1; }
curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/login" | grep -q "200"
curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/api/me" | grep -q "401"

echo "Smoke tests OK"
```

No `dast.yml`, o health check antes do ZAP é um smoke test:

```bash
curl -sf http://localhost:5000/about
```

---

### f) Approval — aprovação manual (opcional)

**O que faz:** humano autoriza deploy em produção após validação em homolog.

**GitHub Environments** (já usado em `deploy.yml`):

```yaml
deploy:
  environment: production   # exige aprovadores configurados em Settings → Environments
  steps:
    - name: Push imagem para Docker Hub
      run: docker push ...
```

**Fluxo:**

```
1. QA valida homolog manualmente
2. PR homolog → main
3. GitHub pede aprovação de "production"
4. Após aprovação, job deploy executa
```

---

### g) Production Deploy — deploy em produção

**Neste projeto** (`deploy.yml` em push em `main`):

1. Checkout + versão via git tag
2. Build imagem Docker
3. Login Docker Hub (secrets)
4. Push `latest` + tag de versão
5. Notificação Slack (opcional)

```yaml
# deploy.yml (trecho)
- name: Build imagem Docker
  run: |
    docker build \
      -t "${{ secrets.DOCKER_USERNAME }}/task-manager:latest" \
      -t "${{ secrets.DOCKER_USERNAME }}/task-manager:${{ steps.version.outputs.version }}" \
      .
```

**Deploy no servidor** (exemplo SSH):

```bash
# No servidor de produção
export IMAGE=usuario/task-manager:v1.3.0
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
./scripts/smoke-test.sh https://app.exemplo.com
```

---

### h) Monitoring — monitoramento pós-deploy

**O que observar após deploy:**

| Sinal | Ferramenta | Alerta |
|-------|------------|--------|
| HTTP 5xx | Prometheus / nginx logs | Taxa de erro > 1% |
| Latência | APM (Datadog, New Relic) | p95 > SLA |
| Health | `GET /about` | Falha consecutiva |
| Segurança | SIEM / audit_log | Login anômalo |
| Infra | Docker / K8s | Container restart loop |

**Task Manager — syslog e audit:**

```python
# Eventos em audit_log + rsyslog (configurável via .env)
SYSLOG_ENABLED=true
```

**Smoke contínuo (cron):**

```bash
# */5 * * * * — a cada 5 min
curl -sf https://app.exemplo.com/about || pagerduty-trigger "Task Manager down"
```

---

## 4. Ambientes

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Development  │ ──► │   Staging    │ ──► │  Production  │
│   (local)    │     │  (homolog)   │     │   (master)   │
└──────────────┘     └──────────────┘     └──────────────┘
  docker compose       mesmo compose         secrets reais
  SECRET_KEY dev       DAST + QA manual      HTTPS, backups
  dados fictícios      cópia anonimizada     usuários reais
```

### Development — máquina local

```bash
cp .env.example .env
docker compose up -d
pytest tests/ -v
curl http://localhost:5000/about
```

- Dados locais, sem impacto em usuários
- `FLASK_ENV=development` ou `testing` nos testes
- SAST/DAST podem rodar localmente (`validate-security.sh`, `zap-baseline-local.sh`)

### Staging (homolog) — replica produção

- Branch Git: `homolog`
- Mesma imagem Docker que irá a produção
- DAST automático em PR/push (`dast.yml`)
- Banco separado; credenciais de homolog no vault
- URL exemplo: `https://homolog.taskmanager.internal`

### Production — ambiente real

- Branch Git: `main` / `master`
- `environment: production` com aprovação
- Secrets via GitHub Secrets / Vault — **nunca** no repositório
- TLS, rate limits reais, backups de PostgreSQL

**Matriz de configuração:**

| Variável | Development | Staging | Production |
|----------|-------------|---------|------------|
| `SECRET_KEY` | valor local | vault homolog | vault prod |
| `FLASK_ENV` | development | production | production |
| `JWT_COOKIE_SECURE` | false | true | true |
| `LOGIN_RATE_LIMIT` | relaxado | real | real |
| DAST full scan | opcional | recomendado | agendado |

---

## 5. Estratégias de Deploy

### a) Blue-Green Deploy

Duas instâncias idênticas; tráfego comuta de uma para outra.

```
                    ┌─────────────┐
   Tráfego ───────► │   GREEN     │  v1.2.0 (ativa)
                    │  (prod)     │
                    └─────────────┘

   Deploy v1.3.0 →  ┌─────────────┐
                    │    BLUE     │  v1.3.0 (nova, em teste)
                    └─────────────┘

   Smoke OK → switch:
                    ┌─────────────┐
   Tráfego ───────► │    BLUE     │  v1.3.0 (ativa)
                    └─────────────┘
                    ┌─────────────┐
                    │   GREEN     │  v1.2.0 (standby / rollback)
                    └─────────────┘
```

**Exemplo com Docker Compose + nginx:**

```yaml
# docker-compose.blue-green.yml (conceito)
services:
  app-blue:
    image: usuario/task-manager:v1.3.0
    profiles: [blue]
  app-green:
    image: usuario/task-manager:v1.2.0
    profiles: [green]
  nginx:
    # upstream aponta para app-blue OU app-green
```

```bash
# Trocar upstream no nginx e reload
nginx -s reload
# Rollback: apontar de volta para green (v1.2.0)
```

| Prós | Contras |
|------|---------|
| Rollback instantâneo | Dobra recursos temporariamente |
| Zero downtime na troca | Migração de estado (DB) precisa cuidado |

---

### b) Canary Deploy

Pequena fração do tráfego na nova versão; aumento gradual se métricas OK.

```
100% tráfego ──► v1.2.0

Canary 5%  ──► v1.3.0
95%        ──► v1.2.0
     │
     ├─ erro 5xx ↑  → rollback automático (100% v1.2.0)
     └─ métricas OK → 25% → 50% → 100% v1.3.0
```

**Exemplo nginx (peso):**

```nginx
upstream task_manager {
    server app-v1-2-0:5000 weight=95;
    server app-v1-3-0:5000 weight=5;
}
```

**Kubernetes (conceito):**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  strategy:
    canary:
      steps:
        - setWeight: 5
        - pause: { duration: 10m }
        - setWeight: 50
        - pause: { duration: 10m }
        - setWeight: 100
```

| Prós | Contras |
|------|---------|
| Detecta problemas com poucos usuários afetados | Requer load balancer + métricas |
| Rollback automático possível | Mais complexo de operar |

---

### c) Rolling Deploy

Atualiza instâncias uma a uma, sem tirar todo o serviço.

```
Instância 1: v1.2.0 → v1.3.0  (drain + replace)
Instância 2: v1.2.0            (ainda ativa)
Instância 3: v1.2.0            (ainda ativa)
         ...
Todas em v1.3.0
```

**Docker Swarm / Kubernetes:**

```bash
kubectl set image deployment/task-manager app=usuario/task-manager:v1.3.0
kubectl rollout status deployment/task-manager
# Rollback:
kubectl rollout undo deployment/task-manager
```

**docker compose scale (conceito):**

```bash
docker compose up -d --scale app=3 --no-recreate
# Atualizar uma réplica por vez com health check entre elas
```

| Prós | Contras |
|------|---------|
| Sem downtime | Duas versões coexistem durante rollout |
| Menos recursos que blue-green | Rollback mais lento que blue-green |
| Nativo em K8s | Versões incompatíveis no DB exigem migração cuidadosa |

### Qual estratégia usar?

| Cenário | Estratégia sugerida |
|---------|---------------------|
| App stateless + Docker simples | Rolling ou blue-green |
| Alta disponibilidade, rollback crítico | Blue-green |
| Muitos usuários, feature arriscada | Canary |
| Task Manager MVP (compose) | Blue-green ou rolling com 2 réplicas |

---

## 6. Segurança em CD (DevSecOps)

A CD não é só velocidade — **gates de segurança** bloqueiam artefatos inseguros.

### Validar SAST/DAST antes do deploy

```yaml
# Pipeline unificado (exemplo)
jobs:
  sast:
    uses: ./.github/workflows/sast.yml
  dast:
    needs: sast
    uses: ./.github/workflows/dast.yml
  deploy:
    needs: [test, sast, dast]
    environment: production
```

**Regras deste projeto:**

- Bandit: falha em **HIGH**
- Dependency-Check: falha em **CRITICAL**
- ZAP: falha em alertas **High/Critical**

### Validar que testes passaram

```yaml
build:
  needs: [test, lint]   # build só se testes OK
```

### Validar dependências seguras

```bash
# CI — Dependency-Check + Safety
./scripts/validate-security.sh
./scripts/compare-sast-dast.sh
```

### Secrets seguros

```yaml
# ✅ Correto — GitHub Secrets
password: ${{ secrets.DOCKER_PASSWORD }}

# ❌ Nunca
password: "minha-senha-123"
```

**`.env` em produção:** injetado no runtime, não na imagem:

```dockerfile
# Dockerfile — NÃO copiar .env
# COPY .env .   ← nunca fazer isso
```

### Auditar quem fez deploy

- GitHub Actions: log com `github.actor`, `github.sha`
- `audit_log` na aplicação para ações de usuário
- Slack webhook em `deploy.yml` registra commit e versão

### Monitorar comportamento pós-deploy

- Picos de `401`/`429` após deploy → possível regressão de auth
- Novos alertas WAF/SIEM
- Re-scan DAST agendado pós-deploy em homolog

**Checklist DevSecOps CD:**

- [ ] `pytest` verde
- [ ] SAST sem HIGH/CRITICAL
- [ ] DAST sem High/Critical (homolog)
- [ ] Secrets no vault, não no Git
- [ ] Smoke test pós-deploy
- [ ] Aprovação em `environment: production`
- [ ] Monitoramento ativo 24h após release

---

## 7. Ferramentas para CD

| Ferramenta | Papel | Uso neste projeto |
|------------|-------|-------------------|
| **GitHub Actions** | CI/CD nativo GitHub | `ci.yml`, `sast.yml`, `dast.yml`, `deploy.yml` |
| **GitLab CI/CD** | CI/CD nativo GitLab | Alternativa equivalente (`.gitlab-ci.yml`) |
| **Jenkins** | Servidor de automação self-hosted | Migrar pipelines Actions para Jenkinsfile |
| **ArgoCD** | Deploy GitOps (K8s) | Sync de manifests a partir do Git |
| **Spinnaker** | Deploy multi-cloud | Pipelines canary/blue-green em escala |
| **Docker Registry** | Armazenar imagens | Docker Hub (`deploy.yml`) |
| **Kubernetes** | Orquestração | Escalar Task Manager além de compose |

### Exemplo — mesmo pipeline em GitLab CI

```yaml
# .gitlab-ci.yml (equivalente conceitual)
stages: [test, security, build, deploy]

test:
  stage: test
  script: pip install -r requirements.txt && pytest tests/ -v

sast:
  stage: security
  script: bandit -r todo_project/todo_project

build:
  stage: build
  script: docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
  needs: [test, sast]

deploy_staging:
  stage: deploy
  environment: homolog
  script: docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  when: manual

deploy_prod:
  stage: deploy
  environment: production
  script: kubectl set image deployment/task-manager app=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  when: manual
  needs: [deploy_staging]
```

### Exemplo — ArgoCD (GitOps)

```yaml
# k8s/deployment.yaml no Git — ArgoCD aplica automaticamente
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-manager
spec:
  template:
    spec:
      containers:
        - name: app
          image: usuario/task-manager:v1.3.0
```

ArgoCD observa o repositório; mudança de tag → sync → rolling update no cluster.

---

## 8. Exemplo de Pipeline CD completo

### Fluxo end-to-end

```
Commit (PR → develop)
    │
    ├─► Build (docker build)
    ├─► Test  (pytest 29 testes)
    ├─► Lint  (flake8, black)
    ├─► SAST  (Bandit, Dep-Check, Safety)
    │
    ▼
Merge develop → homolog
    │
    ├─► DAST (ZAP baseline em docker compose)
    ├─► Staging Deploy (imagem :homolog)
    ├─► Smoke Tests (/about, /login, /api/me → 401)
    │
    ▼
Approval manual (QA + security)
    │
    ▼
Merge homolog → main
    │
    ├─► Production Deploy (push Docker Hub :latest + :vX.Y.Z)
    ├─► Smoke Tests em produção
    └─► Monitoring (logs, health, alertas)
```

### Workflow unificado (exemplo futuro)

```yaml
# .github/workflows/cd-pipeline.yml (referência)
name: CD Pipeline

on:
  push:
    branches: [homolog, main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt && pytest tests/ -v

  security:
    needs: test
    uses: ./.github/workflows/sast.yml

  dast:
    if: github.ref == 'refs/heads/homolog'
    needs: security
    uses: ./.github/workflows/dast.yml

  build-and-push:
    needs: [test, security]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t task-manager:${{ github.sha }} .

  deploy-staging:
    if: github.ref == 'refs/heads/homolog'
    needs: [build-and-push, dast]
    environment: homolog
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploy homolog + ./scripts/smoke-test.sh"

  deploy-production:
    if: github.ref == 'refs/heads/main'
    needs: build-and-push
    environment: production
    runs-on: ubuntu-latest
    steps:
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}
      - run: |
          docker build -t ${{ secrets.DOCKER_USERNAME }}/task-manager:latest .
          docker push ${{ secrets.DOCKER_USERNAME }}/task-manager:latest
```

### Comandos locais que espelham o pipeline

```bash
# 1. Build + Test (CI)
pytest tests/ -v && docker build -t task-manager:latest .

# 2. Security (SAST)
./scripts/validate-security.sh

# 3. Security (DAST) — app rodando
docker compose up -d
./scripts/zap-baseline-local.sh

# 4. Comparação SAST × DAST
./scripts/compare-sast-dast.sh

# 5. Smoke
curl -sf http://localhost:5000/about && echo OK

# 6. Limpeza
./scripts/dast-cleanup.sh
```

---

## Maturidade CD — níveis

| Nível | Características | Este projeto |
|-------|-----------------|--------------|
| 1 — Básico | CI com testes + build manual deploy | ✅ CI (`ci.yml`) |
| 2 — Automatizado | SAST na CI, imagem Docker | ✅ `sast.yml`, `build` |
| 3 — DevSecOps | DAST em homolog, gates de segurança | ✅ `dast.yml` |
| 4 — CD | Deploy automatizado com aprovação | ⚠️ `deploy.yml` (push imagem; deploy servidor a configurar) |
| 5 — CD completo | Staging + smoke + canary + monitor | 🔜 expandir homolog deploy + smoke script |

---

## Referências neste repositório

| Documento | Conteúdo |
|-----------|----------|
| [`SECURITY_VALIDATION.md`](SECURITY_VALIDATION.md) | Validação SAST pós-correção |
| [`SAST_vs_DAST.md`](SAST_vs_DAST.md) | Complementaridade SAST/DAST |
| [`OWASP_ZAP_LOCAL.md`](OWASP_ZAP_LOCAL.md) | Executar ZAP localmente |
| [`DAST_TEST_ENVIRONMENT.md`](DAST_TEST_ENVIRONMENT.md) | Preparar ambiente DAST |
| `CONTRIBUTING.md` | Git Flow develop → homolog → master |
| `.github/workflows/` | Pipelines implementados |

---

## Glossário rápido

| Termo | Significado |
|-------|-------------|
| **Artifact** | Imagem Docker, relatório, pacote gerado pelo pipeline |
| **Gate** | Condição que bloqueia próxima etapa (ex.: testes falharam) |
| **GitOps** | Infra e deploy declarados em Git (ArgoCD) |
| **Smoke test** | Verificação mínima pós-deploy (“app responde?”) |
| **Rollback** | Voltar à versão anterior estável |
| **Staging** | Homolog — espelho de produção para validação |
