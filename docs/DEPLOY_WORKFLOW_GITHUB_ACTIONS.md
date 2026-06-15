# Guia Prático — Workflow de Deploy Contínuo (CD) com GitHub Actions

Este guia descreve o pipeline de **Continuous Delivery** do Task Manager Flask, implementado em `.github/workflows/deploy.yml` e adaptado à estrutura real do projeto.

---

## Visão do pipeline

```
push main/master
      │
      ▼
┌─────────────────────┐
│ security-validation │  pytest + Bandit (SAST)
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  build-and-push     │  Docker Hub :latest + :versão
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ staging-and-smoke   │  compose staging + smoke auth/CRUD
│  (environment:      │
│   homolog)          │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ deploy-production   │  ← aprovação manual (environment: production)
│  blue-green SSH     │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│      notify         │  Slack + resumo
└─────────────────────┘
```

**Arquivos do projeto:**

| Arquivo | Função |
|---------|--------|
| `.github/workflows/deploy.yml` | Pipeline CD completo |
| `docker-compose.staging.yml` | Staging sem bind mount (imagem do registry) |
| `docker-compose.prod.yml` | Blue-green (app-blue / app-green) |
| `scripts/smoke-test.sh` | Smoke básico (`/about`, `/login`, `/api/me`) |
| `scripts/smoke-test-deploy.sh` | Smoke com auth + CRUD (`/tasks`) |
| `scripts/deploy-blue-green.sh` | Troca de slot em produção |

---

## 1. Estrutura do workflow

| Item | Valor neste projeto |
|------|---------------------|
| **Nome** | `Deploy Pipeline` |
| **Arquivo** | `.github/workflows/deploy.yml` |
| **Trigger** | `push` em `main` ou `master` (produção) |
| **Manual** | `workflow_dispatch` (rollback, pular staging) |

```yaml
name: Deploy Pipeline

on:
  push:
    branches: [main, master]
  workflow_dispatch:
    inputs:
      skip_staging:
        description: "Pular staging (apenas emergência)"
        type: boolean
        default: false
      rollback_version:
        description: "Versão para rollback (ex.: v1.2.0)"
        type: string
        required: false

permissions:
  contents: read

env:
  IMAGE_NAME: task-manager
  APP_SOURCE: todo_project/todo_project
```

> **Git Flow:** `develop` → `homolog` → `master/main`. O deploy dispara apenas no merge final em `main`/`master`, após validação em homolog (CI, SAST, DAST).

---

## 2. Jobs do workflow

### a) Build and Push Docker Image

Publica `docker.io/<DOCKER_USERNAME>/task-manager:latest` e tag de versão.

```yaml
build-and-push:
  name: Build and Push Docker Image
  runs-on: ubuntu-latest
  needs: security-validation
  outputs:
    version: ${{ steps.version.outputs.version }}
    image: ${{ steps.meta.outputs.image }}
    previous_version: ${{ steps.prev.outputs.previous_version }}
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0

    - uses: docker/setup-buildx-action@v3

    - name: Obter versão (git tag)
      id: version
      run: |
        if TAG=$(git describe --tags --exact-match HEAD 2>/dev/null); then
          VERSION="$TAG"
        else
          BASE_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")
          VERSION="${BASE_TAG}-build.${GITHUB_SHA::7}"
        fi
        echo "version=${VERSION}" >> "$GITHUB_OUTPUT"

    - uses: docker/login-action@v3
      with:
        username: ${{ secrets.DOCKER_USERNAME }}
        password: ${{ secrets.DOCKER_PASSWORD }}

    - name: Metadados da imagem
      id: meta
      run: echo "image=${{ secrets.DOCKER_USERNAME }}/task-manager" >> "$GITHUB_OUTPUT"

    - name: Build imagem Docker
      run: |
        docker build \
          -t "${{ steps.meta.outputs.image }}:latest" \
          -t "${{ steps.meta.outputs.image }}:${{ steps.version.outputs.version }}" \
          .

    - name: Push para Docker Hub
      run: |
        docker push "${{ steps.meta.outputs.image }}:latest"
        docker push "${{ steps.meta.outputs.image }}:${{ steps.version.outputs.version }}"
```

