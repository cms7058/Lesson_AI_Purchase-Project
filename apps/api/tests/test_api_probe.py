import socket

import pytest
from fastapi import HTTPException

from app.services import api_probe as p


def test_token_and_redaction(monkeypatch):
    calls = []
    def fake(url, method, body=None, token='', form=False):
        calls.append((url, method, token, form))
        data = {'data': {'access_token': 'SECRET'}} if len(calls) == 1 else {'items': [1], 'echo': 'SECRET', 'password': 'abc'}
        return {'status': 200, 'is_json': True, 'data': data, 'bytes': 30}
    monkeypatch.setattr(p, 'request', fake)
    result = p.probe(p.Probe(url='https://example.com/data', auth='endpoint', token_url='https://example.com/token', token_path='data.access_token', token_format='form'))
    assert calls[1][2] == 'SECRET' and calls[0][3]
    assert result['data'] == {'items': [1], 'echo': '***', 'password': '***'}
    assert result['token_acquired']


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:pass@example.com', 'https://example.com:8000'])
def test_bad_urls(url):
    with pytest.raises(ValueError):
        p.request(url, 'GET')


def test_private_dns_blocked(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(2, 1, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(ValueError, match='禁止访问'):
        p.request('https://example.com', 'GET')


def test_missing_token(monkeypatch):
    monkeypatch.setattr(p, 'request', lambda *a, **kw: {'status': 200, 'is_json': True, 'data': {}})
    with pytest.raises(HTTPException) as exc:
        p.probe(p.Probe(url='https://example.com', auth='endpoint', token_url='https://example.com/token'))
    assert exc.value.status_code == 422


def test_permissions():
    from fastapi.testclient import TestClient

    from app.main import app
    response = TestClient(app).post('/api/v1/data-connectors/test-api', headers={'X-User-Role': 'buyer'}, json={'url': 'https://example.com'})
    assert response.status_code == 403
