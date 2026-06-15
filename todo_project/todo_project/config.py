"""Configuração da aplicação via variáveis de ambiente (.env)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes')


class Config:
    """Centraliza configurações — nenhum segredo hardcoded."""

    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    DEBUG = _env_bool('DEBUG', False)
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production')

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('SQLALCHEMY_DATABASE_URI')
        or os.environ.get('DATABASE_URL', 'sqlite:///site.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.environ.get('JWT_EXPIRES_HOURS', '8'))
    )
    JWT_COOKIE_NAME = os.environ.get('JWT_COOKIE_NAME', 'access_token')
    JWT_COOKIE_SECURE = _env_bool('JWT_COOKIE_SECURE', False)
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_SAMESITE = os.environ.get('JWT_COOKIE_SAMESITE', 'Lax')

    # CSRF (Flask-WTF)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # App metadata
    APP_NAME = os.environ.get('APP_NAME', 'Task Manager DevSecOps')
    APP_VERSION = os.environ.get('APP_VERSION', '1.0.0')

    # Registro / bootstrap
    REGISTRATION_ENABLED = _env_bool(
        'REGISTRATION_ENABLED',
        os.environ.get('FLASK_ENV', 'production') != 'production',
    )

    # Syslog
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    SYSLOG_HOST = os.environ.get('SYSLOG_HOST', 'syslog')
    SYSLOG_PORT = int(os.environ.get('SYSLOG_PORT', '514'))
    SYSLOG_ENABLED = _env_bool('SYSLOG_ENABLED', True)

    # Rate limiting — login
    LOGIN_RATE_LIMIT = os.environ.get('LOGIN_RATE_LIMIT', '5 per 15 minutes')

    @staticmethod
    def validate():
        if not Config.SECRET_KEY or Config.SECRET_KEY == 'sua-chave-secreta-aqui':
            if Config.FLASK_ENV == 'production':
                raise RuntimeError('SECRET_KEY deve ser definida em produção.')
