# Deep Research Framework

A super-parallel, multi-agent deep research system that breaks the single-model hallucination loop through adversarial debate and structured external memory.

## 核心设计

```
用户问题
   │
   ▼
[1. 引导补全 Agent] ── 补全背景、时间、地点、人物
   │
   ▼
[2. 研究规划 Agent] ── 拆解子问题 + 选搜索源 + 排序
   │        │
   │        ▼
   │   [3. 方案辩论] ── 多个 Agent 互相质疑方案可行性
   │        │
   │        ▼ 通过
   ▼
[4. 动态子智能体池] ── 并行执行 N 个研究子任务
   │  - 搜索子智能体 × N
   │  - 阅读子智能体 × N
   │  - 验证子智能体 × N
   │  - 反例搜索子智能体
   │
   ▼ 每批结果
[5. 证据辩论] ── 多方交叉验证
   │
   ▼
[6. 综合写作 Agent] ── 生成可发表级报告
   │
   ▼
[7. 质量审查 Agent] ── 查证据链、查反例、查盲点
```

## 破解全量上下文幻觉的机制

不是把所有上下文塞进一个 prompt，而是：
1. **外部证据库** - 每条证据独立存，带溯源
2. **论点-证据图谱** - 结构化存储，避免自然语言裁剪
3. **关键锚点缓存** - 防止长推理遗忘
4. **辩论强制暴露盲点** - 一个模型看不到自己的错误

## 搜索源（"尽可能多"）

A 类 - 直接抓取（Playwright）：
  - cn.bing.com, www.bing.com
  - baidu.com, sogou.com, 360so.com

B 类 - 官方 API：
  - Tavily, Brave, Exa, Searlo, Parallel AI
  - Wikipedia, ArXiv, Semantic Scholar, OpenAlex
  - HackerNews, Reddit, GitHub, Stack Exchange
  - 知乎官方, 阿里云/夸克

C 类 - 付费 API 兜底：
  - SerpAPI, TikHub（国内社交媒体）

## 快速开始

### ⭐ 最简单 —— 一键 Web UI（下载就能用，不需要懂命令行）

```bash
# 下载项目后，一行命令启动：
python run.py
```

自动完成：检测依赖 → 启动服务 → 打开浏览器（http://localhost:8765）

**需要提前安装 Ollama**（如果只用本地模式）：
```bash
# 下载: https://ollama.com
ollama pull qwen3:8b
ollama serve
```

支持 Docker：
```bash
docker build -t deep-research .
docker run -p 8765:8765 deep-research
```

---

### 方式 B —— 命令行

```bash
# 安装
pip install -e ".[web]"
playwright install chromium

# 本地模式（需要 Ollama）
python -m deep_research.cli --local "研究问题"

# 云端模式（需要 OpenAI key）
python -m deep_research.cli "研究问题"
```

## 架构说明

```
用户问题
   │
   ▼
[1. 引导补全 Agent] ── 补全背景、时间、地点、人物
   │
   ▼
[2. 研究规划 Agent] ── 拆解子问题 + 选搜索源 + 排序
   │        │
   │        ▼
   │   [3. 方案辩论] ── 多个 Agent 互相质疑方案可行性
   │        │
   │        ▼ 通过
   ▼
[4. 动态子智能体池] ── 并行执行 N 个研究子任务
   │  - 搜索子智能体 × N
   │  - 阅读子智能体 × N
   │  - 验证子智能体 × N
   │  - 反例搜索子智能体
   │
   ▼ 每批结果
[5. 证据辩论] ── 多方交叉验证
   │
   ▼
[6. 综合写作 Agent] ── 生成可发表级报告
   │
   ▼
[7. 质量审查 Agent] ── 查证据链、查反例、查盲点
```

## 破解全量上下文幻觉的机制

不是把所有上下文塞进 prompt，而是：
1. **外部证据库** - 每条证据独立存，带溯源
2. **论点-证据图谱** - 结构化存储，避免自然语言裁剪
3. **关键锚点缓存** - 防止长推理遗忘
4. **辩论强制暴露盲点** - 一个模型看不到自己的错误

## 本地 vs 云端模式对比

| 维度 | 本地 (--local) | 云端 |
|---|---|---|
| LLM | Ollama / LM Studio / vLLM / llama.cpp | OpenAI / Anthropic 等 |
| 搜索源 | 10 个免 key 源 | 全部 12+ 个（含 Tavily 等付费） |
| 隐私 | 完全本地 | API 请求外网 |
| 费用 | $0 | 按 token 计费 |
| 质量 | 取决于本地模型 | 通常更强 |

## License

MIT
