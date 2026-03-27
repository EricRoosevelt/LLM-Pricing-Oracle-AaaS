# 将规则抽离为全局常量字典（未来甚至可以移到 Redis 或数据库里动态加载）
# key 为模型关键字，value 为 Token 转化系数
# 扩充全局常量字典：[英文系数, 中文系数]
TOKEN_MULTIPLIERS = {
    "gpt": {"en": 0.30, "zh": 0.60},
    "openai": {"en": 0.30, "zh": 0.60},
    "claude": {"en": 0.35, "zh": 0.65},
    "anthropic": {"en": 0.35, "zh": 0.65},
    "gemini": {"en": 0.32, "zh": 0.55},
}
DEFAULT_MULTIPLIER = {"en": 0.40, "zh": 0.70}

def estimate_tokens(char_count: int, model_id: str, language: str = "en") -> int:
    """
    根据字符预估 Token。
    """
    if char_count <= 0:
        return 0
        
    model_lower = model_id.lower()
    # 动态匹配：遍历字典寻找关键字
    multiplier = DEFAULT_MULTIPLIER.get(language, 0.40) # 兜底

    for key, val_dict in TOKEN_MULTIPLIERS.items():
        if key in model_lower:
            multiplier = val_dict.get(language, val_dict["en"])
            break
            
    estimated = int(char_count * multiplier)
    return max(1, estimated)