# 本地开发

## 1. Web

```bash
npm install
npm run dev:web
```

打开 `http://localhost:3000`。

Web 在只读 API 不可用时会自动退回内置 Demo 数据，因此总览、机会池和详情页可单独浏览。情报导入属于写操作，需要同时启动 API。

## 2. PostgreSQL + API

```bash
docker compose up -d db
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
zhituo-api seed
uvicorn app.main:app --reload --port 8000
```

首次演示时，数据库中的英雄项目会刻意初始化为 **72/B**。打开 `/intelligence` 导入预置的 S 级融资与采购情报后，评分引擎才会真正把它重评为 **81/A**，并持久化 Evidence、ScoreSnapshot 和 Event。

如之前已 seed 过最终态 Demo，建议重建本地演示数据库后重新执行迁移与 seed。

## 3. AI 模型

AI 是可选增强，不是系统单点故障。模型名不在仓库中硬编码，请按实际可用的 Responses-compatible 模型配置：

```bash
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL_EXTRACTION=<your-structured-output-model>
AI_MODEL_ANALYSIS=<your-analysis-model>
```

配置后，来源抽取和项目研判优先走 Responses-compatible Structured Output；模型调用失败、未配置密钥或未配置模型时，会自动退回确定性规则/模板化研判。

## 4. 当前可验证路径

- `/`：经营总览
- `/opportunities`：机会池
- `/opportunities/west-africa-port-access-corridor`：英雄项目详情
- `/intelligence`：来源抽取、Evidence 绑定、自动重评入口
- API `/api/sources/ingest`
- API `/api/opportunities/{id}/analyze`

## 5. 自动重评安全阈值

只有同时满足以下条件，来源事实才允许自动修改评分：

1. 来源等级为 S 或 A；
2. 对应 fact 有 `score_hint`；
3. 抽取置信度 ≥ 0.80；
4. 字段属于既定 8 个评分维度。

否则来源只保存为 Evidence，不自动改变经营等级。

## 6. 工程原则

- Demo 数据必须标识 `is_demo=true`，不得伪装成真实项目；
- 分数由规则引擎计算，AI 不直接覆盖总分；
- AI 输出使用 JSON Schema 约束；
- 关键事实绑定 Source / Evidence；
- ScoreSnapshot 与 OpportunityEvent 保留历史变化；
- 比赛现场必须允许 AI 服务异常时完成主链路演示。
