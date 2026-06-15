"""Testes de segurança: hash de senha, JWT, CSRF, XSS, SQL injection e rate limiting."""
from __future__ import annotations

import time
from datetime import timedelta

import jwt
import pytest
from wtforms import ValidationError

from todo_project.auth import (
    check_password,
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password_strength,
)
from todo_project.extensions import db
from todo_project.models import Task, User

from tests.conftest import TEST_USER, clear_limiter_storage, extract_csrf


# ---------------------------------------------------------------------------
# Fixtures — dados reutilizáveis para os cenários de segurança
# ---------------------------------------------------------------------------

@pytest.fixture
def plain_password():
    """Senha em texto plano usada nos testes de hash."""
    return TEST_USER['password']


@pytest.fixture
def xss_payload():
    """Payload clássico de XSS refletido/armazenado via tag script."""
    return '<script>alert("XSS")</script>'


@pytest.fixture
def sql_injection_payload():
    """Tentativa de bypass via injeção SQL em campo de busca (username)."""
    return "admin' OR '1'='1' --"


@pytest.fixture
def task_form_payload(auth_client):
    """Monta payload de formulário de tarefa com CSRF válido."""
    def _build(**overrides):
        page = auth_client.get('/add_task')
        csrf = extract_csrf(page.data.decode())
        data = {
            'csrf_token': csrf,
            'title': 'Tarefa de segurança',
            'description': 'Descrição de teste',
            'priority': 'low',
            'status': 'pending',
            'category': 'security',
            'submit': 'Save Task',
        }
        data.update(overrides)
        return data

    return _build


# ---------------------------------------------------------------------------
# 1. Hash de senha com bcrypt
# ---------------------------------------------------------------------------

def test_password_hashing(app, plain_password):
    """Senhas nunca devem ser armazenadas em texto plano — apenas o hash bcrypt."""
    with app.app_context():
        hashed = hash_password(plain_password)

        # bcrypt gera hashes prefixados com $2a$ / $2b$ (identificador do algoritmo)
        assert hashed.startswith('$2'), 'Hash deve usar o formato bcrypt ($2a$ ou $2b$)'

        # O hash armazenado deve ser diferente da senha original
        assert hashed != plain_password

        # check_password (verify) confirma senha correta e rejeita incorreta
        assert check_password(hashed, plain_password) is True
        assert check_password(hashed, 'SenhaErrada1!') is False


# ---------------------------------------------------------------------------
# 2. Geração de token JWT
# ---------------------------------------------------------------------------

def test_jwt_token_generation(app, test_user):
    """JWT deve carregar user_id e data de expiração (claim exp)."""
    with app.app_context():
        user = db.session.get(User, test_user['id'])
        token = create_access_token(user)
        payload = decode_access_token(token)

        assert payload is not None, 'Token gerado deve ser decodificável'
        assert payload['user_id'] == test_user['id']
        assert payload['email'] == test_user['email']

        # Decodifica sem verificar expiração para inspecionar o claim exp
        raw = jwt.decode(
            token,
            app.config['SECRET_KEY'],
            algorithms=[app.config['JWT_ALGORITHM']],
            options={'verify_exp': False},
        )
        assert 'exp' in raw, 'Token deve conter claim de expiração (exp)'
        assert raw['exp'] > raw['iat']


# ---------------------------------------------------------------------------
# 3. Expiração de token JWT
# ---------------------------------------------------------------------------

def test_jwt_token_expiration(app, test_user, monkeypatch):
    """Token com TTL curto deve ser rejeitado após expirar."""
    monkeypatch.setitem(app.config, 'JWT_ACCESS_TOKEN_EXPIRES', timedelta(seconds=1))

    with app.app_context():
        user = db.session.get(User, test_user['id'])
        token = create_access_token(user)

        # Imediatamente após a criação o token ainda é válido
        assert decode_access_token(token) is not None

        # Aguarda a expiração (1 s de TTL + margem)
        time.sleep(2)

        # Token expirado deve retornar None (PyJWTError capturado em decode_access_token)
        assert decode_access_token(token) is None


# ---------------------------------------------------------------------------
# 4. Validação de token CSRF
# ---------------------------------------------------------------------------

