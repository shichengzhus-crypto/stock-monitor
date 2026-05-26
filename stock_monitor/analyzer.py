"""调用 DeepSeek API 对公告内容进行分析摘要"""
import config
from openai import OpenAI

_client = OpenAI(
    api_key=config.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

_SYSTEM = (
    "你是一个专业的A股投资分析助手。"
    "请分析公司公告，提炼对投资者最重要的信息。"
    "关注：公司实际经营变化、股东回报影响、潜在风险或机会。"
    "回答简洁，使用中文，3-5句话，不废话。"
)


def analyze(title: str, category: str, content: str = "") -> str:
    """返回对一条公告的 AI 分析摘要"""
    if content:
        user_msg = (
            f"公告类别：{category}\n"
            f"公告标题：{title}\n\n"
            f"公告正文（节选）：\n{content}\n\n"
            "请提炼关键信息：①核心内容 ②对经营/投资者的影响 ③需特别关注的点。"
        )
    else:
        user_msg = (
            f"公告类别：{category}\n"
            f"公告标题：{title}\n\n"
            "（仅有标题，无正文）请根据标题推断公告内容，说明投资者应关注什么。"
        )

    try:
        resp = _client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"（AI 分析失败：{e}）"
