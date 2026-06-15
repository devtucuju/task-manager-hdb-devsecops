# Guia: Configurar Secrets no GitHub Actions

Este guia explica como cadastrar os secrets necessários para os pipelines de CI/CD do **Task Manager DevSecOps**, com passos ilustrados e exemplos de uso nos workflows.

> **Importante:** secrets nunca aparecem nos logs do GitHub Actions. Depois de salvos, **não é possível visualizar o valor** — apenas atualizar ou excluir.

---

## Pré-requisitos

- Acesso de **admin** ou **maintain** ao repositório no GitHub
- Credenciais do Docker Hub (usuário + **Access Token**, não a senha da conta)
- URLs de banco de dados para staging e produção
- Chaves JWT fortes e distintas por ambiente
- (Opcional) URL do Incoming Webhook do Slack

---

## Visão geral dos secrets

| Secret | Descrição | Tipo | Obrigatório |
|--------|-----------|------|-------------|
| `DOCKER_USERNAME` | Usuário do Docker Hub | Texto | Sim |
| `DOCKER_PASSWORD` | Token de acesso do Docker Hub | Secret | Sim |
| `STAGING_DATABASE_URL` | Connection string PostgreSQL (staging) | Secret | Sim* |
| `PROD_DATABASE_URL` | Connection string PostgreSQL (produção) | Secret | Sim* |
| `JWT_SECRET_STAGING` | Chave JWT para staging | Secret | Sim* |
| `JWT_SECRET_PROD` | Chave JWT para produção | Secret | Sim* |
| `SLACK_WEBHOOK` | Webhook Slack para notificações | Secret | Não |

