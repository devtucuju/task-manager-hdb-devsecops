# Guia Comparativo: SAST vs DAST

Este documento explica as diferenças entre **SAST** (análise estática) e **DAST** (análise dinâmica), como se complementam no pipeline DevSecOps deste projeto, e exemplos práticos de vulnerabilidades que cada abordagem detecta.

---

## Visão geral

| Aspecto | SAST | DAST |
|---------|------|------|
| **O que analisa** | Código-fonte, dependências, bytecode | Aplicação **em execução** (HTTP, APIs, sessões) |
| **Momento** | Desenvolvimento / build (antes do deploy) | Homologação / staging (app rodando) |
| **Execução da app** | Não necessária | Obrigatória |
| **Velocidade** | Rápido (minutos) | Mais lento (minutos a horas) |
| **Falsos positivos** | Mais frequentes | Menos frequentes |
| **Runtime / config** | Não vê ambiente real | Detecta headers, TLS, CORS, sessão |
| **Ferramentas (este projeto)** | Bandit, Dependency-Check, Safety | OWASP ZAP (baseline) |
| **Workflow CI** | `.github/workflows/sast.yml` | `.github/workflows/dast.yml` |

---

## SAST — Static Application Security Testing

### Características

- Analisa **código-fonte sem executar** a aplicação.
- Detecta vulnerabilidades **estruturais** (padrões inseguros no código).
- Execução **rápida** (tipicamente minutos).
- Pode gerar **falsos positivos** (alerta sem exploit real).
- **Não detecta** misconfiguração de servidor, headers ausentes ou comportamento só visível em runtime.

### Ferramentas comuns

| Ferramenta | Uso neste projeto |
|------------|-------------------|
| **Bandit** | Sim — `todo_project/todo_project/` |
| **SonarQube** | Não integrado (alternativa enterprise) |
| **Checkmarx** | Não integrado (alternativa comercial) |
| **Dependency-Check** | Sim — CVEs em `requirements.txt` |
| **Safety** | Sim — vulnerabilidades conhecidas em pacotes pip |

### Exemplos práticos (SAST)

#### 1. Senha hardcoded no código

```python
# ❌ Bandit detecta: B105 hardcoded_password_string
SECRET_KEY = "minha-chave-fixa-insegura"
```

**Correção:** carregar de variável de ambiente (`config.py` + `.env`).

#### 2. Uso de `eval()` ou `pickle` inseguro

```python
# ❌ Bandit: execução arbitrária de código
result = eval(user_input)
```

**Correção:** validar entrada e usar APIs seguras (JSON, ast.literal_eval com cuidado).

#### 3. SQL concatenado (risco estrutural)

```python
# ❌ SAST flagra concatenação de SQL
query = f"SELECT * FROM user WHERE email = '{email}'"
```

**Correção (já adotada):** SQLAlchemy com parâmetros — `filter_by(email=email)`.

#### 4. Dependência com CVE conhecida

```
# Dependency-Check / Safety alertam:
requests==2.25.0  →  CVE-2023-XXXX (HIGH)
```

**Correção:** atualizar `requirements.txt` para versão corrigida.

#### 5. Função criptográfica fraca

```python
# ❌ hashlib.md5(password) — SAST/linters de segurança
```

**Correção (já adotada):** `bcrypt` via Flask-Bcrypt.

---

## DAST — Dynamic Application Security Testing

### Características

- Testa a aplicação **em execução**, simulando um atacante externo.
- Envia requisições HTTP reais (crawling, fuzzing, injeção).
- Execução **mais lenta** (baseline: minutos; scan completo: horas).
- **Menos falsos positivos** — só reporta o que a app realmente responde.
- Detecta problemas de **configuração, headers, sessão, TLS e runtime**.

### Ferramentas comuns

| Ferramenta | Uso neste projeto |
|------------|-------------------|
| **OWASP ZAP** | Sim — baseline em `dast.yml` |
| **Burp Suite** | Manual / pentest (não na CI) |
| **Acunetix** | Alternativa comercial |

### Como rodamos DAST aqui

1. `docker compose up` sobe app + PostgreSQL.
2. ZAP acessa `http://localhost:5000`.
3. Relatório `report_json.json` — falha CI apenas em alertas **High/Critical**.

---

## Complementaridade: por que usar ambos?

