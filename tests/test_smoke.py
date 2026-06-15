"""
Smoke tests pós-deploy — validam funcionalidades críticas rapidamente.

Execução local (Flask test client + banco em memória):
    pytest tests/test_smoke.py -v -m smoke

Execução pós-deploy (HTTP contra URL real):
    SMOKE_BASE_URL=http://localhost:5000 \\
    SMOKE_EMAIL=admin@example.com \\
    SMOKE_PASSWORD='Change-me1!' \\
    pytest tests/test_smoke.py -v -m smoke

Variáveis opcionais:
    SMOKE_HEALTH_PATH   — padrão /health (fallback automático para /about)
    SMOKE_LOGIN_PATH    — padrão /api/auth/login
    SMOKE_DATABASE_URL  — conexão direta ao banco em modo remoto (SELECT 1)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request as urlrequest

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.smoke

# Rotas configuráveis — alinhadas à API REST do projeto
LOGIN_PATH = os.environ.get('SMOKE_LOGIN_PATH', '/api/auth/login')
TASKS_PATH = '/tasks'

# Headers de segurança esperados em respostas HTML
REQUIRED_SECURITY_HEADERS = (
    'X-Frame-Options',
    'X-Content-Type-Options',
)
OPTIONAL_SECURITY_HEADERS = (
    'Referrer-Policy',
    'Content-Security-Policy',
    'Strict-Transport-Security',
)


# ---------------------------------------------------------------------------
# Cliente HTTP unificado (deploy remoto ou Flask test client)
# ---------------------------------------------------------------------------

@dataclass
class SmokeResponse:
    status_code: int
    data: bytes
    headers: dict[str, str]

    def get_json(self) -> Any:
        if not self.data:
            return None
        return json.loads(self.data.decode())


class RemoteSmokeClient:
    """Cliente HTTP mínimo para smoke tests contra URL de deploy."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> SmokeResponse:
        url = f'{self.base_url}{path}'
        req_headers = dict(headers or {})
        payload = None
        if json_body is not None:
            payload = json.dumps(json_body).encode()
            req_headers.setdefault('Content-Type', 'application/json')

        req = urlrequest.Request(url, data=payload, headers=req_headers, method=method)
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as resp:
                return SmokeResponse(
                    status_code=resp.status,
                    data=resp.read(),
                    headers={k.lower(): v for k, v in resp.headers.items()},
                )
        except error.HTTPError as exc:
            body = exc.read()
            return SmokeResponse(
                status_code=exc.code,
                data=body,
                headers={k.lower(): v for k, v in exc.headers.items()},
            )

    def get(self, path: str, headers: dict | None = None) -> SmokeResponse:
        return self._request('GET', path, headers=headers)

    def post(
        self,
        path: str,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> SmokeResponse:
        return self._request('POST', path, json_body=json, headers=headers)

    def put(
        self,
        path: str,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> SmokeResponse:
        return self._request('PUT', path, json_body=json, headers=headers)

    def delete(self, path: str, headers: dict | None = None) -> SmokeResponse:
        return self._request('DELETE', path, headers=headers)


class LocalSmokeClient:
    """Adaptador sobre Flask test_client com interface compatível."""

    def __init__(self, client):
        self._client = client

    @staticmethod
    def _wrap(response) -> SmokeResponse:
        return SmokeResponse(
            status_code=response.status_code,
            data=response.data,
            headers={k.lower(): v for k, v in response.headers.items()},
        )

    def get(self, path: str, headers: dict | None = None) -> SmokeResponse:
        return self._wrap(self._client.get(path, headers=headers))

    def post(
        self,
        path: str,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> SmokeResponse:
        return self._wrap(self._client.post(path, json=json, headers=headers))

    def put(
        self,
        path: str,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> SmokeResponse:
        return self._wrap(self._client.put(path, json=json, headers=headers))

    def delete(self, path: str, headers: dict | None = None) -> SmokeResponse:
        return self._wrap(self._client.delete(path, headers=headers))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def smoke_base_url() -> str | None:
    return os.environ.get('SMOKE_BASE_URL')


@pytest.fixture
def is_remote(smoke_base_url) -> bool:
    return bool(smoke_base_url)


@pytest.fixture
def api(client, smoke_base_url):
    """Cliente unificado: remoto (urllib) ou local (Flask test client)."""
    if smoke_base_url:
        return RemoteSmokeClient(smoke_base_url)
    return LocalSmokeClient(client)


@pytest.fixture
def smoke_credentials(is_remote, test_user) -> dict[str, str]:
    """Credenciais para login — env em deploy, fixture test_user em modo local."""
    if is_remote:
        return {
            'email': os.environ.get('SMOKE_EMAIL', 'admin@example.com'),
            'password': os.environ.get('SMOKE_PASSWORD', 'Change-me1!'),
        }
    return {
        'email': test_user['email'],
        'password': test_user['password'],
    }


@pytest.fixture
def health_path(api) -> str:
    """Resolve endpoint de health: /health ou fallback /about."""
    configured = os.environ.get('SMOKE_HEALTH_PATH', '/health')
    if api.get(configured).status_code != 404:
        return configured
    if configured != '/about' and api.get('/about').status_code == 200:
        return '/about'
    return configured


@pytest.fixture
def auth_token(api, smoke_credentials) -> str:
    """Obtém JWT via POST login — reutilizado pelos testes autenticados."""
    response = api.post(LOGIN_PATH, json=smoke_credentials)
    assert response.status_code == 200, (
        f'Login smoke falhou: {response.status_code} — {response.get_json()}'
    )
    data = response.get_json()
    assert data and 'token' in data, 'Resposta de login deve conter token JWT'
    return data['token']


@pytest.fixture
def auth_headers(auth_token) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json',
    }


@pytest.fixture
def smoke_task_payload() -> dict[str, str]:
    """Payload mínimo para criação de tarefa — sem dependências complexas."""
    return {
        'title': 'Smoke test task',
        'description': 'Criada por test_smoke.py',
        'priority': 'low',
        'status': 'pending',
        'category': 'smoke',
    }


@pytest.fixture
def created_task(api, auth_headers, smoke_task_payload):
    """Cria tarefa temporária e remove ao final do teste."""
    response = api.post(TASKS_PATH, json=smoke_task_payload, headers=auth_headers)
    assert response.status_code == 201
    task = response.get_json()
    yield task
    api.delete(f'{TASKS_PATH}/{task["id"]}', headers=auth_headers)


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def test_health_check(api, health_path):
    """GET /health — aplicação respondendo com status 200."""
    response = api.get(health_path)
    assert response.status_code == 200


def test_login(api, smoke_credentials):
    """POST /api/auth/login — credenciais válidas retornam JWT."""
    response = api.post(LOGIN_PATH, json=smoke_credentials)
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert 'token' in data
    assert isinstance(data['token'], str) and len(data['token']) > 0


def test_create_task(api, auth_headers, smoke_task_payload):
    """POST /tasks — cria tarefa com dados válidos (201)."""
    response = api.post(TASKS_PATH, json=smoke_task_payload, headers=auth_headers)
    assert response.status_code == 201
    created = response.get_json()
    assert created is not None
    assert created['title'] == smoke_task_payload['title']
    assert 'id' in created

    api.delete(f'{TASKS_PATH}/{created["id"]}', headers=auth_headers)


def test_get_tasks(api, auth_headers):
    """GET /tasks — lista de tarefas com token válido (200)."""
    response = api.get(TASKS_PATH, headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_update_task(api, auth_headers, created_task):
    """PUT /tasks/<id> — atualiza tarefa existente (200)."""
    task_id = created_task['id']
    update_payload = {
        'title': 'Smoke task atualizada',
        'description': 'Atualizada pelo smoke test',
        'priority': 'medium',
        'status': 'in_progress',
        'category': 'smoke',
    }
    response = api.put(
        f'{TASKS_PATH}/{task_id}',
        json=update_payload,
        headers=auth_headers,
    )
    assert response.status_code == 200
    updated = response.get_json()
    assert updated['title'] == update_payload['title']
    assert updated['status'] == update_payload['status']


def test_delete_task(api, auth_headers, smoke_task_payload):
    """DELETE /tasks/<id> — remove tarefa (200)."""
    create_resp = api.post(TASKS_PATH, json=smoke_task_payload, headers=auth_headers)
    assert create_resp.status_code == 201
    task_id = create_resp.get_json()['id']

    response = api.delete(f'{TASKS_PATH}/{task_id}', headers=auth_headers)
    assert response.status_code == 200

    get_resp = api.get(TASKS_PATH, headers=auth_headers)
    tasks = get_resp.get_json()
    assert all(t['id'] != task_id for t in tasks)


def test_database_connection(api, app, db, health_path, is_remote):
    """Banco acessível — SELECT 1 local ou status no health em deploy."""
    if is_remote:
        db_url = os.environ.get('SMOKE_DATABASE_URL')
        if db_url:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                assert conn.execute(text('SELECT 1')).scalar() == 1
            return

        response = api.get(health_path)
        assert response.status_code == 200
        payload = response.get_json() or {}
        if 'database' in payload:
            assert payload['database'] == 'ok'
        else:
            login_resp = api.post(LOGIN_PATH, json={
                'email': os.environ.get('SMOKE_EMAIL', 'admin@example.com'),
                'password': os.environ.get('SMOKE_PASSWORD', 'Change-me1!'),
            })
            assert login_resp.status_code == 200
    else:
        with app.app_context():
            result = db.session.execute(text('SELECT 1')).scalar()
            assert result == 1


def test_security_headers(api):
    """GET / — headers de segurança presentes na resposta."""
    response = api.get('/')
    assert response.status_code == 200

    for header in REQUIRED_SECURITY_HEADERS:
        assert header.lower() in response.headers, (
            f'Header de segurança ausente: {header}'
        )

    present_optional = [
        h for h in OPTIONAL_SECURITY_HEADERS if h.lower() in response.headers
    ]
    assert present_optional, (
        'Nenhum header de segurança adicional encontrado '
        f'(esperado ao menos um de {OPTIONAL_SECURITY_HEADERS})'
    )
