"""Bootstrap de usuário admin (one-time, apenas com banco vazio)."""
import os

from todo_project import app, db, bcrypt
from todo_project.models import User


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes')


def bootstrap_admin() -> None:
    """Cria admin inicial se habilitado, seguro e banco sem usuários."""
    if not _env_bool('BOOTSTRAP_ADMIN_ENABLED', False):
        return

    if app.config.get('FLASK_ENV') == 'production' and not _env_bool(
        'BOOTSTRAP_ADMIN_ALLOW_PRODUCTION', False
    ):
        app.logger.warning(
            'Bootstrap admin ignorado em produção. '
            'Defina BOOTSTRAP_ADMIN_ALLOW_PRODUCTION=true apenas se necessário.'
        )
        return

    username = os.environ.get('BOOTSTRAP_ADMIN_USER', 'admin').strip()
    password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '')

    if not username or len(username) < 3:
        app.logger.warning('Bootstrap admin ignorado: BOOTSTRAP_ADMIN_USER inválido.')
        return

    if len(password) < 8:
        app.logger.warning(
            'Bootstrap admin ignorado: BOOTSTRAP_ADMIN_PASSWORD deve ter ao menos 8 caracteres.'
        )
        return

    if User.query.count() > 0:
        app.logger.info('Bootstrap admin ignorado: já existem usuários no banco.')
        return

    hashed = bcrypt.generate_password_hash(password).decode('utf-8')
    db.session.add(User(username=username, password=hashed))
    db.session.commit()
    app.logger.info("Usuário bootstrap '%s' criado com sucesso.", username)
