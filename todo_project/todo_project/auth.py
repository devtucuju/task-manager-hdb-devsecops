"""Autenticação JWT, hash bcrypt e validação de senha."""
import re
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, redirect, request, url_for, flash

from todo_project.extensions import bcrypt, db
from todo_project.metrics import record_auth_failure
from todo_project.models import User

# Mínimo 8 chars, maiúscula, minúscula, dígito e caractere especial
PASSWORD_REGEX = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>\[\]\\/_+=\-]).{8,}$'
)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Retorna (válida, mensagem de erro)."""
    if not password or not PASSWORD_REGEX.match(password):
        return False, (
            'Senha deve ter no mínimo 8 caracteres, incluindo maiúscula, '
            'minúscula, número e caractere especial.'
        )
    return True, ''


def hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode('utf-8')


def check_password(password_hash: str, password: str) -> bool:
    return bcrypt.check_password_hash(password_hash, password)


def create_access_token(user: User) -> str:
    """Gera JWT com claims de sessão."""
    now = datetime.now(timezone.utc)
    expires = now + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    payload = {
        'user_id': user.id,
        'email': user.email,
        'username': user.username,
        'iat': now,
        'exp': expires,
    }
    return jwt.encode(
        payload,
        current_app.config['SECRET_KEY'],
        algorithm=current_app.config['JWT_ALGORITHM'],
    )


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=[current_app.config['JWT_ALGORITHM']],
        )
    except jwt.PyJWTError:
        return None


def _extract_token() -> str | None:
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1].strip()
    return request.cookies.get(current_app.config['JWT_COOKIE_NAME'])


def load_current_user() -> User | None:
    token = _extract_token()
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user = db.session.get(User, payload.get('user_id'))
    if not user or not user.is_active:
        return None
    return user


def token_required(f):
    """Decorador — exige JWT válido (header Bearer ou cookie httpOnly)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = load_current_user()
        if not user:
            if (
                request.path.startswith('/api/')
                or request.path.startswith('/tasks')
                or request.is_json
            ):
                record_auth_failure('missing_or_invalid_token')
                return jsonify({'error': 'Autenticação necessária'}), 401
            flash('Faça login para continuar.', 'warning')
            return redirect(url_for('login', next=request.path))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated
