"""
test_app.py — Testes pytest para Task Manager DevSecOps (Etapa 1)

Execução:
    # Local (raiz do repositório)
    pip install -r requirements.txt
    pytest test_app.py -v

    # Docker (WORKDIR do container: /app/todo_project)
    docker compose exec app pytest test_app.py -v

Requisitos: pytest, pytest-cov (listados em requirements.txt)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# Flask 2.3 + Werkzeug 3.x: test_client exige __version__ no módulo werkzeug
import werkzeug
if not hasattr(werkzeug, '__version__'):
    werkzeug.__version__ = '3.0.0'

# Garante import do pacote todo_project (WORKDIR Docker: /app/todo_project)
ROOT = Path(__file__).resolve().parent
TODO_PROJECT_DIR = ROOT / 'todo_project'
if str(TODO_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(TODO_PROJECT_DIR))

from sqlalchemy.pool import StaticPool

from todo_project.auth import (
    create_access_token,
    decode_access_token,
    validate_password_strength,
)
from todo_project.extensions import db
from todo_project.factory import create_app
from todo_project.models import AuditLog, Task, User


# ---------------------------------------------------------------------------
# Configuração de teste (SQLite em memória, sem syslog/bootstrap)
# ---------------------------------------------------------------------------
class TestConfig:
    TESTING = True
    SECRET_KEY = 'pytest-secret-key-not-for-production'
    DEBUG = False
    FLASK_ENV = 'testing'

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
    LOGIN_RATE_LIMIT = '100 per minute'  # alto para não interferir entre testes
    APP_NAME = 'Task Manager Test'

    # Evita syslog durante testes (setup_logging lê os.environ)
    @staticmethod
    def init():
        os.environ['SYSLOG_ENABLED'] = 'false'
        os.environ['BOOTSTRAP_ADMIN_ENABLED'] = 'false'


TEST_USER = {
    'username': 'testuser',
    'email': 'testuser@example.com',
    'password': 'TestPass1!',
}


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not match:
        match = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
    assert match, 'CSRF token não encontrado no formulário'
    return match.group(1)


def _seed_user(app) -> User:
    from todo_project.auth import hash_password

    with app.app_context():
        user = User(
            username=TEST_USER['username'],
            email=TEST_USER['email'],
            password_hash=hash_password(TEST_USER['password']),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user


def _login(client, email: str, password: str):
    """Login via formulário web; retorna resposta (302 em sucesso)."""
    login_page = client.get('/login')
    csrf = _extract_csrf(login_page.data.decode())
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
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def app():
    """Uma única instância por módulo — evita acúmulo de handlers do Flask-Limiter."""
    TestConfig.init()
    application = create_app(TestConfig)

    with application.app_context():
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def reset_db(app):
    """Banco limpo antes de cada teste (app compartilhado no módulo)."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        _seed_user(app)
    yield
    with app.app_context():
        db.session.remove()


