"""Bootstrap de usuário admin (one-time, apenas com banco vazio)."""
import os

from todo_project.auth import hash_password, validate_password_strength
from todo_project.extensions import db
from todo_project.models import User


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes')


def bootstrap_admin(app) -> None:
    """Cria admin inicial se habilitado, seguro e banco sem usuários."""
    if not _env_bool('BOOTSTRAP_ADMIN_ENABLED', False):
        return

    if app.config.get('FLASK_ENV') == 'production' and not _env_bool(
        'BOOTSTRAP_ADMIN_ALLOW_PRODUCTION', False
    ):
        app.logger.warning('Bootstrap admin ignorado em produção.')
        return

    username = os.environ.get('BOOTSTRAP_ADMIN_USER', 'admin').strip()
    email = os.environ.get('BOOTSTRAP_ADMIN_EMAIL', 'admin@example.com').strip().lower()
    password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '')

    if not username or len(username) < 3:
        app.logger.warning('Bootstrap admin ignorado: BOOTSTRAP_ADMIN_USER inválido.')
        return

    valid, message = validate_password_strength(password)
    if not valid:
        app.logger.warning('Bootstrap admin ignorado: %s', message)
        return

    if db.session.query(User.id).first():
        app.logger.info('Bootstrap admin ignorado: já existem usuários no banco.')
        return

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    app.logger.info("Usuário bootstrap '%s' (%s) criado.", username, email)
