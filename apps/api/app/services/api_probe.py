"""Bounded HTTPS diagnostics; no credentials or response bodies are persisted."""
import http.client
import ipaddress
import json
import socket
import ssl
import time
from typing import Literal
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, Field


class Probe(BaseModel):
    url: str = Field(max_length=2000)
    method: Literal['GET', 'POST'] = 'GET'
    body: dict = Field(default_factory=dict)
    auth: Literal['none', 'manual', 'endpoint'] = 'none'
    token: str = Field(default='', max_length=8192)
    token_url: str = Field(default='', max_length=2000)
    token_body: dict = Field(default_factory=dict)
    token_format: Literal['json', 'form'] = 'json'
    token_path: str = Field(default='access_token', max_length=200)


def request(url, method, body=None, token='', form=False):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('仅支持不含账号、密码和片段的 HTTPS 地址')
    if parsed.port not in (None, 443):
        raise ValueError('仅允许 HTTPS 443 端口')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    ips = [a[4][0] for a in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('禁止访问内网、回环、链路本地和云元数据地址')
    conn = http.client.HTTPSConnection(parsed.hostname, timeout=10, context=ssl.create_default_context())
    # Pin the validated address, retaining the original hostname for TLS verification.
    conn._create_connection = lambda address, timeout, source_address=None: socket.create_connection((ips[0], 443), timeout, source_address)
    headers = {'Accept': 'application/json'}
    if token:
        if '\n' in token or '\r' in token:
            raise ValueError('Token 格式无效')
        headers['Authorization'] = 'Bearer ' + token
    payload = None
    if method == 'POST':
        payload = (urlencode(body) if form else json.dumps(body)).encode()
        if len(payload) > 65536:
            raise ValueError('请求体不能超过64KB')
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    try:
        conn.request(method, (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''), payload, headers)
        response = conn.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('响应超过1MB，请缩小查询范围')
        if 300 <= response.status < 400:
            raise ValueError('不跟随重定向，请填写最终 API 地址')
        try:
            data = json.loads(raw)
            is_json = True
        except (ValueError, UnicodeDecodeError):
            data = None
            is_json = False
        return {'status': response.status, 'is_json': is_json, 'data': data,
                'bytes': len(raw), 'content_type': response.getheader('Content-Type', '')}
    finally:
        conn.close()


def redact(value, secrets):
    if isinstance(value, dict):
        return {k: '***' if any(word in k.lower() for word in ('token', 'password', 'secret', 'authorization', 'cookie')) else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, '***')
    return value


def probe(config):
    started = time.monotonic()
    token = config.token if config.auth == 'manual' else ''
    try:
        if config.auth == 'manual' and not token:
            raise ValueError('请输入 Bearer Token')
        if config.auth == 'endpoint':
            auth = request(config.token_url, 'POST', config.token_body, form=config.token_format == 'form')
            if not 200 <= auth['status'] < 300 or not auth['is_json']:
                raise ValueError(f"获取 Token 失败，HTTP {auth['status']}；需返回成功的JSON响应")
            token = auth['data']
            for part in config.token_path.split('.'):
                token = token.get(part) if isinstance(token, dict) else None
            if not isinstance(token, str) or not token or len(token) > 8192:
                raise ValueError('Token 字段路径不存在或不是有效字符串')
        result = request(config.url, config.method, config.body, token)
        secrets = [token] + [str(v) for v in config.token_body.values() if isinstance(v, (str, int))]
        result['data'] = redact(result['data'], secrets)
        result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        result['token_acquired'] = config.auth == 'endpoint'
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, http.client.HTTPException):
        raise HTTPException(502, '连接失败或超时，请检查域名、证书、网络和接口地址') from None
