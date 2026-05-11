# Cosmetic AI Agent

基于开源 LLM + 医美知识库的智能咨询 Agent。

> 文档：
> - [设计文档](./docs/design.md)
> - [实施路线图](./docs/roadmap.md)

## 技术栈

- **后端**：FastAPI + LangGraph + LlamaIndex
- **LLM**：DeepSeek V4（主） / Qwen2.5（辅）
- **存储**：PostgreSQL + pgvector / Redis
- **可观测**：Langfuse
- **前端**：Next.js 14 + Vercel AI SDK

---

## Phase 0：本地基础设施

### 前置要求

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（含 Docker Compose v2）
- 可用磁盘 ≥ 5GB
- Windows 用户需启用 WSL2

### 启动步骤

```bash
# 1) 复制环境变量示例
cp .env.example .env

# 2) （可选）按需修改 .env 中的密码 / 端口

# 3) 启动全部基础设施
docker compose up -d

# 4) 查看状态
docker compose ps

# 5) 查看日志
docker compose logs -f langfuse
```

### 服务地址

| 服务      | 地址                       | 说明                      |
|-----------|----------------------------|---------------------------|
| PostgreSQL| `localhost:5432`           | 业务数据 + 向量库         |
| Redis     | `localhost:6379`           | 缓存 / 限流               |
| Langfuse  | http://localhost:3000      | LLM 监控（首次访问需注册）|

### 验证

```bash
# Postgres：进入容器执行 psql，确认 pgvector 已启用
docker exec -it cosmetic-postgres psql -U cosmetic -d cosmetic -c "\dx"

# Redis：ping
docker exec -it cosmetic-redis redis-cli ping
```

预期：
- Postgres 输出包含 `vector` 扩展
- Redis 返回 `PONG`
- 浏览器访问 http://localhost:3000 看到 Langfuse 登录页

### 关停 / 清理

```bash
# 停止容器（保留数据）
docker compose stop

# 删除容器（保留数据卷）
docker compose down

# 彻底清理（含数据卷，谨慎！）
docker compose down -v
```

---

## 项目结构

```
Q:/Cosmetic/
├── docker-compose.yml          # 基础设施编排
├── .env.example                # 环境变量模板
├── .gitignore
├── README.md
├── docs/
│   ├── design.md               # 系统设计文档
│   └── roadmap.md              # 实施路线图
├── infra/
│   └── postgres/
│       └── init/               # PG 初始化 SQL（扩展启用等）
└── backend/                    # FastAPI 应用（Phase 1 创建）
```

---

## 阶段进度

- [x] **Phase 0**：本地基础设施（Postgres + Redis + Langfuse）
- [ ] **Phase 1**：FastAPI 骨架 + DeepSeek 接入
- [ ] **Phase 2**：知识库 + RAG
- [ ] **Phase 3**：LangGraph Agent 编排
- [ ] **Phase 4**：安全合规层
- [ ] **Phase 5**：可观测性
- [ ] **Phase 6**：检索质量优化
- [ ] **Phase 7**：前端 MVP
- [ ] **Phase 8**：知识库扩充
- [ ] **Phase 9**：部署上线
