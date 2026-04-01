[根目录](../CLAUDE.md) > **backend**

# Backend - FastAPI RAG 服务

## 变更记录 (Changelog)

| 时间 | 操作 | 说明 |
|------|------|------|
| 2026-03-31 21:17:53 | 初始化生成 | 首次扫描生成 |

---

## 模块职责

提供 RAG（检索增强生成）API 服务，核心流程：接收用户问题 -> 向量检索卫健委指南片段 -> 构建上下文 -> 调用 LLM 生成回答（SSE 流式输出） -> 管理多轮会话记忆。

---

## 入口与启动

- **主入口**: `main.py` - FastAPI 应用，`uvicorn.run(app, host="0.0.0.0", port=8000)`
- **数据摄入脚本**: `ingest.py` - PDF 解析 -> 分块 -> Embedding -> ChromaDB 存储
- **备份文件**: `main.py.bak` - 旧版本（使用 Qwen-Max 模型，非流式响应）

---

## 对外接口

| 方法 | 路径 | 请求体 / 参数 | 响应 | 说明 |
|------|------|----------------|------|------|
| POST | `/api/chat` | `{question, top_k?, session_id?}` | SSE 流：`meta` -> `delta`* -> `done` | RAG 聊天，流式输出 |
| DELETE | `/api/session/{session_id}` | 路径参数 | `{status, session_id}` | 清除会话 |
| GET | `/api/session/{session_id}/summary` | 路径参数 | `{session_id, summary, messages_count, unsummarized}` | 会话摘要 |
| GET | `/api/stats` | 无 | `{collection, chunk_count, sources[]}` | 向量库统计 |
| GET | `/api/health` | 无 | `{status, collection_count, model, embedding_model, active_sessions}` | 健康检查 |

### SSE 事件流格式

```
data: {"type": "meta", "sources": [...], "model": "...", "session_id": "..."}

data: {"type": "delta", "delta": "文本片段"}
...（多个 delta）

data: {"type": "done", "answer": "完整回答", "sources": [...], ...}

data: [DONE]
```

---

## 关键依赖与配置

### Python 依赖

- `fastapi` - Web 框架
- `openai` - OpenAI 兼容客户端（用于 DashScope 和 yunwu.ai）
- `chromadb` - 向量数据库
- `pdfplumber` - PDF 文本与表格提取（仅 ingest.py）
- `pydantic` - 数据验证
- `python-dotenv` - 环境变量加载

### 配置常量（main.py）

| 常量 | 值 | 说明 |
|------|-----|------|
| `LLM_MODEL` | `claude-sonnet-4-6` | 聊天用 LLM 模型 |
| `EMBEDDING_MODEL` | `text-embedding-v3` | DashScope Embedding 模型 |
| `TOP_K` | 8 | 默认检索 chunk 数 |
| `MAX_HISTORY_MESSAGES` | 999 | 不限历史消息数 |
| `SUMMARIZE_AFTER` | 999 | 摘要功能实质已禁用 |
| `SESSION_TTL_SECONDS` | 3600 | 会话过期时间 60 分钟 |

### LLM 客户端

- **同步客户端** (`llm_client`): DashScope API，用于 Embedding
- **异步客户端** (`async_llm_client`): yunwu.ai 代理，用于 Claude 聊天生成

### 网络修复

文件顶部包含 Windows 环境下的网络修复：
- 设置 `NO_PROXY=*` 绕过系统代理
- 强制 IPv4（`socket.getaddrinfo` monkey-patch）避免 IPv6 连接错误

---

## 数据模型

### Pydantic 模型

- `ChatRequest`: `question: str`, `top_k: Optional[int]`, `session_id: Optional[str]`
- `ChatResponse`: `answer: str`, `sources: List[SourceRef]`, `model: str`, `session_id: str`, `session_summary: Optional[str]`
- `SourceRef`: `source: str`, `page: int`, `text: str`
- `StatsResponse`: `collection: str`, `chunk_count: int`, `sources: List[str]`

### 内存会话存储

```python
_session_store: Dict[str, dict]
# 每个 session: {"messages": [...], "summary": "", "unsummarized": 0, "last_access": float}
```

---

## 数据摄入管线（ingest.py）

1. 扫描 `/app/pdfs/nhc-guidelines/` 目录下所有 PDF
2. 使用 `pdfplumber` 提取文本和表格
3. 按段落分块（chunk_size=800, overlap=150）
4. 通过 DashScope API 批量获取 embedding（batch_size=6）
5. 存入 ChromaDB collection `nhc_guidelines`

---

## 测试与质量

**当前无测试文件。** 建议添加：
- API 端点集成测试（`/api/chat`, `/api/health`）
- 向量检索单元测试（mock ChromaDB）
- SSE 流式输出格式验证

---

## 常见问题 (FAQ)

**Q: 为什么 `SUMMARIZE_AFTER` 设为 999？**
A: 当前使用大上下文窗口模型（128k），不需要对历史做摘要压缩。摘要逻辑保留但实质禁用。

**Q: `main.py.bak` 和 `main.py` 的区别？**
A: `.bak` 使用 Qwen-Max 模型 + 非流式响应；当前版本使用 Claude + SSE 流式输出 + AsyncOpenAI。

---

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 主应用（当前版本，Claude + SSE） |
| `main.py.bak` | 旧版本备份（Qwen-Max + 非流式） |
| `ingest.py` | PDF 数据摄入管线 |
| `../chroma_db/` | ChromaDB 持久化数据目录 |
| `../.env` | 环境变量（API 密钥） |
