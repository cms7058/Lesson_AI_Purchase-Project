import io
import zipfile
from uuid import uuid4

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.services.project_text_import import extract, preview

client = TestClient(app)
H = {'X-User-Role': 'procurement_manager'}
TEXT = '项目名称：装配设备交付\n合同金额：100000元\n交付：2026年12月01日完成设备交付\n验收：交付后30天验收'


def test_text_preview_and_saved_evidence():
    result = client.post('/api/v1/projects/import-text', headers=H, json={'text': TEXT})
    assert result.status_code == 200
    data = result.json()
    assert data['draft']['budget'] == 0 and data['draft']['status'] == 'draft'
    assert data['draft']['tasks'][0]['finish'] == '2026-12-01'
    assert data['draft']['tasks'][1]['finish'] is None
    data['draft']['code'] = uuid4().hex
    project = client.post('/api/v1/projects', headers=H, json=data['draft']).json()
    assert client.get('/api/v1/projects/'+project['id'], headers=H).json()['import_evidence']['source_text'] == TEXT
    repeated = client.post('/api/v1/projects/import-text', headers=H, json={'text': TEXT}).json()
    assert any(p['id'] == project['id'] for p in repeated['existing_projects'])
    assert client.post('/api/v1/projects/import-text', headers={'X-User-Role': 'buyer'}, json={'text': TEXT}).status_code == 403


def test_docx_eml_and_mineru_pdf(monkeypatch):
    doc = Document()
    for line in TEXT.splitlines():
        doc.add_paragraph(line)
    raw = io.BytesIO()
    doc.save(raw)
    text, notes = extract(raw.getvalue(), 'contract.docx')
    assert '装配设备交付' in text and notes
    raw_email = ('MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\nSubject: Project\r\n\r\n'+TEXT).encode()
    response = client.post('/api/v1/projects/import-file', headers=H, files={'file': ('project.eml', raw_email)})
    assert response.status_code == 200
    assert response.json()['draft']['name'] == '装配设备交付'
    assert '邮件主题' in response.json()['draft']['import_evidence']['source_text']
    async def fake_mineru(raw, filename, base_url=''):
        assert raw.startswith(b'%PDF-') and filename == 'project.pdf'
        return TEXT, 'MinerU/pipeline'
    monkeypatch.setattr('app.services.mineru_client.extract_pdf', fake_mineru)
    response = client.post('/api/v1/projects/import-file', headers=H, files={'file': ('project.pdf', b'%PDF-1.7\nscan')})
    assert response.status_code == 200
    assert response.json()['draft']['name'] == '装配设备交付'
    assert any('MinerU/pipeline' in note for note in response.json()['warnings'])


def test_bad_formats_and_dates():
    assert client.post('/api/v1/projects/import-file', headers=H, files={'file': ('scan.pdf', b'%PDF')}).status_code == 422
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as archive:
        archive.writestr('invalid.xml', 'bad')
    assert client.post('/api/v1/projects/import-file', headers=H, files={'file': ('bad.docx', raw.getvalue())}).status_code == 422
    result = preview('交付：2026年02月30日\n验收：2026-10-01至2026-10-05')
    assert all(t['finish'] is None for t in result['draft']['tasks'])


def test_searchable_pdf_falls_back_to_local_extractor(monkeypatch):
    from app.services.mineru_client import MinerUError

    async def unavailable(*_args, **_kwargs):
        raise MinerUError('MinerU不可用')

    monkeypatch.setattr('app.services.mineru_client.extract_pdf', unavailable)
    monkeypatch.setattr(
        'app.services.project_text_import.extract_pdf_text',
        lambda _raw: (TEXT, 'Poppler/pdftotext'),
    )
    response = client.post(
        '/api/v1/projects/import-file',
        headers=H,
        files={'file': ('searchable.pdf', b'%PDF-1.7\nsearchable')},
    )
    assert response.status_code == 200
    assert response.json()['draft']['name'] == '装配设备交付'
    assert any('Poppler/pdftotext' in note for note in response.json()['warnings'])
