import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes')


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', '45cf93c4d41348cd9980674ade9a7356'
)
app.config['DEBUG'] = _env_bool('DEBUG', False)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('SQLALCHEMY_DATABASE_URI')
    or os.environ.get('DATABASE_URL', 'sqlite:///site.db')
)
app.config['APP_NAME'] = os.environ.get('APP_NAME', 'Task Manager DevSecOps')
app.config['APP_VERSION'] = os.environ.get('APP_VERSION', '1.0.0')
app.config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', 'INFO')
app.config['SYSLOG_HOST'] = os.environ.get('SYSLOG_HOST', 'syslog')
app.config['SYSLOG_PORT'] = int(os.environ.get('SYSLOG_PORT', '514'))
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login' 
login_manager.login_message_category = 'danger'

bcrypt = Bcrypt(app)

# Always put Routes at end
from todo_project import routes

with app.app_context():
    db.create_all()