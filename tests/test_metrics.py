"""Testes do endpoint Prometheus /metrics."""


def test_metrics_endpoint_returns_prometheus_format(client):
    response = client.get('/metrics')
    assert response.status_code == 200
    assert b'flask_requests_total' in response.data
    assert b'flask_request_duration_seconds' in response.data
    assert b'auth_failures_total' in response.data


def test_metrics_records_request_after_hit(client):
    client.get('/about')
    response = client.get('/metrics')
    assert b'flask_requests_total' in response.data
    assert b'endpoint="about"' in response.data


def test_auth_failure_metric_on_invalid_login(client):
    client.post(
        '/api/auth/login',
        json={'email': 'nobody@example.com', 'password': 'WrongPass1!'},
    )
    response = client.get('/metrics')
    assert b'auth_failures_total' in response.data
    assert b'invalid_credentials' in response.data
