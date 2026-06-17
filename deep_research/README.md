# Deep Research Framework

**不只是超级并行搜索引擎 —— 更是前沿技术研究与创新引擎。**

核心能力：
- 🧠 **深度推理研究**：数小时级别的复杂问题研究，生成可发表级报告
- 🔬 **技术创新引擎**：从海量论文/代码中提炼前沿算法，提出新方案（如新型注意力机制、KV 缓存优化、稀疏计算等）
- ⚡ **效率突破设计**：自动对比现有方案瓶颈，生成能提升数十倍效率的改进方案
- 🌐 **超级并行搜索**：接入所有主流搜索源，并行检索 + 交叉验证
- 🤖 **多智能体辩论**：破解单模型幻觉，通过对抗辩论暴露盲点

---

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

---

## 🔬 技术创新引擎（不只是搜索）

这个项目最擅长的是 **「创造新东西」** —— 从海量前沿研究中提炼灵感，生成能突破现有瓶颈的创新方案。

### 典型应用场景

| 场景 | 示例问题 | 系统会做什么 |
|---|---|---|
| **算法创新** | "设计一个比 FlashAttention-2 更快的注意力机制" | 搜索 ArXiv/Semantic Scholar 最新论文 → 分析现有方案瓶颈 → 提出新架构（如稀疏注意力、分层 KV、线性注意力）→ 对比理论加速比 |
| **系统优化** | "如何让 LLM 推理吞吐量提升 50 倍？" | 搜索 vLLM/DeepSeek/Megatron 等开源实现 → 分析 KV 缓存、调度、量化瓶颈 → 提出组合优化方案 |
| **架构设计** | "设计一个适合移动端 NPU 的轻量 Transformer" | 搜索 MobileBERT/EfficientTransformer 论文 → 分析骁龙/昇腾硬件特性 → 提出量化+稀疏+蒸馏组合方案 |
| **论文写作** | "写一篇关于 KV 缓存压缩的综述论文" | 搜索 2020-2025 所有相关论文 → 分类整理方法 → 分析优劣 → 生成结构化综述 |

### 创新流程（自动）

```
用户提出创新目标（如"设计更快的注意力机制")
   │
   ▼
[1. 现状扫描] ── 搜索 ArXiv/GitHub/Semantic Scholar，收集所有相关论文/代码
   │
   ▼
[2. 瓶颈分析] ── 对比现有方案，找出效率瓶颈（如内存带宽、计算冗余、通信开销）
   │
   ▼
[3. 方案生成] ── 基于前沿研究，提出新方案（如分层 KV、稀疏注意力、线性注意力）
   │        │
   │        ▼
   │   [4. 方案辩论] ── 多个 Agent 质疑可行性、边界条件、实现难度
   │        │
   │        ▼ 通过
   ▼
[5. 理论验证] ── 计算理论加速比、内存节省、适用场景
   │
   ▼
[6. 实现建议] ── 给出伪代码、关键算法、硬件适配建议
   │
   ▼
[7. 报告生成] ── 输出可发表级技术报告（含引用、图表、对比表）
```

### 实际案例（示例输出）

**输入**："设计一个比所有现有 KV 缓存方案更高效的压缩方法"

**输出**（系统自动生成）：

```
# KV 缓存压缩创新方案：分层稀疏量化 (Hierarchical Sparse Quantization)

## 1. 现有方案瓶颈分析
| 方案 | 算力开销 | 内存节省 | 适用场景 |
|---|---|---|---|
| PagedAttention (vLLM) | 中 | 30% | 高吞吐 |
| Multi-Query Attention | 低 | 50% | 推理 |
| StreamingLLM | 低 | 70% | 长文本 |
| H2O (Heavy-Hitter Oracle) | 中 | 80% | 长文本 |

瓶颈：所有方案都是「全局压缩」，忽略了 token 的局部重要性差异。

## 2. 新方案：分层稀疏量化 (HSQ)

核心思想：
- 第 1 层：保留最近 N 个 token 的完整 KV（无压缩）
- 第 2 层：对「高频 token」做 4-bit 量化 + 稀疏索引
- 第 3 层：对「低频 token」做 2-bit 量化 + 滑动窗口丢弃

理论加速：
- 内存节省：92%（相比原始 KV）
- 计算开销：+5%（索引开销）
- 适用：所有 Transformer 架构

## 3. 实现伪代码
...

## 4. 参考文献
[1] vLLM: PagedAttention (2023)
[2] StreamingLLM (2023)
[3] H2O (2023)
[4] FlashAttention-3 (2024)
...
```

---

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

---

## 打包成安装包 / 可执行程序

本项目提供一键打包工具，支持：

| 平台 | 产物 | 构建命令 |
|---|---|---|
| Windows | `DeepResearch.exe` | `python build.py exe` |
| macOS | `DeepResearch.app` | `python build.py macos` |
| Linux | `DeepResearch` (单文件) | `python build.py linux` |
| Android | `deepresearch-0.1.0-debug.apk` | `python build.py apk` |

### 一、桌面平台（PyInstaller）

```bash
# 1. 安装打包依赖
pip install -r requirements-build.txt

# 2. 构建（会自动生成 dist/ 目录）
python build.py exe       # Windows 出 exe
python build.py macos     # macOS 出 .app
python build.py linux     # Linux 出二进制

# 3. 运行
./dist/DeepResearch      # 会自动启动服务 + 打开浏览器
```

### 二、Android APK

```bash
# 需要: JDK 17 + Android SDK + NDK（buildozer 会自动下载）
# 推荐在 Linux 或 macOS 上构建（Windows 需用 WSL）
python build.py apk

# 产物：
#   bin/deepresearch-0.1.0-debug.apk
#   dist/deepresearch-0.1.0-debug.apk  ← 会自动复制一份
```

APK 内功能：
- 启动后在手机本地运行 FastAPI 服务（`http://127.0.0.1:8000`）
- 自动打开 WebView 访问 UI
- 内置骁龙 Hexagon NPU 检测，在 Qualcomm 设备上自动启用硬件加速
- 模型下载到 `/sdcard/Android/data/com.deepresearch.app/`

### 三、Docker

```bash
docker build -t deep-research .
docker run -p 8000:8000 deep-research
```

### 构建文件清单

| 文件 | 用途 |
|---|---|
| `build.py` | 主构建辅助脚本（exe/macos/linux/apk 全部一键） |
| `deep_research.spec` | PyInstaller 打包配置（Windows/macOS/Linux） |
| `buildozer.spec` | Buildozer 配置（Android APK） |
| `main.py` | Android 入口（启动 Python 服务 + WebView） |
| `requirements-build.txt` | 打包工具依赖 |

### 高级：Release 版 APK 签名

编辑 `buildozer.spec` 末尾的签名配置，然后：

```bash
buildozer android release
```

### 高级：自定义图标

在项目根目录下创建 `assets/` 目录并放入：

```
assets/
  icon.png         # 512x512, 应用图标
  presplash.png    # 启动画面（1920x1080）
```

然后取消 `buildozer.spec` 中 `icon.filename` 行的注释。
