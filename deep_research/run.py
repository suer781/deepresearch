#!/usr/bin/env python3
"""一键启动脚本。

自动检测并安装依赖、启动服务、打开浏览器。
支持：本地 Ollama / LM Studio（免 key）或云端 API（需 key）。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _print(msg: str, emoji: str = "🔧") -> None:
    print(f"{emoji}  {msg}")


def _run(*args: str, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, **kwargs, check=check)


def _check(p: str) -> bool:
    return shutil.which(p) is not None


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def _wait_for_server(port: int, timeout: int = 15) -> bool:
    import httpx
    for _ in range(timeout):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"http://127.0.0.1:{port}/status", timeout=2)
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


def _install_deps() -> None:
    """检查并安装缺失的依赖。"""
    _print("检查依赖...", "🔍")

    # 核心依赖
    try:
        import fastapi  # noqa: F401
    except ImportError:
        _print("安装 FastAPI + Uvicorn...", "📦")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]", "httpx", "-q"],
            check=True,
        )

    # Playwright
    try:
        import playwright  # noqa: F401
    except ImportError:
        _print("安装 Playwright...", "📦")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright", "-q"],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )

    # 搜索依赖
    deps = [
        "duckduckgo-search>=6.0.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=5.0.0",
        "arxiv>=2.1.0",
        "wikipedia>=1.4.0",
    ]
    missing = []
    for d in deps:
        name = d.split(">")[0].split("=")[0]
        try:
            __import__(name.lower().replace("-", "_"))
        except ImportError:
            missing.append(d)

    if missing:
        _print(f"安装搜索依赖：{missing}...", "📦")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing, "-q"],
            check=True,
        )

    _print("依赖检查完成", "✅")


def _check_local_llm() -> tuple[bool, str]:
    """检测本地 LLM 是否可用，返回 (available, url)。"""
    import httpx
    default_url = "http://localhost:11434/v1"
    try:
        r = httpx.post(
            default_url + "/chat/completions",
            json={"model": "qwen3:8b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            timeout=5,
            headers={"Content-Type": "application/json"},
        )
        if r.status_code < 500:
            return True, default_url
    except Exception:
        pass

    # 尝试 LM Studio
    lm_url = "http://localhost:1234/v1"
    try:
        r = httpx.post(
            lm_url + "/chat/completions",
            json={"model": "local", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            timeout=5,
        )
        if r.status_code < 500:
            return True, lm_url
    except Exception:
        pass

    return False, default_url


def _main() -> None:
    port = 8765

    # Banner
    banner = r"""
╔══════════════════════════════════════════╗
║       🔬 Deep Research  ·  一键启动       ║
╚══════════════════════════════════════════╝
"""
    print(banner)

    # 依赖检查
    _install_deps()

    # 检查端口占用
    if _port_in_use(port):
        _print(f"端口 {port} 已被占用，尝试直接打开浏览器...", "⚠️")
        webbrowser.open(f"http://127.0.0.1:{port}")
        return

    # 检测 LLM（_install_deps 后才能 import httpx）
    llm_ok, llm_url = _check_local_llm()
    if llm_ok:
        _print(f"本地 LLM 检测成功：{llm_url}", "✅")
    else:
        _print("未检测到本地 LLM（Ollama / LM Studio）", "⚠️")
        _print("  → 本地模式将不可用，需要云端 API key", "")
        _print("  → 或启动 Ollama：ollama serve", "💡")

    # 写临时 .env 方便 web server 读取
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file.write_text(f"""\
DR_USE_LOCAL_MODEL=true
DR_LOCAL_MODEL_URL={llm_url}
DR_LOCAL_MODEL_NAME=qwen3:8b
DR_DEBUG=false
""")
        _print("已生成 .env 配置文件", "📄")

    # 启动服务
    _print(f"启动服务 http://127.0.0.1:{port} ...", "🚀")

    # 启动 uvicorn
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "deep_research.web_api:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--reload",
        ],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(SRC)},
    )

    # 等待服务就绪
    _print("等待服务就绪...", "⏳")
    ok = asyncio.run(_wait_for_server(port))
    if not ok:
        _print("服务启动超时，请检查错误日志", "❌")
        proc.terminate()
        sys.exit(1)

    _print(f"服务就绪！打开浏览器...", "✅")
    webbrowser.open(f"http://127.0.0.1:{port}")

    # 等待用户中断
    _print("\n按 Ctrl+C 停止服务", "📌")
    try:
        proc.wait()
    except KeyboardInterrupt:
        _print("停止服务...", "👋")
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    _main()
