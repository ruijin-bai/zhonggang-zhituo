# 本地开发

## 1. Web

```bash
npm install
npm run dev:web
```

打开 `http://localhost:3000`。

Web 在 API 不可用时会自动退回内置 Demo 数据，因此可单独启动并浏览核心页面。

## 2. API

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

健康检查：`GET http://127.0.0.1:8000/health`

## 3. PostgreSQL

```bash
docker compose up -d db
```

当前 v0.1 API 为了保证首轮工程基线稳定，默认读取 `data/demo/opportunities.json`；SQLAlchemy 数据模型已经建立，下一阶段完成迁移和 seed 后切换为 PostgreSQL Repository。

## 4. 当前可验证路径

- `/`：经营总览
- `/opportunities`：机会池
- `/opportunities/west-africa-port-access-corridor`：72 → 81 英雄项目详情
- API `/api/opportunities`
- API `/api/opportunities/{id}`
- API `/api/opportunities/{id}/score`
- API `/api/opportunities/{id}/analyze`

## 5. 工程原则

- Demo 数据必须标识 `is_demo=true`，不得伪装成真实项目；
- 分数由规则引擎计算，AI 不直接篡改分数；
- AI 接口先固定 Structured Output 契约，再接具体模型；
- 关键事实后续必须绑定 Evidence；
- 评分历史必须保留，支持解释项目为何发生变化。