**Exemplo de imagem publicada:**

```
docker.io/seu-usuario/task-manager:latest
docker.io/seu-usuario/task-manager:v1.0.0-build.a1b2c3d
```

**Health check na imagem** (já no `Dockerfile`):

```dockerfile
HEALTHCHECK ... CMD python -c "urllib.request.urlopen('http://127.0.0.1:5000/about')"
```

---

### b) Deploy to Staging

Usa `docker-compose.staging.yml` — imagem do registry, sem bind mount de código.

```yaml
staging-and-smoke:
  name: Deploy Staging + Smoke Tests
  runs-on: ubuntu-latest
  needs: build-and-push
  environment: homolog
  steps:
    - uses: actions/checkout@v4
    - uses: docker/setup-buildx-action@v3
    - uses: docker/login-action@v3
      with:
        username: ${{ secrets.DOCKER_USERNAME }}
        password: ${{ secrets.DOCKER_PASSWORD }}

    - name: Deploy staging (Docker Compose)
      env:
        DOCKER_IMAGE: ${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.version }}
      run: |
        export SECRET_KEY=staging-cd-${{ github.sha }}
        export REGISTRATION_ENABLED=true
        docker compose -f docker-compose.staging.yml up -d

    - name: Aguardar health check
      run: |
        for i in $(seq 1 36); do
          curl -sf http://localhost:5000/about && exit 0
          sleep 5
        done
        docker compose -f docker-compose.staging.yml logs app --tail 40
        exit 1
```

**`docker-compose.staging.yml` (trecho):**

```yaml
services:
  app:
    image: ${DOCKER_IMAGE:-task-manager:latest}
    ports:
      - "5000:5000"
    environment:
      FLASK_APP: todo_project
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}
      REGISTRATION_ENABLED: ${REGISTRATION_ENABLED:-true}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/about')"]
```

**Deploy remoto (servidor de homolog via SSH):**

```yaml
- name: Deploy staging via SSH
  uses: appleboy/ssh-action@v1.2.0
  with:
    host: ${{ secrets.STAGING_SSH_HOST }}
    username: ${{ secrets.STAGING_SSH_USER }}
    key: ${{ secrets.STAGING_SSH_KEY }}
    script: |
      export DOCKER_IMAGE="${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.version }}"
      cd /opt/task-manager
      docker compose -f docker-compose.staging.yml pull
      docker compose -f docker-compose.staging.yml up -d
```

---

### c) Smoke Tests

Executados no **mesmo job** que o staging (mesmo runner), contra `http://localhost:5000`.

```yaml
    - name: Instalar jq
      run: sudo apt-get install -y -qq jq

    - name: Smoke tests — endpoints e auth
      run: |
        chmod +x scripts/smoke-test.sh scripts/smoke-test-deploy.sh
        ./scripts/smoke-test.sh http://localhost:5000
        ./scripts/smoke-test-deploy.sh http://localhost:5000

    - name: Encerrar staging
      if: always()
      run: docker compose -f docker-compose.staging.yml down -v
```

**O que `smoke-test-deploy.sh` valida:**

| Teste | Endpoint | Esperado |
|-------|----------|----------|
| Health | `GET /about` | 200 |
| Login page | `GET /login` | 200 |
| Auth obrigatória | `GET /api/me` | 401 |
| Registro | `POST /api/auth/register` | 201 |
| Login | `POST /api/auth/login` | 200 + JWT |
| Perfil | `GET /api/me` + Bearer | 200 |
| Criar tarefa | `POST /tasks` | 201 |
| Listar | `GET /api/tasks` | 200 |
| Atualizar | `PUT /tasks/{id}` | 200 |
| Remover | `DELETE /tasks/{id}` | 200 |

**Local:**

```bash
docker compose -f docker-compose.staging.yml up -d
./scripts/smoke-test-deploy.sh http://localhost:5000
```

---

### d) Security Validation

