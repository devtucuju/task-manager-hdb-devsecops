"""
Application factory — Etapa 1 DevSecOps.

Centraliza configuração, extensões, logging, rotas e inicialização do banco.
"""
from flask import Flask, g
from flask_cors import CORS

from todo_project.bootstrap import bootstrap_admin
from todo_project.config import Config
from todo_project.extensions import bcrypt, csrf, db, limiter
from todo_project.logging_config import setup_logging
from todo_project.metrics import init_metrics


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.config['FLASK_ENV'] == 'production':
        config_class.validate()

    # Extensões
    db.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r'/api/*': {'origins': app.config.get('CORS_ORIGINS', '*')}})

    setup_logging(app)
    init_metrics(app)

    # Jinja2 auto-escape (XSS) — habilitado por padrão; reforço explícito
    app.jinja_env.autoescape = True

    @app.context_processor
    def inject_globals():
        return {
            'current_user': getattr(g, 'current_user', None),
            'app_name': app.config.get('APP_NAME'),
        }

    @app.before_request
    def attach_user():
        from todo_project.auth import load_current_user
        g.current_user = load_current_user()

    from todo_project.routes import register_routes
    register_routes(app)

    with app.app_context():
        db.create_all()
        bootstrap_admin(app)

    return app
