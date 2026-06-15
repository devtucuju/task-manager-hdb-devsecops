# 📋 Task Manager - DevSecOps Study Case

> Aplicação web Flask para gerenciamento de tarefas com foco em práticas **DevSecOps**: autenticação JWT, audit log, rate limiting, logging centralizado via syslog, pipelines de CI/CD e análises de segurança (SAST/DAST).

Repositório: [devtucuju/task-manager-hdb-devsecops](https://github.com/devtucuju/task-manager-hdb-devsecops)

---

## 📖 Sobre o Projeto

O **Task Manager** é um estudo de caso DevSecOps que evolui um gerenciador de tarefas Flask para demonstrar segurança em profundidade, observabilidade e automação de pipeline. A aplicação oferece:

- Interface web para CRUD de tarefas e gerenciamento de conta
- API REST autenticada com JWT (Bearer token ou cookie httpOnly)
- Persistência em **PostgreSQL** com SQLAlchemy ORM
- Registro de auditoria (banco + syslog via rsyslog)
- Pipelines GitHub Actions para testes, lint, SAST, DAST e deploy

---

## ✅ Requisitos

| Requisito | Versão / Observação |
|-----------|---------------------|
| 🐳 **Docker** | Engine recente com suporte a Compose |
| 🐳 **Docker Compose** | v2+ (`docker compose` ou `docker-compose`) |
| 🐍 **Python** | 3.11+ (desenvolvimento e testes locais) |
| 📦 **Git** | Para clonar o repositório e contribuir |

---

## 🚀 Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/devtucuju/task-manager-hdb-devsecops.git
cd task-manager-hdb-devsecops
git checkout develop
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` e altere pelo menos a `SECRET_KEY` antes de usar em produção. Nunca commite o arquivo `.env` (já está no `.gitignore`).

### 3. Construir e subir os containers

```bash
docker-compose build
docker-compose up -d
```

> **Alternativa (Compose v2):** `docker compose build && docker compose up -d --build`

O stack sobe três serviços:

| Serviço | Descrição | Porta |
|---------|-----------|-------|
| `app` | Flask + Gunicorn | `5000` |
| `db` | PostgreSQL 15 | `5432` |
| `syslog` | Coletor rsyslog (UDP) | `514` |

### 4. Verificar logs

```bash
docker-compose logs -f app
```

> ⚠️ Se alterar `DB_PASSWORD` ou `DB_NAME` após o primeiro `up`, recrie o volume:
> `docker-compose down -v && docker-compose up -d --build`

### Credenciais padrão (bootstrap)

Na primeira execução, com banco vazio, um usuário admin é criado automaticamente:

| Campo | Valor padrão |
|-------|--------------|
| Email | `admin@example.com` |
| Senha | `Change-me1!` |

---

## 💻 Uso

### Interface web

Acesse: **http://localhost:5000**

Rotas principais da interface:

| Rota | Descrição |
|------|-----------|
| `/` ou `/about` | Página inicial |
| `/login` | Login |
| `/register` | Registro (se `REGISTRATION_ENABLED=true`) |
| `/all_tasks` | Listagem de tarefas |
| `/add_task` | Criar tarefa |
| `/account` | Configurações da conta |

### Endpoints da API

#### Autenticação

| Método | Endpoint | Auth | Descrição |
|--------|----------|------|-----------|
| `POST` | `/api/auth/login` | ❌ | Login — retorna JWT |
| `POST` | `/api/auth/register` | ❌ | Registro de usuário |
| `POST` | `/api/auth/logout` | ✅ | Logout |
| `POST` | `/api/auth/change-password` | ✅ | Alterar senha |
| `GET` | `/api/me` | ✅ | Dados do usuário autenticado |

#### Tarefas (REST)

| Método | Endpoint | Auth | Descrição |
|--------|----------|------|-----------|
| `GET` | `/tasks` | ✅ | Listar tarefas (`?status=`, `?q=`) |
| `POST` | `/tasks` | ✅ | Criar tarefa |
| `PUT` | `/tasks/<id>` | ✅ | Atualizar tarefa |
| `DELETE` | `/tasks/<id>` | ✅ | Remover tarefa |
| `GET` | `/api/tasks` | ✅ | Alias de listagem (com CSRF) |

**Prioridades válidas:** `low`, `medium`, `high`  
**Status válidos:** `pending`, `in_progress`, `done`

### Exemplos com curl

#### Login e obtenção do token

```bash
curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Change-me1!"}'
```

Resposta:

```json
{
  "token": "<JWT>",
  "token_type": "Bearer"
}
```

#### Listar tarefas

```bash
export TOKEN="<seu-jwt>"

curl -s http://localhost:5000/tasks \
  -H "Authorization: Bearer $TOKEN"
```

#### Criar tarefa

```bash
curl -s -X POST http://localhost:5000/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Revisar pipeline CI",
    "description": "Validar jobs SAST e DAST",
    "priority": "high",
    "status": "pending",
    "category": "devsecops"
  }'
