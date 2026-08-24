## 变更目标

<!-- 用 1-3 句话说明这个 PR 解决什么问题，避免同时扩大多个主线。 -->

## 影响范围

- [ ] Web / BFF
- [ ] API / Worker / Beat
- [ ] Database / Alembic
- [ ] Tenant / RBAC / RLS
- [ ] Async / retry / idempotency
- [ ] External connector / notification
- [ ] Deployment / operations
- [ ] Documentation only

## 生产边界自检

- [ ] 数据事实源和权威边界没有被模糊或复制
- [ ] 新增/修改写操作已考虑权限、幂等和并发
- [ ] 新表/查询已考虑 Organization 隔离与 PostgreSQL RLS
- [ ] 外部网络 I/O 不持有不必要的数据库长事务
- [ ] 失败、重试、stale worker / stale claim 行为明确
- [ ] 迁移可从 clean database 升级，并考虑回滚/兼容窗口
- [ ] 日志、审计、指标或运维查询足以定位故障
- [ ] Demo/测试数据不会静默进入 production 事实链

## 验证

- [ ] 新行为有自动化测试或明确说明为什么不需要
- [ ] 相关回归测试已覆盖
- [ ] Web TypeScript / production build 通过（如适用）
- [ ] API tests / PostgreSQL RLS tests 通过（如适用）
- [ ] production image / compose 验证通过（如适用）
- [ ] `zhituo/ci-gate` 全绿后再合并

## 风险与回滚

<!-- 写出最主要的失败方式，以及出现问题时如何关闭功能、回退代码或恢复数据。 -->

## 后续工作

<!-- 明确不属于本 PR 的内容，防止 scope creep。 -->
