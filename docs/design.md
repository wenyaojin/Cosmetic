# 医美 AI Agent 系统设计文档

> Version: 0.1 (Draft)
> Date: 2026-05-08
> Status: Design Review

---

## 1. 项目背景与目标

### 1.1 背景
医美行业信息不对称严重，消费者面对玻尿酸、肉毒、光电、手术等数百个项目难以判断：
- 哪些项目适合自己？
- 不同项目效果、风险、价格区间？
- 术前术后注意事项？
- 是否有禁忌症？

传统咨询渠道（机构客服、社交平台）存在销售导向、信息片面、专业度不一等问题。

### 1.2 目标
构建一个基于开源 LLM + 医美专业知识库的 AI Agent，提供：
- **科普问答**：准确回答医美项目相关问题，附引用来源
- **个性化咨询**：通过多轮对话收集用户信息，推荐合适方案
- **风险提示**：识别禁忌症、不合理诉求，给出免责声明
- **引导面诊**：明确边界，复杂问题引导线下专业医生

### 1.3 非目标（Out of Scope）
- ❌ 不做线上诊断（受《互联网诊疗管理办法》限制）
- ❌ 不开处方、不替代执业医师
- ❌ 不提供机构推荐 / 商业导流（一期）
- ❌ 不处理急症、重症医疗咨询

---

## 2. 用户场景

### 2.1 典型用户
- **小白用户**：完全不懂医美，想了解某个项目
- **进阶用户**：在多个方案间犹豫，需要对比
- **术后用户**：关心护理、并发症识别

### 2.2 核心用户旅程

```
用户："我 28 岁，鼻基底凹陷，预算 1 万以内，有什么推荐？"
  ↓
Agent：收集信息（确认肤质、过敏史、是否孕期、是否做过手术）
  ↓
Agent：检索知识库（鼻基底填充相关项目）
  ↓
Agent：风险评估（用户是否有禁忌症）
  ↓
Agent：输出方案对比（玻尿酸 vs 自体脂肪 vs 假体），附适应症/风险/价格区间/引用
  ↓
Agent：免责声明 + 引导线下面诊
```

---

## 3. 系统架构

### 3.1 总体架构图

```
┌──────────────────────────────────────────────────────┐
│  Client Layer                                        │
│  Next.js 14 + TypeScript + Tailwind + shadcn/ui      │
│  Vercel AI SDK（流式聊天 UI）                         │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP / SSE
┌─────────────────────▼────────────────────────────────┐
│  API Gateway                                         │
│  FastAPI + Pydantic v2                               │
│  ├─ Auth（JWT）                                      │
│  ├─ Rate Limit                                       │
│  └─ Request Validation                               │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│  Agent Orchestration Layer                           │
│  LangGraph（状态机编排）                              │
│  ├─ Node: Intake（信息收集）                          │
│  ├─ Node: Retrieve（RAG 检索）                        │
│  ├─ Node: SafetyCheck（风险/禁忌评估）                │
│  ├─ Node: Recommend（方案生成）                       │
│  └─ Node: Disclaim（免责声明）                        │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
┌──────────▼──────────┐  ┌─────────▼─────────┐
│  RAG Layer          │  │  LLM Layer         │
│  LlamaIndex         │  │  DeepSeek V4 (主) │
│  ├─ Hybrid Retrieval│  │  Qwen2.5-7B (辅) │
│  ├─ bge Embedding   │  │  via OpenAI SDK    │
│  └─ bge Rerank      │  │                    │
└──────────┬──────────┘  └────────────────────┘
           │
┌──────────▼─────────────────────────────────────────┐
│  Storage Layer                                     │
│  ├─ PostgreSQL + pgvector（业务数据 + 向量索引）   │
│  ├─ Redis（会话缓存、限流）                         │
│  └─ Object Storage（原始文档、图片）                │
└────────────────────────────────────────────────────┘
           ▲
           │
┌──────────┴────────────────────────────────────────┐
│  Observability                                    │
│  Langfuse（LLM trace） + Prometheus + Grafana    │
└───────────────────────────────────────────────────┘
```

### 3.2 关键技术选型

