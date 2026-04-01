import unittest

from backend.chat_logic import build_context, build_query_texts, resolve_history_messages


class BuildQueryTextsTests(unittest.TestCase):
    def test_uses_injected_user_history_for_generic_follow_up(self):
        history = [
            {"role": "user", "content": "我发烧两天了"},
            {"role": "assistant", "content": "还有哪些症状？"},
            {"role": "user", "content": "还咳嗽胸闷"},
        ]

        query_texts = build_query_texts(history, "怎么办")

        self.assertEqual(query_texts[0], "我发烧两天了；怎么办")
        self.assertEqual(query_texts[1], "怎么办")


class BuildContextTests(unittest.TestCase):
    def test_serializes_explicit_history_without_session_state(self):
        history = [
            {"role": "user", "content": "我发烧"},
            {"role": "assistant", "content": "体温多少？"},
        ]

        context = build_context(history, "39度，需要去医院吗？")

        self.assertIn("【当前问题】", context)
        self.assertIn("【用户】我发烧", context)
        self.assertIn("【助手】体温多少？", context)
        self.assertIn("39度，需要去医院吗？", context)


class ResolveHistoryMessagesTests(unittest.TestCase):
    def test_prefers_injected_history_over_session_messages(self):
        session_messages = [{"role": "user", "content": "session"}]
        injected_history = [{"role": "user", "content": "injected"}]

        resolved = resolve_history_messages(session_messages, injected_history)

        self.assertEqual(resolved, injected_history)
        self.assertEqual(session_messages[0]["content"], "session")


if __name__ == "__main__":
    unittest.main()
