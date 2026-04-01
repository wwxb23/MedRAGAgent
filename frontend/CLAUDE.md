[根目录](../CLAUDE.md) > **frontend**

# Frontend - React 聊天界面

## 变更记录 (Changelog)

| 时间 | 操作 | 说明 |
|------|------|------|
| 2026-03-31 21:17:53 | 初始化生成 | 首次扫描生成 |

---

## 模块职责

提供用户交互界面，包括：医学问题输入、SSE 流式回答展示（Markdown 渲染）、引用来源展示、会话管理（新建/切换对话）。采用 Dark Glassmorphism 深色毛玻璃视觉风格。

---

## 入口与启动

- **入口文件**: `src/index.js` - React 18 `createRoot` 挂载
- **主组件**: `src/app.js` - 单文件 SPA，包含全部业务逻辑
- **HTML 模板**: `public/index.html` - 中文 lang 属性
- **启动命令**: `npm start`（react-scripts）
- **构建命令**: `npm run build`

---

## 对外接口

前端调用后端 API：
- `POST /api/chat` - 发送问题，接收 SSE 流式回答
- 通过 `REACT_APP_API_BASE` 环境变量配置 API 基础 URL（默认为空，即同源）

---

## 关键依赖与配置

### 依赖（package.json）

| 依赖 | 版本 | 用途 |
|------|------|------|
| `react` | ^18.3.1 | UI 框架 |
| `react-dom` | ^18.3.1 | DOM 渲染 |
| `react-markdown` | ^9.0.1 | Markdown 渲染 |
| `react-scripts` | 5.0.1 | CRA 脚手架 |
| `lucide-react` | ^0.468.0 | 图标库（声明但未在代码中使用） |
| `remark-gfm` | (隐式) | GFM 表格/任务列表支持 |
| `rehype-raw` | (隐式) | 允许 HTML 标签 |
| `rehype-sanitize` | (隐式) | HTML 安全过滤 |

### 构建工具

- `react-scripts`（CRA）用于生产构建
- `devDependencies` 中声明了 `vite` ^8.0.3 和 `@vitejs/plugin-react`（可能计划迁移）

### 环境变量

- `.env`: `INLINE_RUNTIME_CHUNK=false`（避免内联 JS，利于 Nginx sub_filter）

### Docker 构建

- 多阶段构建：Node 20 Alpine 构建 -> Nginx Alpine 运行
- 构建后去除文件名 content hash（`main.[hash].js` -> `main.js`）
- Nginx 配置：API 代理到 `backend:8000`，SSE 禁用 buffering

---

## 数据模型

### 前端状态（React useState）

- `messages: Array<{role, content, sources?, id?, model?}>` - 聊天消息列表
- `input: string` - 输入框内容
- `loading: boolean` - 加载状态
- `sessionId: string` - 会话 ID（localStorage 持久化）

### SSE 解析

按 `\n\n` 分帧，支持三种事件类型：
- `meta` - 设置引用来源和模型名
- `delta` - 追加文本内容
- `error` - 显示错误信息
- `[DONE]` - 流结束标记

---

## 测试与质量

**当前无测试文件。** `package.json` 声明了 `react-scripts test` 但未发现测试用例。

建议添加：
- 组件渲染测试（`App` 初始欢迎页、消息列表）
- SSE 解析逻辑单元测试
- 用户交互测试（发送消息、新建对话）

---

## 常见问题 (FAQ)

**Q: `lucide-react` 声明了但似乎未使用？**
A: 在 `package.json` 中声明但当前 `app.js` 未 import，可能是历史遗留或计划使用。

**Q: 为什么 Dockerfile 中要去除 content hash？**
A: 使文件名固定为 `main.js` / `main.css`，便于 Nginx `sub_filter` 等运行时替换操作。

**Q: `src/fix_md.js` 是什么？**
A: 一个 Node.js 脚本，用于对旧版 `App.js` 打 Markdown 表格渲染补丁。当前版本已使用 `react-markdown` 库，此文件不再需要。

---

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `src/app.js` | 主应用组件（当前版本，ReactMarkdown + SSE） |
| `src/index.js` | React 入口 |
| `src/App.css` | 全局样式（Dark Glassmorphism） |
| `src/fix_md.js` | 旧版 Markdown 补丁脚本（已废弃） |
| `public/index.html` | HTML 模板 |
| `build/questions.json` | 示例问题列表（旧版用，当前版本内置于代码） |
| `package.json` | 依赖与脚本 |
| `Dockerfile` | 多阶段 Docker 构建 |
| `nginx.conf` | Nginx 配置（API 代理 + SPA fallback） |
| `.env` | 构建环境变量 |
