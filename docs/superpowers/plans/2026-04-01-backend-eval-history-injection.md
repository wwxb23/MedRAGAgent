# Backend Eval History Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a private evaluation path that accepts injected dialogue history, uses the existing backend agent logic to answer the final user turn, and can be consumed by automated HealthBench-style samplers without mutating production session state.

**Architecture:** Keep the production `/api/chat` endpoint intact for SSE chat traffic, but extract the history/context/query preparation logic into a small pure-Python helper module. Add a non-streaming `/api/eval/chat` endpoint that reuses the same retrieval and prompting flow while accepting explicit `history` input and skipping session persistence. Verification uses `unittest` for the pure helper module plus syntax compilation for the FastAPI entrypoint because the current local Python environment does not have backend dependencies installed.

**Tech Stack:** Python 3.9, FastAPI, Pydantic, standard-library `unittest`, OpenAI-compatible chat client, ChromaDB

---

## File Structure

### New files

- `backend/chat_logic.py`
  - Pure helper functions for history injection, context assembly, and retrieval query expansion.
- `tests/test_chat_logic.py`
  - `unittest` coverage for history injection behavior and query/context generation.

### Modified files

- `backend/main.py`
  - Import and use `chat_logic` helpers.
  - Add evaluation request models.
  - Add a private `/api/eval/chat` endpoint.
  - Keep `/api/chat` streaming behavior unchanged for existing clients.

## Task 1: Extract pure history and context helpers

**Files:**
- Create: `backend/chat_logic.py`
- Test: `tests/test_chat_logic.py`

- [ ] **Step 1: Write the failing test for history-based query expansion**

```python
import unittest

from backend.chat_logic import build_query_texts


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_chat_logic.BuildQueryTextsTests.test_uses_injected_user_history_for_generic_follow_up -v`  
Expected: FAIL with `ModuleNotFoundError` or missing function import because `backend.chat_logic` does not exist yet.

- [ ] **Step 3: Write minimal helper implementation**

```python
from typing import List, Dict


GENERIC_PATTERNS = [
    "什么症状",
    "有什么症状",
    "怎么治疗",
    "怎么办",
    "怎么用药",
    "用什么药",
    "临床表现",
]


def extract_recent_user_questions(messages: List[Dict[str, str]], limit: int = 2) -> List[str]:
    return [m["content"] for m in messages if m.get("role") == "user"][-limit:]


def build_query_texts(messages: List[Dict[str, str]], question: str) -> List[str]:
    history_user_questions = extract_recent_user_questions(messages, limit=2)
    is_generic = len(question) < 8 or any(pattern in question for pattern in GENERIC_PATTERNS)
    if is_generic and history_user_questions:
        return [f"{history_user_questions[0]}；{question}", question]
    return [question] + history_user_questions[:2]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_chat_logic.BuildQueryTextsTests.test_uses_injected_user_history_for_generic_follow_up -v`  
Expected: PASS

- [ ] **Step 5: Add context assembly coverage**

```python
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
```

- [ ] **Step 6: Run the full helper test file**

Run: `python -m unittest tests.test_chat_logic -v`  
Expected: PASS

## Task 2: Refactor `backend/main.py` to use extracted helper logic

**Files:**
- Modify: `backend/main.py`
- Reuse: `backend/chat_logic.py`
- Test: `tests/test_chat_logic.py`

- [ ] **Step 1: Write the failing test for eval-history normalization**

```python
from backend.chat_logic import resolve_history_messages


class ResolveHistoryMessagesTests(unittest.TestCase):
    def test_prefers_injected_history_over_session_messages(self):
        session_messages = [{"role": "user", "content": "session"}]
        injected_history = [{"role": "user", "content": "injected"}]

        resolved = resolve_history_messages(session_messages, injected_history)

        self.assertEqual(resolved, injected_history)
        self.assertEqual(session_messages[0]["content"], "session")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_chat_logic.ResolveHistoryMessagesTests.test_prefers_injected_history_over_session_messages -v`  
