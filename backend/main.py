"""
卫健委指南 RAG - Backend (FastAPI)
POST /api/chat - RAG chat with multi-turn memory + async summarization
"""
import os
import socket
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI, AsyncOpenAI
import chromadb
from dotenv import load_dotenv

from backend.chat_logic import build_context, build_query_texts, resolve_history_messages

# Fix: Windows system proxy (127.0.0.1:17890) + IPv6 cause connection errors
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only

# Load environment from project root.
# When launched from sandboxed or mirrored working directories on Windows,
# __file__ may not resolve to the real project path, so prefer cwd fallback.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_candidates = [
    os.path.join(project_root, '.env'),
    os.path.join(os.getcwd(), '.env'),
    os.path.join(os.path.dirname(os.getcwd()), '.env'),
]
for dotenv_path in dotenv_candidates:
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        project_root = os.path.dirname(dotenv_path)
        break

# ── Config ────────────────────────────────────────────────────────────────────
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
CHROMA_DIR = os.path.join(project_root, 'chroma_db')
LLM_MODEL = "claude-sonnet-4-6"
EMBEDDING_MODEL = "text-embedding-v3"
TOP_K = 8
MAX_HISTORY_MESSAGES = 999     # no limit: qwen-max 128k context can handle it
SUMMARIZE_AFTER = 999          # disabled: full history every time
SESSION_TTL_SECONDS = 3600     # 60 min TTL
SUMMARY_MODEL = "claude-sonnet-4-6"   # kept for compatibility, not used

# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位兼具极高专业素养与同理心的资深医学顾问。你的任务是接收生硬、学术的指南检索内容，将其转化为通俗易懂、结构清晰且有温度的科普解答。

【绝对忠于原文】
你必须严格基于提供的指南检索内容进行回答。禁止捏造数据、禁止引入指南未提及的治疗方案、禁止脱离原文主观臆断。如指南内容无法回答用户问题，明确说明"抱歉，关于这个问题我尚未检索到充分的指南依据，建议您咨询专业医生"。

【语气与风格】
- 开篇对用户的焦虑或症状表示理解，给予安抚
- 多用短句和场景化标题（配合 Emoji）
- 专业术语保留但必须配合生活化解释
- 危险信号（Red Flags）和"必须立即就医"情况要极度强化

【模块结构（必须全部包含）】

【症状定性与共情】
一句话概括用户的核心症状/疑问，用通俗语言解释这在医学上通常意味着什么，给予初步安抚。

【核心评估标准（💡 指南重点】
将指南中最核心的评估标准、分级判断标准转化为用户可自行对照的 Checklist。

【其他可能性排查（🔍 鉴别诊断】
如指南中提及需鉴别的疾病，用最简练语言列出其典型特征，辅助用户自我判断。

【明确行动指南（🏥 下一步怎么做】
"红线"（什么情况必须立即就医）和"可先观察"的情况分开列出，极具实操性。

