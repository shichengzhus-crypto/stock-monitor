"""调用 DeepSeek API 对公告内容进行分析摘要"""
import config
from openai import OpenAI

_client = OpenAI(
    api_key=config.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

_SYSTEM = (
    "你是上市公司公告速读助手。"
    "用1～2句话直接说明公告的核心事实，包含关键数字（如有）。"
    "不要分析影响，不要套话，不要'需关注'之类的废话，只陈述发生了什么。"
    "用中文回答。"
)


def analyze(title: str, category: str, content: str = "") -> str:
    """返回对一条公告的 AI 分析摘要"""
    if content:
        user_msg = (
            f"公告类别：{category}\n"
            f"公告标题：{title}\n\n"
            f"公告正文（节选）：\n{content}"
        )
    else:
        user_msg = (
            f"公告类别：{category}\n"
            f"公告标题：{title}"
        )

    try:
        resp = _client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"（AI 分析失败：{e}）"
