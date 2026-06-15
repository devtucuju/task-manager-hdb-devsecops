"""
Pacote principal da aplicação Task Manager DevSecOps.

Exporta `app` para Gunicorn: todo_project:app
"""
from todo_project.factory import create_app

app = create_app()