Gate **antes** do build — falha bloqueia todo o deploy.

```yaml
security-validation:
  name: Security Validation
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - run: pip install -r requirements.txt bandit pytest

    - name: Testes automatizados (pytest)
      env:
        FLASK_ENV: testing
        SECRET_KEY: ci-secret-key-not-for-production
        SYSLOG_ENABLED: "false"
        BOOTSTRAP_ADMIN_ENABLED: "false"
      run: pytest tests/ -v --tb=short

    - name: SAST — Bandit
      run: |
        bandit -r todo_project/todo_project -f json -o bandit-report.json || true
        python -c "
        import json, sys
        from pathlib import Path
        data = json.loads(Path('bandit-report.json').read_text())
        crit = [r for r in data.get('results',[]) if r.get('issue_severity') in ('HIGH','CRITICAL')]
        sys.exit(1 if crit else 0)
        "

    - name: Nota — DAST em homolog
      run: echo "DAST (dast.yml) deve estar verde em homolog antes do merge em main."
```

**Validações e origem:**

| Validação | Onde roda no CD | Workflow dedicado |
|-----------|-----------------|-------------------|
| Testes | `security-validation` | `ci.yml` |
| SAST Bandit | `security-validation` | `sast.yml` |
| Dependências CVE | PR em develop/homolog | `sast.yml` (Dependency-Check) |
| DAST ZAP | Gate manual — homolog | `dast.yml` |

```bash
# Validação local completa antes do merge
pytest tests/ -v
./scripts/validate-security.sh
./scripts/zap-baseline-local.sh
```

---

### e) Manual Approval (opcional)

Configurado via **GitHub Environments** — não é YAML no repositório.

**Passos:**

1. GitHub → **Settings** → **Environments**
2. Criar `homolog` e `production`
3. Em `production`: marcar **Required reviewers** e **Wait timer** (opcional)
4. O job referencia o environment:

```yaml
deploy-production:
  environment: production   # ← pausa até aprovação
  needs: [build-and-push, staging-and-smoke]
```

**Quem aprova:** usuários/equipes definidos nas protection rules do environment.

---

### f) Deploy to Production

Blue-green com `docker-compose.prod.yml` + `scripts/deploy-blue-green.sh`.

```yaml
deploy-production:
  name: Deploy to Production
  runs-on: ubuntu-latest
  needs: [build-and-push, staging-and-smoke]
  environment: production
  steps:
    - uses: actions/checkout@v4
    - uses: docker/login-action@v3
      with:
        username: ${{ secrets.DOCKER_USERNAME }}
        password: ${{ secrets.DOCKER_PASSWORD }}

    - name: Deploy produção via SSH (blue-green)
      if: ${{ secrets.PROD_SSH_HOST != '' }}
      uses: appleboy/ssh-action@v1.2.0
      with:
        host: ${{ secrets.PROD_SSH_HOST }}
        username: ${{ secrets.PROD_SSH_USER }}
        key: ${{ secrets.PROD_SSH_KEY }}
        script: |
          export DOCKER_IMAGE="${{ needs.build-and-push.outputs.image }}:${{ steps.deploy.outputs.version }}"
          export SECRET_KEY="${{ secrets.PROD_JWT_SECRET }}"
          export DATABASE_URL="${{ secrets.PROD_DATABASE_URL }}"
          cd /opt/task-manager
          ./scripts/deploy-blue-green.sh "${{ steps.deploy.outputs.version }}"

    - name: Smoke tests produção
      if: vars.PROD_URL != ''
      id: prod_smoke
      continue-on-error: true
      run: ./scripts/smoke-test.sh "${{ vars.PROD_URL }}"

    - name: Rollback automático se smoke falhar
      if: steps.prod_smoke.outcome == 'failure'
      uses: appleboy/ssh-action@v1.2.0
      with:
        host: ${{ secrets.PROD_SSH_HOST }}
        key: ${{ secrets.PROD_SSH_KEY }}
        script: |
          cd /opt/task-manager
          ./scripts/deploy-blue-green.sh "${{ needs.build-and-push.outputs.previous_version }}" --rollback
```