```

#### Atualizar tarefa

```bash
curl -s -X PUT http://localhost:5000/tasks/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

#### Excluir tarefa

```bash
curl -s -X DELETE http://localhost:5000/tasks/1 \
  -H "Authorization: Bearer $TOKEN"
```

#### Buscar tarefas por palavra-chave

```bash
curl -s "http://localhost:5000/tasks?q=pipeline&status=pending" \
  -H "Authorization: Bearer $TOKEN"
```

#### Perfil do usuário autenticado

```bash
curl -s http://localhost:5000/api/me \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🧪 Testes

A suite de testes usa **pytest** com banco SQLite em memória, cobrindo autenticação, rotas da API, CSRF, XSS, SQL injection e rate limiting.

| Arquivo | Escopo |
|---------|--------|
| `tests/test_auth.py` | Registro, login, logout, troca de senha |
| `tests/test_routes.py` | CRUD de tarefas via API |
| `tests/test_security.py` | JWT, bcrypt, CSRF, XSS, SQLi, rate limit |

### Executar testes localmente

```bash
pip install -r requirements.txt

export FLASK_ENV=testing
export SECRET_KEY=pytest-secret-key-not-for-production
export SYSLOG_ENABLED=false
export BOOTSTRAP_ADMIN_ENABLED=false

pytest tests/ -v
```

### Executar testes no Docker

Com o stack em execução:

```bash
docker-compose exec app pytest /app/tests -v
```

Ou em um container efêmero:

```bash
docker-compose run --rm app pytest /app/tests -v
```

### Cobertura de testes

```bash
# Local — relatório no terminal
pytest tests/ -v --cov=todo_project --cov-report=term-missing

# Local — relatório HTML (abrir htmlcov/index.html)
pytest tests/ -v --cov=todo_project --cov-report=html

# Local — XML para CI (Codecov)
pytest tests/ -v --cov=todo_project --cov-report=xml
```

O workflow `ci.yml` executa testes com cobertura e faz upload opcional para o **Codecov** (configure o secret `CODECOV_TOKEN` no GitHub).

---

## 🔄 Pipeline CI/CD

O projeto utiliza **GitHub Actions** com Git Flow (`develop` → `homolog` → `master`).

```
feat/<escopo>-<descricao>  →  develop  →  homolog  →  master
     (feature)              (integração)  (staging)   (produção)
