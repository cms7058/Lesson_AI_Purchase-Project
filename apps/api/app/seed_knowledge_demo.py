from uuid import NAMESPACE_URL, uuid5

from app.core.database import Base, SessionLocal, engine
from app.domain.knowledge import KnowledgeDocumentRecord


def _id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, "pebs-knowledge-demo-v1:" + key))


def seed(db) -> int:
    documents = [
        {
            "key": "toc",
            "title": "【演示】TOC综合采购成本评审规则",
            "domain": "procurement",
            "document_type": "policy",
            "source_name": "采购成本管理制度（演示）",
            "tags": "TOC,询价,定标,质量,交期",
            "content": "TOC评审须在物料、币种、计量单位和数量口径一致的前提下进行。综合成本包括采购价、物流、延期、返工及其他可追溯成本，并扣减退款。历史回归需检查样本量、残差和DOE验证，不得以模型拟合替代业务审批。",
        },
        {
            "key": "emergency",
            "title": "【演示】备件紧急采购与VMI协同指南",
            "domain": "procurement",
            "document_type": "guide",
            "source_name": "MRO采购作业指导书（演示）",
            "tags": "备件,紧急采购,VMI,停机",
            "content": "关键备件紧急采购应记录停机等级、需求时间、最高溢价和备用方案。采用VMI或寄售时必须明确库存所有权、最低保障量、补货响应时间、盘点差异和结算触发点，并将实际领用反馈到库存参数模型。",
        },
        {
            "key": "project",
            "title": "【演示】项目节点偏差与成本预警处置",
            "domain": "project",
            "document_type": "procedure",
            "source_name": "项目管理流程（演示）",
            "tags": "项目,里程碑,延期,成本预警",
            "content": "项目节点出现延期时，应先比较当前计划与已批准基线，识别关键路径和关联采购订单，再由任务负责人提交纠偏日期与影响说明。成本超预算预警必须关联订单、合同或人工成本证据，AI只提供分析与跟踪建议，不自动修改基线。",
        },
        {
            "key": "governance",
            "title": "【演示】AI回答证据与人工确认原则",
            "domain": "shared",
            "document_type": "policy",
            "source_name": "AI治理规范（演示）",
            "tags": "AI,证据,审批,权限",
            "content": "AI回答应标注实时业务数据或知识文档来源。审批、定标、签署、发送、删除和权限变更属于影响性操作，必须由有权限的用户在对应业务页面确认；资料不足时应明确提示缺失字段，不得补造事实。",
        },
    ]
    added = 0
    for item in documents:
        item_id = _id(item["key"])
        if db.get(KnowledgeDocumentRecord, item_id) is None:
            values = {key: value for key, value in item.items() if key != "key"}
            db.add(KnowledgeDocumentRecord(id=item_id, status="active", created_by="demo-manager", **values))
            added += 1
    db.commit()
    return added


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        print({"knowledge_documents_added": seed(session)})
