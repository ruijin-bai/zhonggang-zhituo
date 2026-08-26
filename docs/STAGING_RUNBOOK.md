# 中港智拓 Persistent Staging Runbook

## 1. 目标

Staging 用于验证“长期运行的系统行为”，不是把 CI 换个名字。

它应能持续保留数据库、对象文件、Redis durable state 和测试邮件，并运行与生产形态一致的 API / Worker / Beat / Web 进程，使以下问题可以被真实发现：

- Worker / Beat 连续运行是否稳定；
- Reminder / Email outbox 是否会按周期推进；
- 数据库 migration、重启和恢复是否安全；
- S3-compatible DocumentStore 是否真实可写；
- 浏览器/BFF/API/数据库链路在进程重启后是否仍正常；
- SMTP delivery adapter 是否真实产生投递结果。

## 2. 拓扑

```text
Browser
  │
  ▼
Web :3001
  │
  ▼
FastAPI
  ├──────── PostgreSQL 17 ── persistent volume
  ├──────── Redis 8 (AOF) ── persistent volume
  ├──────── MinIO (S3) ───── persistent volume
  └──────── Mailpit SMTP ─── persistent volume
              ▲
Worker / Beat ┘
```

Compose 还包含两个 one-shot lifecycle 服务：

- `object-store-init`：确保 `zhituo-staging-documents` bucket 存在；
- `migrate`：每次启动前执行 `alembic upgrade head`。

Demo seed 是显式 lifecycle 步骤，不属于业务服务。

网络分层：

- `backend` 为 `internal` 网络，承载 API 与 PostgreSQL / Redis / MinIO / Mailpit 等内部业务通信；
- `inspection` 只挂载需要通过宿主机 `127.0.0.1` 检查的 PostgreSQL / MinIO / Mailpit / Web，使 loopback 端口真实可达，同时不取消 `backend` 的 internal 隔离；
- `egress` 仅供需要对外访问的 API runtime / Worker / Beat / lifecycle 容器使用。

所有宿主机发布端口仍只绑定 `127.0.0.1`，`inspection` 不等于对公网暴露服务。

## 3. 为什么 `APP_ENV=test`

当前 Staging 是单机、内网测试环境，MinIO 使用 HTTP，Mailpit SMTP 不启用 TLS。API 的 production guardrails 正确禁止生产环境使用这些配置，因此 Staging 明确运行 `APP_ENV=test`，但仍主动开启生产关键边界：

- `DATA_BACKEND=database`
- `DATABASE_RLS_ENABLED=true`
- `JOB_MODE=queue`
- `ALLOW_DEMO_FALLBACK=false`
- `DOCUMENT_STORE_BACKEND=s3`
- durable Worker / Beat
- durable email outbox + real SMTP delivery to Mailpit

这不等于生产部署。正式 Production 仍必须使用 OIDC/trusted proxy、HTTPS S3、TLS SMTP、真实 Secret Manager/KMS 等生产约束。

## 4. 首次启动

要求：Docker Engine + Docker Compose v2。

从仓库根目录执行：

```bash
bash scripts/staging-up.sh
```

如果 `deploy/staging/.env` 不存在，脚本会自动生成随机 PostgreSQL / MinIO 密码并以本地文件保存；该文件被 `.gitignore` 排除。

脚本顺序：

1. 校验 Compose；
2. 从当前 checkout 构建 API / Web 镜像；
3. 启动 PostgreSQL / Redis / MinIO / Mailpit；
4. 创建 S3 bucket；
5. Alembic migration；
6. 默认执行 deterministic demo seed；
7. 启动 API / Worker / Beat / Web；
8. 执行 smoke checks。

若需要保留一套完全不自动 seed 的数据环境：

```bash
ZHITUO_STAGING_SKIP_SEED=true bash scripts/staging-up.sh
```

## 5. 默认入口

- Web: `http://127.0.0.1:3001`
- Mailpit: `http://127.0.0.1:8025`
- MinIO API: `http://127.0.0.1:9000`
- MinIO Console: `http://127.0.0.1:9001`
- PostgreSQL host inspection: `127.0.0.1:55432`

这些端口全部绑定在 `127.0.0.1`，默认不会直接暴露到外网。共享测试机需要通过受控反向代理/VPN 暴露 Web，而不是把数据库、MinIO 或 Mailpit 直接公开。

## 6. Smoke Check

可随时执行：

```bash
bash scripts/staging-smoke.sh
```

当前 smoke 覆盖：

- PostgreSQL `pg_isready`；
- Redis `PING`；
- MinIO liveness；
- Mailpit HTTP API；
- FastAPI dependency-aware `/api/health/ready`；
- Web → BFF → API → PostgreSQL `/pursuit`；
- 从 API 容器通过真实 SMTP 协议向 Mailpit 发送唯一 probe，并在 Mailpit API 中确认邮件实际入箱。

## 7. 停机与数据保留

普通停止：

```bash
bash scripts/staging-down.sh
```

这会停止并删除容器/网络，但保留所有 named volumes。下一次 `staging-up.sh` 会继续使用原数据。

永久清空 staging 数据必须同时给出两层显式意图：

```bash
CONFIRM_PURGE=YES bash scripts/staging-down.sh --purge
```

该操作会删除 PostgreSQL、Redis、MinIO、Mailpit volumes，不可恢复。共享 Staging 在执行 purge 前应先完成 PostgreSQL 和对象存储备份。

## 8. 镜像与升级原则

Staging 默认从当前 checkout 构建：

- `zhituo-api:staging`
- `zhituo-web:staging`

实际共享主机可把 `.env` 中的镜像改为 CI/registry 产出的 immutable digest。每次升级继续先跑 migration，再替换长驻服务。

基础设施镜像应使用明确版本，不使用 `latest`。当前 PostgreSQL/Redis 使用 major-alpine pin；MinIO 使用经典版本明确 tag；Mailpit 使用已修复已知安全问题的 `v1.30.1`。

## 9. Staging Definition of Done

只有同时满足以下条件，才能说“Staging 基础设施代码完成”：

1. Compose config 可由 CI 验证；
2. shell lifecycle scripts 通过 `bash -n`；
3. 一次完整 ephemeral staging smoke 在 CI 中通过；
4. PostgreSQL / Redis / MinIO / Mailpit 均使用 persistent volumes；
5. migration 和 object bucket initialization 可重复执行；
6. API / Worker / Beat / Web 都在 staging topology 中真实启动；
7. browser/API/SMTP/S3 关键边界至少有 smoke evidence。

只有将该 topology 部署到一台持续运行的测试主机后，才能进一步说“Persistent Staging 实例正在运行”。仓库代码完成不等于外部主机已经上线。
