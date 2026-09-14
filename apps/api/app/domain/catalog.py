from pydantic import BaseModel


class ModuleDefinition(BaseModel):
    code: str
    name: str
    description: str
    route: str
    phase: int
    status: str = "planned"


MODULES = [
    ModuleDefinition(code="assistant", name="AI采购助手", description="查数、分析、修正、优化与报告生成", route="/assistant", phase=1, status="active"),
    ModuleDefinition(code="data", name="数据与API接入", description="文件导入、系统连接器、映射和同步审计", route="/data-sources", phase=1, status="active"),
    ModuleDefinition(code="rfqs", name="询价项目与回标", description="询价附件、供应商在线报价、自动回标与定标", route="/rfqs", phase=1, status="active"),
    ModuleDefinition(code="mail-settings", name="邮件发送设置", description="SMTP配置、询价发布自动通知及失败重试", route="/mail-settings", phase=1, status="active"),
    ModuleDefinition(code="orders", name="采购订单", description="创建、审批、发送、变更和履约跟踪", route="/orders", phase=1, status="active"),
    ModuleDefinition(code="requisitions", name="采购申请与审批", description="需求申请、预算估算、提交审批与订单转换", route="/requisitions", phase=1, status="active"),
    ModuleDefinition(code="fulfillment", name="收货质检与退货", description="到货登记、质量检验、不合格品退货", route="/fulfillment", phase=1, status="active"),
    ModuleDefinition(code="settlements", name="对账发票与付款", description="订单对账、发票验真、付款审批与支付", route="/settlements", phase=1, status="active"),
    ModuleDefinition(code="templates", name="业务模板中心", description="订单、报价与合同模板及字段填充", route="/templates", phase=1, status="active"),
    ModuleDefinition(code="workflows", name="自动化工作流", description="报价、订单、合同签署与邮件通知", route="/workflows", phase=2, status="active"),
    ModuleDefinition(code="forecast", name="需求预测", description="需求预测、采购建议与情景模拟", route="/forecast", phase=2, status="active"),
    ModuleDefinition(code="sourcing", name="智能寻源", description="外部候选发现、匹配、准入与风险", route="/sourcing", phase=2, status="active"),
    ModuleDefinition(code="suppliers", name="供应商管理", description="供应商质量、交付与服务绩效分析及档案管理", route="/suppliers", phase=1, status="active"),
    ModuleDefinition(code="materials", name="三级物料管理", description="三级分类自动编号、物料归类与供方能力关联", route="/materials", phase=1, status="active"),
    ModuleDefinition(code="personnel", name="人员与采购权限", description="角色管理与采购员分类有效期授权", route="/personnel", phase=1, status="active"),
    ModuleDefinition(code="routing", name="多工厂路径优化", description="供货分配、路线优化与中断重算", route="/routing", phase=3, status="active"),
    ModuleDefinition(code="contracts", name="合同管理", description="合同建档、模板关联、审批与履约", route="/contracts", phase=1, status="active"),
    ModuleDefinition(code="reports", name="报告与审计", description="报告中心、通知、审批和全链路留痕", route="/reports", phase=1, status="active"),
]
