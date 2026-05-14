import re

_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_ID_CARD_RE = re.compile(r"\d{17}[\dXx]")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

FORBIDDEN_OUTPUT_WORDS = [
    "诊断结果", "确诊", "处方", "开药",
    "保证效果", "100%", "绝对安全", "零风险",
    "最便宜", "最好的医院",
]


def mask_pii(text: str) -> str:
    text = _PHONE_RE.sub("1**********", text)
    text = _ID_CARD_RE.sub("****", text)
    text = _EMAIL_RE.sub("***@***.com", text)
    return text


def check_output(text: str) -> list[str]:
    return [w for w in FORBIDDEN_OUTPUT_WORDS if w in text]
