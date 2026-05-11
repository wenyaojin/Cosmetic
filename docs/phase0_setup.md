# Phase 0：环境与基础设施搭建

> 目标：本地 `docker compose up` 一键启动 Postgres（带 pgvector）+ Redis + Langfuse。

---

## 1. 已交付内容

| 文件 | 作用 |
|---|---|
| `docker-compose.yml` | 编排 4 个容器：postgres / redis / langfuse-db / langfuse |
| `.env.example` | 环境变量模板（API key、密码等） |
| `.gitignore` | 排除 `.env`、虚拟环境、缓存、日志等 |
| `infra/postgres/init/01_extensions.sql` | Postgres 启动时自动启用 `vector` 与 `pg_trgm` 扩展 |
| `README.md` | 项目入口、启动指南、阶段进度 |

---

## 2. 容器清单

```
postgres     pgvector/pgvector:pg16    业务数据 + 向量库
redis        redis:7-alpine            缓存 / 会话 / 限流
langfuse-db  postgres:16-alpine        Langfuse 自己的元数据库（与业务库隔离）
langfuse     langfuse/langfuse:2       LLM 监控 UI
```

> Langfuse 单独一个 PG 实例，**避免 Langfuse 表污染你的业务库**。

---

## 3. 操作步骤（用户执行）

### 3.1 安装 Docker Desktop
- 下载：https://www.docker.com/products/docker-desktop/
- Windows：装好后在 PowerShell 或 bash 验证：
  ```bash
  docker --version
  docker compose version
  ```

### 3.2 准备 `.env`
```bash
cd Q:/Cosmetic
cp .env.example .env
```
- DeepSeek / Embedding / Langfuse 的 key 暂时可以留 placeholder（Phase 0 用不到）
- 数据库密码、端口可保持默认

### 3.3 启动
```bash
docker compose up -d
```
首次拉镜像需几分钟。完成后查看：
```bash
docker compose ps
```
应看到 4 个容器全部 `running` / `healthy`。

### 3.4 验证

```bash
# Postgres 扩展是否启用
docker exec -it cosmetic-postgres psql -U cosmetic -d cosmetic -c "\dx"
# 应看到 vector 和 pg_trgm

# Redis 是否可用
docker exec -it cosmetic-redis redis-cli ping
# 返回 PONG

# Langfuse 访问
# 浏览器打开 http://localhost:3000
# 首次访问需注册一个本地账号
```

### 3.5 在 Langfuse 拿到 API Key

进入 Langfuse 后：
1. 创建组织 / 项目（默认已自动建好 `cosmetic-agent`）
2. Settings → API Keys → Create new key
3. 把 `Public Key` 和 `Secret Key` 填入 `.env`：
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-xxx
   LANGFUSE_SECRET_KEY=sk-lf-xxx
   ```

> 这一步可以等 Phase 5 真正接 Langfuse SDK 时再做。

---

## 4. 验收 Checklist

- [ ] `docker compose ps` 4 个容器全部 healthy
- [ ] Postgres `\dx` 看到 `vector` 扩展
- [ ] Redis `ping` 返回 PONG
- [ ] http://localhost:3000 能打开 Langfuse 登录页
- [ ] `.env` 已从 `.env.example` 复制并填写（至少占位符）
- [ ] `.env` 没被 git 跟踪（`git status` 看不到）

---

## 5. 常见问题

### 端口冲突（5432 / 6379 / 3000 已被占用）
修改 `.env` 里的端口映射：
```
POSTGRES_PORT=15432
REDIS_PORT=16379
LANGFUSE_PORT=13000
```
然后 `docker compose up -d` 重启。

### Langfuse 启动失败
查看日志：
```bash
docker compose logs langfuse
```
最常见原因：`NEXTAUTH_SECRET` / `SALT` 太短，确保 ≥ 32 字符。

### 完全重置
```bash
docker compose down -v   # 删容器 + 数据卷
docker compose up -d     # 全新启动
```

---

## 6. 下一步

✅ Phase 0 完成 → 进入 **Phase 1：FastAPI 骨架 + DeepSeek 接入**