**Blue-green (`docker-compose.prod.yml`):**

```yaml
services:
  app-blue:
    profiles: [blue]
    image: ${DOCKER_IMAGE}
    ports: ["5001:5000"]
  app-green:
    profiles: [green]
    image: ${DOCKER_IMAGE}
    ports: ["5002:5000"]
```

**Fluxo:**

```
1. Slot inativo (ex.: green) sobe com nova imagem
2. Health check em :5002/about
3. Proxy/nginx troca tráfego para green
4. Slot blue é drenado
5. Se smoke falhar → rollback para previous_version
```

---

## 3. Variáveis de ambiente

### GitHub Variables (não sensíveis)

| Variável | Exemplo | Uso |
|----------|---------|-----|
| `STAGING_URL` | `http://homolog.internal:5000` | Smoke remoto |
| `PROD_URL` | `https://app.exemplo.com` | Smoke pós-deploy prod |

Configurar em: **Settings → Secrets and variables → Actions → Variables**

### Variáveis da aplicação (`.env` / servidor)

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | Chave Flask (equivale a JWT HS256 neste projeto) |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/taskmanager` |
| `FLASK_ENV` | `production` em staging/prod |
| `REGISTRATION_ENABLED` | `true` em staging; `false` em prod (recomendado) |
| `JWT_COOKIE_SECURE` | `true` em HTTPS |

Ver `.env.example` para lista completa.

---

## 4. Secrets

Configurar em: **Settings → Secrets and variables → Actions → Secrets**

| Secret | Obrigatório | Descrição |
|--------|-------------|-----------|
| `DOCKER_USERNAME` | Sim | Usuário Docker Hub |
| `DOCKER_PASSWORD` | Sim | **Token** de acesso Docker Hub |
| `PROD_DATABASE_URL` | Deploy SSH | URL PostgreSQL produção |
| `PROD_JWT_SECRET` | Deploy SSH | `SECRET_KEY` de produção |
| `PROD_SSH_HOST` | Deploy auto | IP/hostname do servidor |
| `PROD_SSH_USER` | Deploy auto | Usuário SSH (ex.: `deploy`) |
| `PROD_SSH_KEY` | Deploy auto | Chave privada SSH |
| `STAGING_SSH_HOST` | Opcional | Host staging remoto |
| `STAGING_SSH_KEY` | Opcional | Chave SSH staging |
| `SLACK_WEBHOOK_URL` | Opcional | Webhook Slack |

**Exemplo — nunca commitar:**

```yaml
# ✅
password: ${{ secrets.DOCKER_PASSWORD }}

# ❌
password: "senha123"
```

---

## 5. Notificações

### Slack

```yaml
notify:
  if: always()
  steps:
    - name: Slack — sucesso
      if: needs.deploy-production.result == 'success'
      uses: slackapi/slack-github-action@v2.0.0
      with:
        webhook: ${{ secrets.SLACK_WEBHOOK_URL }}
        webhook-type: incoming-webhook
        payload: |
          {
            "text": "✅ Deploy OK — `${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.version }}`"
          }

    - name: Slack — falha
      if: needs.deploy-production.result == 'failure'
      uses: slackapi/slack-github-action@v2.0.0
      with:
        webhook: ${{ secrets.SLACK_WEBHOOK_URL }}
        webhook-type: incoming-webhook
        payload: |
          {"text": "❌ Deploy falhou — ver Actions"}
```

### Email (opcional)

```yaml
    - name: Email stakeholders
      if: failure()
      uses: dawidd6/action-send-mail@v3
      with:
        server_address: smtp.gmail.com
        server_port: 465
        username: ${{ secrets.MAIL_USERNAME }}
        password: ${{ secrets.MAIL_PASSWORD }}
        subject: "[Task Manager] Deploy falhou"
        to: devops@exemplo.com
        from: ci@exemplo.com
        body: "Workflow: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

### Comentário em PR

O deploy dispara em `push` para `main`, não em PR. Para status em PR, use workflows `ci.yml` + `sast.yml` + `dast.yml` com branch protection.

