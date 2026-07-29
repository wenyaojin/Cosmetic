"""Prompt strings for A/C conditions. C reuses the production prompt path."""

# Condition A: naive baseline — reasonable but domain-agnostic Chinese prompt.
# Simulates a first-pass product prompt someone would write without medical
# training or few-shot examples. Kept in Chinese because the production path
# (C) also emits Chinese, keeping the output language axis controlled.
NAIVE_PROMPT = """你是一位面部美容顾问 AI。请分析用户上传的面部正面照片，识别其中的美容问题并给出改善建议。

请从以下方面进行分析：
1. 皮肤问题（如色斑、痘痘、毛孔、皱纹、暗沉等）
2. 面部结构问题（如松弛、下垂、比例等）
3. 每个问题的严重程度（轻度/中度/重度）
4. 建议改善方向

请以 JSON 格式输出，包含问题列表和整体评价。"""
