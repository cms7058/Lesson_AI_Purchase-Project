import hashlib
import hmac
import io
import json
import secrets
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import StaffUserRecord
from app.domain.teaching import (
    ExamAttemptRecord,
    LearningAccountRecord,
    LearningSessionRecord,
    TrainingMaterialRecord,
)
from app.services.audit_service import write_audit_log

router = APIRouter(tags=["teaching"])
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}
FILES = Path("private_training_materials")
MAX_PDF_BYTES = 80 * 1024 * 1024
PAPER_CODE = "AI-PM-PROC-001"
PAPER_TITLE = "AI赋能项目采购与备件管理学员测试"
EXAM_MINUTES = 45

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
addMapping("STSong-Light", 0, 0, "STSong-Light")
addMapping("STSong-Light", 0, 1, "STSong-Light")
addMapping("STSong-Light", 1, 0, "STSong-Light")
addMapping("STSong-Light", 1, 1, "STSong-Light")


QUESTIONS = [
    (1, "项目", "single", "项目范围、进度和预算发生冲突时，项目负责人首先应采取哪项行动？", ["立即压缩采购周期，不再评估风险", "明确优先级与授权边界，并按变更流程更新基线", "让AI自动决定牺牲哪个目标", "暂停记录，等项目结束后统一处理"], "B", "先明确约束、优先级和授权，再进行受控变更。"),
    (2, "项目", "single", "WBS在项目管理中的主要作用是什么？", ["只用于统计供应商数量", "代替项目进度计划", "按交付物把范围拆成可负责、可验收的工作包", "只记录项目费用"], "C", "WBS界定范围和工作包，依赖关系仍需在进度计划中表达。"),
    (3, "项目", "single", "关于关键路径，下列说法正确的是哪一项？", ["关键路径上的任务延期不会影响项目完工", "关键路径决定给定依赖条件下的最早完工时间", "关键路径一定是成本最低的路径", "关键路径上的任务都可以并行执行"], "B", "关键路径上的延误通常会传递到项目完工日期。"),
    (4, "项目", "single", "项目成本预警最合理的触发依据是什么？", ["实际成本加完工预测超过批准基线或预警阈值", "项目成员收到一封新邮件", "供应商账号完成登录", "新建了一个物料编码"], "A", "预警应与批准基线、预测完工成本和阈值关联。"),
    (5, "备件采购", "single", "本系统的MRO物料画像除ABC、VED、FSN外，还应重点考虑哪组因素？", ["供应商名称和采购员姓名", "需求特性、飞机影响、供应风险、交期、价值、替代性、合规与Repair属性", "物料描述的字数", "只考虑历史最低价"], "B", "多维画像决定预测模型、采购提前量和供应策略。"),
    (6, "备件采购", "single", "ABC分类通常首先依据什么指标？", ["年耗用金额", "供应商距离", "维修人员数量", "物料名称长度"], "A", "ABC通常以年耗用量乘以单价得到的年耗用金额为基础。"),
    (7, "备件采购", "single", "VED与FSN分类的主要区别是什么？", ["VED关注价值，FSN关注价格", "VED关注关键性和停机后果，FSN关注领用频率与流动性", "VED只用于生产件，FSN只用于合同", "两者含义完全相同"], "B", "VED描述关键性，FSN描述流动性，低频不等于不重要。"),
    (8, "备件采购", "single", "单一来源、长交期、高价值备件应优先采用哪种预测思路？", ["只取最近一次采购数量", "结合AMOS维修事件、装机量、交期和Repair回转信息进行推断", "只用所有月份的简单平均数", "由供应商自行决定采购数量"], "B", "低频关键件往往由维修事件驱动，单纯趋势法可能失真。"),
    (9, "备件采购", "single", "当需求或交期样本明显不服从正态分布时，系统应优先采用哪种统计口径？", ["最大值", "均值加三倍标准差，不再检查异常值", "中位数与四分位距，并回查异常值原因", "直接删除所有偏离均值的数据"], "C", "中位数和四分位距对异常值更稳健。"),
    (10, "备件采购", "single", "计算自有库有效可用库存时，正确的基本口径是什么？", ["账面数量全部可用", "账面数量减预留、减隔离，并核对预计可用日期", "只看最近一次入库数量", "账面数量加报废数量"], "B", "预留和隔离库存不能直接满足新需求，可用日期也影响计划。"),
    (11, "备件采购", "single", "采购与供货日历中，某物料库存足以满足计划需求时，正确操作是什么？", ["激活供货并生成仓库检货任务", "同时生成全量采购订单", "删除该计划事件", "将库存全部隔离"], "A", "库存足够时只走供货和检货流程，不重复采购。"),
    (12, "备件采购", "single", "关于VMI与寄售，下列说法正确的是哪一项？", ["VMI必然等同于寄售", "寄售库存一定由采购方负责补货", "两者都不需要盘点和服务水平约定", "VMI主要约定补货责任，寄售主要涉及所有权和结算触发，两者可组合"], "D", "补货责任、所有权和结算触发需要分别约定。"),
    (13, "备件采购", "single", "联合采购策略模型不应只输出哪一种结果？", ["各策略成本", "单一最低采购价且不说明风险和约束", "时间、成本与合规冲突", "数据缺口和修正建议"], "B", "结论必须同时反映成本、风险、冲突、缺项和授权条件。"),
    (14, "AI", "single", "AI采购助手查询订单、供应商或物料数据时，最重要的前提是什么？", ["可以绕过人员权限以获得完整数据", "只给出结论，不展示查询范围", "使用授权数据，并说明查询条件、范围和来源", "将缺失记录自动补成真实数据"], "C", "数据权限、来源和筛选条件决定结果是否可核验。"),
    (15, "AI", "single", "AI助手提出项目或采购建议后，最终批准责任应由谁承担？", ["具备相应授权的人员", "大模型服务商", "系统数据库", "自动化工作流本身"], "A", "AI负责辅助分析和解释，授权人员负责批准和追责。"),
    (16, "项目", "multi", "项目需求发生重大变更时，应同步重新评估哪些内容？", ["项目范围和交付标准", "进度、关键路径和里程碑", "成本预测、采购计划与风险", "责任人、审批权限和通知对象"], "ABCD", "重大变更会同时影响范围、时间、成本、风险和治理责任。"),
    (17, "备件采购", "multi", "生产件采购的DOE与TOC实际采购成本模型可考虑哪些因子？", ["价格与交期", "响应时间与供货及时率", "合格率与返修率", "供应商Logo颜色"], "ABC", "模型因子需有业务机制和可验证数据，Logo颜色不构成成本因子。"),
    (18, "备件采购", "multi", "形成备件采购缺口前，系统应检查哪些库存或状态？", ["自有库的账面、预留和隔离状态", "寄售库与VMI库存", "修理回转库存及预计可用日期", "已确认在途和需求日期是否匹配"], "ABCD", "采购缺口必须在统一扣减全部有效资源后计算。"),
    (19, "备件采购", "multi", "物料联合策略分析的专业输出应包含哪些内容？", ["各策略的计算过程和成本换算", "供应风险与成本影响四象限", "时间、成本、合规等矛盾点", "数据缺口、修正建议和人工确认记录"], "ABCD", "系统需要展示分析过程和冲突，而不仅给出一个最终结论。"),
    (20, "AI", "multi", "在项目与采购管理中负责任地使用AI，应遵循哪些原则？", ["核验数据来源、权限和时效", "展示关键假设、计算依据和限制", "由授权人员复核并批准重要决定", "数据不足时让AI编造合理记录以完成分析"], "ABC", "AI不得编造业务记录；重要结论必须可追溯并经人工批准。"),
]


