# AI助力

面向课堂教学和学员实训的智能项目与采购体验平台。系统由 Vue 2.7 管理端、FastAPI 服务和 PostgreSQL 数据库组成，覆盖项目计划、采购申请、询报价、订单履约、MRO、库存、合同、供应商分析和 AI 辅助决策。

## Docker 云端部署

标准入口是根目录的 [`docker-compose.yml`](docker-compose.yml)，首次启动会自动建表并幂等导入带有“【演示】”标识的教学数据：

```bash
cp deploy/docker.env.example .env.docker
# 在 .env.docker 中填写随机 POSTGRES_PASSWORD 和云端域名
docker compose --env-file .env.docker up -d --build
./deploy/check-deployment.sh
```

完整的服务器准备、HTTPS、访问限制、备份和升级方法见 [Docker 部署说明](docs/DOCKER-DEPLOYMENT.md)。`compose.deploy.yml` 保留为兼容入口。

## 本地启动

后端：

```bash
cd apps/api
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd apps/web
npm install
npm run serve
```

访问地址：

- 教学首页：http://localhost:8080
- 采购驾驶舱：http://localhost:8080/procurement-dashboard
- 系统人员管理：http://localhost:8080/personnel
- 课件与考试管理：http://localhost:8080/training-admin
- 学员独立登录入口：http://localhost:8080/learning
- 系统登录页：http://localhost:8080/login（教学管理员默认账号 `admin / admin123456`，公网部署前应通过环境变量修改密码）
- API文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/v1/health

## 当前完成

询价内最低价/TOC定标、按物料供货指标和外部反馈接入使用说明见 [供货分析与数据对接](docs/SUPPLY-ANALYSIS.md)。查看演示询价 `DEMO-FB-RFQ` 时请勾选“包含模拟数据”。独立物料采购成本分析菜单已迁入询价定标。

新增询价在线回标、供应商门户与邮件配置，使用说明及对外部署边界见 [供应商门户说明](docs/SUPPLIER-PORTAL.md)。供应商入口 `/supplier`；请勿直接将开发管理端暴露到公网。

演示数据与本轮测试说明见 [回归检查报告](docs/QA-2026-09-04.md)。运行 `cd apps/api && .venv/bin/python -m app.seed_demo` 可增量导入模拟数据；物料成本分析可查询 `DEMO-MAT-001`。

- 系统模块目录和运行状态接口
- 采购订单创建、查询和金额计算API
- SQLite 开发持久化；生产环境可切换 PostgreSQL
- 演示身份头、采购角色授权与订单/连接器审计日志
- ERP、SRM、QMS、WMS、自定义 API 连接器的配置与查询接口
- 报价结构化录入，支持人工、OCR识别和系统 API 来源标识
- TOC 自动比价：含税货款、物流成本、预期质量损失、交期、服务和成品率综合评标
- 订单、报价单和合同模板的版本化管理；订单模板可根据占位字段自动生成文档预览
- 订单、报价、模板、合同支持创建、分页查询、修改、删除与审计留痕
- 供应商准入与绩效档案、物料标准、工厂收货能力均支持搜索、服务端分页、创建、修改、删除与权限审计
- 采购申请支持多物料明细、预算估算、提交、批准/驳回及自动生成采购订单
- 正式询价项目支持询价范围、合格供应商邀请、发布锁定、报价回标关联和经理定标
- 订单履约支持到货登记、确认收货、质量检验、不合格品退货及状态追踪
- 财务结算支持订单对账、供应商发票验真、付款计划审批和支付确认
- 合同支持模板关联与变更、提交审批、批准/驳回、生效履约、终止及 Word/PDF 文件生成
- 自动化工作流支持报价、订单、合同、采购申请和付款业务对象的流程定义、启停、手动运行及分页审计
- 工作流支持审批、邮件、状态更新、文档生成和 Webhook 步骤；邮件采用发件箱机制，配置 SMTP 后由授权用户确认发送
- 系统连接器已补全搜索、服务端分页、创建、编辑、启停和删除
- 订单可直接选择订单模板；报价和合同通过可审计的单据—模板关联记录绑定对应模板
- AI助手可直接检索工作区实时数据并完成预测校正、寻源、路径优化和报告任务引导；配置兼容接口后可调用大模型，失败时自动回退到本地可验证分析
- Vue管理端导航、驾驶舱、订单录入、AI助手和系统连接器页面
- 需求预测支持线性趋势方程、MAE、未来多期预测，以及结合库存、在途和安全库存的采购建议量
- 外部智能寻源支持候选来源与能力证据录入，以及价格、质量、交付、风险综合排名
- 多工厂路径优化支持产能、需求、线路容量、运输成本、交期和风险约束下的最小费用流计算
- 报告中心可基于实时订单、供应商、合同、收货和质检数据生成采购洞察；审计日志支持服务端分页和筛选
- 物料分类支持三级树形编码（如 `01-01-01`）、物料末级归类及供应商与分类的多对多资质关联
- 分类编码支持自定义每级 1–8 位字母/数字，留空自动生成；树形表按一级分类分页，子级展开；新增物料可逐级选择分类并自动建议流水编码
- 提供非标制造、汽车零部件制造起步分类模板，每套 26 项；导入前预览，同编码同名称跳过，冲突时整批回滚；模板不是官方标准，也不会生成虚构产品档案
- 智能分析 → 物料采购成本分析：按物料、币种检索采购订单、供应商报价、比价快照、收货质检和退货记录，支持供应商筛选及按需分页加载
- 批次成本修正：按订单含税价格计价的收货货款，加物流/返工/延期/其他费用，减退款索赔，再按合格品数量折算单位成本；经理可填写凭证/估算依据，保存或清除修正均有审计记录
- 成本图表区分原始单价、修正合格品成本、供货质量与批次走势；不同币种隔离、不同单位分组，未完成全批质检或价格歧义的批次不纳入核算；结果不替代财务已结算成本
- 比价结果从快照功能上线起留存，后续报价修改不改变历史快照；不存在的旧比价历史不会自动补造
- 人员权限支持管理员、采购经理、采购员、分析员、审计员角色，并可按物料分类和有效期授权采购员
- 系统人员管理新增学员、讲师档案和独立学习账号；密码采用加盐哈希保存，连续失败会临时锁定，停用人员后学习账号同步失效
- 学员可在线完成45分钟计时考试；系统自动评分、保留考试记录，并支持下载空白试卷和个人答题解析PDF
- 教学资料支持PDF上传、发布/归档、在线预览和下载；学员仅能访问已发布资料，Docker部署时原文件随 `/data` 数据卷持久化
- 左侧导航按工作台、采购业务、智能分析、基础资料、系统配置组织为可折叠二级菜单
- 采购驾驶舱、供应商与主数据、采购订单已接入 ECharts 实时聚合图表
- PostgreSQL 持久化与 Docker Compose 云端部署

