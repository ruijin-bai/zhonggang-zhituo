# 中港智拓仓库治理基线

## 1. 目标

智拓已经进入 Production Alpha，中后续变更不再以“能运行”为唯一合并条件。仓库治理必须确保：主线不可绕过自动门禁、PR 范围可审查、生产边界可追溯、失败可回滚。

## 2. `main` 分支保护

GitHub `main` 应启用 Repository Ruleset，并至少设置：

1. 禁止直接 push 到 `main`；
2. 所有变更通过 Pull Request；
3. 合并前必须通过 required status check：`zhituo/ci-gate`；
4. 合并前要求分支与 `main` 保持最新，避免基于过期基线合并；
5. 不配置常态 bypass；
6. 禁止删除 `main` 和 force push；
7. 只允许 squash merge，并要求 linear history；
8. 单人开发阶段 required approvals 为 0，但 PR review conversation 必须解决。

仓库提供幂等配置脚本，第一次执行会创建同名 Ruleset，后续执行会更新它：

```bash
gh auth login
bash scripts/configure-github-ruleset.sh
```

也可以显式指定仓库：

```bash
bash scripts/configure-github-ruleset.sh ruijin-bai/zhonggang-zhituo
```

脚本会先检查：GitHub CLI 登录状态、仓库 Administration 权限、默认分支，以及 `zhituo/ci-gate` 是否真实出现在当前默认分支提交状态中。只有预检通过才会创建或更新 `main-production-protection`，避免因状态名拼错把主分支锁死。

可通过环境变量覆盖默认值：

```bash
RULESET_NAME=main-production-protection \
REQUIRED_CHECK=zhituo/ci-gate \
bash scripts/configure-github-ruleset.sh
```

## 3. PR 规模与审查规则

每个 PR 只解决一个清晰主题。以下情况应拆分：

- 同时修改核心数据模型和无关 UI；
- 同时引入多个外部系统；
- 同时进行大规模重构和业务功能扩展；
- CI 暴露历史问题后继续扩大功能范围。

PR 描述必须说明：目标、事实边界、权限/租户影响、失败路径、验证方式、回滚方式、明确不做的内容。

## 4. 自动门禁

`zhituo/ci-gate` 是主线唯一 required status check，对下列工作汇总负责：

- Web 类型检查与 production build；
- Python Ruff correctness/import lint；
- API unit / integration / PostgreSQL RLS tests；
- API coverage，当前首版 fail-under 为 69%；
- clean migration 与 latest downgrade/re-upgrade；
- runtime / backup 数据库最小权限；
- PostgreSQL backup / restore drill；
- production Compose 与 API/Web image build；
- Python/Web 依赖安全审计与 SBOM。

后续按独立 PR 增加：

- Playwright 黄金 E2E；
- coverage 逐步抬升；
- container CVE scan；
- secret scanning / SAST；
- release / staging smoke gate。

## 5. 合并纪律

只有同时满足以下条件才允许合并：

1. PR scope 已冻结；
2. 所有必要自动化测试已增加或更新；
3. `zhituo/ci-gate` 成功；
4. 没有未解释的数据迁移、租户隔离或失败恢复风险；
5. Roadmap / Runbook / Deployment Contract 等受影响文档已同步；
6. 已明确下一步，而不是在同一 PR 中继续横向扩张。

## 6. Production Alpha 当前开发节奏

从本基线开始，优先级从“快速增加功能”切换为：

```text
Repository Governance
→ Quality Gates
→ Browser E2E
→ Staging
→ Golden Dataset / Evaluation
→ Pilot
→ Enterprise Connectors / Outcome Loop
```

在真实 Staging 和业务评测形成稳定证据前，原则上不优先引入 Vector DB、通用 RAG、多 Agent、微服务拆分或额外通知渠道。
