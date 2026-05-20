# 医美知识库 — 文献采集工作目录

## 目录结构

```
knowledge/
├── _inbox/         # 把下载的原始文献（PDF/Word/网页/MD）扔这里
├── _processed/     # 自动处理通过的标准化文档（可直接入库）
├── _review/        # 需要人工复审的文档（命中红线词等）
├── _templates/     # 标准文档模板
├── _meta/          # 元数据（红线词库、schema 等）
│
├── 通用知识/
├── 注射填充/
├── 光电美肤/
├── 紧致抗衰/
├── 皮肤管理/
└── 身体塑形/
```

---

## 使用流程（3 步）

### 第 1 步：下载原始文献到 `_inbox/`

支持格式：PDF / Word / HTML / Markdown / TXT

来源建议：
- NMPA 官网：nmpa.gov.cn
- 卫健委：nhc.gov.cn
- 厂商官网（艾尔建、高德美、Solta 等）
- PubMed / CNKI

### 第 2 步：运行处理脚本

```bash
cd Q:/Cosmetic/backend

# 先设置 LLM API Key（DeepSeek 或 OpenAI）
export DEEPSEEK_API_KEY=sk-xxx

# 处理 _inbox/ 里所有文件
python -m scripts.process_inbox

# 或试运行（只扫描不写盘）
python -m scripts.process_inbox --dry-run

# 或只处理单个文件
python -m scripts.process_inbox --file ../knowledge/_inbox/瑞蓝2号.pdf
```

脚本会自动：
1. PDF/Word → Markdown
2. LLM 按模板改写为结构化文档
3. 扫描合规红线词
4. 通过的存到 `_processed/`，有问题的存到 `_review/`

### 第 3 步：人工审核

- 看 `_processed/` 里的文档 → 没问题就移到对应品类目录
- 看 `_review/` 里的文档 → 改完红线词后移走

---

## 入库到 RAG

确认无误的文档放进 `注射填充/` `光电美肤/` 等品类目录后：

```bash
cd Q:/Cosmetic/backend
python -m scripts.batch_ingest ../knowledge/注射填充
```

---

## 合规红线（自动扫描）

详见 `_meta/redline.yaml`，包含：
- **绝对禁止词**：根治、永久、最佳、零风险、100% 等
- **限制使用词**：明显改善、显著效果等
- **必须出现的声明**：因人而异、仅供参考