【引用溯源（灰色小字】
文末以斜体灰色小字标注所依据的指南名称、文件全称及页码，体现权威性。
"""

# ── Session State Store (in-memory) ─────────────────────────────────────────
# {session_id: {"messages": [...], "summary": "...", "unsummarized": 0, "last_access": time.time()}}
_session_store: Dict[str, dict] = {}
_store_lock = threading.Lock()

# ── Async Background Pool ─────────────────────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=4)
_loop = None
_loop_lock = threading.Lock()

def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None or not _loop.is_running():
            try:
                _loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_loop)
            except RuntimeError:
                _loop = asyncio.get_event_loop()
        return _loop


def _get_or_create_session(session_id: str) -> dict:
    """Get or create a session entry with TTL tracking."""
    with _store_lock:
        now = time.time()
        if session_id not in _session_store:
            _session_store[session_id] = {
                "messages": [],
                "summary": "",
                "unsummarized": 0,
                "last_access": now,
            }
        else:
            _session_store[session_id]["last_access"] = now
        return _session_store[session_id]


def _cleanup_expired():
    """Remove sessions older than SESSION_TTL_SECONDS."""
    now = time.time()
    with _store_lock:
        expired = [sid for sid, s in _session_store.items()
                   if now - s["last_access"] > SESSION_TTL_SECONDS]
        for sid in expired:
            del _session_store[sid]


def _do_summarize(session_id: str, summary: str, messages: List[dict]) -> str:
    """
    Synchronous LLM call to generate a new summary.
    Runs in thread pool (non-blocking for FastAPI).
    """
    if not messages:
        return summary  # nothing to summarize, keep old summary

    # Build the conversation excerpt (last N messages, strip RAG context)
    recent = []
    for m in messages:
        role = "用户" if m["role"] == "user" else "助手"
        recent.append(f"{role}：{m['content'][:300]}")
    conversation_text = "\n".join(recent)

    prompt = (
        f"【旧摘要】（如有）：{summary or '（首次摘要，无旧摘要）'}\n\n"
        f"【最近对话】：\n{conversation_text}\n\n"
        "请基于上述旧摘要和最近对话，生成一个简洁的摘要，"
        "保留所有关键医学事实、疾病名称、药物名称、检验指标、"
        "关键剂量数值及单位、用户意图。"
        "特别注意：如果对话中提到具体剂量（如 mg/kg、ml/kg、g 等），"
        "必须原封不动保留数值和单位！"
        "摘要用中文，不超过200字。"
    )

    client = OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    response = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=400,
    )
    return response.choices[0].message.content


def _schedule_summarize(session_id: str):
    """
    Schedule an async summarization task (fires-and-forgets in thread pool).
    Called after every N turns when unsummarized >= SUMMARIZE_AFTER.
    """
    def _bg_task():
        try:
            # Read current state under lock
            with _store_lock:
                if session_id not in _session_store:
                    return
                state = _session_store[session_id]
                unsummarized = state["unsummarized"]

            if unsummarized < SUMMARIZE_AFTER:
                return

            # Take the oldest SUMMARIZE_AFTER turns as a batch
            with _store_lock:
                if session_id not in _session_store:
                    return
                state = _session_store[session_id]
                msgs = list(state["messages"])
                old_summary = state["summary"]

            # How many pairs to summarize?
            to_summarize = min(unsummarized, len(msgs) // 2)
            if to_summarize <= 0:
                return

            # Grab the oldest N pairs
            batch = msgs[:to_summarize * 2]

            new_summary = _do_summarize(session_id, old_summary, batch)

            with _store_lock:
                if session_id not in _session_store:
                    return
                state = _session_store[session_id]
                # Replace old messages with summarized ones replaced by a marker
                new_messages = [
                    {"role": "system_summary", "content": f"[已摘要] {new_summary}"}
                ] + state["messages"][to_summarize * 2:]
                state["messages"] = new_messages
                state["summary"] = new_summary
                state["unsummarized"] = max(0, state["unsummarized"] - to_summarize)
                state["last_access"] = time.time()

            print(f"[Summary] session={session_id} summarized={to_summarize} pairs, "
                  f"new_summary_len={len(new_summary)}")
        except Exception as e:
            print(f"[Summary ERROR] session={session_id}: {e}")

    _executor.submit(_bg_task)


# ── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(title="卫健委指南 RAG", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm_client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

async_llm_client = AsyncOpenAI(
    api_key="sk-4MatcCp8GWOCNAf92LbCtPCXsRbS5IqL555gxvXenjnC5pLL",
    base_url="https://yunwu.ai/v1"
)

chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = chroma_client.get_collection("nhc_guidelines")


# ── Models ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str
    top_k: Optional[int] = TOP_K
    session_id: Optional[str] = None


class HistoryMessage(BaseModel):
    role: str
    content: str


class SourceRef(BaseModel):
    source: str
    page: int
    text: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceRef]
    model: str = LLM_MODEL
    session_id: str
    session_summary: Optional[str] = None   # sent to frontend for display


class StatsResponse(BaseModel):
    collection: str
    chunk_count: int
    sources: List[str]


class EvalChatRequest(BaseModel):
    question: str
    history: List[HistoryMessage] = Field(default_factory=list)
    top_k: Optional[int] = TOP_K
    session_id: Optional[str] = None


# ── Embedding / Retrieval ─────────────────────────────────────────────────────
def get_embedding(texts: List[str]) -> List[List[float]]:
    all_embeddings = []
    batch_size = 6
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            response = llm_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
                dimensions=1024
            )
            all_embeddings.extend([item.embedding for item in response.data])
        except Exception as e:
            print(f"Embedding error: {e}")
            all_embeddings.extend([[0.0] * 1024 for _ in batch])
    return all_embeddings


def retrieve_chunks(query_texts: List[str], top_k: int) -> tuple[List[SourceRef], List[str]]:
    embeddings = get_embedding(query_texts)
    seen_ids = set()
    sources: List[SourceRef] = []
    context_parts: List[str] = []
    max_chunks = top_k * len(query_texts)

    for emb in embeddings:
        if len(seen_ids) >= max_chunks:
            break
        results = collection.query(
            query_embeddings=[emb],
            n_results=top_k,
            include=["documents", "metadatas", "uris"]
        )
        if not (results["documents"] and results["documents"][0]):
            continue
        for doc, meta, doc_uri in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["uris"][0]
        ):
            if doc_uri in seen_ids or len(seen_ids) >= max_chunks:
                continue
            seen_ids.add(doc_uri)
            sources.append(SourceRef(
                source=meta.get("source", "未知来源"),
                page=meta.get("page", 0),
                text=doc[:300] + "..." if len(doc) > 300 else doc
            ))
            context_parts.append(
                f"【参考资料 {len(context_parts)+1} - {meta.get('source', '未知')} 第{meta.get('page', '?')}页】\n{doc}"
            )
    return sources, context_parts


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _build_user_content(history_messages: List[dict], question: str, context_parts: List[str]) -> str:
    context_str = "\n\n---\n\n".join(context_parts) if context_parts else ""
    user_content = build_context(history_messages, question)

    if context_str:
        return f"【检索到的参考资料】\n{context_str}\n\n{user_content}"

    return user_content + "\n\n（未检索到任何相关参考资料）"


def _prepare_chat_messages(question: str, history_messages: List[dict], top_k: int):
    query_texts = build_query_texts(history_messages, question)
    sources, context_parts = retrieve_chunks(query_texts, top_k)
    user_content = _build_user_content(history_messages, question, context_parts)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    source_payload = [
        {"source": s.source, "page": s.page, "text": s.text}
        for s in sources
    ]
    return messages, sources, source_payload


async def _generate_full_answer(messages: List[dict]) -> str:
    response = await async_llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=4000,
        stream=False,
    )
    return response.choices[0].message.content or ""


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    RAG chat with multi-turn memory + async summarization.
    Flow: read session → build context → retrieve → generate → update store → trigger summary
    """
    try:
        # Cleanup expired sessions occasionally (not on every request)
        if len(_session_store) > 100 and int(time.time()) % 20 == 0:
            _cleanup_expired()

        session_id = request.session_id or "default"
        state = _get_or_create_session(session_id)
        top_k = min(request.top_k or TOP_K, 10)
        history_messages = resolve_history_messages(state["messages"])
        messages, sources, source_payload = _prepare_chat_messages(
            request.question,
            history_messages,
            top_k,
        )

        async def event_generator():
            full_answer = ""
            try:
                yield f"data: {json.dumps({'type': 'meta', 'sources': source_payload, 'model': LLM_MODEL, 'session_id': session_id}, ensure_ascii=False)}\n\n"

                response = await async_llm_client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=4000,
                    stream=True,
                )

                async for chunk in response: # 使用 async for 迭代异步流
                    if not chunk.choices or not chunk.choices[0].delta:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    delta = delta.replace('\n', '\n')  # 将 \n 文本转为真实换行
                    full_answer += delta
                    yield f"data: {json.dumps({'type': 'delta', 'delta': delta}, ensure_ascii=False)}\n\n"

                with _store_lock:
                    curr_state = _session_store.get(session_id)
                    if curr_state:
                        curr_state["messages"].append({"role": "user", "content": request.question})
                        curr_state["messages"].append({"role": "assistant", "content": full_answer})
                        curr_state["unsummarized"] += 1
                        curr_state["last_access"] = time.time()

                        if SUMMARIZE_AFTER < 999 and curr_state["unsummarized"] >= SUMMARIZE_AFTER:
                            _schedule_summarize(session_id)

                yield f"data: {json.dumps({'type': 'done', 'answer': full_answer, 'sources': source_payload, 'model': LLM_MODEL, 'session_id': session_id}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/eval/chat", response_model=ChatResponse)
