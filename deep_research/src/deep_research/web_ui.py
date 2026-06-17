"""内嵌 Web UI：单文件 HTML/CSS/JS。

设计：
  - 移动端优先布局（< 480px / < 900px 分层布局）
  - 顶部三栏 Tab：Setup / Research / Sandbox
  - Setup 栏：硬件检测 → 模型选择 → 下载 SSE 进度 → 启动服务
  - Research 栏：一键研究 + 实时 SSE 进度
  - Sandbox 栏：搜索沙箱调试
"""
from __future__ import annotations


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<meta name="theme-color" content="#0f172a">
<title>Deep Research · 超级并行研究</title>
<style>
  :root {
    --bg: #0b1020;
    --surface: #131a2e;
    --surface-2: #1a2442;
    --border: #2a3558;
    --text: #e8eefb;
    --text-dim: #9aa6c7;
    --accent: #6366f1;
    --accent-2: #22d3ee;
    --success: #22c55e;
    --warn: #f59e0b;
    --danger: #ef4444;
    --radius: 12px;
    --radius-sm: 8px;
    --shadow: 0 4px 24px rgba(0,0,0,0.35);
    font-size: 16px;
  }

  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body { margin: 0; padding: 0; }
  body {
    background:
      radial-gradient(1200px 600px at 10% -10%, #1e2a55 0%, transparent 60%),
      radial-gradient(800px 500px at 110% 110%, #1a3a4a 0%, transparent 55%),
      var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.55;
    min-height: 100vh;
    padding-bottom: 80px;
  }

  header {
    padding: 20px 16px 8px;
    text-align: center;
  }
  header h1 {
    font-size: 1.35rem;
    margin: 0 0 4px;
    background: linear-gradient(135deg, #a5b4fc 0%, #22d3ee 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    letter-spacing: 0.5px;
  }
  header .sub {
    color: var(--text-dim);
    font-size: 0.82rem;
  }

  /* 底部 Tabs */
  nav.tabs {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(11, 16, 32, 0.88);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-top: 1px solid var(--border);
    display: flex;
    z-index: 100;
  }
  nav.tabs button {
    flex: 1;
    background: transparent;
    color: var(--text-dim);
    border: 0;
    padding: 14px 8px 18px;
    font-size: 0.82rem;
    cursor: pointer;
    transition: color 0.2s, background 0.2s;
    position: relative;
    font-weight: 500;
    font-family: inherit;
  }
  nav.tabs button .icon {
    display: block;
    font-size: 1.25rem;
    margin-bottom: 2px;
  }
  nav.tabs button.active {
    color: var(--accent-2);
  }
  nav.tabs button.active::before {
    content: "";
    position: absolute;
    top: 0; left: 50%;
    transform: translateX(-50%);
    width: 32px; height: 3px;
    background: var(--accent-2);
    border-radius: 0 0 4px 4px;
  }
  nav.tabs button:hover { background: rgba(255,255,255,0.03); }

  /* 主要内容卡片 */
  .panel {
    max-width: 760px;
    margin: 14px auto;
    padding: 0 14px;
    display: none;
  }
  .panel.active { display: block; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    box-shadow: var(--shadow);
    margin-bottom: 14px;
  }
  .card h2 {
    margin: 0 0 12px;
    font-size: 1rem;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .card h2 .tag {
    background: var(--surface-2);
    color: var(--text-dim);
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 400;
    border: 1px solid var(--border);
  }

  /* 环境检测 */
  .env-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
  }
  .env-item {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px;
    text-align: center;
  }
  .env-item .label {
    font-size: 0.72rem;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .env-item .value {
    font-size: 0.95rem;
    font-weight: 600;
    margin-top: 3px;
    color: var(--text);
    word-break: break-all;
  }

  /* 模型卡片列表 */
  .model-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .model-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: border-color 0.2s;
  }
  .model-card.active { border-color: var(--accent); }
  .model-card .row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
  }
  .model-card .name {
    font-weight: 600;
    font-size: 0.95rem;
  }
  .model-card .meta {
    color: var(--text-dim);
    font-size: 0.78rem;
    margin-top: 3px;
  }
  .model-card .size-pill {
    background: rgba(99, 102, 241, 0.15);
    color: #a5b4fc;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    white-space: nowrap;
    border: 1px solid rgba(99, 102, 241, 0.3);
  }
  .model-card .recommend {
    display: inline-block;
    margin-left: 6px;
    background: linear-gradient(135deg, #f59e0b, #ef4444);
    color: #fff;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
  }

  /* 按钮 */
  button.btn {
    background: linear-gradient(135deg, var(--accent) 0%, #7c3aed 100%);
    color: #fff;
    border: 0;
    padding: 11px 16px;
    border-radius: var(--radius-sm);
    font-size: 0.88rem;
    cursor: pointer;
    font-weight: 600;
    transition: transform 0.1s, opacity 0.2s;
    font-family: inherit;
    width: 100%;
  }
  button.btn:hover { transform: translateY(-1px); }
  button.btn:active { transform: translateY(0); }
  button.btn:disabled { opacity: 0.5; cursor: not-allowed; }
  button.btn.secondary {
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--text);
  }
  button.btn.success {
    background: linear-gradient(135deg, var(--success) 0%, #15803d 100%);
  }
  button.btn.danger {
    background: linear-gradient(135deg, var(--danger) 0%, #991b1b 100%);
  }

  .btn-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .btn-row button.btn { flex: 1; min-width: 100px; }

  /* 下载进度 */
  .progress-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: rgba(99, 102, 241, 0.08);
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: var(--radius-sm);
    padding: 10px;
  }
  .progress-bar {
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    overflow: hidden;
  }
  .progress-bar > div {
    height: 100%;
    background: linear-gradient(90deg, var(--accent) 0%, var(--accent-2) 100%);
    border-radius: 4px;
    transition: width 0.3s;
  }
  .progress-info {
    display: flex;
    justify-content: space-between;
    font-size: 0.78rem;
    color: var(--text-dim);
  }

  /* 状态标记 */
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-left: auto;
  }
  .badge.ready { background: rgba(34, 197, 94, 0.15); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.3); }
  .badge.running { background: rgba(34, 197, 94, 0.15); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.3); animation: pulse 2s ease infinite; }
  .badge.downloading { background: rgba(245, 158, 11, 0.15); color: var(--warn); border: 1px solid rgba(245, 158, 11, 0.3); }
  .badge.notready { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  /* 输入框 */
  textarea, input[type="text"] {
    width: 100%;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px;
    color: var(--text);
    font-size: 0.95rem;
    font-family: inherit;
    resize: vertical;
    min-height: 90px;
    transition: border-color 0.2s;
  }
  textarea:focus, input[type="text"]:focus {
    outline: none;
    border-color: var(--accent-2);
    box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.1);
  }

  /* 选项 */
  .options {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    flex-wrap: wrap;
  }
  .options label {
    flex: 1;
    min-width: 120px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px;
    text-align: center;
    font-size: 0.82rem;
    color: var(--text-dim);
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
  }
  .options input[type="radio"] { display: none; }
  .options input[type="radio"]:checked + span {
    color: var(--accent-2);
  }
  .options label:has(input[type="radio"]:checked) {
    border-color: var(--accent-2);
    background: rgba(34, 211, 238, 0.08);
    color: var(--accent-2);
  }

  /* 步骤时间线 */
  .timeline {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .step {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: 0.88rem;
    opacity: 0.5;
    transition: opacity 0.3s, border-color 0.2s;
  }
  .step.done { opacity: 1; border-color: rgba(34, 197, 94, 0.4); }
  .step.active { opacity: 1; border-color: var(--accent); background: rgba(99, 102, 241, 0.08); }
  .step .dot {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    font-weight: 700;
    flex-shrink: 0;
  }
  .step.done .dot { background: var(--success); color: #fff; }
  .step.active .dot { background: var(--accent); color: #fff; animation: pulse 1.5s ease infinite; }

  /* 报告渲染 */
  .report {
    line-height: 1.7;
  }
  .report h1, .report h2, .report h3 {
    margin-top: 22px;
    margin-bottom: 8px;
    line-height: 1.3;
  }
  .report h1 { font-size: 1.35rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .report h2 { font-size: 1.15rem; color: var(--accent-2); }
  .report h3 { font-size: 1rem; }
  .report p { margin: 10px 0; }
  .report code { background: var(--surface-2); padding: 2px 6px; border-radius: 4px; font-size: 0.85em; }
  .report pre { background: var(--surface-2); padding: 12px; border-radius: var(--radius-sm); overflow-x: auto; border: 1px solid var(--border); }
  .report pre code { background: none; padding: 0; }
  .report ul, .report ol { padding-left: 22px; margin: 10px 0; }
  .report li { margin: 4px 0; }
  .report blockquote { border-left: 3px solid var(--accent); padding: 4px 12px; color: var(--text-dim); margin: 10px 0; }
  .report a { color: var(--accent-2); }
  .report table { border-collapse: collapse; margin: 12px 0; width: 100%; }
  .report th, .report td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
  .report th { background: var(--surface-2); }

  /* 加载动画 */
  .spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid var(--text-dim);
    border-top-color: var(--accent-2);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* 空状态 */
  .empty {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-dim);
    font-size: 0.9rem;
  }
  .empty .big-icon {
    font-size: 2.5rem;
    opacity: 0.4;
    display: block;
    margin-bottom: 10px;
  }

  /* 桌面放大 */
  @media (min-width: 760px) {
    :root { font-size: 17px; }
    nav.tabs button { padding: 16px 8px; }
    header { padding: 40px 16px 20px; }
    header h1 { font-size: 1.8rem; }
  }

  /* Toast 通知 */
  .toast {
    position: fixed;
    top: 14px;
    left: 50%;
    transform: translateX(-50%) translateY(-60px);
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 10px 16px;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow);
    z-index: 200;
    transition: transform 0.3s;
    max-width: 90%;
    text-align: center;
    font-size: 0.88rem;
  }
  .toast.show { transform: translateX(-50%) translateY(0); }
  .toast.success { border-color: rgba(34, 197, 94, 0.4); }
  .toast.error { border-color: rgba(239, 68, 68, 0.4); }

  details {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    margin-bottom: 8px;
  }
  details[open] { padding-bottom: 14px; }
  summary {
    cursor: pointer;
    font-weight: 600;
    color: var(--text);
    font-size: 0.9rem;
    outline: none;
    user-select: none;
  }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "▶ "; display: inline-block; transition: transform 0.2s; font-size: 0.7rem; color: var(--accent-2); }
  details[open] summary::before { transform: rotate(90deg); }
  details .content { margin-top: 10px; color: var(--text-dim); font-size: 0.85rem; }
  details .content b { color: var(--text); }

  /* 推理后端选择器 */
  .backend-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .backend-label {
    font-size: 0.78rem;
    color: var(--text-dim);
    white-space: nowrap;
  }
  .be-label {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--text-dim);
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }
  .be-label:hover { border-color: var(--accent-2); color: var(--text); }
  .be-label.active {
    background: rgba(99, 102, 241, 0.18);
    border-color: var(--accent);
    color: var(--accent-2);
  }
  .be-label.active:hover { border-color: var(--accent-2); }
</style>
</head>
<body>

<header>
  <h1>⚡ Deep Research</h1>
  <div class="sub">多智能体并行搜索 · 本地部署 · 沙箱检索</div>
</header>

<!-- Setup 面板 -->
<section class="panel active" id="panel-setup">

  <div class="card">
    <h2>🖥️ 环境检测 <span class="tag" id="env-loading">加载中...</span></h2>
    <div id="env-grid" class="env-grid"></div>
  </div>

  <div class="card">
    <h2>🧠 选择模型</h2>
    <div style="color: var(--text-dim); font-size: 0.88rem; margin-bottom: 12px;">
      根据你的硬件自动推荐。手机端请选择 <b>Qwen3 1.7B</b> 以获得流畅体验。
    </div>
    <div class="model-list" id="model-list"></div>
  </div>

  <div class="card" id="running-card" style="display:none">
    <h2>🔄 当前运行状态</h2>
    <div id="running-info" style="font-size: 0.9rem;"></div>
    <div style="height: 10px;"></div>
    <div class="btn-row">
      <button class="btn danger" onclick="stopModel()">停止服务</button>
    </div>
  </div>

  <div class="card">
    <h2>💡 下一步</h2>
    <div id="next-step">请先选择并启动一个模型</div>
  </div>

</section>

<!-- Research 面板 -->
<section class="panel" id="panel-research">

  <div class="card">
    <h2>🔎 开始研究 <span class="tag" id="research-mode-tag">本地模式</span></h2>
    <textarea id="question" placeholder="输入你想研究的问题，例如："量子计算在未来20年对全球银行业的系统性影响路径分析""></textarea>
    <div class="options">
      <label><input type="radio" name="depth" value="quick"><span>快速 · ~3分钟</span></label>
      <label><input type="radio" name="depth" value="normal" checked><span>标准 · ~10分钟</span></label>
      <label><input type="radio" name="depth" value="deep"><span>深度 · ~30分钟</span></label>
    </div>
    <div style="height: 12px;"></div>
    <div class="options">
      <label><input type="radio" name="locale" value="zh-CN" checked><span>中文</span></label>
      <label><input type="radio" name="locale" value="en-US"><span>English</span></label>
      <label><input type="radio" name="mode" value="local" checked><span>本地搜索</span></label>
      <label><input type="radio" name="mode" value="cloud"><span>云端搜索</span></label>
    </div>
    <div style="height: 14px;"></div>
    <button class="btn" id="start-btn" onclick="startResearch()">🚀 开始研究</button>
  </div>

  <div class="card" id="progress-card" style="display:none">
    <h2>⚡ 实时进度 <span class="badge running" id="run-status-badge">运行中</span></h2>
    <div class="timeline" id="timeline"></div>
  </div>

  <div class="card" id="report-card" style="display:none">
    <h2>📄 研究报告</h2>
    <div class="report" id="report"></div>
  </div>

</section>

<!-- Sandbox 面板 -->
<section class="panel" id="panel-sandbox">

  <div class="card">
    <h2>🔬 搜索沙箱测试</h2>
    <div style="color: var(--text-dim); font-size: 0.88rem; margin-bottom: 12px;">
      多搜索引擎并行检索，每个源独立超时隔离，失败不阻塞整体。
    </div>
    <input type="text" id="sandbox-q" placeholder="搜索关键词..." style="margin-bottom: 10px;">
    <button class="btn" onclick="runSandbox()">并行搜索</button>
  </div>

  <div class="card" id="sandbox-result-card" style="display:none">
    <h2>📊 结果</h2>
    <div id="sandbox-summary" style="margin-bottom: 12px;"></div>
    <div id="sandbox-details"></div>
  </div>

</section>

<!-- Tab 导航 -->
<nav class="tabs">
  <button class="active" data-target="setup"><span class="icon">⚙️</span>Setup</button>
  <button data-target="research"><span class="icon">🔎</span>Research</button>
  <button data-target="sandbox"><span class="icon">🔬</span>Sandbox</button>
</nav>

<div class="toast" id="toast"></div>

<!-- marked.js: 轻量 Markdown 渲染 -->
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

<script>
// ====================== 状态 ======================
let currentRunId = null;
let currentEventSource = null;
let runningModelServer = null; // {model_id, model_name, base_url}

// ====================== Toast ======================
function toast(msg, type = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show " + type;
  setTimeout(() => t.classList.remove("show"), 2800);
}

// ====================== Tab 切换 ======================
document.querySelectorAll("nav.tabs button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav.tabs button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    document.getElementById("panel-" + btn.dataset.target).classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});

// ====================== 环境检测 ======================
async function loadEnv() {
  document.getElementById("env-loading").textContent = "加载中...";
  try {
    const data = await fetch("/status").then(r => r.json());
    const grid = document.getElementById("env-grid");
    const items = [
      { label: "CPU Cores", value: data.hardware?.cpu_count || "?" },
      { label: "RAM", value: data.hardware?.ram_gb ? data.hardware.ram_gb + " GB" : "?" },
      { label: "GPU", value: data.hardware?.has_gpu ? "✓ " + (data.hardware.gpu_names?.[0] || data.hardware.gpu_type || "") : "—" },
      { label: "平台", value: data.hardware?.platform || (data.hardware?.system + " " + (data.hardware?.machine || "")) },
      { label: "本地 LLM", value: data.local_llm_running ? "✓ 运行中" : "未启动" },
      { label: "可用模型", value: (data.models_available || []).length },
    ];
    // 骁龙 NPU 扩展显示
    if (data.hardware?.has_npu) {
      items.push({
        label: "骁龙 NPU",
        value: (data.hardware.npu_brand || data.hardware.npu_type || "?") +
               " · " + (data.hardware.npu_tops ? data.hardware.npu_tops + " TOPS" : "") +
               " · Hexagon " + (data.hardware.npu_arch || "?")
      });
    }
    grid.innerHTML = items.map(i =>
      `<div class="env-item"><div class="label">${i.label}</div><div class="value">${i.value}</div></div>`
    ).join("");

    // 渲染模型列表
    renderModels(data);

    // 检查本地 LLM 是否运行
    if (data.local_llm_running) {
      const h = await fetch("/models/health").then(r => r.json()).catch(() => null);
      if (h && h.status === "running") {
        runningModelServer = h;
        document.getElementById("running-card").style.display = "block";
        document.getElementById("running-info").innerHTML =
          `✅ <b>${h.model || "本地模型"}</b> 正在 <code style="color:var(--accent-2)">${h.base_url}</code><br>` +
          `端口: ${h.port} · OpenAI 兼容接口已就绪`;
        document.getElementById("research-mode-tag").textContent = "本地模式 · 就绪";
        document.getElementById("next-step").innerHTML = "✅ 本地模型已就绪，点击上方 <b>Research</b> 开始研究。";
      }
    }

    document.getElementById("env-loading").textContent = "完成";
  } catch (e) {
    document.getElementById("env-loading").textContent = "失败";
    toast("环境检测失败: " + e.message, "error");
  }
}

// ====================== 模型列表渲染 ======================
function renderModels(data) {
  const list = document.getElementById("model-list");
  const models = data.models_available || [];
  const recommend = data.recommended_model || "";
  const hasNpu = data.hardware?.has_npu || false;
  const npuBrand = data.hardware?.npu_brand || data.hardware?.npu_type || "";
  const npuTops = data.hardware?.npu_tops ? data.hardware.npu_tops + " TOPS" : "";

  // 如果有 NPU，给模型卡片加一个特殊标注
  const npuNote = hasNpu
    ? `<div style="font-size:0.72rem; color:var(--accent-2); margin-top:4px;">⚡ NPU 加速可用 · ${npuBrand}${npuTops ? " · " + npuTops : ""}</div>`
    : "";

  // 存储用户当前选择的推理后端（模型ID → 后端）
  if (!window._modelBackends) window._modelBackends = {};

  list.innerHTML = models.map(m => {
    const downloaded = m.downloaded;
    const sizeMB = Math.round((m.size_bytes || 0) / 1024 / 1024);
    const isRec = m.id === recommend;
    let statusBadge;
    if (downloaded) {
      statusBadge = `<span class="badge ready">已下载</span>`;
    } else {
      statusBadge = `<span class="badge notready">未下载</span>`;
    }

    // 推理后端选择（4选1）
    const backends = [
      { value: "auto", label: "自动" },
      { value: "cpu",  label: "CPU" },
      { value: "gpu",  label: "GPU" },
      { value: "npu",  label: "NPU" },
    ];
    const savedBackend = window._modelBackends[m.id] || "auto";
    const backendRadios = backends.map(b =>
      `<label class="be-label${savedBackend === b.value ? ' active' : ''}" title="${b.label}"
                onclick="window._modelBackends['${m.id}']='${b.value}'; this.parentElement.querySelectorAll('.be-label').forEach(l=>l.classList.remove('active')); this.classList.add('active')">
         <span>${b.label}</span>
       </label>`
    ).join("");

    let actionBtn;
    if (downloaded) {
      actionBtn = `<button class="btn success" onclick="startModel('${m.id}')">▶ 启动服务</button>`;
    } else {
      actionBtn = `<button class="btn" onclick="downloadModel('${m.id}')">⬇ 下载 (${sizeMB} MB)</button>`;
    }

    return `
      <div class="model-card" data-id="${m.id}">
        <div class="row">
          <div>
            <div class="name">${m.name}${isRec ? '<span class="recommend">推荐</span>' : ''}</div>
            <div class="meta">${m.description || ''} · ${m.param_size || ''}</div>
            ${hasNpu ? npuNote : ''}
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap: 6px;">
            <span class="size-pill">${sizeMB} MB</span>
            ${statusBadge}
          </div>
        </div>
        <div class="backend-row">
          <span class="backend-label">推理后端：</span>
          ${backendRadios}
        </div>
        <div id="progress-${m.id}"></div>
        <div class="btn-row">${actionBtn}</div>
      </div>
    `;
  }).join("");
}

// ====================== 下载模型 ======================
async function downloadModel(modelId) {
  toast(`开始下载 ${modelId}...`, "success");
  const card = document.querySelector(`.model-card[data-id="${modelId}"]`);
  if (!card) return;
  card.classList.add("active");

  // 启动下载
  const startResp = await fetch(`/models/download/${modelId}`, { method: "POST" }).then(r => r.json());
  if (startResp.status === "already_downloaded") {
    toast("模型已下载", "success");
    loadEnv();
    return;
  }

  // 替换按钮区为进度条
  const progWrap = document.getElementById("progress-" + modelId);
  progWrap.innerHTML = `
    <div class="progress-wrap">
      <div class="progress-bar"><div id="pb-${modelId}" style="width:0%"></div></div>
      <div class="progress-info">
        <span id="pi-${modelId}">0 MB / 0 MB · 0%</span>
        <span id="et-${modelId}">--</span>
      </div>
    </div>
  `;
  const btnRow = card.querySelector(".btn-row");
  btnRow.innerHTML = `<button class="btn secondary" disabled><span class="spinner"></span> 下载中...</button>`;

  // SSE 订阅进度
  const es = new EventSource(`/models/download/${modelId}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === "progress") {
      document.getElementById("pb-" + modelId).style.width = data.percent + "%";
      document.getElementById("pi-" + modelId).textContent =
        `${data.mb_done} MB / ${data.mb_total} MB · ${data.percent}%`;
      document.getElementById("et-" + modelId).textContent = `⏱ ${data.elapsed_sec}s`;
    } else if (data.type === "done") {
      es.close();
      toast(`✅ ${modelId} 下载完成`, "success");
      progWrap.innerHTML = "";
      btnRow.innerHTML = `<button class="btn success" onclick="startModel('${modelId}')">▶ 启动服务</button>`;
      // 更新状态
      const badges = card.querySelectorAll(".badge");
      badges.forEach(b => { b.className = "badge ready"; b.textContent = "已下载"; });
      card.classList.remove("active");
    } else if (data.type === "error") {
      es.close();
      toast("下载失败: " + (data.error || ""), "error");
      progWrap.innerHTML = "";
      btnRow.innerHTML = `<button class="btn" onclick="downloadModel('${modelId}')">🔁 重试</button>`;
      card.classList.remove("active");
    }
  };
  es.onerror = () => {
    es.close();
    toast("下载连接中断", "error");
  };
}

// ====================== 启动模型服务 ======================
async function startModel(modelId) {
  const card = document.querySelector(`.model-card[data-id="${modelId}"]`);
  if (card) card.classList.add("active");
  const backend = window._modelBackends[modelId] || "auto";
  const backendLabel = { auto: "自动", cpu: "CPU", gpu: "GPU", npu: "NPU" }[backend] || backend;
  toast(`启动 ${modelId} (${backendLabel})...`);

  try {
    const resp = await fetch(`/models/start/${modelId}?backend=${backend}`, { method: "POST" }).then(r => {
      if (!r.ok) return r.json().then(j => Promise.reject(j.detail || "启动失败"));
      return r.json();
    });
    runningModelServer = resp;
    document.getElementById("running-card").style.display = "block";
    const respBackend = resp.backend || backend;
    const respBackendLabel = { auto: "自动", cpu: "CPU", gpu: "GPU", npu: "NPU" }[respBackend] || respBackend;
    document.getElementById("running-info").innerHTML =
      `✅ <b>${resp.model_name}</b> 已启动<br>` +
      `<code style="color:var(--accent-2)">${resp.base_url}</code><br>` +
      `推理后端: <b>${respBackendLabel}</b> · OpenAI 兼容接口`;
    document.getElementById("research-mode-tag").textContent = `本地 · ${respBackendLabel} · 就绪`;
    document.getElementById("next-step").innerHTML =
      `✅ 模型已启动（<b>${respBackendLabel}</b>），点击上方 <b>Research</b> 开始研究。`;
    toast(`模型已就绪！ (${respBackendLabel})`, "success");
  } catch (err) {
    toast(String(err), "error");
  } finally {
    if (card) card.classList.remove("active");
  }
}

async function stopModel() {
  if (!confirm("停止当前模型服务？")) return;
  await fetch("/models/stop", { method: "POST" });
  runningModelServer = null;
  document.getElementById("running-card").style.display = "none";
  document.getElementById("research-mode-tag").textContent = "本地模式";
  document.getElementById("next-step").textContent = "请先选择并启动一个模型";
  toast("服务已停止");
}

// ====================== 研究流程 ======================
function startResearch() {
  const q = document.getElementById("question").value.trim();
  if (!q) { toast("请先输入问题", "error"); return; }

  const depth = document.querySelector('input[name="depth"]:checked').value;
  const locale = document.querySelector('input[name="locale"]:checked').value;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const localMode = mode === "local";

  document.getElementById("progress-card").style.display = "block";
  document.getElementById("report-card").style.display = "none";
  document.getElementById("timeline").innerHTML = "";
  document.getElementById("run-status-badge").textContent = "运行中";
  document.getElementById("run-status-badge").className = "badge running";

  fetch("/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: q, depth, locale, local_mode: localMode })
  }).then(r => r.json()).then(data => {
    currentRunId = data.run_id;
    subscribeEvents(data.run_id);
  }).catch(e => toast("启动失败: " + e.message, "error"));
}

function subscribeEvents(runId) {
  if (currentEventSource) currentEventSource.close();
  currentEventSource = new EventSource(`/research/${runId}/events`);

  const steps = {};
  currentEventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === "connected") return;

    if (data.type === "progress") {
      if (!(data.step in steps)) {
        steps[data.step] = { message: data.message, done: !!data.done };
        renderTimeline(steps, data.step);
      } else {
        steps[data.step].message = data.message;
        steps[data.step].done = !!data.done;
        renderTimeline(steps, data.step);
      }
    }

    if (data.type === "done") {
      document.getElementById("run-status-badge").textContent = "完成";
      document.getElementById("run-status-badge").className = "badge ready";
      currentEventSource.close();
      renderReport(data.report);
    }

    if (data.type === "error") {
      document.getElementById("run-status-badge").textContent = "错误";
      document.getElementById("run-status-badge").className = "badge notready";
      currentEventSource.close();
      toast("研究失败: " + data.error, "error");
    }
  };

  currentEventSource.onerror = () => {
    toast("连接已断开", "error");
  };
}

function renderTimeline(steps, activeKey) {
  const keys = Object.keys(steps);
  document.getElementById("timeline").innerHTML = keys.map((k, i) => {
    const s = steps[k];
    const cls = s.done ? "done" : (k === activeKey ? "active" : "");
    const icon = s.done ? "✓" : (i + 1);
    return `<div class="step ${cls}"><div class="dot">${icon}</div><div>${s.message}</div></div>`;
  }).join("");
}

function renderReport(report) {
  if (!report) return;
  document.getElementById("report-card").style.display = "block";
  const el = document.getElementById("report");
  const md = `# ${report.title || "研究报告"}\n\n` +
             (report.executive_summary || "") + "\n\n" +
             (report.body || "");
  el.innerHTML = marked.parse(md);

  // 参考链接
  if (report.sources && report.sources.length) {
    const src = `<h2>📎 参考来源</h2><ul>` +
      report.sources.slice(0, 30).map(s =>
        `<li><a href="${s}" target="_blank" rel="noopener">${s}</a></li>`).join("") + `</ul>`;
    el.innerHTML += src;
  }

  // 附录
  if (report.appendix) {
    el.innerHTML += `<h2>📑 附录</h2><pre><code>${JSON.stringify(report.appendix, null, 2)}</code></pre>`;
  }

  // 滚动到报告
  setTimeout(() => document.getElementById("report-card").scrollIntoView({ behavior: "smooth", block: "start" }), 100);
}

// ====================== 沙箱测试 ======================
async function runSandbox() {
  const q = document.getElementById("sandbox-q").value.trim();
  if (!q) { toast("请输入关键词", "error"); return; }

  document.getElementById("sandbox-result-card").style.display = "block";
  document.getElementById("sandbox-summary").innerHTML = `<div class="spinner"></div> 并行检索中...`;
  document.getElementById("sandbox-details").innerHTML = "";

  try {
    const data = await fetch(`/sandbox/search?q=${encodeURIComponent(q)}`).then(r => r.json());
    document.getElementById("sandbox-summary").innerHTML =
      `<div style="display:flex; gap:8px; flex-wrap:wrap;">
         <span class="badge ready">✓ ${data.successful_sources.length} 成功</span>
         <span class="badge notready">✗ ${data.failed_sources.length} 失败</span>
         <span class="badge ready">📄 ${data.total_items} 条结果</span>
       </div>`;

    let html = "";
    for (const d of data.details) {
      html += `
        <details>
          <summary>${d.ok ? "✅" : "❌"} ${d.source} · ${d.count}条 · ${d.duration_ms}ms</summary>
          <div class="content">
            ${d.error ? `<b>错误:</b> ${d.error}<br><br>` : ""}
          </div>
        </details>
      `;
    }

    if (data.items && data.items.length) {
      html += `<h3 style="margin-top:16px;">前 10 条结果</h3>`;
      html += data.items.slice(0, 10).map((it, i) =>
        `<div style="padding:10px; background:var(--surface-2); border:1px solid var(--border); border-radius:8px; margin-bottom:8px;">
           <div style="font-size:0.72rem; color:var(--text-dim); margin-bottom:4px;">[${it.source || "?"}]</div>
           <div style="font-weight:600; margin-bottom:4px;">${it.title || "(无标题)"}</div>
           <div style="font-size:0.88rem; color:var(--text-dim);">${(it.snippet || "").slice(0, 300)}...</div>
           ${it.url ? `<div style="margin-top:6px;"><a href="${it.url}" target="_blank" rel="noopener" style="font-size:0.82rem;">${it.url}</a></div>` : ""}
         </div>`
      ).join("");
    }
    document.getElementById("sandbox-details").innerHTML = html;
  } catch (e) {
    document.getElementById("sandbox-summary").innerHTML = `<span style="color:var(--danger);">失败: ${e.message}</span>`;
  }
}

// ====================== 初始化 ======================
window.addEventListener("load", loadEnv);
</script>

</body>
</html>
"""
