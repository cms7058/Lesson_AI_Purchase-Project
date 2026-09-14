import io
import json

import pytest
from PIL import Image

from app.domain.rfqs import RFQLine
from app.services import quotation_vision


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        content = {"delivery_days": 9, "validity_days": 45, "lines": [{"material_code": "MAT-01", "unit_price": 98.6, "tax_rate": 0.13, "logistics_cost": 12}]}
        return {"choices": [{"message": {"content": json.dumps(content)}}]}


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (600, 300), "white").save(stream, "PNG")
    return stream.getvalue()


def test_visual_image_extraction_is_constrained_to_rfq_lines(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(quotation_vision.httpx, "post", fake_post)
    lines = [RFQLine(material_code="MAT-01", material_name="轴承", quantity=10, unit="件")]
    config = {"enabled": True, "base_url": "https://vision.example/v1", "model": "vision-test", "api_key": "secret"}
    result = quotation_vision.extract_visual_quotation(image_bytes(), "报价.png", lines, config)
    assert result["extraction_mode"] == "vision"
    assert result["lines"][0]["material_code"] == "MAT-01"
    assert result["lines"][0]["unit_price"] == 98.6
    assert result["delivery_days"] == 9
    assert captured["url"] == "https://vision.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_visual_requires_configuration():
    lines = [RFQLine(material_code="MAT-01", material_name="轴承", quantity=10, unit="件")]
    with pytest.raises(quotation_vision.VisionExtractionError, match="尚未配置"):
        quotation_vision.extract_visual_quotation(image_bytes(), "报价.png", lines, {"enabled": False})


def test_invalid_image_rejected_before_model_call():
    lines = [RFQLine(material_code="MAT-01", material_name="轴承", quantity=10, unit="件")]
    with pytest.raises(quotation_vision.VisionExtractionError, match="损坏"):
        quotation_vision.extract_visual_quotation(b"not-an-image", "报价.png", lines, {"enabled": True})