```
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline DevSecOps                        │
├─────────────────────────────────────────────────────────────┤
│  SAST (rápido, no PR)          DAST (app rodando, homolog)  │
│  ─────────────────────         ────────────────────────────  │
│  • Código inseguro             • Headers HTTP ausentes       │
│  • CVEs em dependências        • Cookies sem Secure/SameSite │
│  • Secrets no repo             • XSS refletido em runtime   │
│  • Padrões SQLi no código      • Auth bypass em rotas      │
└─────────────────────────────────────────────────────────────┘
         │                                    │
         └────────── Segurança completa ──────┘
```

| Cenário | SAST encontra? | DAST encontra? |
|---------|----------------|----------------|
| `eval()` no código Python | ✅ | ❌ (se nunca exposto) |
| CSP header ausente | ❌ | ✅ |
| Cookie sem `Secure` em HTTPS | ❌ | ✅ |
| `requests` com CVE | ✅ | ❌ |
| Login sem rate limit em produção | Parcial (código) | ✅ (429 após N tentativas) |
| SQLAlchemy parametrizado | ✅ (código ok) | ❌ (não há bypass) |

**Conclusão:** SAST protege o **código e a cadeia de suprimentos**; DAST valida o **comportamento real** da aplicação deployada.

---

## 10 vulnerabilidades típicas detectadas por DAST (com exemplos)

### 1. Configuração inadequada de headers HTTP

**O que é:** ausência de headers que endurecem o navegador contra ataques.

**Exemplo prático (Task Manager):** scan ZAP reporta *"Content Security Policy (CSP) Header Not Set"* em `/login` e `/about`.

**Resposta HTTP atual (simplificada):**
```http
HTTP/1.1 200 OK
Content-Type: text/html
# Sem Content-Security-Policy
# Sem X-Frame-Options
```

**Risco:** XSS e clickjacking têm mais superfície de exploração.

**Correção:**
```python
@app.after_request
def security_headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    response.headers['X-Frame-Options'] = 'DENY'
    return response
```

---

### 2. Exposição de informações sensíveis em respostas

**O que é:** stack traces, versões de framework ou dados internos vazados em erros HTTP.

**Exemplo prático:**
```http
HTTP/1.1 500 Internal Server Error

Traceback (most recent call last):
  File "/app/todo_project/routes.py", line 42
  psycopg2.OperationalError: FATAL: password authentication failed
```

**Risco:** atacante mapeia tecnologia, caminhos e credenciais de DB.

**Correção:** páginas de erro genéricas (`errors/500.html`), `DEBUG=False` em produção, logs só no servidor.

---

### 3. Problemas de autenticação/autorização em runtime

**O que é:** rotas protegidas acessíveis sem token ou com token de outro usuário.

**Exemplo prático:**
```bash
# Sem autenticação — deve retornar 401/302, não 200 com dados
curl -i http://localhost:5000/api/tasks

# IDOR — acessar tarefa de outro usuário
curl -H "Authorization: Bearer <token_user_A>" \
     http://localhost:5000/all_tasks/99/update_task
```

**No projeto:** `/api/tasks` retorna `401`; rotas web redirecionam para `/login` — DAST valida isso em runtime.

---

### 4. Vulnerabilidades de sessão

**O que é:** cookies de sessão/JWT com flags incorretas ou sem expiração.

**Exemplo prático (alerta ZAP):** *"Cookie without SameSite Attribute"* no cookie `access_token` ou CSRF.

```http
Set-Cookie: access_token=eyJ...; HttpOnly; Path=/
# Falta: Secure; SameSite=Strict
```

**Risco:** roubo de sessão via CSRF ou interceptação em HTTP.

**Correção (parcialmente aplicada):** `JWT_COOKIE_HTTPONLY=True`, `JWT_COOKIE_SECURE=True` em produção HTTPS.

---

### 5. Problemas de CORS

**O que é:** API permite origens arbitrárias, expondo dados a sites maliciosos.

**Exemplo prático:**
```http
GET /api/me HTTP/1.1
Origin: https://evil-site.com

HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
```

**Risco:** site malicioso lê resposta da API com credenciais da vítima.

**Correção:** restringir `CORS_ORIGINS` em `config.py` (não usar `*` em produção).

---

### 6. Certificados SSL/TLS inválidos

**O que é:** HTTPS com certificado expirado, autoassinado ou protocolo fraco (TLS 1.0).

