import pytest

from app.services.mineru_client import MinerUError, _endpoint, _markdown


def test_mineru_endpoint_and_markdown_protocol():
    assert _endpoint('http://mineru:8000') == 'http://mineru:8000/file_parse'
    assert _endpoint('https://docs.example/file_parse') == 'https://docs.example/file_parse'
    assert _markdown({'results': {'project.pdf': {'md_content': '# 项目\n交付任务'}}}) == '# 项目\n交付任务'


@pytest.mark.parametrize('value', ['', 'file:///tmp/a', 'https://user@example.com'])
def test_mineru_rejects_invalid_endpoint(value):
    with pytest.raises(MinerUError):
        _endpoint(value)