| 层 | 组件 | 选型 | 理由 |
|---|---|---|---|
| LLM 主 | 主对话/方案生成 | **DeepSeek V4** | 中文强、推理强、tool calling 稳定、长上下文 |
| LLM 辅 | 意图识别/审核 | **Qwen2.5-7B** | 便宜、快速、本地可部署 |
| Embedding | 向量化 | **bge-large-zh-v1.5** | 中文 SOTA、开源、1024 维 |
| Rerank | 检索精排 | **bge-reranker-v2-m3** | 精度提升 30%+ |
| Agent | 编排 | **LangGraph** | 显式状态机、可中断、可回放 |
| RAG | 检索 | **LlamaIndex** | 检索能力专业、与 LangGraph 兼容 |
| 后端 | API | **FastAPI** | 异步、高性能、自带 OpenAPI |
| 数据 | 主存 + 向量 | **PostgreSQL + pgvector** | 单库满足，省运维成本 |
| 缓存 | 会话/限流 | **Redis** | 标准方案 |
| 前端 | UI | **Next.js 14 + Vercel AI SDK** | 流式开箱即用 |
| 可观测 | LLM Trace | **Langfuse** | 开源自部署、专门为 LLM 设计 |
| 部署 | 容器 | **Docker Compose**（MVP）→ K8s | 渐进式 |

---

## 4. Agent 设计（核心）

### 4.1 状态机定义

```python
class ConsultState(TypedDict):
    # 输入
    user_message: str
    session_id: str
    history: list[Message]

    # 收集到的用户信息
    user_profile: dict  # 年龄、性别、肤质、预算、禁忌、过敏史等
    intent: Literal["科普", "项目咨询", "方案推荐", "术后护理", "其他"]

    # 中间产物
    retrieved_docs: list[Document]
    risk_flags: list[str]

    # 输出
    response: str
    citations: list[Citation]
    needs_human: bool  # 是否需要引导面诊
```

### 4.2 节点定义

```
START
  ↓
[Intake]：意图识别 + 用户信息抽取
  ├─ 信息不全 → 反问用户 → END（等待下一轮）
  └─ 信息足够 → 继续
  ↓
[SafetyGate]：敏感问题拦截
  ├─ 涉及诊断/处方 → 拒答 + 引导面诊 → END
  └─ 通过 → 继续
  ↓
[Retrieve]：LlamaIndex 混合检索
  ├─ 向量召回 Top 20
  ├─ BM25 关键词召回 Top 20
  └─ Rerank → Top 5
  ↓
[RiskAssessment]：禁忌症/适应症匹配
  ↓
[Recommend]：DeepSeek V4 生成方案
  ↓
[Disclaim]：附加免责声明 + 引用
  ↓
END
```

### 4.3 工具（Tools）清单

| 工具名 | 功能 | 实现 |
|---|---|---|
| `search_knowledge` | 检索医美知识库 | LlamaIndex hybrid retriever |
| `lookup_project` | 查询项目结构化信息（适应症、价格） | PostgreSQL 查询 |
| `check_contraindication` | 检查禁忌症 | 规则引擎 + LLM |
| `extract_user_profile` | 从对话抽取用户画像 | DeepSeek V4 function call |
| `escalate_to_human` | 转人工 / 引导面诊 | 标记 + 通知 |

### 4.4 Prompt 策略

- **System Prompt**：定义角色（医美科普助手，非医生）、能力边界、安全红线
- **Few-shot**：每类意图准备 3-5 个示例
- **CoT**：风险评估节点用思维链
- **强制 Citation**：回答必须标注 `[1][2]` 引用来源，无来源不答

---

## 5. RAG 设计

### 5.1 知识库分类

```
knowledge_base/
├── projects/           # 项目百科（玻尿酸、肉毒、热玛吉…）
├── indications/        # 适应症 / 禁忌症
├── drug_device/        # 药械说明书（NMPA/FDA）
├── guidelines/         # 临床指南（中华医学会、ISAPS）
├── papers/             # 学术论文（PubMed、知网）
├── post_care/          # 术后护理与并发症
└── pricing/            # 市场价格区间（脱敏）
```

### 5.2 文档处理管线

```
原始文档（PDF/Word/HTML）
  ↓ MinerU / markitdown 解析
结构化 Markdown
  ↓ 按语义切分（chunk_size=512, overlap=64）
Chunk
  ↓ bge-large-zh embedding
向量 + 元数据（来源、分类、发布日期、权威等级）
  ↓
PostgreSQL + pgvector
```

### 5.3 检索策略

- **混合检索**：向量召回（语义）+ BM25（关键词）→ RRF 融合
- **元数据过滤**：按项目类别、文档权威等级筛选
- **Rerank**：bge-reranker-v2-m3 精排到 Top 5
- **引用强制**：检索失败 → 拒答（不允许 LLM 自由发挥）

