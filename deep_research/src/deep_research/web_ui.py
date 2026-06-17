"""内嵌 Web UI：单文件 HTML/CSS/JS，无任何外部依赖（CDN 只用 marked.js）。"""
from __future__ import annotations

INDEX_HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deep Research - 超级并行研究引擎</title>
<style>
  :root {
    --bg: #0a0e1a;
    --surface: #111827;
    --surface2: #1f2937;
    --border: #374151;
    --accent: #6366f1;
    --accent2: #818cf8;
    --text: #f9fafb;
    --text2: #9ca3af;
    --green: #10b981;
    --yellow: #f59e0b;
    --red: #ef4444;
    --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, 'SF Pro Text', 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.6;
  }

  /* Header */
  header {
    background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .logo { font-size: 20px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 8px; }
  .logo-icon { font-size: 24px; }
  .header-right { display: flex; gap: 12px; align-items: center; }

  /* Main */
  main { max-width: 860px; margin: 0 auto; padding: 32px 24px; }

  /* Mode toggle */
  .mode-bar {
    display: flex;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 6px;
    margin-bottom: 24px;
    width: fit-content;
  }
  .mode-btn {
    padding: 8px 20px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
    background: transparent;
    color: var(--text2);
  }
  .mode-btn.active { background: var(--accent); color: white; }
  .mode-btn:not(.active):hover { background: var(--surface2); color: var(--text); }

  /* Status badge */
  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    background: var(--surface2);
    color: var(--text2);
  }
  .status-badge.ok { background: #022c22; color: var(--green); border: 1px solid #065f46; }
  .status-badge.error { background: #450a0a; color: var(--red); border: 1px solid #7f1d1d; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .dot.pulse { animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  /* Card */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 20px;
  }
  .card-title { font-size: 13px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; }

  /* Question input */
  #question {
    width: 100%;
    min-height: 120px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 15px;
    padding: 14px 16px;
    resize: vertical;
    font-family: inherit;
    line-height: 1.6;
    transition: border-color 0.2s;
  }
  #question:focus { outline: none; border-color: var(--accent); }
  #question::placeholder { color: var(--text2); }

  /* Start button */
  .btn-primary {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 12px 28px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    margin-top: 16px;
  }
  .btn-primary:hover:not(:disabled) { background: var(--accent2); transform: translateY(-1px); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Progress */
  #progress-area { display: none; }
  .step {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .step:last-child { border-bottom: none; }
  .step-icon { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; margin-top: 1px; }
  .step-icon.pending { background: var(--surface2); color: var(--text2); }
  .step-icon.active { background: #1e1b4b; color: var(--accent2); animation: pulse 1.5s infinite; }
  .step-icon.done { background: #022c22; color: var(--green); }
  .step-icon.error { background: #450a0a; color: var(--red); }
  .step-content { flex: 1; }
  .step-title { font-size: 14px; font-weight: 500; }
  .step-msg { font-size: 13px; color: var(--text2); margin-top: 2px; }

  /* Report */
  #report-area { display: none; }
  .report-header { border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 16px; }
  .report-title { font-size: 22px; font-weight: 700; color: var(--text); }
  .report-meta { font-size: 13px; color: var(--text2); margin-top: 4px; }
  .report-section { margin-bottom: 20px; }
  .report-section h2 { font-size: 16px; font-weight: 600; margin-bottom: 8px; color: var(--accent2); }
  .report-section p { font-size: 14px; color: var(--text); margin-bottom: 8px; }
  .report-section ul { padding-left: 20px; margin-bottom: 8px; }
  .report-section li { font-size: 14px; margin-bottom: 4px; }
  .report-refs { background: var(--surface2); border-radius: 8px; padding: 16px; margin-top: 16px; }
  .report-refs h3 { font-size: 13px; font-weight: 600; color: var(--text2); margin-bottom: 10px; }
  .ref-item { font-size: 12px; color: var(--text2); padding: 4px 0; border-bottom: 1px solid var(--border); }
  .ref-item:last-child { border-bottom: none; }
  .ref-item a { color: var(--accent2); text-decoration: none; }
  .ref-item a:hover { text-decoration: underline; }

  /* Settings panel */
  #settings-area { display: none; }
  .setting-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }
  .setting-row:last-child { border-bottom: none; }
  .setting-label { font-size: 14px; font-weight: 500; }
  .setting-desc { font-size: 12px; color: var(--text2); }
  input[type=text], input[type=password] {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    padding: 6px 10px;
    font-size: 13px;
    width: 220px;
  }
  input:focus { outline: none; border-color: var(--accent); }

  /* Error */
  .error-box { background: #450a0a; border: 1px solid #7f1d1d; border-radius: 8px; padding: 14px; color: var(--red); font-size: 14px; margin-top: 12px; }

  /* Download btn */
  .btn-download {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--surface2); color: var(--text);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 16px; font-size: 13px; cursor: pointer;
    text-decoration: none; margin-top: 12px;
  }
  .btn-download:hover { border-color: var(--accent); color: var(--accent2); }

  /* Footer */
  footer { text-align: center; padding: 24px; color: var(--text2); font-size: 12px; }
</style>
</head>
<body>

<header>
  <div class="logo"><span class="logo-icon">🔬</span> Deep Research</div>
  <div class="header-right">
    <div class="status-badge" id="llm-status">
      <span class="dot"></span> 检查中...
    </div>
  </div>
</header>

<main>
  <!-- Mode -->
  <div class="mode-bar">
    <button class="mode-btn active" id="btn-local" onclick="setMode('local')">🏠 本地模式</button>
    <button class="mode-btn" id="btn-cloud" onclick="setMode('cloud')">☁️ 云端模式</button>
  </div>

  <!-- Question -->
  <div class="card">
    <div class="card-title">研究问题</div>
    <textarea id="question" placeholder="例如：深度研究 Qwen3 与 Llama3 在中文 RAG 场景的对比，包括架构差异、训练数据、性能基准、应用建议..."></textarea>
    <button class="btn-primary" id="btn-start" onclick="startResearch()">
      <span>🚀</span> 开始深度研究
    </button>
  </div>

  <!-- Progress -->
  <div class="card" id="progress-area">
    <div class="card-title">研究进度</div>
    <div id="steps"></div>
  </div>

  <!-- Report -->
  <div class="card" id="report-area">
    <div class="report-header">
      <div class="report-title" id="report-title"></div>
      <div class="report-meta" id="report-meta"></div>
    </div>
    <div id="report-body"></div>
    <a class="btn-download" id="btn-download" download="report.md">📄 下载 Markdown</a>
  </div>

  <!-- Error -->
  <div id="error-area" style="display:none"></div>

  <!-- Settings -->
  <div class="card" id="settings-area">
    <div class="card-title">⚙️ 设置</div>
    <div class="setting-row">
      <div>
        <div class="setting-label">本地 LLM 地址</div>
        <div class="setting-desc">Ollama / LM Studio / vLLM 的 OpenAI 兼容端点</div>
      </div>
      <input type="text" id="cfg-local-url" value="http://localhost:11434/v1">
    </div>
    <div class="setting-row">
      <div>
        <div class="setting-label">本地模型名</div>
        <div class="setting-desc">如 qwen3:8b、deepseek-r1:14b、llama3.3:70b</div>
      </div>
      <input type="text" id="cfg-local-model" value="qwen3:8b">
    </div>
    <div class="setting-row">
      <div>
        <div class="setting-label">OpenAI API Key</div>
        <div class="setting-desc">云端模式需要（仅在使用云端时发送）</div>
      </div>
      <input type="password" id="cfg-openai-key" placeholder="sk-...">
    </div>
  </div>
</main>

<footer>Deep Research · 超级并行多智能体研究系统 · v0.1</footer>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
const API = '';
let currentMode = 'local';
let currentRunId = null;
let evtSource = null;
let conf = {};

async function init() {
  // Load settings from localStorage
  const saved = localStorage.getItem('dr_conf');
  if (saved) { conf = JSON.parse(saved); applyConf(); }

  // Check env
  try {
    const r = await fetch(API + '/status');
    const d = await r.json();
    const badge = document.getElementById('llm-status');
    if (d.local_llm_available) {
      badge.className = 'status-badge ok';
      badge.innerHTML = '<span class="dot pulse"></span> LLM 已连接';
    } else {
      badge.className = 'status-badge error';
      badge.innerHTML = '<span class="dot"></span> LLM 未运行（请启动 Ollama）';
    }
  } catch(e) {
    document.getElementById('llm-status').textContent = '⚠ 服务未就绪';
  }

  document.getElementById('settings-area').style.display = 'block';
}

function applyConf() {
  if (conf.localUrl) document.getElementById('cfg-local-url').value = conf.localUrl;
  if (conf.localModel) document.getElementById('cfg-local-model').value = conf.localModel;
  if (conf.openaiKey) document.getElementById('cfg-openai-key').value = conf.openaiKey;
}

function saveConf() {
  conf = {
    localUrl: document.getElementById('cfg-local-url').value,
    localModel: document.getElementById('cfg-local-model').value,
    openaiKey: document.getElementById('cfg-openai-key').value,
  };
  localStorage.setItem('dr_conf', JSON.stringify(conf));
}

function setMode(m) {
  currentMode = m;
  document.getElementById('btn-local').className = 'mode-btn' + (m==='local'?' active':'');
  document.getElementById('btn-cloud').className = 'mode-btn' + (m==='cloud'?' active':'');
}

const STEPS = ['queued','clarify','plan','debate','search','verify','write','review'];
const STEP_ICONS = {'queued':'⏳','clarify':'🔍','plan':'📋','debate':'⚖️','search':'🚀','verify':'🔎','write':'✍️','review':'🔍'};

function initSteps() {
  const el = document.getElementById('steps');
  el.innerHTML = '';
  STEPS.forEach(s => {
    el.innerHTML += `<div class="step" id="step-${s}">
      <div class="step-icon pending" id="icon-${s}">${STEP_ICONS[s]||'•'}</div>
      <div class="step-content">
        <div class="step-title" id="title-${s}">${s}</div>
        <div class="step-msg" id="msg-${s}">等待中...</div>
      </div>
    </div>`;
  });
}

function setStep(s, status, msg) {
  const icon = document.getElementById('icon-' + s);
  if (!icon) return;
  icon.className = 'step-icon ' + status;
  if (msg) document.getElementById('msg-' + s).textContent = msg;
}

async function startResearch() {
  const q = document.getElementById('question').value.trim();
  if (!q) { alert('请输入研究问题'); return; }
  saveConf();

  // Reset UI
  document.getElementById('report-area').style.display = 'none';
  document.getElementById('error-area').style.display = 'none';
  document.getElementById('progress-area').style.display = 'block';
  initSteps();
  document.getElementById('btn-start').disabled = true;
  currentRunId = null;

  try {
    const body = { question: q, local_mode: currentMode === 'local', locale: 'zh-CN' };

    const r = await fetch(API + '/research', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error('启动失败: ' + r.status);
    const d = await r.json();
    currentRunId = d.run_id;

    // Connect SSE
    if (evtSource) evtSource.close();
    evtSource = new EventSource(API + '/research/' + currentRunId + '/events');

    evtSource.onmessage = e => {
      const ev = JSON.parse(e.data);
      handleEvent(ev);
    };
    evtSource.onerror = () => {
      // will auto-retry via browser
    };

  } catch(e) {
    showError(e.message);
    document.getElementById('btn-start').disabled = false;
  }
}

function handleEvent(ev) {
  if (ev.type === 'ping') return;

  if (ev.type === 'progress') {
    const s = ev.step || 'queued';
    if (STEPS.includes(s)) {
      setStep(s, ev.done ? 'done' : 'active', ev.message);
      if (ev.done) {
        // Find next pending step
        const idx = STEPS.indexOf(s);
        for (let i = idx + 1; i < STEPS.length; i++) {
          setStep(STEPS[i], 'pending', '等待中...');
        }
      }
    }
    return;
  }

  if (ev.type === 'done') {
    document.getElementById('btn-start').disabled = false;
    showReport(ev.report);
    if (evtSource) { evtSource.close(); evtSource = null; }
    return;
  }

  if (ev.type === 'error') {
    showError(ev.error);
    document.getElementById('btn-start').disabled = false;
    if (evtSource) { evtSource.close(); evtSource = null; }
    return;
  }
}

function showReport(r) {
  document.getElementById('progress-area').style.display = 'none';
  document.getElementById('report-area').style.display = 'block';
  document.getElementById('report-title').textContent = r.title || '研究报告';
  document.getElementById('report-meta').textContent = `问题: ${r.question} · ${r.references?.length || 0} 条参考文献`;

  let html = '';
  (r.sections || []).forEach(sec => {
    html += `<div class="report-section">`;
    if (sec.heading) html += `<h2>${sec.heading}</h2>`;
    const content = typeof sec.content === 'string' ? sec.content : '';
    html += `<div>${marked.parse(content)}</div>`;
    html += `</div>`;
  });

  if (r.open_questions?.length) {
    html += `<div class="report-section"><h2>⚠️ 未解决问题</h2><ul>`;
    r.open_questions.forEach(q => { html += `<li>${q}`; });
    html += `</ul></div>`;
  }

  const refs = r.references || [];
  if (refs.length) {
    html += `<div class="report-refs"><h3>📚 参考文献（${refs.length} 条）</h3>`;
    refs.forEach(ref => {
      html += `<div class="ref-item">[<b>${(ref.confidence || 0).toFixed(2)}</b>] ${ref.claim || ''} — <a href="${ref.source || '#'}" target="_blank">${ref.source_name || ref.source || '来源'}</a></div>`;
    });
    html += `</div>`;
  }

  document.getElementById('report-body').innerHTML = html;

  // Download
  let md = `# ${r.title}\n\n**问题**: ${r.question}\n\n`;
  (r.sections || []).forEach(sec => {
    if (sec.heading) md += `## ${sec.heading}\n\n${sec.content || ''}\n\n`;
  });
  const blob = new Blob([md], {type: 'text/markdown'});
  document.getElementById('btn-download').href = URL.createObjectURL(blob);
}

function showError(msg) {
  document.getElementById('progress-area').style.display = 'none';
  const el = document.getElementById('error-area');
  el.style.display = 'block';
  el.innerHTML = `<div class="error-box">❌ 错误: ${msg}</div>`;
}

init();
</script>
</body>
</html>
"""