\* Obrigatório quando o workflow de deploy/staging usar variáveis de ambiente do banco ou JWT. O `deploy.yml` atual usa `DOCKER_*` e `SLACK_WEBHOOK_URL` (veja [nota sobre Slack](#slack_webhook-opcional)).

---

## Passo a passo

### Passo 1 — Abrir as configurações do repositório

1. Acesse o repositório no GitHub (ex.: `https://github.com/<org>/task-manager-devsecops`)
2. Clique na aba **Settings** (ícone de engrenagem)
3. No menu lateral, em **Security**, expanda **Secrets and variables**
4. Clique em **Actions**

![Navegação até Secrets and variables > Actions](images/github-secrets-step1-settings.png)

---

### Passo 2 — Acessar a lista de secrets

Na página **Actions secrets and variables**, a aba **Secrets** mostra:

- **Environment secrets** — vinculados a ambientes (`staging`, `production`, etc.)
- **Repository secrets** — disponíveis para todos os workflows do repositório

Para este projeto, comece pelos **Repository secrets**.

![Lista de repository secrets](images/github-secrets-step2-list.png)

---

### Passo 3 — Criar um novo secret

1. Clique em **New repository secret**
2. Preencha **Name** (nome exato, maiúsculas e underscores)
3. Cole o **Secret** (valor sensível)
4. Clique em **Add secret**

![Formulário New repository secret](images/github-secrets-step3-new-secret.png)

Repita este passo para cada secret da tabela abaixo.

---

### Passo 4 — Confirmar que todos foram adicionados

Após cadastrar todos, a lista deve exibir os nomes (sem revelar os valores):

![Secrets cadastrados com sucesso](images/github-secrets-step4-success.png)

---

## Detalhes de cada secret

### 1. `DOCKER_USERNAME`

| Campo | Valor |
|-------|-------|
| **Nome** | `DOCKER_USERNAME` |
| **Valor** | Seu usuário no [Docker Hub](https://hub.docker.com/) |
| **Tipo** | Texto (não é mascarado no formulário, mas trate como sensível) |

**Exemplo:** `meuusuario`

**Uso no projeto:** tag e push da imagem `task-manager` em [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

---

### 2. `DOCKER_PASSWORD`

| Campo | Valor |
|-------|-------|
| **Nome** | `DOCKER_PASSWORD` |
| **Valor** | **Access Token** do Docker Hub (recomendado), não a senha da conta |
| **Tipo** | Secret (mascarado em logs) |

**Como gerar o token:**

1. Docker Hub → **Account Settings** → **Security** → **New Access Token**
2. Permissão: **Read, Write, Delete**
3. Copie o token e cole no secret (só é exibido uma vez)

```yaml
# deploy.yml
- uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKER_USERNAME }}
    password: ${{ secrets.DOCKER_PASSWORD }}
```

---

### 3. `STAGING_DATABASE_URL`

| Campo | Valor |
|-------|-------|
| **Nome** | `STAGING_DATABASE_URL` |
| **Valor** | `postgresql://user:password@db:5432/taskmanager_staging` |
| **Tipo** | Secret |

Substitua `user` e `password` por credenciais reais do ambiente de homologação.

**Exemplo de uso em workflow:**

```yaml
env:
  DATABASE_URL: ${{ secrets.STAGING_DATABASE_URL }}
```

---

### 4. `PROD_DATABASE_URL`

| Campo | Valor |
|-------|-------|
| **Nome** | `PROD_DATABASE_URL` |
| **Valor** | `postgresql://user:password@prod-db:5432/taskmanager` |
| **Tipo** | Secret |

Use credenciais exclusivas de produção, com usuário de permissão mínima.

```yaml
env:
  DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
```

---

### 5. `JWT_SECRET_STAGING`

| Campo | Valor |
|-------|-------|
| **Nome** | `JWT_SECRET_STAGING` |
| **Valor** | String aleatória longa (mín. 32 caracteres) |
| **Tipo** | Secret |

**Gerar chave segura (Linux/macOS):**

```bash
openssl rand -hex 32
```

```yaml
env:
  JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_STAGING }}
```

---

### 6. `JWT_SECRET_PROD`

| Campo | Valor |
|-------|-------|
| **Nome** | `JWT_SECRET_PROD` |
| **Valor** | Chave **diferente** da de staging |
| **Tipo** | Secret |

Nunca reutilize a mesma chave entre ambientes.

```yaml
env:
  JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_PROD }}
```

---

### 7. `SLACK_WEBHOOK` (opcional)

| Campo | Valor |
|-------|-------|
| **Nome** | `SLACK_WEBHOOK` ou `SLACK_WEBHOOK_URL` |
| **Valor** | URL do Incoming Webhook do Slack |
| **Tipo** | Secret |

**Nota:** o workflow [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) usa o nome **`SLACK_WEBHOOK_URL`**. Se você cadastrar apenas `SLACK_WEBHOOK`, ajuste o workflow ou crie o secret com o nome esperado:

```yaml
# deploy.yml (atual)
webhook: ${{ secrets.SLACK_WEBHOOK_URL }}

# Alternativa se você usar SLACK_WEBHOOK
webhook: ${{ secrets.SLACK_WEBHOOK }}
```

**Como obter o webhook:**

1. [Slack API](https://api.slack.com/apps) → Create App → Incoming Webhooks
2. Ative webhooks e adicione ao canal desejado
3. Copie a URL (`https://hooks.slack.com/services/...`)

---

## Como usar nos workflows

### Sintaxe básica

```yaml
${{ secrets.NOME_DO_SECRET }}
```

### Exemplos práticos

**Login no Docker Hub:**

```yaml
- name: Login no Docker Hub
  uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKER_USERNAME }}
    password: ${{ secrets.DOCKER_PASSWORD }}
```

**Variáveis de ambiente em um job:**

```yaml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    env:
      DATABASE_URL: ${{ secrets.STAGING_DATABASE_URL }}
      JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_STAGING }}
```

**Deploy de produção (como no projeto):**

```yaml
- name: Build imagem Docker
  run: |
    docker build \
      -t "${{ secrets.DOCKER_USERNAME }}/task-manager:latest" \
      .
```

### Secrets por ambiente (recomendado para produção)

Para aprovações manuais e isolamento, use **Environments** em **Settings → Environments**:

1. Crie ambientes `staging` e `production`
2. Em cada ambiente, adicione secrets específicos (ex.: `DATABASE_URL`, `JWT_SECRET_KEY`)
3. No workflow, referencie o ambiente:

```yaml
jobs:
  deploy:
    environment: production
    steps:
      - run: echo "Deploy com secrets do ambiente production"
```

Secrets de ambiente têm precedência sobre repository secrets com o mesmo nome.

---

## Boas práticas de segurança

| Prática | Motivo |
|---------|--------|
| Nunca commitar secrets no Git | Histórico do Git é difícil de apagar |
| Usar token Docker Hub, não senha | Revogação granular e auditoria |
| Chaves JWT distintas por ambiente | Comprometimento em staging não afeta prod |
| Rotacionar secrets periodicamente | Reduz janela de exposição |
| Permissões mínimas no banco | `user` de prod só com DDL/DML necessário |
| Não ecoar secrets em `run:` | GitHub mascara `secrets.*`, mas evite `echo` do valor |

O GitHub **mascara automaticamente** valores de secrets nos logs quando referenciados como `${{ secrets.* }}`.

---

## Checklist rápido

- [ ] `DOCKER_USERNAME` cadastrado
- [ ] `DOCKER_PASSWORD` cadastrado (token Docker Hub)
- [ ] `STAGING_DATABASE_URL` cadastrado
- [ ] `PROD_DATABASE_URL` cadastrado
- [ ] `JWT_SECRET_STAGING` gerado com `openssl rand -hex 32`
- [ ] `JWT_SECRET_PROD` gerado (valor diferente de staging)
- [ ] `SLACK_WEBHOOK` ou `SLACK_WEBHOOK_URL` (opcional)
- [ ] Workflow `deploy.yml` executado com sucesso após push em `main`

---

## Solução de problemas

| Erro | Causa provável | Solução |
|------|----------------|---------|
| `denied: requested access to the resource is denied` | `DOCKER_USERNAME`/`DOCKER_PASSWORD` incorretos | Verifique token com permissão Read/Write |
| Secret vazio no job | Nome digitado errado | Nomes são case-sensitive: `DOCKER_PASSWORD` ≠ `docker_password` |
| Slack não notifica | Secret ausente ou nome errado | Use `SLACK_WEBHOOK_URL` conforme `deploy.yml` |
| Não consigo ver o valor do secret | Comportamento esperado | Atualize com **Update** ou recrie o secret |

---

## Referências

- [GitHub Docs — Using secrets in GitHub Actions](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)
- [Docker Hub — Access tokens](https://docs.docker.com/security/for-developers/access-tokens/)
- [Workflow de deploy do projeto](../.github/workflows/deploy.yml)
- [Guia de CD DevSecOps](./CONTINUOUS_DELIVERY_DEVSECOPS.md)