def _clear_limiter_storage():
    """Limpa storage in-memory global compartilhado entre apps de teste."""
    from todo_project.extensions import limiter

    limiter.reset()
    storage = getattr(limiter, '_storage', None)
    if storage is not None and hasattr(storage, 'reset'):
        storage.reset()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Limpa contadores do Flask-Limiter entre testes (storage in-memory global)."""
    _clear_limiter_storage()
    yield
    _clear_limiter_storage()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client, app):
    """Client autenticado via cookie JWT (evita POST /login repetidos)."""
    with app.app_context():
        user = db.session.query(User).filter_by(email=TEST_USER['email']).one()
        token = create_access_token(user)
    client.set_cookie(
        key=app.config['JWT_COOKIE_NAME'],
        value=token,
        domain='localhost',
        path='/',
    )
    return client


@pytest.fixture
def jwt_token(app):
    with app.app_context():
        user = db.session.query(User).filter_by(email=TEST_USER['email']).one()
        return create_access_token(user)


# ---------------------------------------------------------------------------
# 1. Aplicação inicia corretamente
# ---------------------------------------------------------------------------
class TestAppStartup:
    def test_app_factory_creates_instance(self, app):
        assert app is not None
        assert app.config['TESTING'] is True

    def test_about_route_is_public(self, client):
        response = client.get('/about')
        assert response.status_code == 200
        assert b'About' in response.data or response.status_code == 200

    def test_database_tables_exist(self, app):
        with app.app_context():
            assert db.session.query(User).count() == 1
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            assert 'user' in tables
            assert 'task' in tables
            assert 'audit_log' in tables


# ---------------------------------------------------------------------------
# 2. Rota de login funciona
# ---------------------------------------------------------------------------
class TestLoginRoute:
    def test_login_page_get(self, client):
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Login' in response.data

    def test_login_success_redirects(self, client):
        response = _login(client, TEST_USER['email'], TEST_USER['password'])
        assert response.status_code == 302
        assert '/all_tasks' in response.headers.get('Location', '')

    def test_login_sets_jwt_cookie(self, client, app):
        response = _login(client, TEST_USER['email'], TEST_USER['password'])
        cookie_name = app.config['JWT_COOKIE_NAME']
        assert cookie_name in response.headers.get('Set-Cookie', '')

    def test_login_invalid_credentials(self, client):
        response = _login(client, TEST_USER['email'], 'WrongPass1!')
        assert response.status_code == 200
        assert b'Invalid email or password' in response.data


# ---------------------------------------------------------------------------
# 3. Autenticação JWT funciona
# ---------------------------------------------------------------------------
class TestJWTAuth:
    def test_create_and_decode_token(self, app, jwt_token):
        with app.app_context():
            payload = decode_access_token(jwt_token)
            assert payload is not None
            assert payload['email'] == TEST_USER['email']
            assert 'user_id' in payload

    def test_api_me_with_bearer_token(self, client, jwt_token):
        response = client.get(
            '/api/me',
            headers={'Authorization': f'Bearer {jwt_token}'},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['email'] == TEST_USER['email']
        assert data['username'] == TEST_USER['username']

    def test_invalid_jwt_rejected(self, client):
        response = client.get(
            '/api/me',
            headers={'Authorization': 'Bearer token-invalido'},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 4. Proteção de rotas (token_required)
# ---------------------------------------------------------------------------
class TestRouteProtection:
    def test_all_tasks_requires_auth(self, client):
        response = client.get('/all_tasks')
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')

    def test_api_tasks_requires_auth(self, client):
        response = client.get('/api/tasks')
        assert response.status_code == 401
        assert response.get_json()['error'] == 'Autenticação necessária'

    def test_authenticated_access_all_tasks(self, auth_client):
        response = auth_client.get('/all_tasks')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 5. CRUD de tarefas funciona
# ---------------------------------------------------------------------------
class TestTaskCRUD:
    def _task_form_data(self, client, **overrides):
        page = client.get('/add_task')
        csrf = _extract_csrf(page.data.decode())
        data = {
            'csrf_token': csrf,
            'title': 'Tarefa pytest',
            'description': 'Descrição de teste',
            'priority': 'high',
            'status': 'pending',
            'category': 'dev',
            'submit': 'Save Task',
        }
        data.update(overrides)
        return data

    def test_create_task(self, auth_client, app):
        response = auth_client.post('/add_task', data=self._task_form_data(auth_client))
        assert response.status_code == 302

        with app.app_context():
            task = db.session.query(Task).filter_by(title='Tarefa pytest').one()
            assert task.priority == 'high'
            assert task.user_id is not None

    def test_read_tasks_list(self, auth_client, app):
        with app.app_context():
            user = db.session.query(User).filter_by(email=TEST_USER['email']).one()
            db.session.add(Task(user_id=user.id, title='Read test', priority='low', status='done'))
            db.session.commit()

        response = auth_client.get('/all_tasks')
        assert response.status_code == 200
        assert b'Read test' in response.data

    def test_update_task(self, auth_client, app):
        auth_client.post('/add_task', data=self._task_form_data(auth_client, title='Original'))

        with app.app_context():
            task = db.session.query(Task).filter_by(title='Original').one()
            task_id = task.id

        update_page = auth_client.get(f'/all_tasks/{task_id}/update_task')
        csrf = _extract_csrf(update_page.data.decode())
        response = auth_client.post(
            f'/all_tasks/{task_id}/update_task',
            data={
                'csrf_token': csrf,
                'title': 'Atualizada',
                'description': 'Nova desc',
                'priority': 'medium',
                'status': 'in_progress',
                'category': 'qa',
                'submit': 'Save Task',
            },
        )
        assert response.status_code == 302

        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.title == 'Atualizada'
            assert task.status == 'in_progress'

    def test_delete_task(self, auth_client, app):
        auth_client.post('/add_task', data=self._task_form_data(auth_client, title='Deletar'))

        with app.app_context():
            task = db.session.query(Task).filter_by(title='Deletar').one()
            task_id = task.id

        list_page = auth_client.get('/all_tasks')
        csrf = _extract_csrf(list_page.data.decode())
        response = auth_client.post(
            f'/all_tasks/{task_id}/delete_task',
            data={'csrf_token': csrf},
        )
        assert response.status_code == 302

        with app.app_context():
            assert db.session.get(Task, task_id) is None


# ---------------------------------------------------------------------------
# 6. Logging de eventos funciona
# ---------------------------------------------------------------------------
class TestAuditLogging:
    def test_login_success_logged(self, client, app):
        _login(client, TEST_USER['email'], TEST_USER['password'])

        with app.app_context():
            entry = (
                db.session.query(AuditLog)
                .filter_by(action='login_success')
                .order_by(AuditLog.id.desc())
                .first()
            )
            assert entry is not None
            assert entry.ip_address is not None
            assert 'testuser@example.com' in (entry.details or '')

    def test_login_failure_logged(self, client, app):
        _login(client, TEST_USER['email'], 'WrongPass1!')

        with app.app_context():
            entry = (
                db.session.query(AuditLog)
                .filter_by(action='login_failure')
                .first()
            )
            assert entry is not None

    def test_task_create_logged(self, auth_client, app):
        page = auth_client.get('/add_task')
        csrf = _extract_csrf(page.data.decode())
        auth_client.post(
            '/add_task',
            data={
                'csrf_token': csrf,
                'title': 'Audit log task',
                'description': '',
                'priority': 'low',
                'status': 'pending',
                'submit': 'Save Task',
            },
        )

        with app.app_context():
            entry = (
                db.session.query(AuditLog)
                .filter_by(action='create', resource_type='task')
                .first()
            )
            assert entry is not None


# ---------------------------------------------------------------------------
# 7. Validação de força de senha funciona
# ---------------------------------------------------------------------------
class TestPasswordValidation:
    @pytest.mark.parametrize(
        'password,expected',
        [
            ('TestPass1!', True),
            ('Short1!', False),
            ('alllowercase1!', False),
            ('ALLUPPERCASE1!', False),
            ('NoSpecialChar1', False),
            ('NoDigits!!aa', False),
        ],
    )
    def test_password_strength_rules(self, password, expected):
        valid, _ = validate_password_strength(password)
        assert valid is expected

    def test_registration_rejects_weak_password(self, client):
        page = client.get('/register')
        csrf = _extract_csrf(page.data.decode())
        response = client.post(
            '/register',
            data={
                'csrf_token': csrf,
                'username': 'weakuser',
                'email': 'weak@example.com',
                'password': 'weak',
                'confirm_password': 'weak',
                'submit': 'Register',
            },
        )
        assert response.status_code == 200
        assert b'Senha deve ter' in response.data or b'Password' in response.data


# ---------------------------------------------------------------------------
# 8. Rate limiting funciona
# ---------------------------------------------------------------------------
class TestRateLimiting:
    def test_login_rate_limit_blocks_after_threshold(self, app, client, monkeypatch):
        """Patch do limite em runtime — LOGIN_RATE_LIMIT é lido via current_app.config."""
        from todo_project.extensions import limiter

        monkeypatch.setitem(app.config, 'LOGIN_RATE_LIMIT', '4 per minute')
        monkeypatch.setattr(limiter, '_key_func', lambda: 'pytest-rate-limit-isolated')
        _clear_limiter_storage()

        login_page = client.get('/login')
        csrf = _extract_csrf(login_page.data.decode())
        payload = {
            'csrf_token': csrf,
            'email': TEST_USER['email'],
            'password': 'WrongPass1!',
            'submit': 'Login',
        }

        for i in range(2):
            resp = client.post('/login', data=payload)
            assert resp.status_code == 200, f'tentativa {i + 1} deveria retornar 200'

        resp = client.post('/login', data=payload)
        assert resp.status_code == 429

    def test_login_rate_limit_configured(self, app):
        assert app.config['RATELIMIT_ENABLED'] is True
        assert 'per' in app.config['LOGIN_RATE_LIMIT']