```

### Workflows

| Workflow | Arquivo | Gatilho | Descrição |
|----------|---------|---------|-----------|
| 🔧 **CI Pipeline** | `ci.yml` | Push/PR em `main`, `develop` | Testes, lint e build Docker |
| 🔍 **SAST** | `sast.yml` | Push/PR em `main`, `master`, `develop` | Análise estática de segurança |
| 🎯 **DAST** | `dast.yml` | Push em `homolog` / manual | Scan dinâmico com OWASP ZAP |
| 🚀 **Deploy** | `deploy.yml` | Push em `homolog`/`master` / manual | Build e deploy (placeholder) |
| 📝 **Commitlint** | `commitlint.yml` | Pull requests | Valida Conventional Commits |

### CI Pipeline (`ci.yml`)

Executa três jobs em sequência paralela + build:

1. **Test** — `pytest` com cobertura (`--cov=todo_project`)
2. **Lint** — `flake8` + `black --check`
3. **Build** — constrói a imagem Docker (depende de test + lint)

### SAST — Static Application Security Testing

| Ferramenta | Escopo | Comportamento |
|------------|--------|---------------|
| 🐍 **Bandit** | Código Python (`todo_project/todo_project/`) | Falha em issues **HIGH/CRITICAL** |
| 📦 **OWASP Dependency-Check** | Dependências e artefatos do projeto | Falha em vulnerabilidades **CRITICAL** (CVSS ≥ 9.0) |
| 🛡️ **Safety** | Pacotes pip (`requirements.txt`) | Gera relatório JSON de vulnerabilidades conhecidas |

Artefatos (`bandit-report.json`, `dependency-check-report.json`, `safety-report.json`) são publicados como artifacts do workflow.

### DAST — Dynamic Application Security Testing

O workflow `dast.yml`:

1. Sobe o stack completo via Docker Compose
2. Executa **OWASP ZAP Baseline Scan** contra `http://localhost:5000`
3. Encerra os containers ao final (mesmo em caso de falha)

Disparado automaticamente em push na branch `homolog` ou manualmente via `workflow_dispatch`.

### Deploy

| Job | Branch / Input | Ação |
|-----|----------------|------|
| **Deploy Homolog** | `homolog` | Build `task-manager-flask:homolog` |
| **Deploy Production** | `master` | Build `task-manager-flask:production` |

> Os steps de deploy são placeholders — configure SSH, Kubernetes, ECS ou sua infraestrutura conforme necessário.

---

## 🔐 Segurança

### Autenticação JWT

- Tokens **HS256** com expiração configurável (`JWT_EXPIRES_HOURS`, padrão 8h)
- Suporte a **Bearer token** (API) e **cookie httpOnly** (interface web)
- Cookies com flags `Secure`, `SameSite` e `HttpOnly` configuráveis via `.env`
- Decorador `@token_required` protege rotas web e API

### Logging via syslog

- Logs da aplicação enviados para o serviço **rsyslog** (UDP 514) via `rfc5424-logging-handler`
- Eventos de auditoria registrados no banco (`audit_log`) e replicados ao syslog
- Logs persistidos em `./logs/` no host
- Desabilitável com `SYSLOG_ENABLED=false` (útil em testes/CI)

### Validações implementadas

| Área | Medida |
|------|--------|
| Senhas | bcrypt + política de complexidade (8+ chars, maiúscula, minúscula, número, especial) |
| Formulários web | Flask-WTF com proteção **CSRF** |
| API JSON | Rotas `/api/*` e `/tasks` isentas de CSRF; exigem JWT |
| Tarefas | Validação de título, prioridade, status, tamanho de campos |
| Login | **Rate limiting** (`LOGIN_RATE_LIMIT`, padrão 5 tentativas / 15 min) |
| Configuração | Segredos via `.env` — nenhum hardcoded; `SECRET_KEY` obrigatória em produção |
| Container | Usuário **não-root** (`appuser`) no Dockerfile |

### Proteção contra OWASP Top 10

| Risco | Mitigação no projeto |
|-------|----------------------|
| **A01 — Broken Access Control** | JWT + isolamento de tarefas por `user_id`; rotas protegidas com `@token_required` |
| **A02 — Cryptographic Failures** | bcrypt para senhas; JWT assinado com `SECRET_KEY` |
| **A03 — Injection** | SQLAlchemy ORM (parametrizado); testes de SQL injection |
| **A04 — Insecure Design** | Audit log, rate limiting, bootstrap admin controlado |
| **A05 — Security Misconfiguration** | Validação de config em produção; registro desabilitável em prod |
| **A06 — Vulnerable Components** | Safety + OWASP Dependency-Check no pipeline SAST |
| **A07 — Auth Failures** | Rate limit no login; senha forte; JWT com expiração |
| **A08 — Software/Data Integrity** | CI com lint, testes e SAST em PRs |
| **A09 — Logging Failures** | Audit log + syslog centralizado |
| **A10 — SSRF** | N/A direto — app não faz requisições externas arbitrárias |

