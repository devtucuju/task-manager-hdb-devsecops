"""Fixtures compartilhadas para a suite de testes pytest."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
import werkzeug

if not hasattr(werkzeug, '__version__'):
    werkzeug.__version__ = '3.0.0'

ROOT = Path(__file__).resolve().parent.parent
TODO_PROJECT_DIR = ROOT / 'todo_project'
if str(TODO_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(TODO_PROJECT_DIR))

from sqlalchemy.pool import StaticPool

from todo_project.auth import create_access_token, hash_password
from todo_project.extensions import db as database
from todo_project.factory import create_app
from todo_project.models import Task, User


class TestConfig:
    """Configuração isolada para testes — banco em memória e segredos fictícios."""

    TESTING = True
    SECRET_KEY = 'pytest-secret-key-not-for-production'
    DEBUG = False
    FLASK_ENV = 'testing'

    # SQLite em memória compartilhado via StaticPool (uma conexão por sessão de testes)
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False},
        'poolclass': StaticPool,
    }

    JWT_ALGORITHM = 'HS256'
    JWT_ACCESS_TOKEN_EXPIRES = __import__('datetime').timedelta(hours=1)
    JWT_COOKIE_NAME = 'access_token'
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_SAMESITE = 'Lax'

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    REGISTRATION_ENABLED = True
    SYSLOG_ENABLED = False
    LOG_LEVEL = 'INFO'
    RATELIMIT_ENABLED = True
    LOGIN_RATE_LIMIT = '100 per minute'
    APP_NAME = 'Task Manager Test'

    @staticmethod
    def init():
        """Desativa bootstrap de admin e syslog que interferem nos testes."""
        os.environ['SYSLOG_ENABLED'] = 'false'
        os.environ['BOOTSTRAP_ADMIN_ENABLED'] = 'false'


# Credenciais padrão reutilizadas pelas fixtures e pelos testes
TEST_USER = {
    'username': 'testuser',
    'email': 'testuser@example.com',
    'password': 'TestPass1!',
}


def extract_csrf(html: str) -> str:
    """Extrai o token CSRF de um formulário HTML renderizado."""
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not match:
        match = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
    assert match, 'CSRF token não encontrado no formulário'
    return match.group(1)


def clear_limiter_storage():
    """Zera o contador do Flask-Limiter entre testes de rate limiting."""
    from todo_project.extensions import limiter

    limiter.reset()
    storage = getattr(limiter, '_storage', None)
    if storage is not None and hasattr(storage, 'reset'):
        storage.reset()


def login(client, email: str, password: str):
    """Helper: autentica via formulário web com CSRF válido."""
    login_page = client.get('/login')
    csrf = extract_csrf(login_page.data.decode())
    return client.post(
        '/login',
        data={
            'csrf_token': csrf,
            'email': email,
            'password': password,
            'submit': 'Login',
        },
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# Fixtures principais
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def app():
    """
    Cria a aplicação Flask em modo de teste (escopo session).

    A app é instanciada uma vez por sessão de pytest para reduzir custo
    de inicialização; o banco é resetado por teste via fixture `db`.
    """
    TestConfig.init()
    application = create_app(TestConfig)

    with application.app_context():
        database.create_all()

    yield application

    with application.app_context():
        database.session.remove()
        database.drop_all()


@pytest.fixture(autouse=True)
def db(app):
    """
    Banco SQLite em memória isolado por teste (escopo function, autouse).

    Antes de cada teste: remove e recria todas as tabelas.
    Após cada teste: encerra a sessão SQLAlchemy para evitar vazamento de estado.
    Retorna a instância `db` do SQLAlchemy para uso direto nos testes.
    """
    with app.app_context():
        database.drop_all()
        database.create_all()

    yield database

    with app.app_context():
        database.session.remove()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Garante que o rate limiter não acumule contadores entre testes."""
    clear_limiter_storage()
    yield
    clear_limiter_storage()


@pytest.fixture
def client(app):
    """
    Cliente de teste Flask (escopo function).

    Permite simular requisições HTTP sem subir um servidor real.
    """
    return app.test_client()


@pytest.fixture
def test_user(app, db):
    """
    Persiste um usuário padrão no banco e retorna seus dados (escopo function).

    Retorna dict com id, email e password em texto plano (apenas para asserções).
    """
    with app.app_context():
        user = User(
            username=TEST_USER['username'],
            email=TEST_USER['email'],
            password_hash=hash_password(TEST_USER['password']),
            is_active=True,
        )
        database.session.add(user)
        database.session.commit()
        database.session.refresh(user)
        return {
            'id': user.id,
            'email': user.email,
            'password': TEST_USER['password'],
        }


@pytest.fixture
def test_user_token(app, test_user):
    """
    Gera um JWT válido para o usuário de teste (escopo function).

    Depende de `test_user` — o token é assinado com SECRET_KEY da app de teste.
    """
    with app.app_context():
        user = database.session.get(User, test_user['id'])
        return create_access_token(user)


@pytest.fixture
def test_task(app, db, test_user):
    """
    Cria uma tarefa vinculada ao usuário de teste (escopo function).

    Retorna dict com os campos principais da tarefa para asserções.
    """
    with app.app_context():
        task = Task(
            user_id=test_user['id'],
            title='Tarefa de teste',
            description='Descrição da tarefa de teste',
            priority='medium',
            status='pending',
            category='test',
        )
        database.session.add(task)
        database.session.commit()
        database.session.refresh(task)
        return {
            'id': task.id,
            'user_id': task.user_id,
            'title': task.title,
            'description': task.description,
            'priority': task.priority,
            'status': task.status,
            'category': task.category,
        }


@pytest.fixture
def auth_headers(test_user_token):
    """
    Cabeçalhos HTTP com Bearer JWT para rotas autenticadas (escopo function).

    Uso típico: client.get('/tasks', headers=auth_headers)
    """
    return {
        'Authorization': f'Bearer {test_user_token}',
        'Content-Type': 'application/json',
    }


# ---------------------------------------------------------------------------
# Fixtures de conveniência (compatibilidade com testes existentes)
# ---------------------------------------------------------------------------

@pytest.fixture
def jwt_token(test_user_token):
    """Alias de `test_user_token` para testes que usam esse nome."""
    return test_user_token


@pytest.fixture
def auth_client(client, app, test_user_token):
    """
    Cliente Flask com cookie JWT httpOnly — para rotas web com formulários.

    Complementa `auth_headers` (Bearer) em cenários de UI/CSRF.
    """
    client.set_cookie(
        key=app.config['JWT_COOKIE_NAME'],
        value=test_user_token,
        domain='localhost',
        path='/',
    )
    return client
