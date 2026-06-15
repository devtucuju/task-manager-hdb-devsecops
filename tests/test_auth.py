"""
Testes unitários de autenticação — API REST /api/auth/*

Fixtures locais complementam tests/conftest.py (app, client, banco SQLite em memória).
"""
from __future__ import annotations

import json

import pytest

from todo_project.auth import decode_access_token
from todo_project.extensions import db
from todo_project.models import User

from tests.conftest import TEST_USER, clear_limiter_storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def flask_client(client):
    """Cliente Flask de teste para requisições HTTP."""
    return client


def _json_post(client, url, payload, headers=None):
    """Helper: POST JSON."""
    hdrs = {'Content-Type': 'application/json'}
    if headers:
        hdrs.update(headers)
    return client.post(url, data=json.dumps(payload), headers=hdrs)


# ---------------------------------------------------------------------------
# 1. Registro com sucesso
# ---------------------------------------------------------------------------
def test_register_user_success(flask_client, app):
    # Registra novo usuário com dados válidos via API JSON
    payload = {
        'username': 'novouser',
        'email': 'novo@example.com',
        'password': 'NovaSenha1!',
    }
    response = _json_post(flask_client, '/api/auth/register', payload)

    # Deve retornar 201 Created
    assert response.status_code == 201
    data = response.get_json()
    assert data['email'] == 'novo@example.com'
    assert data['username'] == 'novouser'

    # Verifica persistência no banco de dados
    with app.app_context():
        user = db.session.query(User).filter_by(email='novo@example.com').one()
        assert user.username == 'novouser'
        assert user.is_active is True


# ---------------------------------------------------------------------------
# 2. Registro com senha fraca
# ---------------------------------------------------------------------------
def test_register_user_weak_password(flask_client):
    # Tenta registrar com senha que não atende à política de força
    payload = {
        'username': 'weakuser',
        'email': 'weak@example.com',
        'password': 'fraca',
    }
    response = _json_post(flask_client, '/api/auth/register', payload)

    # Deve rejeitar com 400 Bad Request
    assert response.status_code == 400
    data = response.get_json()
    assert 'error' in data
    # Mensagem deve mencionar requisitos de força da senha
    assert 'Senha deve ter' in data['error']


# ---------------------------------------------------------------------------
# 3. Registro com email duplicado
# ---------------------------------------------------------------------------
def test_register_user_duplicate_email(flask_client, test_user):
    # Tenta registrar usando email já existente no banco
    payload = {
        'username': 'outrouser',
        'email': test_user['email'],
        'password': 'OutraSenha1!',
    }
    response = _json_post(flask_client, '/api/auth/register', payload)

    # Deve retornar 409 Conflict
    assert response.status_code == 409
    data = response.get_json()
    assert 'error' in data
    assert 'cadastrado' in data['error'].lower() or 'já' in data['error'].lower()


# ---------------------------------------------------------------------------
# 4. Login com credenciais válidas
# ---------------------------------------------------------------------------
def test_login_success(flask_client, app, test_user):
    # Login via API com email e senha corretos
    response = _json_post(flask_client, '/api/auth/login', {
        'email': test_user['email'],
        'password': test_user['password'],
    })

    assert response.status_code == 200
    data = response.get_json()

    # Resposta deve conter token JWT
    assert 'token' in data
    assert data.get('token_type') == 'Bearer'

    # Token decodificado deve conter dados do usuário
    with app.app_context():
        payload = decode_access_token(data['token'])
        assert payload is not None
        assert payload['email'] == test_user['email']
        assert payload['user_id'] == test_user['id']


# ---------------------------------------------------------------------------
# 5. Login com credenciais inválidas
# ---------------------------------------------------------------------------
def test_login_invalid_credentials(flask_client, test_user):
    # Tenta login com senha incorreta
    response = _json_post(flask_client, '/api/auth/login', {
        'email': TEST_USER['email'],
        'password': 'SenhaErrada1!',
    })

    # Deve retornar 401 Unauthorized
    assert response.status_code == 401
    data = response.get_json()
    assert 'error' in data
    # Não deve retornar token
    assert 'token' not in data


# ---------------------------------------------------------------------------
# 6. Rate limiting no login
# ---------------------------------------------------------------------------
def test_login_rate_limiting(flask_client, app, test_user, monkeypatch):
    from todo_project.extensions import limiter

    # Limite de 10/min ≈ 5 POSTs antes do bloqueio (custo ~2 unidades/req no Flask-Limiter)
    monkeypatch.setitem(app.config, 'LOGIN_RATE_LIMIT', '10 per minute')
    monkeypatch.setattr(limiter, '_key_func', lambda: 'pytest-api-rate-limit')
    clear_limiter_storage()

    payload = {
        'email': TEST_USER['email'],
        'password': 'SenhaErrada1!',
    }

    # Primeiras 5 tentativas falhadas retornam 401
    for i in range(5):
        resp = _json_post(flask_client, '/api/auth/login', payload)
        assert resp.status_code == 401, f'tentativa {i + 1} deveria retornar 401'

    # 6ª tentativa deve ser bloqueada pelo rate limiter
    resp = _json_post(flask_client, '/api/auth/login', payload)
    assert resp.status_code == 429
    data = resp.get_json()
    assert 'error' in data
    assert 'Muitas tentativas' in data['error']


# ---------------------------------------------------------------------------
# 7. Logout
# ---------------------------------------------------------------------------
def test_logout(flask_client, auth_headers):
    # Logout com token JWT válido no header Authorization
    response = _json_post(flask_client, '/api/auth/logout', {}, headers=auth_headers)

    assert response.status_code == 200
    data = response.get_json()
    assert 'message' in data
    assert 'sucesso' in data['message'].lower()


# ---------------------------------------------------------------------------
# 8. Alteração de senha
# ---------------------------------------------------------------------------
def test_change_password(flask_client, app, auth_headers, test_user):
    new_password = 'NovaSenha2!'

    # Altera senha autenticado via API
    response = _json_post(
        flask_client,
        '/api/auth/change-password',
        {
            'old_password': test_user['password'],
            'new_password': new_password,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert 'sucesso' in response.get_json()['message'].lower()

    # Nova senha deve funcionar no login
    login_resp = _json_post(flask_client, '/api/auth/login', {
        'email': test_user['email'],
        'password': new_password,
    })
    assert login_resp.status_code == 200
    assert 'token' in login_resp.get_json()

    # Senha antiga não deve mais funcionar
    old_login = _json_post(flask_client, '/api/auth/login', {
        'email': test_user['email'],
        'password': test_user['password'],
    })
    assert old_login.status_code == 401