Expected: FAIL because `resolve_history_messages` does not exist yet.

- [ ] **Step 3: Implement the missing helper and refactor `main.py` to consume it**

```python
def resolve_history_messages(session_messages, injected_history=None):
    source = injected_history if injected_history is not None else session_messages
    return [dict(message) for message in source]
```

`backend/main.py` changes:

- Import `build_context`, `build_query_texts`, and `resolve_history_messages`.
- Replace direct reads of `state["messages"]` in retrieval prep with `history_messages = resolve_history_messages(state["messages"])`.
- Change `build_context(state, request.question)` to `build_context(history_messages, request.question)`.
- Add Pydantic input model:

```python
class HistoryMessage(BaseModel):
    role: str
    content: str


class EvalChatRequest(BaseModel):
    question: str
    history: List[HistoryMessage] = []
    top_k: Optional[int] = TOP_K
    session_id: Optional[str] = None
```

- Add a private endpoint:

```python
@app.post("/api/eval/chat", response_model=ChatResponse)
async def eval_chat(request: EvalChatRequest):
    history_messages = [message.model_dump() for message in request.history]
    top_k = min(request.top_k or TOP_K, 10)
    query_texts = build_query_texts(history_messages, request.question)
    sources, context_parts = retrieve_chunks(query_texts, top_k)
    context_str = "\n\n---\n\n".join(context_parts) if context_parts else ""
    user_content = build_context(history_messages, request.question)
    if context_str:
        user_content = f"【检索到的参考资料】\n{context_str}\n\n{user_content}"
    else:
        user_content += "\n\n（未检索到任何相关参考资料）"
    response = await async_llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=4000,
        stream=False,
    )
    answer = response.choices[0].message.content or ""
    return ChatResponse(
        answer=answer,
        sources=sources,
        session_id=request.session_id or "eval",
    )
```

- [ ] **Step 4: Run helper tests to verify the refactor stays green**

Run: `python -m unittest tests.test_chat_logic -v`  
Expected: PASS

- [ ] **Step 5: Compile the backend entrypoint**

Run: `python -m py_compile backend/main.py backend/chat_logic.py tests/test_chat_logic.py`  
Expected: no output, exit code 0

## Task 3: Document and verify feasibility constraints

**Files:**
- Modify: `docs/evals/2026-04-01-medical-agent-eval-datasets.md`
- Optional Modify: `backend/requirements.txt`

- [ ] **Step 1: Record the runtime constraint discovered during local validation**

Add a short note that the current local Python environment is missing:

- `fastapi`
- `openai`
- `chromadb`
- `pydantic`

This blocks full HTTP runtime validation until backend dependencies are installed.

- [ ] **Step 2: Run the verification commands and capture the result**

Run:

```bash
python -m unittest tests.test_chat_logic -v
python -m py_compile backend/main.py backend/chat_logic.py tests/test_chat_logic.py
```

Expected:

- unit tests: PASS
- syntax compile: PASS

- [ ] **Step 3: State the remaining end-to-end validation command**

Once dependencies are installed, run:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Then exercise:

```bash
curl -X POST http://127.0.0.1:8000/api/eval/chat \
  -H "Content-Type: application/json" \
  -d "{\"history\":[{\"role\":\"user\",\"content\":\"我发烧两天了\"},{\"role\":\"assistant\",\"content\":\"还有哪些症状？\"}],\"question\":\"现在需要去急诊吗？\"}"
```

Expected:

- HTTP 200
- JSON answer body
- no session mutation required for the eval call

## Self-Review

- Scope stays focused on history injection and automated eval compatibility.
- The plan avoids unnecessary framework churn and keeps SSE chat behavior intact.
- Testing is realistic for the current environment because it does not assume `pytest` or backend dependencies are already installed.