def test_csrf_token_validation(app, client):
    """Flask-WTF gera tokens CSRF válidos e rejeita tokens forjados."""
    from flask_wtf.csrf import generate_csrf, validate_csrf

    with app.test_request_context():
        valid_token = generate_csrf()
        # Token gerado pela aplicação deve passar na validação
        validate_csrf(valid_token)

    # Token inventado deve ser rejeitado
    with app.test_request_context():
        with pytest.raises(ValidationError):
            validate_csrf('token-csrf-invalido-12345')

    # Requisição POST sem CSRF deve retornar 400 Bad Request
    response = client.post(
        '/login',
        data={
            'email': TEST_USER['email'],
            'password': TEST_USER['password'],
            'submit': 'Login',
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# 5. Proteção contra XSS
# ---------------------------------------------------------------------------

def test_xss_protection(auth_client, app, xss_payload, task_form_payload):
    """HTML malicioso em tarefas deve ser escapado na renderização (Jinja2 |e)."""
    auth_client.post(
        '/add_task',
        data=task_form_payload(title=xss_payload, description=xss_payload),
    )

    response = auth_client.get('/all_tasks')
    html = response.data.decode()

    # O payload bruto não deve aparecer como HTML executável
    assert xss_payload not in html
    assert '<script>alert("XSS")</script>' not in html

    # Conteúdo escapado deve estar presente (proteção XSS do template)
    assert '&lt;script&gt;' in html
    assert 'alert(&quot;XSS&quot;)' in html or 'alert("XSS")' not in html

    with app.app_context():
        task = db.session.query(Task).filter_by(title=xss_payload).one()
        # Dados persistem sem escape no banco; o escape ocorre na saída HTML
        assert task.title == xss_payload


# ---------------------------------------------------------------------------
# 6. Proteção contra SQL injection
# ---------------------------------------------------------------------------

def test_sql_injection_protection(client, app, sql_injection_payload, test_user):
    """Queries SQLAlchemy são parametrizadas — injeção não autentica nem vaza dados."""
    with app.app_context():
        # Simula "pesquisa" maliciosa via filter_by (ORM parametrizado, não concatena SQL)
        injected_user = db.session.query(User).filter_by(username=sql_injection_payload).first()
        assert injected_user is None

        legitimate = db.session.query(User).filter_by(email=TEST_USER['email']).one()
        assert legitimate.username == TEST_USER['username']
        assert db.session.query(User).count() == 1

    # Via HTTP: tenta registrar com username malicioso (consulta de unicidade no banco)
    page = client.get('/register')
    csrf = extract_csrf(page.data.decode())
    response = client.post(
        '/register',
        data={
            'csrf_token': csrf,
            'username': sql_injection_payload,
            'email': 'sqli@example.com',
            'password': 'SecureP@ss1',
            'confirm_password': 'SecureP@ss1',
            'submit': 'Register',
        },
    )

    # Injeção é tratada como string literal — registro pode criar usuário sem bypass de SQL
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')

    with app.app_context():
        # Username malicioso é armazenado como texto, não executado como SQL
        created = db.session.query(User).filter_by(username=sql_injection_payload).one()
        assert created.email == 'sqli@example.com'

        # Sem vazamento em massa: apenas o seed + o novo usuário
        assert db.session.query(User).count() == 2
        assert db.session.query(User).filter_by(email=TEST_USER['email']).one().username == TEST_USER['username']


# ---------------------------------------------------------------------------
# 7. Validação de força da senha
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'password, expected_valid, reason',
    [
        ('abc', False, 'menos de 8 caracteres'),
        ('abcdefgh1!', False, 'sem letra maiúscula'),
        ('ABCDEFGH1!', False, 'sem letra minúscula'),
        ('Abcdefgh!', False, 'sem dígito'),
        ('Abcdefgh1', False, 'sem caractere especial'),
        ('SecureP@ss1', True, 'senha forte válida'),
    ],
    ids=[
        'weak_too_short',
        'weak_no_uppercase',
        'weak_no_lowercase',
        'weak_no_digit',
        'weak_no_special',
        'strong_valid',
    ],
)
def test_password_strength_validation(password, expected_valid, reason):
    """validate_password_strength aplica regex de complexidade mínima."""
    valid, message = validate_password_strength(password)
    assert valid is expected_valid, f'Falha no cenário: {reason}'
    if not expected_valid:
        assert message  # mensagem de erro deve existir para senhas fracas


# ---------------------------------------------------------------------------
# 8. Rate limiting
# ---------------------------------------------------------------------------

def test_rate_limiting(app, client, monkeypatch):
    """Múltiplas tentativas de login rápidas devem ser bloqueadas (HTTP 429)."""
    from todo_project.extensions import limiter

    # Limite baixo para o teste (custo ~2 unidades/POST no Flask-Limiter)
    monkeypatch.setitem(app.config, 'LOGIN_RATE_LIMIT', '4 per minute')
    monkeypatch.setattr(limiter, '_key_func', lambda: 'pytest-rate-limit-security')
    clear_limiter_storage()

    login_page = client.get('/login')
    csrf = extract_csrf(login_page.data.decode())
    payload = {
        'csrf_token': csrf,
        'email': TEST_USER['email'],
        'password': 'WrongPass1!',
        'submit': 'Login',
    }

    # Requisições dentro do limite retornam 200 (credenciais inválidas, mas processadas)
    for attempt in range(2):
        resp = client.post('/login', data=payload)
        assert resp.status_code == 200, f'tentativa {attempt + 1} deveria ser aceita'

    # A próxima requisição excede o limite e é bloqueada
    blocked = client.post('/login', data=payload)
    assert blocked.status_code == 429
