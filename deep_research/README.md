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

```bash
pip install -e .
playwright install chromium
cp config/.env.example config/.env  # 填入 API keys

python -m deep_research.cli "深度研究：xxx"
```

## License

MIT