## M0.2 接口约定

- 身份：开发环境通过 `X-User-Id`、`X-User-Role` 传递。角色包括 `admin`、`procurement_manager`、`buyer`、`analyst`、`auditor`。
- 连接器：`GET/POST /api/v1/data-connectors`。连接器配置只记录地址和同步策略；密钥须由部署环境的密钥管理服务注入。
- 审计：`GET /api/v1/audit-logs`，仅采购经理、管理员或审计员可查看。
- 报价：`GET/POST /api/v1/quotations`，使用 `GET /api/v1/quotations/compare?material_code=...&quantity=...` 生成 TOC 综合比价结果。
- 模板：`GET/POST /api/v1/templates`；使用 `POST /api/v1/templates/{template_id}/render/orders/{order_id}` 按订单数据填充预览。
- 合同：`GET/POST/PATCH/DELETE /api/v1/contracts`，支持合同模板选择与关联留痕。
- 公司标识：`GET/PUT /api/v1/company-profile`，`POST /api/v1/company-profile/logo` 上传 PNG/JPEG Logo。
- 单据导出：`POST /api/v1/documents/{order|quotation|contract}/{id}/export`，传入模板 ID 与 `docx` 或 `pdf` 格式，返回下载地址。
- 供应商：`GET/POST/PATCH/DELETE /api/v1/suppliers`，支持关键词及准入状态筛选。
- 物料和工厂：`GET/POST/PATCH/DELETE /api/v1/materials`、`/api/v1/factories`，提供采购与路径优化所需基础数据。
- 采购申请：`/api/v1/requisitions`，并提供 `submit`、`decision`、`convert-to-order` 状态操作。
- 询价项目：`/api/v1/rfqs`，并提供 `publish`、`responses`、`award` 状态操作。
- 履约：`/api/v1/receipts`、`inspections`、`returns`。
- 结算：`/api/v1/reconciliations`、`invoices`、`payments`。
- 工作流：`/api/v1/workflows`、`workflow-runs`、`notification-outbox`，支持流程执行、审批及邮件发送。
- 需求预测：`/api/v1/forecasts`，支持方案 CRUD、分页检索和重新计算。
- 智能寻源：`/api/v1/sourcing-projects`，支持候选维护和综合评价。
- 路径优化：`/api/v1/routing-plans`，支持方案 CRUD 与最小费用流优化。
- 报告审计：`/api/v1/reports`、`audit-logs`，支持实时报告生成和分页审计查询。
- 物料组织：`/api/v1/material-categories`、`material-category-assignments`、`supplier-category-links`。
- 人员授权：`/api/v1/staff-users`、`buyer-authorizations`，由采购经理或管理员维护。
- 运营图表：`GET /api/v1/analytics/procurement`，提供订单、金额、供应风险、绩效和物料分类聚合数据。
- 物料成本：`GET /api/v1/material-costs/summary`、`GET /api/v1/material-costs/history/{orders|receipts|quotations|comparisons}`；`PUT/DELETE /api/v1/material-costs/receipts/{id}/adjustment` 修正/清除批次附加费用。
- 行业分类：`GET /api/v1/material-categories/industry-templates/{nonstandard|automotive}` 预览；`POST /api/v1/material-categories/import/{industry}` 导入。

### 物料成本浏览器回归

使用隔离数据库 API（不要连接生产库）：

```bash
cd apps/api
DATABASE_URL=sqlite:////tmp/pebs-cost-e2e.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18001
```

前端 8080 启动后，运行 `cd apps/web && node tests/material-costs.e2e.js`。测试浏览器把 API 请求转发到隔离的 18001 端口，验证图表、成本修正、比价快照、分类导入、树形展开、自定义分类编码和物料自动编号，不写入日常业务库。

当前产品规划中的采购业务、AI增强与管理支撑模块均已提供可操作纵向闭环。

### 组合查询与采购状态

新增的字段类型组合查询、订单收货/质量追溯状态联动、当前询价 TOC 模拟批次及测试方法，见 [组合查询使用说明](docs/COMBINED-QUERIES.md)。

供应商门户的接单、分批发货、采购收货及发票上传审核，见 [供应商交付与发票说明](docs/SUPPLIER-EXECUTION.md)。
