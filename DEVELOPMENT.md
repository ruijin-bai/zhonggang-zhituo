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

也可以在首次开发时执行 `zhituo-api init-db` 快速建表并 seed；正式迁移流程以 Alembic 为准。

健康检查：`GET http://127.0.0.1:8000/health`

## 3. AI 模型

AI 是可选增强，不是系统单点故障。

在 `.env` 配置：

```bash
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL_EXTRACTION=gpt-5.6-luna
AI_MODEL_ANALYSIS=gpt-5.6-terra
```

配置后，来源抽取和项目研判优先走 Responses-compatible Structured Output；模型调用失败或未配置密钥时，会自动退回确定性规则/模板化研判。

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