---

## 6. Rollback

### Automático — smoke falha em produção

O job `deploy-production` chama `deploy-blue-green.sh` com `previous_version` (tag git anterior).

### Manual — workflow_dispatch

1. Actions → **Deploy Pipeline** → **Run workflow**
2. Preencher `rollback_version`: `v1.2.0`
3. Opcional: `skip_staging: true` (emergência)

```yaml
workflow_dispatch:
  inputs:
    rollback_version:
      description: "Versão para rollback"
      type: string
```

### Manual — servidor

```bash
ssh deploy@prod.exemplo.com
cd /opt/task-manager
export DOCKER_IMAGE=usuario/task-manager:v1.2.0
export SECRET_KEY=...
export DATABASE_URL=...
./scripts/deploy-blue-green.sh v1.2.0 --rollback
```

### Reverter imagem Docker Hub

```bash
# Re-tag versão estável como latest (emergência)
docker pull usuario/task-manager:v1.2.0
docker tag usuario/task-manager:v1.2.0 usuario/task-manager:latest
docker push usuario/task-manager:latest
```

---

## 7. Monitoramento pós-deploy

### Logs da aplicação

```bash
# Servidor de produção
docker compose -f docker-compose.prod.yml logs -f app-blue
docker compose -f docker-compose.prod.yml logs -f app-green

# Local (staging)
docker compose -f docker-compose.staging.yml logs app --tail 100
```

### Health check contínuo

```bash
# Cron a cada 5 min
*/5 * * * * curl -sf https://app.exemplo.com/about || alerta-pagerduty
```

### Métricas (exemplo Prometheus)

| Métrica | Alerta |
|---------|--------|
| CPU container > 80% | Warning |
| Memória > 90% do limit (512m) | Critical |
| Taxa HTTP 5xx > 1% | Critical |
| Latência p95 > 2s | Warning |

### Rastrear erros

- **Gunicorn:** `--access-logfile - --error-logfile -` (já no Dockerfile)
- **Syslog:** `SYSLOG_ENABLED=true` → serviço `syslog` no compose
- **Audit:** tabela `audit_log` + eventos de login

### Resumo no workflow

O job `notify` imprime status de cada etapa no log do GitHub Actions.

---

## Configuração inicial (checklist)

### No GitHub

- [ ] Secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`
- [ ] Environment `homolog` (sem aprovação ou com QA)
- [ ] Environment `production` com **Required reviewers**
- [ ] Variables: `PROD_URL`, `STAGING_URL` (se aplicável)
- [ ] Branch protection em `main`/`master`: CI + SAST obrigatórios

### No servidor de produção

```bash
sudo mkdir -p /opt/task-manager
sudo chown deploy:deploy /opt/task-manager
# Copiar: docker-compose.prod.yml, scripts/deploy-blue-green.sh
# Configurar nginx para proxy :5000 → slot ativo (:5001 ou :5002)
```

### Testar localmente

```bash
# Build
docker build -t task-manager:local .

# Staging
export DOCKER_IMAGE=task-manager:local
docker compose -f docker-compose.staging.yml up -d
./scripts/smoke-test-deploy.sh http://localhost:5000
docker compose -f docker-compose.staging.yml down -v
```

---

## Comandos úteis

```bash
# Disparar deploy manual
gh workflow run deploy.yml

# Rollback manual
gh workflow run deploy.yml -f rollback_version=v1.2.0 -f skip_staging=true

# Ver últimas execuções
gh run list --workflow=deploy.yml

# Smoke local
./scripts/smoke-test.sh
./scripts/smoke-test-deploy.sh
```

---

## Referências

- Pipeline implementado: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
- CD conceitual: [`CONTINUOUS_DELIVERY_DEVSECOPS.md`](CONTINUOUS_DELIVERY_DEVSECOPS.md)
- SAST/DAST: [`sast.yml`](../.github/workflows/sast.yml), [`dast.yml`](../.github/workflows/dast.yml)
- Git Flow: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