### 5.4 文档权威分级

| 等级 | 来源 | 权重 |
|---|---|---|
| L1 | NMPA/FDA、临床指南、教科书 | 1.0 |
| L2 | 三甲医院科普、PubMed RCT | 0.8 |
| L3 | 行业协会、专业期刊 | 0.6 |
| L4 | 厂商资料、机构网站 | 0.4 |

---

## 6. 数据模型

### 6.1 核心表结构

```sql
-- 用户表
CREATE TABLE users (
  id UUID PRIMARY KEY,
  phone VARCHAR(20) UNIQUE,
  created_at TIMESTAMP
);

-- 会话表
CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  user_profile JSONB,  -- 年龄、肤质、预算等
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- 消息表
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  role VARCHAR(20),  -- user / assistant / system
  content TEXT,
  citations JSONB,
  trace_id VARCHAR(64),  -- 关联 Langfuse
  created_at TIMESTAMP
);

-- 知识库文档
CREATE TABLE documents (
  id UUID PRIMARY KEY,
  title TEXT,
  source TEXT,
  category VARCHAR(50),
  authority_level INT,  -- 1-4
  published_at DATE,
  raw_content TEXT,
  metadata JSONB
);

-- 向量索引（chunk 级）
CREATE TABLE doc_chunks (
  id UUID PRIMARY KEY,
  doc_id UUID REFERENCES documents(id),
  chunk_text TEXT,
  embedding vector(1024),  -- bge-large-zh
  chunk_index INT
);
CREATE INDEX ON doc_chunks USING hnsw (embedding vector_cosine_ops);

-- 审计日志
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY,
  session_id UUID,
  event_type VARCHAR(50),  -- 拒答/敏感词/转人工等
  payload JSONB,
  created_at TIMESTAMP
);
```

---

## 7. API 设计

### 7.1 核心接口

```
POST /api/v1/chat
  Request:
    {
      "session_id": "uuid",
      "message": "我28岁鼻基底凹陷，有推荐项目吗？"
    }
  Response: SSE 流
    event: token   data: {"text": "..."}
    event: cite    data: {"citations": [...]}
    event: done    data: {"message_id": "..."}

GET  /api/v1/sessions/{id}/messages
POST /api/v1/sessions
GET  /api/v1/projects/{name}            # 项目结构化信息
POST /api/v1/feedback                   # 用户反馈（点赞/点踩）
```

### 7.2 错误处理

- 4xx：参数错误、限流、未授权
- 5xx：LLM 超时、检索失败 → 降级到通用回复 + 引导人工

---

## 8. 安全与合规（重点）

### 8.1 输入侧

- **敏感词过滤**：色情、政治、辱骂
- **意图拦截**：诊断类问题（"我得了 XX 病吗"）→ 拒答
- **PII 脱敏**：用户输入的手机号、身份证号入库前打码

### 8.2 输出侧

- **强制免责声明**：每次回答末尾自动追加
  > 本回答仅供科普参考，不构成医疗建议。任何医美项目请前往正规医疗机构面诊评估。
- **禁用词**：屏蔽"诊断""处方""治愈""保证效果"等违规用语
- **引用强制**：回答必须有 citation，否则不输出
- **价格脱敏**：只给区间，不报具体机构价

### 8.3 合规要点

| 法规 | 要点 | 应对 |
|---|---|---|
| 《互联网诊疗管理办法》 | 不得线上首诊、不得开处方 | 定位科普，明确边界 |
| 《广告法》 | 医疗广告需审批 | 不做机构推荐 |
| 《个人信息保护法》 | 用户数据收集需告知 | 隐私协议 + 数据加密 |
| 《生成式 AI 服务管理办法》 | 大模型备案 | 用已备案模型（DeepSeek 已备案） |

### 8.4 审计

- 所有对话落库，保留 6 个月以上
- 拒答、转人工、用户投诉均记录到 `audit_logs`

---

## 9. 可观测性

### 9.1 LLM Trace（Langfuse）

每次请求记录：
- 完整 prompt / completion
- Token 消耗、延迟、成本
- 检索到的文档与得分
- Agent 各节点耗时
- 用户反馈（点赞/点踩）关联

### 9.2 业务指标

