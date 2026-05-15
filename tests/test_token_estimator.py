from app.services.token_estimator import estimate_tokens

def test_estimate_tokens_for_openai():
    # 测试 OpenAI 系数 (1000 * 0.3 = 300)
    tokens = estimate_tokens(1000, "openai/gpt-4o")
    assert tokens == 300

def test_estimate_tokens_for_anthropic():
    # 测试 Claude 系数 (1000 * 0.35 = 350)
    tokens = estimate_tokens(1000, "anthropic/claude-3-haiku")
    assert tokens == 350

def test_estimate_tokens_edge_cases():
    # 边缘测试：负数或 0 字符应该返回 0
    assert estimate_tokens(0, "openai/gpt-4") == 0
    assert estimate_tokens(-50, "openai/gpt-4") == 0
    
    # 边缘测试：哪怕只有 1 个字符，也至少算 1 个 Token
    assert estimate_tokens(1, "unknown/model") == 1


def test_estimate_tokens_for_chinese_defaults():
    assert estimate_tokens(1000, "moonshot/moonshot-v1-32k", "zh") == 700


def test_estimate_tokens_for_gemini_chinese():
    assert estimate_tokens(1000, "gemini/gemini-2.0-flash", "zh") == 550
