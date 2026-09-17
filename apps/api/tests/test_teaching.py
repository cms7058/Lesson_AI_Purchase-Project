import io
from uuid import uuid4

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Id": "training-manager", "X-User-Role": "procurement_manager"}


def pdf_bytes() -> bytes:
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(72, 760, "AI training material")
    page.save()
    return output.getvalue()


def test_learning_account_exam_and_material_closed_loop():
    marker = uuid4().hex[:8]
    admin_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"})
    assert admin_login.status_code == 200
    admin = {"Authorization": f"Bearer {admin_login.json()['token']}"}
    assert client.get("/api/v1/auth/me", headers=admin).json()["role"] == "admin"
    staff = client.post(
        "/api/v1/staff-users",
        headers=MANAGER,
        json={
            "user_code": f"STU-{marker}",
            "name": f"测试学员-{marker}",
            "department": "培训班",
            "title": "学员",
            "role": "student",
            "status": "active",
        },
    )
    assert staff.status_code == 201, staff.text
    account = client.post(
        "/api/v1/learning-accounts",
        headers=MANAGER,
        json={"staff_id": staff.json()["id"], "username": f"student-{marker}", "password": "Study@2026", "active": True},
    )
    assert account.status_code == 201, account.text
    system_login = client.post("/api/v1/auth/login", json={"username": f"student-{marker}", "password": "Study@2026"})
    assert system_login.status_code == 200
    student_system = {"Authorization": f"Bearer {system_login.json()['token']}"}
    assert client.get("/api/v1/auth/me", headers=student_system).json()["role"] == "student"
    assert client.get("/api/v1/training-materials", headers=student_system).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=student_system).status_code == 200
    assert client.get("/api/v1/auth/me", headers=student_system).status_code == 401
    logged = client.post("/api/v1/learning/login", json={"username": f"student-{marker}", "password": "Study@2026"})
    assert logged.status_code == 200, logged.text
    learner = {"Authorization": f"Bearer {logged.json()['token']}"}

    exam = client.get("/api/v1/learning/exam", headers=learner)
    assert exam.status_code == 200 and exam.json()["question_count"] == 20
    attempt = client.post("/api/v1/learning/exam/start", headers=learner)
    assert attempt.status_code == 200 and attempt.json()["status"] == "in_progress"
    submitted = client.post(
        f"/api/v1/learning/exam/{attempt.json()['id']}/submit",
        headers=learner,
        json={"answers": {"1": "B", "2": "C", "16": ["D", "A", "C", "B"]}},
    )
    assert submitted.status_code == 200
    assert submitted.json()["score"] == 16
    assert len(submitted.json()["review"]) == 20
    assert client.get("/api/v1/learning/exam/paper.pdf", headers=learner).content.startswith(b"%PDF-")
    assert client.get(f"/api/v1/learning/exam/{attempt.json()['id']}/analysis.pdf", headers=learner).content.startswith(b"%PDF-")

    material = client.post(
        "/api/v1/training-materials",
        headers=MANAGER,
        data={"title": f"课件-{marker}", "category": "courseware", "description": "测试课件"},
        files={"file": (f"course-{marker}.pdf", pdf_bytes(), "application/pdf")},
    )
    assert material.status_code == 201, material.text
    listed = client.get("/api/v1/learning/materials", headers=learner)
    assert any(item["id"] == material.json()["id"] for item in listed.json())
    viewed = client.get(f"/api/v1/learning/materials/{material.json()['id']}/file", headers=learner)
    assert viewed.status_code == 200 and viewed.content.startswith(b"%PDF-")

    assert client.delete(f"/api/v1/training-materials/{material.json()['id']}", headers=MANAGER).status_code == 204
    # 已有考试记录的账号不可删除，只能停用，以保护培训档案。
    assert client.delete(f"/api/v1/learning-accounts/{account.json()['id']}", headers=MANAGER).status_code == 409
