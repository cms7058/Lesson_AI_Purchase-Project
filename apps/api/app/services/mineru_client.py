"""Optional MinerU adapter for high-fidelity PDF-to-Markdown extraction."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import get_settings


class MinerUError(ValueError):
    pass


def _endpoint(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise MinerUError("尚未配置MinerU PDF解析服务")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise MinerUError("MinerU服务地址必须是有效的HTTP或HTTPS地址")
    path = parsed.path.rstrip("/")
    if not path.endswith("/file_parse"):
        path += "/file_parse"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _markdown(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    results = payload.get("results")
    if not isinstance(results, dict):
        return ""
    blocks = []
    for result in results.values():
        if not isinstance(result, dict):
            continue
        value = result.get("md_content") or result.get("md") or result.get("markdown")
        if isinstance(value, str) and value.strip():
            blocks.append(value.strip())
    return "\n\n".join(blocks)


async def extract_pdf(raw: bytes, filename: str, base_url: str = "") -> tuple[str, str]:
    if not raw.startswith(b"%PDF-"):
        raise MinerUError("PDF文件结构无效")
    settings = get_settings()
    endpoint = _endpoint(base_url or settings.mineru_base_url)
    headers = {}
    if settings.mineru_api_key:
        headers["Authorization"] = f"Bearer {settings.mineru_api_key}"
    form = {
        "backend": settings.mineru_backend,
        "parse_method": "auto",
        "lang_list": "ch",
        "formula_enable": "true",
        "table_enable": "true",
        "return_md": "true",
        "return_middle_json": "false",
        "return_model_output": "false",
        "return_content_list": "false",
        "return_images": "false",
        "response_format_zip": "false",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=settings.mineru_timeout_seconds) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                data=form,
                files={"files": (Path(filename).name, raw, "application/pdf")},
            )
            response.raise_for_status()
            text = _markdown(response.json())
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise MinerUError("MinerU解析失败，请检查服务状态、接口版本和网络配置") from exc
    if len(text.strip()) < 10:
        raise MinerUError("MinerU未返回足够的PDF正文")
    return text, f"MinerU/{settings.mineru_backend}"
