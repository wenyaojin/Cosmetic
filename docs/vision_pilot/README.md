# Vision Pilot

这个目录实现 `Q:\paper-read\research\vision-pilot\design.md` 中的 pilot，但运行位置在 Cosmetic 项目内。

目标：只验证 vision extraction + recommendation-conditioned re-examination 机制，不接入正式 chat agent / RAG pipeline。

## 环境

```powershell
cd Q:\Cosmetic\backend
python -m pip install -e .
```

API key 会按顺序读取：

- `DASHSCOPE_API_KEY`
- `.env` / 环境变量中的 `LLM_API_KEY`

## 数据

把 5-8 张 `.jpg` / `.png` / `.webp` 放到：

```text
Q:\Cosmetic\docs\vision_pilot\data
```

真实图片默认作为本地实验数据，不进入 git。

## 运行

只测试文件生成链路，不调用 API：

```powershell
cd Q:\Cosmetic\backend
python -m scripts.vision_pilot --dry-run --limit 1
```

跑完整 pilot（默认仅使用 `qwen3-vl-flash`，便宜 + 快）：

```powershell
cd Q:\Cosmetic\backend
python -m scripts.vision_pilot
```

可先小样本验证：

```powershell
python -m scripts.vision_pilot --limit 2 --max-tokens 500
```

如确需对比 `qwen-vl-max`（更贵），可显式覆盖：

```powershell
python -m scripts.vision_pilot --models qwen3-vl-flash qwen-vl-max
```

## 输出

- `runs/<image>__<model>.md`：每张图每个模型的 V1/V2/V3 原始输出、latency、tokens、估算成本和人工评分表
- `report.md`：汇总报告模板
- `summary.json`：机器可读的运行元数据

人工填完 `runs/*.md` 的评分表后执行：

```powershell
python -m scripts.vision_pilot summarize
```

脚本会按 design doc 的规则重写 `report.md`，给出 GO / PIVOT / KILL 建议。最终决策仍需要人工复核。
