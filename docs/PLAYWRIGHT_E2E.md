# Browser E2E Gate

## 目标

Playwright 用真实浏览器覆盖智拓最关键的 Pursuit 协同黄金路径，验证浏览器 → Next.js/BFF → FastAPI → PostgreSQL 的完整写入与读取链路，而不是只做页面 200 smoke test。

## 当前黄金路径

固定 Demo 机会：`west-africa-port-access-corridor`。

测试步骤：

1. 以 `admin@zhituo.local` 进入 Pursuit Workspace；
2. 验证 canonical workspace 已加载；
3. 创建新的 Work Item；
4. 指派给真实 Demo Membership `智拓管理员 · admin`；
5. 设置 high priority；
6. 等待后端持久化并在 Workspace 中回显；
7. 跳转 My Work；
8. 验证当前用户能看到刚创建的 Work Item。

该测试覆盖真实 PostgreSQL、真实 FastAPI、真实 Next.js production build 与浏览器交互。

## CI 运行环境

`e2e` job 在独立 PostgreSQL 17 + Redis 服务中运行：

- Alembic upgrade 到 head；
- 执行 repeatable demo seed；
- 启动 FastAPI；
- 安装 Chromium；
- production build 并启动 Next.js；
- 执行 Playwright；
- 失败时保留 screenshot / trace / video 以及 API/Web server logs。

`zhituo/ci-gate` 依赖 `e2e`，因此黄金路径失败会阻断 `main` 合并。

## 本地运行

需要本地 PostgreSQL、Redis、API 和 Web 已按 test/development-header 环境启动，然后：

```bash
npm ci
npx playwright install chromium
npm --workspace apps/web run test:e2e
```

可通过环境变量覆盖：

- `E2E_BASE_URL`
- `E2E_USER_EMAIL`

## 维护原则

- 只保留少量高价值黄金路径，避免把整个 UI 回归测试全部塞入 required gate；
- 优先验证真实跨层业务闭环；
- 测试失败必须保留可诊断 Artifact；
- Demo seed 必须稳定、幂等，不允许依赖人工预置数据库；
- 后续扩展优先覆盖 Candidate review → Opportunity 和 Gate decision 两条核心路径。
