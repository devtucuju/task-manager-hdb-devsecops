"""Métricas Prometheus para observabilidade da aplicação Flask."""
import time

from flask import Response, current_app, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

request_count = Counter(
    'flask_requests_total',
    'Total de requisições',
    ['method', 'endpoint', 'status'],
)
request_duration = Histogram(
    'flask_request_duration_seconds',
    'Duração das requisições',
    ['method', 'endpoint'],
)
auth_failures = Counter(
    'auth_failures_total',
    'Tentativas de autenticação falhadas',
    ['reason'],
)


def record_auth_failure(reason: str) -> None:
    """Incrementa contador de falhas de autenticação."""
    if not current_app.config.get('METRICS_ENABLED', True):
        return
    auth_failures.labels(reason=reason).inc()


def init_metrics(app) -> None:
    """Registra hooks e rota /metrics quando METRICS_ENABLED=true."""

    @app.before_request
    def _metrics_before_request():
        if not app.config.get('METRICS_ENABLED', True):
            return
        if request.path == '/metrics':
            return
        g._metrics_start_time = time.perf_counter()

    @app.after_request
    def _metrics_after_request(response):
        if not app.config.get('METRICS_ENABLED', True):
            return response
        if request.path == '/metrics':
            return response

        start = getattr(g, '_metrics_start_time', None)
        if start is None:
            return response

        duration = time.perf_counter() - start
        endpoint = request.endpoint or 'unmatched'
        request_count.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
        ).inc()
        request_duration.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)
        return response

    @app.route('/metrics')
    def metrics():
        if not app.config.get('METRICS_ENABLED', True):
            return Response('Metrics disabled\n', status=404, mimetype='text/plain')
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
