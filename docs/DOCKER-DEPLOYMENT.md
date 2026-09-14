# AI助力 Docker 云端部署

本方案用于单台云服务器上的教学演示环境。容器包含 Nginx/Vue、FastAPI、项目通知任务和 PostgreSQL；数据库、生成文档、附件及邮件密钥均使用 Docker 卷持久化。数据库和 API 不直接发布到宿主机。

> 当前管理端使用教学身份请求头，不是真实的用户登录认证。公网课堂环境必须在云防火墙限制学员来源 IP，或在前置 HTTPS 网关增加统一身份认证/访问密码。不要把它当作正式生产采购系统直接对公众开放。

## 1. 服务器准备

建议配置为 2 核 CPU、4 GB 内存、30 GB 可用磁盘，安装 Docker Engine 24+ 与 Docker Compose v2。将项目上传到服务器后，在根目录执行：

```bash
cp deploy/docker.env.example .env.docker
chmod 600 .env.docker
openssl rand -hex 32
```

把随机字符串写入 `POSTGRES_PASSWORD`。示例配置：

```dotenv
POSTGRES_PASSWORD=替换为随机十六进制密码
WEB_BIND_ADDRESS=0.0.0.0
WEB_PORT=8080
WEB_ORIGINS=https://training.example.com
IMAGE_TAG=2026.09
SEED_DEMO_DATA=true
LLM_PROVIDER=disabled
```

- 直接通过云服务器 IP 体验时，开放 TCP 8080，并把来源限制为课堂公网 IP。
- 使用域名时，让 HTTPS 网关转发到 `127.0.0.1:8080`，同时把 `WEB_BIND_ADDRESS` 改为 `127.0.0.1`。
- 接入大模型时填写 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`；密钥文件不得提交到仓库。`AI_ASSIST_SECRET_KEY` 可留空，系统会在持久卷中自动生成邮件配置加密密钥。

### 可选的 MinerU PDF 识别

项目资料导入支持调用自托管 [MinerU](https://github.com/opendatalab/MinerU) 的同步 `/file_parse` 接口。MinerU 应作为独立服务部署，不放入本项目默认 Compose：官方推荐的完整解析环境需要明显高于本教学平台的内存和磁盘资源，CPU pipeline 也建议至少准备 16GB 内存。

在“系统与知识库 → 数据与API”中新建 `MinerU PDF解析` 连接器，填写服务根地址或 `/file_parse` 地址，保存后再次编辑为“已启用”。也可以用以下容器环境变量作为后备配置：

```dotenv
MINERU_BASE_URL=http://host.docker.internal:8001
MINERU_API_KEY=
MINERU_BACKEND=pipeline
MINERU_TIMEOUT_SECONDS=120
```

数据库中已启用的 MinerU 连接器优先于 `MINERU_BASE_URL`。本系统提交 `parse_method=auto`、中文 OCR、表格和公式识别，并读取返回的 `md_content`；失败时只对可检索 PDF 尝试本地文本回退。敏感合同应使用企业自托管 MinerU，避免把文件发送到未经批准的第三方服务。所有结果只生成待核对的项目草稿。

## 2. 构建和启动

```bash
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps -a
docker compose --env-file .env.docker logs --tail=120 db-init api web
BASE_URL=http://127.0.0.1:8080 ./deploy/check-deployment.sh
```

`db-init` 成功后显示 `Exited (0)` 属于正常状态。它会建表，并在 `SEED_DEMO_DATA=true` 时导入演示数据；脚本使用固定 ID，重复启动不会重复插入或覆盖用户数据。随后 API、项目通知任务和 Web 服务自动启动。

访问入口：

- `/`：AI助力教学首页
- `/procurement-dashboard`：采购驾驶舱
- `/project-dashboard`：项目驾驶舱
- `/supplier`：供应商体验端
- `/api/v1/ready`：数据库就绪检查

## 3. 教学环境说明

演示资料的编号以 `DEMO-` 开头，名称含“【演示】”；邮件地址使用不可投递示例域。学员可在共享数据集上完成查询、创建、修改与分析操作。多人同时上课时建议每个班级部署独立实例，避免不同班级互相修改数据。

如需空库，把 `.env.docker` 中的 `SEED_DEMO_DATA` 改为 `false` 后首次启动。已有卷不会因为修改该值而删除数据。清理或重置课堂数据前必须先备份，且不要在教学进行中执行。

## 4. HTTPS 与网络

推荐使用云厂商负载均衡、Nginx Proxy Manager、Traefik 或已有网关终止 HTTPS，并把流量转发到本机端口。网关至少应具备：

- TLS 证书与 HTTP 自动跳转 HTTPS；
- 课堂访问密码、单点登录或来源 IP 白名单；
- 上传体积限制不低于 12 MB；
- `/api/` 与 `/files/` 使用同一域名转发；
- WebSocket 无要求，但 API 长请求超时建议不低于 65 秒。

云安全组不要开放 5432 和 8000。外部 ERP/MES/WMS API、SMTP 与大模型调用需要允许服务器出站访问；连接器中的 `localhost` 指向容器自身，不能代表外部业务系统。

## 5. 数据持久化与备份

`postgres_data` 保存数据库，`app_data` 保存生成的 Word/PDF、公司 Logo、询价/报价附件、供应商发票和邮件密钥。备份前暂停写入：

```bash
mkdir -p backups
chmod 700 backups
docker compose --env-file .env.docker stop web api project-worker
docker compose --env-file .env.docker exec -T postgres pg_dump -U aiassist -d ai_assist -Fc > backups/database.dump
docker compose --env-file .env.docker run --rm --no-deps api tar czf - -C /data . > backups/files.tar.gz
docker compose --env-file .env.docker start api web project-worker
chmod 600 backups/database.dump backups/files.tar.gz
```

将备份复制到服务器之外并使用日期命名。恢复必须先在隔离实例验证。不要执行 `docker compose down -v`，该命令会删除数据库与文件卷；普通 `down` 和重新构建不会删除卷。

## 6. 升级与验收

升级前备份，修改 `IMAGE_TAG` 后重新构建。镜像回滚不等于数据库回滚；涉及表结构的版本应配套迁移脚本。

课堂发布前至少检查：

1. 首页、采购驾驶舱、项目驾驶舱和供应商入口可打开，刷新子路由不出现 404；
2. `db-init` 成功退出，API 与 Web 健康检查为 `healthy`；
3. 演示物料、供应商、询价和订单可见；
4. 列表增删改查、分页、附件上传、Word/PDF 生成可用；
5. RFQ 的 DOE/TOC、路线优化和图表可以展示；
6. 重建容器后数据库、附件与生成文档仍然存在；
7. HTTPS、课堂访问限制、备份和日志轮转已生效。

本地开发机如果没有安装 Docker，只能完成 Compose 静态校验和原生前后端测试；镜像构建、PostgreSQL 容器启动、卷重建及 HTTPS 验收必须在安装 Docker 的目标服务器执行。
