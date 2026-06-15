"""Registro de auditoria (banco + syslog)."""
import json
from datetime import datetime, timezone

from flask import current_app, request

from todo_project.extensions import db
from todo_project.models import AuditLog


def get_client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def record_audit(
    action: str,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Persiste AuditLog e envia evento ao syslog."""
    ip = get_client_ip()
    details_json = json.dumps(details or {}, ensure_ascii=False)

    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details_json,
        ip_address=ip,
        timestamp=datetime.now(timezone.utc),
    )
    db.session.add(entry)
    db.session.commit()

    user_label = str(user_id) if user_id else 'anonymous'
    current_app.logger.info(
        'audit action=%s resource=%s:%s ip=%s user=%s details=%s',
        action,
        resource_type or '-',
        resource_id or '-',
        ip,
        user_label,
        details_json,
    )


def log_login_attempt(email: str, success: bool, user_id: int | None = None) -> None:
    action = 'login_success' if success else 'login_failure'
    record_audit(
        action=action,
        user_id=user_id,
        resource_type='user',
        resource_id=user_id,
        details={'email': email, 'success': success},
    )


def log_crud(action: str, resource_type: str, resource_id: int, user_id: int, **details) -> None:
    record_audit(
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