| 指标 | 目标 |
|---|---|
| 回答准确率（人工评估） | ≥ 85% |
| 引用命中率 | ≥ 90% |
| P95 端到端延迟 | ≤ 5s |
| 拒答率 | 5%-15%（合理区间） |
| 用户满意度（点赞率） | ≥ 70% |

### 9.3 系统指标（Prometheus + Grafana）

- API QPS、错误率、延迟分布
- LLM API 调用成功率、限流触发次数
- 数据库连接池、慢查询
- Redis 命中率

---

## 10. 部署架构

### 10.1 MVP 阶段

```
单台云服务器（4C8G）
├─ Docker Compose
│  ├─ FastAPI (3 worker)
│  ├─ PostgreSQL + pgvector
│  ├─ Redis
│  └─ Langfuse
├─ DeepSeek API（外部）
└─ bge 模型（CPU 推理 / 或用 SiliconFlow API）
```
预估月成本：服务器 ~200元 + API ~500-2000元

### 10.2 生产阶段

```
K8s 集群
├─ FastAPI Deployment（HPA 2-10 副本）
├─ PostgreSQL（云托管 RDS）
├─ Redis（云托管）
├─ 对象存储（OSS）
├─ Langfuse（独立部署）
└─ GPU 节点（可选，自部署 Qwen2.5）

CDN（前端静态资源）
WAF + DDoS 防护
```

---

## 11. 路线图（Roadmap）

### Phase 1：MVP（Week 1-2）
- [ ] FastAPI 骨架 + DeepSeek API 接入
- [ ] LlamaIndex + pgvector 跑通基础 RAG
- [ ] 灌入 50-100 篇精选医美资料
- [ ] 简单聊天 UI
- **里程碑**：能回答"玻尿酸维持多久"这类基础问题，附引用

### Phase 2：Agent 化（Week 3-6）
- [ ] LangGraph 编排，多轮信息收集
- [ ] 安全审核节点（敏感词、违规词）
- [ ] 免责声明、Citation 强制
- [ ] Langfuse 接入
- **里程碑**：能完成完整咨询流程

### Phase 3：知识库扩充（Week 7-12，持续）
- [ ] 系统化收集 1000+ 篇资料
- [ ] 引入 bge-reranker
- [ ] 混合检索（向量 + BM25）
- [ ] 项目结构化数据库
- **里程碑**：覆盖主流医美项目 80%+

### Phase 4：专业化（Month 4+）
- [ ] 专家审核语料 + 轻量 SFT
- [ ] 自部署 Qwen2.5（数据合规需求）
- [ ] 真实医生人工兜底
- [ ] 用户画像持久化、多轮记忆
- **里程碑**：达到准专业咨询水平

---

## 12. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| LLM 输出违规医疗建议 | 中 | 高 | 多层审核 + 强制免责 + 人工抽检 |
| 知识库质量不够 → 回答不准 | 高 | 高 | 专家审核 + 引用强制 + 拒答机制 |
| DeepSeek API 不稳定/涨价 | 低 | 中 | 多模型 fallback（Qwen/通义） |
| 数据合规问题 | 中 | 高 | 用已备案模型 + 法务审核 |
| 用户当成医生（情感依赖） | 中 | 中 | 强引导面诊 + 边界声明 |
| 成本超预算 | 中 | 中 | 缓存 + 小模型分流 + 限流 |

---

## 13. 待决策事项（Open Questions）

1. **商业模式**：纯工具 / 给医美机构提供 SaaS / C 端会员？影响合规策略
2. **数据归属**：用户对话数据是否用于模型迭代？需要隐私协议明确
3. **是否做机构推荐**：涉及医疗广告法，需法务评估
4. **多模态**：是否支持用户上传照片做项目推荐？涉及医疗影像监管，建议二期
5. **本地化部署时间点**：什么数据量/客户类型触发自部署？

---

## 14. 附录

### 14.1 参考资料
- DeepSeek V4 文档：https://platform.deepseek.com/docs
- LangGraph 文档：https://langchain-ai.github.io/langgraph/
- LlamaIndex 文档：https://docs.llamaindex.ai/
- Langfuse：https://langfuse.com/
- pgvector：https://github.com/pgvector/pgvector

### 14.2 术语表
- **RAG**：Retrieval-Augmented Generation，检索增强生成
- **Agent**：能自主决策、调用工具的 LLM 应用
- **Embedding**：将文本映射为向量
- **Rerank**：对检索候选重新排序提升精度
- **MoE**：Mixture of Experts，混合专家模型架构
- **SSE**：Server-Sent Events，单向流式推送