**Exemplo prático:**
```bash
curl -v https://app.exemplo.com
# SSL certificate problem: certificate has expired
# ou: TLS 1.0 offered
```

**Risco:** MITM, interceptação de credenciais.

**Correção:** certificado válido (Let's Encrypt), TLS 1.2+, HSTS no reverse proxy (nginx/Traefik).

> Em desenvolvimento local (`http://localhost`) o DAST não testa TLS; validar em homolog/produção.

---

### 7. Redirecionamentos inseguros

**O que é:** parâmetro `next` ou `redirect` apontando para domínio externo (open redirect).

**Exemplo prático:**
```bash
# Após login, redireciona para site malicioso
curl -i "http://localhost:5000/login?next=https://phishing.com"
```

**Resposta vulnerável:**
```http
HTTP/1.1 302 Found
Location: https://phishing.com
```

**Correção:** validar `next` — apenas URLs relativas ou whitelist de domínios.

---

### 8. Problemas de cache

**O que é:** páginas autenticadas cacheadas em proxy/navegador e servidas a outro usuário.

**Exemplo prático:**
```http
GET /account HTTP/1.1
Authorization: Bearer ...

HTTP/1.1 200 OK
Cache-Control: public, max-age=3600   # ❌ dados sensíveis cacheados
```

**Risco:** usuário B vê dados do usuário A em terminal compartilhado.

**Correção:**
```http
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
```

---

### 9. Vulnerabilidades de API

**O que é:** endpoints REST sem auth, rate limit, validação de entrada ou verbos perigosos.

**Exemplos práticos no Task Manager:**

| Teste DAST/manual | Esperado seguro |
|-------------------|-----------------|
| `POST /api/auth/login` sem limite | 429 após N tentativas |
| `GET /api/me` sem Bearer | 401 |
| `POST /api/auth/register` senha fraca | 400 |
| `DELETE /api/tasks/1` sem auth | 401 |

DAST fuzza parâmetros JSON e detecta respostas inesperadas (500 com stack trace, 200 sem auth).

---

### 10. Problemas de validação em runtime

**O que é:** validação só no front-end ou WTForms bypassada via API direta.

**Exemplo prático:**
```bash
# Bypass do formulário web — API aceita payload inválido?
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"a","email":"not-an-email","password":"1"}'
```

**Resposta segura:** `400` com mensagem de validação — não `201` com usuário criado.

**Contraste com SAST:** SAST vê se existe `validate_password_strength()` no código; DAST confirma que a API **rejeita** `"password":"1"` em produção.

---

## Matriz resumida: quem detecta o quê?

| Vulnerabilidade | SAST | DAST |
|-----------------|------|------|
| CVE em `requirements.txt` | ✅ | ❌ |
| `hardcoded_password` no .py | ✅ | ❌ |
| CSP header ausente | ❌ | ✅ |
| Cookie sem SameSite | ❌ | ✅ |
| SQLi (código concatenado) | ✅ | ✅* |
| XSS (escape no template) | Parcial | ✅ |
| Open redirect | Parcial | ✅ |
| TLS inválido | ❌ | ✅ |
| Rate limit no login | Parcial | ✅ |

\* DAST só confirma SQLi se a injeção funcionar em runtime; com SQLAlchemy parametrizado, DAST não encontra bypass.

---

## Aplicação neste repositório

| Etapa | Ferramenta | Quando roda |
|-------|------------|-------------|
| SAST — código Python | Bandit | Todo PR/push (`sast.yml`) |
| SAST — dependências | Dependency-Check + Safety | Todo PR/push (`sast.yml`) |
| DAST — app rodando | OWASP ZAP baseline | PR/push develop (`dast.yml`) |
| Testes de regressão | pytest `tests/test_security.py` | CI (`ci.yml`) |

**Comando local de validação combinada:**
```bash
./scripts/validate-security.sh          # SAST + pytest
docker compose up -d && # DAST manual com ZAP contra localhost:5000
```

---

## Referências

- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [Bandit](https://bandit.readthedocs.io/)
- [OWASP ZAP](https://www.zaproxy.org/)
- Guia de validação pós-correção: [`SECURITY_VALIDATION.md`](SECURITY_VALIDATION.md)
- Workflows: `.github/workflows/sast.yml`, `.github/workflows/dast.yml`
