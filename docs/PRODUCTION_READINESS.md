# 中港智拓生产就绪基线

> 本文档将智拓的建设目标从“比赛可演示”提升为“可部署、可运维、可审计、可扩展的生产级海外市场经营系统”。比赛 Demo 只是生产系统的一种演示模式，不再反向决定架构。

## 1. 生产级定义

智拓达到生产级，不等于“页面能打开、接口能返回”。至少需要同时满足：

- **可部署**：环境配置明确，应用、数据库、Redis、Worker 可独立部署和扩缩容；
- **可升级**：所有数据库变更通过 Alembic 管理，升级和回滚路径明确；
- **可恢复**：数据库与关键配置有备份、恢复和灾难演练机制；
- **可观测**：有 liveness、readiness、结构化日志、错误追踪和关键业务指标；
- **可审计**：关键写操作有操作者、组织、对象、时间、请求和变更记录；
- **可隔离**：组织、用户、角色和数据访问边界不可依赖前端约定；
- **可降级**：AI、外网或单个来源异常不能破坏已写入的 Source / Evidence / Opportunity；
- **可验证**：CI 必须覆盖编译、依赖、测试、真实数据库迁移和关键运行依赖；
- **可安全运行**：生产环境禁止 Demo fallback、开发身份、默认凭据和同步长任务。

## 2. 当前已具备

- FastAPI + PostgreSQL + Redis + Celery 架构；
- Alembic 数据迁移；
- Opportunity / Source / Evidence / Snapshot / Event / Audit 等业务状态；
- Draft 人工确认、评分规则、证据置信度和 Unknown 机制；
- 角色权限与组织维度基础；
- 长任务 Queue 模式与生产环境强制约束；
- Demo 与生产配置隔离；
- CI：Web check/build、API pytest；
- CI 增强：PostgreSQL 17、Redis 8、Alembic clean migration、pip check、compileall、Redis ping、repeatable demo seed；
- `/api/health/live`：进程存活探针；
- `/api/health/ready`：数据库及 Queue 模式 Redis 就绪探针。

## 3. 生产化优先级

### P0｜上线阻断项

1. **真实身份认证**：OIDC / 企业 SSO / 可信网关，不允许生产依赖 `X-Zhituo-User` 或开发邮箱模拟身份；
2. **多租户强隔离**：所有 Opportunity、Evidence、Source、Draft、Action、Alert、Strategy 查询和写入必须强制 Organization scope；
3. **Secrets 管理**：数据库、Redis、AI Key 只通过部署平台 Secret/KMS 注入，不进入仓库或镜像；
4. **生产容器镜像**：Web/API/Worker 独立 Dockerfile，多阶段构建、非 root 用户、固定启动命令；
5. **数据库备份恢复**：明确 RPO/RTO，建立定期备份、恢复验证和迁移前备份；
6. **请求与任务幂等性**：商机确认、情报入库、自动重评、Job 提交避免重复请求造成重复记录；
7. **可观测性**：结构化日志、request_id/correlation_id、错误追踪、Worker 失败率和 Job latency；
8. **安全头与流量边界**：TLS 终止、反向代理、请求体限制、速率限制、CORS 精确白名单；
9. **CI/CD 门禁**：main 禁止跳过 CI，迁移失败、测试失败、镜像构建失败不得部署。

### P1｜稳定运营

1. Dependency lock / 自动依赖更新与漏洞扫描；
2. SLO：API 可用性、P95/P99 延迟、Queue 等待时间、AI 调用失败率；
3. 数据质量监控：重复项目、Evidence 缺失、异常评分变化、低置信度自动重评拦截；
4. Worker 重试策略、Dead Letter / 失败任务人工恢复；
5. 数据保留与归档策略；
6. 组织级权限管理 UI；
7. 操作审计查询与导出；
8. 零停机或低停机数据库迁移规范。

### P2｜企业级扩展

- 企业知识库 / 历史项目数据接入；
- 国家、区域、客户、竞争对手主数据治理；
- 多语言与跨区域运营；
- 企业消息、邮件、CRM/OA 集成；
- 模型路由、成本治理、Prompt/Schema 版本管理；
- 高可用 PostgreSQL / Redis 与多实例 Worker；
- 灾备环境与跨区域恢复。

## 4. 生产环境强制配置

至少：

```bash
APP_ENV=production
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
DATA_BACKEND=database
JOB_MODE=queue
DATABASE_URL=postgresql+psycopg://<secret>@<production-db>/zhituo
REDIS_URL=redis://<production-redis>:6379/0
CORS_ORIGINS=https://<official-domain>
```

生产环境不得使用：

- 默认数据库密码；
- localhost 数据库/Redis；
- Demo 数据自动回退；
- 开发身份模拟；
- API 进程内执行网页抓取和 AI 长任务；
- 未经迁移工具管理的数据库结构变化。

## 5. 部署健康检查

Kubernetes / ECS / Docker 平台应分别使用：

- Liveness：`GET /api/health/live`
- Readiness：`GET /api/health/ready`

Readiness 在 Queue 模式下同时检查 PostgreSQL 和 Redis。依赖异常时实例应停止接收新流量，但不应被错误判定为进程死亡并无限重启。

## 6. CI 作为上线门禁

当前 CI 已开始从“单测流水线”升级为部署前验证：

1. Web TypeScript check；
2. Web production build；
3. Python editable install；
4. `pip check`；
5. Python bytecode compile；
6. 在全新 PostgreSQL 17 上执行 `alembic upgrade head`；
7. Redis 8 实例连通性；
8. pytest；
9. `reset-demo` / CLI smoke check。

后续继续增加：镜像构建、迁移 downgrade/upgrade 验证、依赖漏洞扫描、集成 API smoke test。

## 7. 当前原则

从现在起：

> **任何为了比赛方便而加入的能力，都必须明确隔离在 Demo/Development 模式；任何会进入生产路径的设计，都按真实企业系统的失败模式来评审。**

比赛仍然使用英雄案例和离线容错，但不能以牺牲生产数据可信度、安全边界或系统可维护性为代价。