def _manager(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in MANAGERS:
        raise HTTPException(403, "需要管理员或采购经理权限")
    return user


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"{salt}:{digest}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt = encoded.split(":", 1)[0]
        return hmac.compare_digest(encoded, _hash_password(password, salt))
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _account_out(db: Session, account: LearningAccountRecord) -> dict:
    staff = db.get(StaffUserRecord, account.staff_id)
    return {
        "id": account.id,
        "staff_id": account.staff_id,
        "staff_code": staff.user_code if staff else "",
        "staff_name": staff.name if staff else "已删除人员",
        "department": staff.department if staff else "",
        "username": account.username,
        "active": account.active,
        "last_login_at": account.last_login_at,
        "created_at": account.created_at,
    }


def _learning_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> LearningAccountRecord:
    token = authorization.removeprefix("Bearer ").strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest() if token else ""
    session = db.get(LearningSessionRecord, token_hash)
    account = db.get(LearningAccountRecord, session.account_id) if session and session.expires_at > _now() else None
    staff = db.get(StaffUserRecord, account.staff_id) if account else None
    if not account or not account.active or not staff or staff.status != "active":
        raise HTTPException(401, "学习账号未登录或会话已过期")
    return account


class AccountInput(BaseModel):
    staff_id: str
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str | None = Field(default=None, min_length=8, max_length=128)
    active: bool = True


class LearningLogin(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=128)


class ExamSubmit(BaseModel):
    answers: dict[str, str | list[str]] = Field(default_factory=dict)


class MaterialUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    category: str | None = Field(default=None, pattern="^(courseware|teaching|case|reference)$")
    description: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


@router.get("/learning-accounts")
def list_learning_accounts(
    keyword: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_manager),
):
    statement = select(LearningAccountRecord)
    if keyword:
        staff_ids = select(StaffUserRecord.id).where(
            or_(StaffUserRecord.name.ilike(f"%{keyword}%"), StaffUserRecord.user_code.ilike(f"%{keyword}%"))
        )
        statement = statement.where(or_(LearningAccountRecord.username.ilike(f"%{keyword}%"), LearningAccountRecord.staff_id.in_(staff_ids)))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(LearningAccountRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [_account_out(db, row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/learning-accounts", status_code=201)
def create_learning_account(payload: AccountInput, db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    staff = db.get(StaffUserRecord, payload.staff_id)
    if not staff:
        raise HTTPException(404, "未找到关联人员")
    if db.scalar(select(LearningAccountRecord.id).where(LearningAccountRecord.staff_id == payload.staff_id)):
        raise HTTPException(409, "该人员已有学习账号")
    if db.scalar(select(LearningAccountRecord.id).where(LearningAccountRecord.username == payload.username)):
        raise HTTPException(409, "登录名已存在")
    if not payload.password:
        raise HTTPException(422, "新账号必须设置至少8位密码")
    row = LearningAccountRecord(staff_id=payload.staff_id, username=payload.username, password_hash=_hash_password(payload.password), active=payload.active, created_by=user.user_id)
    db.add(row)
    db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="create", resource_type="learning_account", resource_id=row.id, detail=f"创建学习账号 {payload.username}（不记录密码）")
    db.commit()
    db.refresh(row)
    return _account_out(db, row)


@router.put("/learning-accounts/{account_id}")
def update_learning_account(account_id: str, payload: AccountInput, db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    row = db.get(LearningAccountRecord, account_id)
    if not row:
        raise HTTPException(404, "未找到学习账号")
    staff = db.get(StaffUserRecord, payload.staff_id)
    if not staff:
        raise HTTPException(404, "未找到关联人员")
    duplicate = db.scalar(select(LearningAccountRecord).where(LearningAccountRecord.username == payload.username))
    if duplicate and duplicate.id != row.id:
        raise HTTPException(409, "登录名已存在")
    linked = db.scalar(select(LearningAccountRecord).where(LearningAccountRecord.staff_id == payload.staff_id))
    if linked and linked.id != row.id:
        raise HTTPException(409, "该人员已有学习账号")
    row.staff_id = payload.staff_id
    row.username = payload.username
    row.active = payload.active
    if payload.password:
        row.password_hash = _hash_password(payload.password)
        row.failures = 0
        row.locked_until = None
    db.execute(delete(LearningSessionRecord).where(LearningSessionRecord.account_id == row.id))
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="learning_account", resource_id=row.id, detail=f"更新学习账号 {row.username}（不记录密码）")
    db.commit()
    db.refresh(row)
    return _account_out(db, row)


@router.delete("/learning-accounts/{account_id}", status_code=204)
def delete_learning_account(account_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    row = db.get(LearningAccountRecord, account_id)
    if not row:
        raise HTTPException(404, "未找到学习账号")
    if db.scalar(select(ExamAttemptRecord.id).where(ExamAttemptRecord.account_id == account_id).limit(1)):
        raise HTTPException(409, "账号已有考试记录，请停用账号以保留培训档案")
    db.execute(delete(LearningSessionRecord).where(LearningSessionRecord.account_id == row.id))
    db.delete(row)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="delete", resource_type="learning_account", resource_id=account_id, detail="删除未参加考试的学习账号")
    db.commit()


@router.post("/learning/login")
def learning_login(payload: LearningLogin, db: Session = Depends(get_db)):
    row = db.scalar(select(LearningAccountRecord).where(LearningAccountRecord.username == payload.username))
    now = _now()
    valid = row and row.active and (not row.locked_until or row.locked_until <= now)
    if not valid or not _verify_password(payload.password, row.password_hash):
        if row:
            row.failures += 1
            if row.failures >= 5:
                row.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(401, "账号或密码错误；连续失败5次后锁定15分钟")
    staff = db.get(StaffUserRecord, row.staff_id)
    if not staff or staff.status != "active":
        raise HTTPException(403, "人员档案已停用")
    row.failures = 0
    row.locked_until = None
    row.last_login_at = now
    token = secrets.token_urlsafe(40)
    db.add(LearningSessionRecord(token_hash=hashlib.sha256(token.encode()).hexdigest(), account_id=row.id, expires_at=now + timedelta(hours=12)))
    db.commit()
    return {"token": token, "user": {"id": row.id, "username": row.username, "name": staff.name, "department": staff.department}}


@router.post("/learning/logout")
def learning_logout(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        db.execute(delete(LearningSessionRecord).where(LearningSessionRecord.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        db.commit()
    return {"ok": True}


def _question_out(question: tuple) -> dict:
    number, category, kind, text, options, *_ = question
    return {"number": number, "category": category, "type": kind, "text": text, "options": [{"key": chr(65 + index), "text": value} for index, value in enumerate(options)], "points": 8 if kind == "multi" else 4}


@router.get("/learning/exam")
def get_exam(account: LearningAccountRecord = Depends(_learning_user)):
    return {"code": PAPER_CODE, "title": PAPER_TITLE, "duration_minutes": EXAM_MINUTES, "total_score": 100, "question_count": len(QUESTIONS), "questions": [_question_out(q) for q in QUESTIONS]}


@router.post("/learning/exam/start")
def start_exam(db: Session = Depends(get_db), account: LearningAccountRecord = Depends(_learning_user)):
    now = _now()
    active = db.scalar(select(ExamAttemptRecord).where(ExamAttemptRecord.account_id == account.id, ExamAttemptRecord.paper_code == PAPER_CODE, ExamAttemptRecord.status == "in_progress").order_by(ExamAttemptRecord.started_at.desc()))
    if active and active.expires_at > now:
        return _attempt_out(db, active, include_review=False)
    if active:
        active.status = "expired"
        active.timed_out = True
    row = ExamAttemptRecord(account_id=account.id, paper_code=PAPER_CODE, started_at=now, expires_at=now + timedelta(minutes=EXAM_MINUTES))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _attempt_out(db, row, include_review=False)


def _normalize_answer(value) -> str:
    if isinstance(value, list):
        return "".join(sorted({str(item).upper() for item in value if str(item).upper() in "ABCD"}))
    return "".join(sorted({char for char in str(value).upper() if char in "ABCD"}))


def _attempt_out(db: Session, row: ExamAttemptRecord, include_review: bool = True) -> dict:
    account = db.get(LearningAccountRecord, row.account_id)
    staff = db.get(StaffUserRecord, account.staff_id) if account else None
    result = {
        "id": row.id,
        "paper_code": row.paper_code,
        "paper_title": PAPER_TITLE,
        "student_name": staff.name if staff else "",
        "status": row.status,
        "started_at": row.started_at,
        "expires_at": row.expires_at,
        "submitted_at": row.submitted_at,
        "score": row.score,
        "correct_count": row.correct_count,
        "timed_out": row.timed_out,
        "server_time": _now(),
    }
    if include_review and row.status == "submitted":
        answers = json.loads(row.answers_json or "{}")
        result["review"] = [
            {
                "number": q[0],
                "category": q[1],
                "question": q[3],
                "answer": q[5],
                "user_answer": _normalize_answer(answers.get(str(q[0]), "")),
                "correct": _normalize_answer(answers.get(str(q[0]), "")) == q[5],
                "explanation": q[6],
            }
            for q in QUESTIONS
        ]
    return result


@router.post("/learning/exam/{attempt_id}/submit")
def submit_exam(attempt_id: str, payload: ExamSubmit, db: Session = Depends(get_db), account: LearningAccountRecord = Depends(_learning_user)):
    row = db.get(ExamAttemptRecord, attempt_id)
    if not row or row.account_id != account.id:
        raise HTTPException(404, "未找到本人的考试记录")
    if row.status == "submitted":
        return _attempt_out(db, row)
    if row.status not in {"in_progress", "expired"}:
        raise HTTPException(409, "当前考试状态不能交卷")
    normalized = {str(key): _normalize_answer(value) for key, value in payload.answers.items()}
    correct = 0
    score = 0
    for question in QUESTIONS:
        if normalized.get(str(question[0]), "") == question[5]:
            correct += 1
            score += 8 if question[2] == "multi" else 4
    now = _now()
    row.answers_json = json.dumps(normalized, ensure_ascii=False)
    row.submitted_at = now
    row.status = "submitted"
    row.score = score
    row.correct_count = correct
    row.timed_out = now > row.expires_at
    db.commit()
    db.refresh(row)
    return _attempt_out(db, row)


@router.get("/learning/exam-attempts")
def my_exam_attempts(db: Session = Depends(get_db), account: LearningAccountRecord = Depends(_learning_user)):
    rows = db.scalars(select(ExamAttemptRecord).where(ExamAttemptRecord.account_id == account.id).order_by(ExamAttemptRecord.started_at.desc()))
    return [_attempt_out(db, row, include_review=False) for row in rows]


@router.get("/exam-attempts")
def all_exam_attempts(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    statement = select(ExamAttemptRecord)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(ExamAttemptRecord.started_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [_attempt_out(db, row, include_review=False) for row in rows], "total": total, "page": page, "page_size": page_size}


def _pdf_document(title: str, story: list) -> bytes:
    data = io.BytesIO()
    doc = SimpleDocTemplate(data, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title=title)
    doc.build(story)
    return data.getvalue()


def _styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("cn-title", parent=styles["Title"], fontName="STSong-Light", fontSize=18, leading=25, textColor=colors.HexColor("#101828")),
        "head": ParagraphStyle("cn-head", parent=styles["Heading2"], fontName="STSong-Light", fontSize=12, leading=18, textColor=colors.HexColor("#101828"), spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("cn-body", parent=styles["BodyText"], fontName="STSong-Light", fontSize=9.5, leading=15, spaceAfter=4),
        "small": ParagraphStyle("cn-small", parent=styles["BodyText"], fontName="STSong-Light", fontSize=8.2, leading=12, textColor=colors.HexColor("#475467")),
    }


@router.get("/learning/exam/paper.pdf")
def download_exam_paper(account: LearningAccountRecord = Depends(_learning_user)):
    styles = _styles()
    story = [Paragraph(PAPER_TITLE, styles["title"]), Paragraph(f"考试时间：{EXAM_MINUTES}分钟　总分：100分　共20题", styles["small"]), Spacer(1, 5 * mm)]
    for q in QUESTIONS:
        story.append(Paragraph(f"{q[0]}. {escape(q[3])}（　　）", styles["body"]))
        story.append(Paragraph("　　".join(f"{chr(65+i)}. {escape(value)}" for i, value in enumerate(q[4])), styles["small"]))
        story.append(Spacer(1, 2 * mm))
    return StreamingResponse(io.BytesIO(_pdf_document(PAPER_TITLE, story)), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="training-exam.pdf"'})


@router.get("/learning/exam/{attempt_id}/analysis.pdf")
def download_exam_analysis(attempt_id: str, db: Session = Depends(get_db), account: LearningAccountRecord = Depends(_learning_user)):
    row = db.get(ExamAttemptRecord, attempt_id)
    if not row or row.account_id != account.id or row.status != "submitted":
        raise HTTPException(404, "未找到已提交的本人答题解析")
    result = _attempt_out(db, row)
    styles = _styles()
    story = [Paragraph("学员答题解析", styles["title"]), Paragraph(f"学员：{escape(result['student_name'])}　得分：{row.score}　答对：{row.correct_count}/20", styles["head"]), Spacer(1, 3 * mm)]
    for item in result["review"]:
        state = "正确" if item["correct"] else "错误"
        story.append(Paragraph(f"{item['number']}. {escape(item['question'])}", styles["body"]))
        story.append(Paragraph(f"作答：{item['user_answer'] or '未答'}　标准答案：{item['answer']}　判定：{state}<br/>解析：{escape(item['explanation'])}", styles["small"]))
        story.append(Spacer(1, 1.5 * mm))
    return StreamingResponse(io.BytesIO(_pdf_document("学员答题解析", story)), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="exam-analysis.pdf"'})


def _material_out(row: TrainingMaterialRecord) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "category": row.category,
        "description": row.description,
        "original_filename": row.original_filename,
        "file_size": row.file_size,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/training-materials")
def list_training_materials(keyword: str = "", category: str = "", status: str = "", page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    conditions = []
    if keyword:
        conditions.append(or_(TrainingMaterialRecord.title.ilike(f"%{keyword}%"), TrainingMaterialRecord.original_filename.ilike(f"%{keyword}%")))
    if category:
        conditions.append(TrainingMaterialRecord.category == category)
    if status:
        conditions.append(TrainingMaterialRecord.status == status)
    statement = select(TrainingMaterialRecord).where(*conditions)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(TrainingMaterialRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [_material_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/training-materials", status_code=201)
async def upload_training_material(file: UploadFile = File(), title: str = Form(), category: str = Form("courseware"), description: str = Form(""), db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    if category not in {"courseware", "teaching", "case", "reference"}:
        raise HTTPException(422, "资料分类不正确")
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(415, "仅支持PDF格式的课件和授课文件")
    data = await file.read(MAX_PDF_BYTES + 1)
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "文件内容不是有效PDF")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF文件不得超过80MB")
    FILES.mkdir(parents=True, exist_ok=True)
    stored = FILES / f"{uuid4().hex}.pdf"
    stored.write_bytes(data)
    row = TrainingMaterialRecord(title=title.strip(), category=category, description=description.strip(), original_filename=filename, storage_path=str(stored), file_size=len(data), sha256=hashlib.sha256(data).hexdigest(), created_by=user.user_id)
    db.add(row)
    db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="upload", resource_type="training_material", resource_id=row.id, detail=f"上传PDF资料 {row.title}")
    db.commit()
    db.refresh(row)
    return _material_out(row)


@router.patch("/training-materials/{material_id}")
def update_training_material(material_id: str, payload: MaterialUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    row = db.get(TrainingMaterialRecord, material_id)
    if not row:
        raise HTTPException(404, "未找到培训资料")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="training_material", resource_id=row.id, detail=f"更新PDF资料 {row.title}")
    db.commit()
    db.refresh(row)
    return _material_out(row)


@router.delete("/training-materials/{material_id}", status_code=204)
def delete_training_material(material_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    row = db.get(TrainingMaterialRecord, material_id)
    if not row:
        raise HTTPException(404, "未找到培训资料")
    path = Path(row.storage_path)
    db.delete(row)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="delete", resource_type="training_material", resource_id=material_id, detail=f"删除PDF资料 {row.title}")
    db.commit()
    path.unlink(missing_ok=True)


def _file_response(row: TrainingMaterialRecord, disposition: str):
    path = Path(row.storage_path)
    if not path.is_file():
        raise HTTPException(404, "PDF原文件不存在")
    return FileResponse(path, media_type="application/pdf", filename=row.original_filename, content_disposition_type=disposition)


@router.get("/training-materials/{material_id}/file")
def admin_material_file(material_id: str, download: bool = False, db: Session = Depends(get_db), user: CurrentUser = Depends(_manager)):
    row = db.get(TrainingMaterialRecord, material_id)
    if not row:
        raise HTTPException(404, "未找到培训资料")
    return _file_response(row, "attachment" if download else "inline")


@router.get("/learning/materials")
def learner_materials(db: Session = Depends(get_db), account: LearningAccountRecord = Depends(_learning_user)):
    rows = db.scalars(select(TrainingMaterialRecord).where(TrainingMaterialRecord.status == "active").order_by(TrainingMaterialRecord.created_at.desc()))
    return [_material_out(row) for row in rows]


@router.get("/learning/materials/{material_id}/file")
def learner_material_file(material_id: str, download: bool = False, db: Session = Depends(get_db), account: LearningAccountRecord = Depends(_learning_user)):
    row = db.get(TrainingMaterialRecord, material_id)
    if not row or row.status != "active":
        raise HTTPException(404, "未找到可用培训资料")
    return _file_response(row, "attachment" if download else "inline")
