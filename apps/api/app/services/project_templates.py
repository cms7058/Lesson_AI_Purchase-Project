"""Reusable project templates for the teaching project workspace."""


APQP_TEMPLATE_ID = "apqp-exhaust-weld-pipe-v1"


def _requirements() -> list[dict]:
    return [
        {
            "code": "APQP-1",
            "phase": "项目策划与客户需求",
            "gate": "策划评审门",
            "deliverables": ["客户特殊要求", "项目任务书", "质量目标", "初始风险清单"],
            "criteria": ["订单、产品范围和交付节点已确认", "CC/SC特殊特性完成初步识别"],
            "evidence": ["客户图纸/技术协议", "评审纪要", "项目质量目标"],
            "metrics": ["客户要求覆盖率", "初始风险关闭率"],
        },
        {
            "code": "APQP-2",
            "phase": "产品设计开发",
            "gate": "设计冻结门",
            "deliverables": ["产品图纸", "材料规范", "DFMEA", "设计评审记录"],
            "criteria": ["设计输出满足客户要求", "关键尺寸和焊接特性已纳入DFMEA"],
            "evidence": ["受控图纸", "DFMEA版本", "设计评审签字"],
            "metrics": ["DFMEA高风险项关闭率", "设计变更响应周期"],
        },
        {
            "code": "APQP-3",
            "phase": "过程设计开发",
            "gate": "过程准备门",
            "deliverables": ["过程流程图", "PFMEA", "控制计划", "工装/检具清单"],
            "criteria": ["PFMEA与控制计划逐项关联", "焊接参数、气密性和尺寸检测方法已定义"],
            "evidence": ["过程流程图", "PFMEA版本", "控制计划", "检具校验记录"],
            "metrics": ["PFMEA高风险项关闭率", "控制计划覆盖率"],
        },
        {
            "code": "APQP-4",
            "phase": "产品与过程验证",
            "gate": "试制放行门",
            "deliverables": ["试制报告", "MSA", "初始过程能力", "尺寸/材料/性能报告"],
            "criteria": ["关键特性完成测量系统确认", "Cp/Cpk达到项目目标", "泄漏/压力测试合格"],
            "evidence": ["MSA报告", "Cp/Cpk分析", "首件检验报告", "焊缝和气密性记录"],
            "metrics": ["Cp", "Cpk", "首件一次合格率", "泄漏不良率"],
        },
        {
            "code": "APQP-5",
            "phase": "反馈、评估与持续改进",
            "gate": "量产移交门",
            "deliverables": ["量产问题清单", "纠正预防措施", "经验教训", "客户反馈闭环"],
            "criteria": ["遗留高风险问题有责任人和期限", "客户问题完成验证关闭"],
            "evidence": ["8D/纠正措施", "客户反馈", "量产审核记录"],
            "metrics": ["问题按期关闭率", "客户投诉响应时间", "首批量产合格率"],
        },
        {
            "code": "PPAP",
            "phase": "PPAP提交与批准",
            "gate": "PPAP批准门",
            "deliverables": ["PSW", "设计记录", "过程流程图", "PFMEA", "控制计划", "MSA", "能力研究", "样件与检验结果", "客户批准"],
            "criteria": ["提交等级和客户特殊要求已确认", "PPAP资料包完整且版本一致", "PSW获得客户批准"],
            "evidence": ["PPAP资料包", "PSW签署版", "客户批准/特采记录"],
            "metrics": ["PPAP资料完整率", "PPAP一次批准率", "客户批准周期"],
        },
    ]


def _tasks() -> list[dict]:
    phases = [
        ("apqp-1", "APQP 1｜项目策划与客户需求", "APQP-1"),
        ("apqp-2", "APQP 2｜产品设计开发", "APQP-2"),
        ("apqp-3", "APQP 3｜过程设计开发", "APQP-3"),
        ("apqp-4", "APQP 4｜产品与过程验证", "APQP-4"),
        ("apqp-5", "APQP 5｜反馈评估与持续改进", "APQP-5"),
        ("ppap", "PPAP｜提交、评审与客户批准", "PPAP"),
    ]
    tasks = []
    for index, (phase_id, name, code) in enumerate(phases):
        tasks.append({
            "id": phase_id,
            "name": name,
            "kind": "work_package",
            "parent_id": None,
            "owner_id": None,
            "start": None,
            "finish": None,
            "progress": 0,
            "predecessors": [phases[index - 1][0]] if index else [],
            "source": f"APQP模板/{code}",
            "apqp_stage": code,
        })
    detail = [
        ("apqp-1", "确认客户图纸、技术协议与特殊要求", "APQP-1"),
        ("apqp-1", "建立项目质量目标与初始风险清单", "APQP-1"),
        ("apqp-2", "完成产品设计记录与材料规范评审", "APQP-2"),
        ("apqp-2", "完成DFMEA并关闭高风险项目", "APQP-2"),
        ("apqp-3", "建立焊管过程流程图与工艺参数表", "APQP-3"),
        ("apqp-3", "完成PFMEA并关联控制计划", "APQP-3"),
        ("apqp-3", "确认工装、检具和测量设备准备状态", "APQP-3"),
        ("apqp-4", "完成试制并记录焊缝、尺寸和气密性结果", "APQP-4"),
        ("apqp-4", "完成MSA与Cp/Cpk初始过程能力分析", "APQP-4"),
        ("apqp-4", "完成产品性能和材料检验报告", "APQP-4"),
        ("apqp-5", "建立量产问题与纠正措施闭环", "APQP-5"),
        ("apqp-5", "完成客户反馈和经验教训回顾", "APQP-5"),
        ("ppap", "整理PPAP资料包并执行版本一致性检查", "PPAP"),
        ("ppap", "完成PSW提交、客户评审和批准记录", "PPAP"),
    ]
    previous = {}
    for index, (parent_id, name, code) in enumerate(detail, start=1):
        task_id = f"apqp-task-{index:02d}"
        tasks.append({
            "id": task_id,
            "name": name,
            "kind": "task",
            "parent_id": parent_id,
            "owner_id": None,
            "start": None,
            "finish": None,
            "progress": 0,
            "predecessors": [previous[parent_id]] if parent_id in previous else [],
            "source": f"APQP模板/{code}",
            "apqp_stage": code,
        })
        previous[parent_id] = task_id
    return tasks


def apqp_template() -> dict:
    requirements = _requirements()
    return {
        "id": APQP_TEMPLATE_ID,
        "name": "汽车排气管焊管 APQP→PPAP 质量项目",
        "description": "适用于汽车排气管焊管行业，从客户需求策划、设计与过程开发、试制验证到PPAP客户批准。新建后所有任务、交付物和阶段门禁均可修改。",
        "project_type": "apqp_exhaust_weld_pipe",
        "tasks": _tasks(),
        "quality_requirements": requirements,
        "gate_count": len(requirements),
    }


def list_templates() -> list[dict]:
    return [apqp_template()]
