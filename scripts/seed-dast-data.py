#!/usr/bin/env python3
"""
seed-dast-data.py — Cria usuários e tarefas para testes DAST.

Execução (dentro do container):
  docker compose exec app python /app/scripts/seed-dast-data.py

Execução (host, com stack rodando):
  python scripts/seed-dast-data.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODO_PROJECT = ROOT / "todo_project"
if str(TODO_PROJECT) not in sys.path:
    sys.path.insert(0, str(TODO_PROJECT))

os.environ.setdefault("SYSLOG_ENABLED", "false")
os.environ.setdefault("BOOTSTRAP_ADMIN_ENABLED", "false")

from todo_project.auth import hash_password
from todo_project.extensions import db
from todo_project.factory import create_app
from todo_project.models import Task, User

DAST_USERS = [
    {
        "username": "dast_user",
        "email": "dast-user@example.com",
        "password": "DastUser1!",
    },
    {
        "username": "dast_peer",
        "email": "dast-peer@example.com",
        "password": "DastPeer1!",
    },
]

DAST_TASKS = [
    {"title": "DAST Task — pending", "priority": "high", "status": "pending", "user_email": "dast-user@example.com"},
    {"title": "DAST Task — in progress", "priority": "medium", "status": "in_progress", "user_email": "dast-user@example.com"},
    {"title": "DAST Peer Task — private", "priority": "low", "status": "done", "user_email": "dast-peer@example.com"},
]


def seed():
    app = create_app()
    with app.app_context():
        for data in DAST_USERS:
            email = data["email"]
            user = db.session.query(User).filter_by(email=email).first()
            if user:
                print(f"Usuário já existe: {email}")
                continue
            user = User(
                username=data["username"],
                email=email,
                password_hash=hash_password(data["password"]),
                is_active=True,
            )
            db.session.add(user)
            print(f"Usuário criado: {email}")

        db.session.commit()

        for task_data in DAST_TASKS:
            user = db.session.query(User).filter_by(email=task_data["user_email"]).one()
            exists = db.session.query(Task).filter_by(title=task_data["title"], user_id=user.id).first()
            if exists:
                print(f"Tarefa já existe: {task_data['title']}")
                continue
            task = Task(
                user_id=user.id,
                title=task_data["title"],
                description="Dados de teste para varredura DAST",
                priority=task_data["priority"],
                status=task_data["status"],
                category="dast",
            )
            db.session.add(task)
            print(f"Tarefa criada: {task_data['title']} (user={user.email})")

        db.session.commit()
        print("Seed DAST concluído.")


if __name__ == "__main__":
    seed()
