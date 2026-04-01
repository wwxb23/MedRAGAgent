import React, { useState, useRef, useEffect } from 'react';
import './App.css';
// 使用专门库增加 Markdown 渲染能力。
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
// 支持模型输出中的原生 HTML，并用 sanitize 约束可渲染标签与属性。
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';

const API_BASE = (process.env.REACT_APP_API_BASE || '').trim();

const generateSessionId = () =>
  Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 9);

const getOrCreateSessionId = () => {
  let sid = localStorage.getItem('med_rag_session_id');
  if (!sid) {
    sid = generateSessionId();
    localStorage.setItem('med_rag_session_id', sid);
  }
  return sid;
};

const EXAMPLE_QUESTIONS = [
  '孩子3天前开始发热咳嗽，咳嗽越来越重，精神也不太好，该怎么办？',
  '家里老人说胸闷喘不上气，走路快了就更严重，休息能好一些，是什么问题？',
  '38岁女性体检发现HPV16阳性，TCT正常，下一步怎么处理？',
  '这个月体重下降了很多，而且总是口干想喝水，是不是有什么问题？',
  '5岁孩子身上起了疹子，摸着烫烫的，眼睛也红红的，这是什么情况？'
];

const sanitizeSchema = {
  ...defaultSchema,
  // 为医疗问答常见结构放开表格标签。
  tagNames: [...(defaultSchema.tagNames || []), 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
  attributes: {
    ...(defaultSchema.attributes || {}),
    // 允许安全链接属性，统一使用新窗口打开策略。
    a: [...((defaultSchema.attributes && defaultSchema.attributes.a) || []), 'target', 'rel']
  }
};


const markdownComponents = {
  // 避免当前页面被跳转离开。
  a: ({ href, children, ...props }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    >
      {children}
    </a>
  )
};

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => getOrCreateSessionId());
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const startNewConversation = () => {
    const newSid = generateSessionId();
    localStorage.setItem('med_rag_session_id', newSid);
    setSessionId(newSid);
    setMessages([]);
    setInput('');
  };

  const sendMessage = async (text) => {
    const question = text || input.trim();
    if (!question || loading) return;

    setInput('');
    setLoading(true);

    const userMsg = { role: 'user', content: question };
    setMessages((prev) => [...prev, userMsg]);

    const assistantMsgId = Date.now();
    setMessages((prev) => [
      ...prev,
      {
        role: 'assistant',
        content: '',
        sources: [],
        id: assistantMsgId,
        // 前端默认模型名改为 claude-sonnet-4-6。
        model: 'claude-sonnet-4-6'
      }
    ]);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k: 5, session_id: sessionId })
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!response.body) throw new Error('未收到流式响应体');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 按 SSE 协议使用空行分帧，避免 JSON 被截断解析。
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';

        for (const frame of frames) {
          const line = frame.trim();
          if (!line.startsWith('data: ')) continue;

          const jsonStr = line.replace('data: ', '').trim();
          if (jsonStr === '[DONE]') continue;

          let data;
          try {
            data = JSON.parse(jsonStr);
          } catch (_) {
            continue;
          }

          if (data.type === 'meta') {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      sources: data.sources || [],
                      // 优先使用后端返回模型名，否则回退到前端默认值。
                      model: data.model || m.model || 'claude-sonnet-4-6'
                    }
                  : m
              )
            );
          } else if (data.type === 'delta') {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: (m.content || '') + (data.delta || '') }
                  : m
              )
            );
          } else if (data.type === 'error') {
            throw new Error(data.message || '流式返回错误');
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, role: 'error', content: `请求失败: ${err.message}` }
            : m
        )
      );
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleExampleClick = (q) => {
    sendMessage(q);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <div className="header-icon">🏥</div>
          <div>
            <h1>卫健委诊疗指南智能问答</h1>
            <p className="header-sub">RAG + Claude 大模型 · 严格依据指南原文</p>
          </div>
        </div>
        <div className="header-actions">
          <a className="home-btn" href="/">🏠 主页</a>
          {messages.length > 0 && (
            <button className="new-chat-btn" onClick={startNewConversation}>
              ↺ 新对话
            </button>
          )}
          <span className="header-badge">NHC RAG v1.0</span>
        </div>
      </header>

      <main className="main">
        {messages.length === 0 ? (
          <div className="welcome">
            <div className="welcome-icon">📋</div>
            <h2>卫健委指南智能问答</h2>
            <p>基于卫健委诊疗指南 PDF 构建，使用向量检索 + Claude 大模型进行问答</p>
            <p className="welcome-note">⚠️ 仅供参考，不能替代专业医疗建议</p>
            <div className="examples">
              <p className="examples-label">试试这些问题</p>
              {EXAMPLE_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  className="example-btn"
                  onClick={() => handleExampleClick(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages">
            {messages.map((msg, i) => (
              <div key={i} className={`message message-${msg.role}`}>
                {msg.role === 'user' && <div className="avatar avatar-user">👤</div>}
                {msg.role === 'assistant' && <div className="avatar avatar-bot">🤖</div>}
                {msg.role === 'error' && <div className="avatar avatar-error">⚠️</div>}
                <div className="message-body">
                  {msg.role === 'assistant' && (
                    <span className="model-tag">
                      智能助手 ({msg.model || 'claude-sonnet-4-6'})
                    </span>
                  )}
                  <div className="message-content">
                    {/* 使用 Markdown + GFM + 受控 HTML 渲染，替代危险 innerHTML。 */}
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
                      components={markdownComponents}
                    >
                      {msg.content || ''}
                    </ReactMarkdown>
                  </div>
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="sources">
                      <div className="sources-header">📚 引用来源 ({msg.sources.length})</div>
                      {msg.sources.map((src, k) => (
                        <div key={k} className="source-item">
                          <span className="source-file">📄 {src.source}</span>
                          <span className="source-page">第 {src.page} 页</span>
                          <p className="source-text">{src.text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && !messages[messages.length - 1]?.content && (
              <div className="message message-assistant loading-message">
                <div className="message-body loading-body">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span className="thinking-text">正在检索指南并生成回答...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      <footer className="footer">
        <div className="input-container">
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              className="input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入您的医学问题..."
              rows={1}
              disabled={loading}
            />
          </div>
          <button
            className="send-btn"
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
          >
            发送 ✨
          </button>
        </div>
        <p className="disclaimer">
          ⚠️ 本系统仅供医学知识查询参考，不构成任何医疗诊断或治疗建议。如有健康问题，请咨询专业医生。
        </p>
      </footer>
    </div>
  );
}

export default App;
