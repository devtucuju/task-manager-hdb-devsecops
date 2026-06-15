"""
app.py — Ponto de entrada principal (Etapa 1 DevSecOps).

Uso local:
    cd todo_project && python app.py

Docker / Gunicorn usa: todo_project:app
"""
from todo_project import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', False))