async def eval_chat(request: EvalChatRequest):
    """Private non-streaming endpoint for automated benchmark samplers."""
    try:
        history_messages = resolve_history_messages(
            [],
            [_model_to_dict(message) for message in request.history],
        )
        top_k = min(request.top_k or TOP_K, 10)
        messages, sources, _ = _prepare_chat_messages(
            request.question,
            history_messages,
            top_k,
        )
        answer = await _generate_full_answer(messages)
        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=request.session_id or "eval",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    """Clear all memory for a session."""
    with _store_lock:
        _session_store.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}


@app.get("/api/session/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Return the current summary for a session (if any)."""
    with _store_lock:
        state = _session_store.get(session_id)
    if not state:
        return {"session_id": session_id, "summary": "", "messages_count": 0}
    return {
        "session_id": session_id,
        "summary": state.get("summary", ""),
        "messages_count": len(state.get("messages", [])),
        "unsummarized": state.get("unsummarized", 0),
    }


@app.get("/api/stats", response_model=StatsResponse)
async def stats():
    """Return vector store statistics."""
    chunk_count = collection.count()
    result = collection.get(include=["metadatas"])
    unique_sources = sorted(set(
        m.get("source", "未知来源")
        for m in result["metadatas"] if m
    ))
    return StatsResponse(
        collection="nhc_guidelines",
        chunk_count=chunk_count,
        sources=unique_sources,
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "collection_count": collection.count(),
        "model": LLM_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "active_sessions": len(_session_store),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