---

## 📁 Estrutura do Projeto

```
task-manager-devsecops/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # Testes, lint e build Docker
│   │   ├── sast.yml            # Bandit, Dependency-Check, Safety
│   │   ├── dast.yml            # OWASP ZAP baseline
│   │   ├── deploy.yml          # Deploy homolog / production
│   │   └── commitlint.yml      # Validação de commits
│   └── pull_request_template.md
├── config/
│   └── rsyslog/
│       └── remote.conf         # Configuração do coletor syslog
├── tests/
│   ├── conftest.py             # Fixtures pytest compartilhadas
│   ├── test_auth.py            # Testes de autenticação
│   ├── test_routes.py          # Testes da API de tarefas
│   └── test_security.py        # Testes de segurança (CSRF, XSS, etc.)
├── todo_project/               # Diretório de execução da app
│   ├── app.py                  # Entry point alternativo
│   ├── run.py                  # Servidor de desenvolvimento
│   └── todo_project/           # Pacote Flask principal
│       ├── __init__.py         # Instância `app` (Gunicorn)
│       ├── auth.py             # JWT, bcrypt, validação de senha
│       ├── audit.py            # Registro de auditoria
│       ├── bootstrap.py        # Criação do admin inicial
│       ├── config.py           # Configuração via .env
│       ├── extensions.py       # SQLAlchemy, CSRF, Limiter, bcrypt
│       ├── factory.py          # Application factory
│       ├── forms.py            # Formulários WTForms
│       ├── logging_config.py   # Logging + syslog
│       ├── models.py           # User, Task, AuditLog
│       ├── routes.py           # Rotas web e API
│       ├── static/             # CSS e assets
│       └── templates/          # Templates Jinja2
├── logs/                       # Logs do rsyslog (gerado em runtime)
├── .env.example                # Template de variáveis de ambiente
├── .commitlintrc.json          # Regras Conventional Commits
├── .githooks/                  # Hook commit-msg local
├── CONTRIBUTING.md             # Guia de contribuição detalhado
├── docker-compose.yml          # Stack app + db + syslog
├── Dockerfile                  # Imagem de produção (Gunicorn)
├── requirements.txt            # Dependências Python
├── LICENSE                     # MIT License
└── README.md                   # Este arquivo
```

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Consulte o guia completo em **[CONTRIBUTING.md](CONTRIBUTING.md)**.

### Resumo do fluxo

1. Faça fork e clone o repositório
2. Crie uma branch a partir de `develop`: `feat/<escopo>-<descricao>`
3. Desenvolva seguindo os padrões abaixo
4. Execute testes e lint localmente
5. Abra um Pull Request para `develop`

### Padrões de código

| Aspecto | Padrão |
|---------|--------|
| **Commits** | [Conventional Commits](https://www.conventionalcommits.org/) — ex.: `feat(auth): adicionar endpoint de logout` |
| **Branches** | `<tipo>/<escopo>-<descricao>` — ex.: `fix/login-redirect` |
| **Formatação** | [Black](https://black.readthedocs.io/) |
| **Lint** | flake8 (`--max-line-length=120`) |
| **Testes** | pytest — novas features devem incluir testes quando aplicável |

### Hook de commit local (opcional)

```bash
git config core.hooksPath .githooks
chmod +x .githooks/commit-msg
```

---

## 📄 Licença

Este projeto está licenciado sob a **MIT License** — veja o arquivo [LICENSE](LICENSE).

```
Copyright (c) 2020 AdityaBagad
```

Projeto derivado de [Task-Manager-using-Flask](https://github.com/AdityaBagad/Task-Manager-using-Flask), estendido com práticas DevSecOps.

---

<p align="center">
  Feito com ☕ e 🔒 para estudo de DevSecOps
</p>
