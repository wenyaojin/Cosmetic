import jieba
from pathlib import Path
from app.core.logging import get_logger

logger = get_logger("tokenizer")

_DICT_LOADED = False

STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "吗", "什么", "那",
    "可以", "么", "想", "能", "吧", "呢", "啊", "哦", "嗯", "呀",
    "这个", "那个", "怎么", "怎样", "如何", "请问", "请",
}


def _ensure_dict():
    global _DICT_LOADED
    if _DICT_LOADED:
        return
    dict_path = Path(__file__).parent.parent / "data" / "medical_dict.txt"
    if dict_path.exists():
        jieba.load_userdict(str(dict_path))
        logger.info("Loaded medical dictionary: %s", dict_path)
    _DICT_LOADED = True


def tokenize(text: str) -> list[str]:
    _ensure_dict()
    words = jieba.cut_for_search(text)
    return [w.strip() for w in words if w.strip() and w.strip() not in STOPWORDS]


def tokenize_for_index(text: str) -> str:
    return " ".join(tokenize(text))
