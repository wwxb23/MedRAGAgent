from typing import Dict, List, Optional


GENERIC_PATTERNS = [
    "什么症状",
    "有什么症状",
    "怎么治疗",
    "怎么办",
    "怎么用药",
    "用什么药",
    "临床表现",
]


def resolve_history_messages(
    session_messages: List[Dict[str, str]],
    injected_history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    source = injected_history if injected_history is not None else session_messages
    return [dict(message) for message in source]


def extract_recent_user_questions(messages: List[Dict[str, str]], limit: int = 2) -> List[str]:
    return [message["content"] for message in messages if message.get("role") == "user"][-limit:]


def build_query_texts(messages: List[Dict[str, str]], question: str) -> List[str]:
    history_user_questions = extract_recent_user_questions(messages, limit=2)
    is_generic = len(question) < 8 or any(pattern in question for pattern in GENERIC_PATTERNS)

    if is_generic and history_user_questions:
        return [f"{history_user_questions[0]}；{question}", question]

    return [question] + history_user_questions[:2]


def build_context(messages: List[Dict[str, str]], question: str) -> str:
    parts = [f"【当前问题】\n{question}"]

    if messages:
        lines = []
        for message in messages:
            role = "用户" if message.get("role") in ("user", "system_summary") else "助手"
            lines.append(f"【{role}】{message['content']}")
        parts.append("【对话历史（完整）】\n" + "\n".join(lines))

    return "\n\n".join(parts)
