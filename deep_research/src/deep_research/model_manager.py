"""模型管理器 — 自动检测硬件、下载 GGUF 模型、启动 OpenAI 兼容服务。

设计目标：
- 用户不需要手动安装 Ollama / LM Studio / 下载模型文件
- 根据用户设备自动推荐合适大小的模型（手机/低 RAM 用 1.7B，桌面用 7B）
- 启动后监听本地端口，对上层代码透明（和 Ollama 一样的 /chat/completions 接口）

依赖：llama-cpp-python（纯 Python，支持 CPU / Metal / CUDA 自动选择）
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx


# 可选择的模型（GGUF, 来自 HuggingFace/HF_MIRROR）
# 优先级：先试 HF，失败用 mirror
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "qwen3-1.7b": {
        "name": "Qwen3 1.7B Instruct",
        "repo": "Qwen/Qwen3-1.7B-Instruct-GGUF",
        "file": "qwen3-1.7b-instruct-q4_k_m.gguf",
        "size": 1.2,  # GB
        "min_ram": 4,
        "chat_template": "qwen",
        "lang": "zh+en",
        "recommended_for": "手机 / 4GB+ 内存 / 低性能设备",
    },
    "qwen3-7b": {
        "name": "Qwen3 7B Instruct",
        "repo": "Qwen/Qwen3-7B-Instruct-GGUF",
        "file": "qwen3-7b-instruct-q4_k_m.gguf",
        "size": 4.8,
        "min_ram": 10,
        "chat_template": "qwen",
        "lang": "zh+en",
        "recommended_for": "桌面 / 10GB+ 内存 / 主力使用",
    },
    "qwen3-14b": {
        "name": "Qwen3 14B Instruct",
        "repo": "Qwen/Qwen3-14B-Instruct-GGUF",
        "file": "qwen3-14b-instruct-q4_k_m.gguf",
        "size": 9.5,
        "min_ram": 18,
        "chat_template": "qwen",
        "lang": "zh+en",
        "recommended_for": "强设备 / 18GB+ 内存 / 高质量推理",
    },
    "llama3.3-8b": {
        "name": "Llama 3.3 8B Instruct",
        "repo": "bartowski/Llama-3.3-8B-Instruct-GGUF",
        "file": "Llama-3.3-8B-Instruct-Q4_K_M.gguf",
        "size": 5.5,
        "min_ram": 12,
        "chat_template": "llama3",
        "lang": "en",
        "recommended_for": "英文场景 / 高质量推理",
    },
    "smollm-1.7b": {
        "name": "SmolLM2 1.7B Instruct",
        "repo": "HuggingFaceTB/SmolLM2-1.7B-Instruct-v0.1-GGUF",
        "file": "smollm2-1.7b-instruct-v0.1-q4_k_m.gguf",
        "size": 1.1,
        "min_ram": 3,
        "chat_template": "chatml",
        "lang": "en",
        "recommended_for": "极限小模型 / 3GB 内存",
    },
}

DOWNLOAD_MIRRORS: list[str] = [
    "https://huggingface.co/{repo}/resolve/main/{file}",
    "https://hf-mirror.com/{repo}/resolve/main/{file}",
]


# ---- 硬件检测 ----

@dataclass
class HardwareProfile:
    system: str
    machine: str  # x86_64 / arm64
    cpu_cores: int
    ram_gb: float
    has_gpu: bool = False
    gpu_type: str | None = None  # cuda / metal / vulkan

    def recommend_model(self) -> str:
        """根据硬件推荐最合适的模型 ID。"""
        if self.ram_gb >= 18:
            return "qwen3-14b"
        if self.ram_gb >= 10:
            return "qwen3-7b"
        if self.ram_gb >= 4:
            return "qwen3-1.7b"
        return "smollm-1.7b"


def detect_hardware() -> HardwareProfile:
    """检测 CPU/内存/GPU。"""
    system = platform.system()
    machine = platform.machine()
    cores = os.cpu_count() or 4

    ram_gb = 8.0
    try:
        if system == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            total_bytes = ctypes.c_ulonglong()
            kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(total_bytes))
            ram_gb = total_bytes.value / (1024 * 1024)
        elif system == "Darwin" or system == "Linux":
            try:
                import psutil
                ram_gb = psutil.virtual_memory().total / (1024 ** 3)
            except ImportError:
                if system == "Linux":
                    with open("/proc/meminfo") as f:
                        for line in f:
                            if line.startswith("MemTotal:"):
                                kb = int(line.split()[1])
                                ram_gb = kb / (1024 * 1024)
                                break
    except Exception:
        pass

    # GPU 检测
    gpu = False
    gpu_type = None
    if system == "Darwin":
        gpu = True  # macOS 金属加速器默认可用
        gpu_type = "metal"
    else:
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, timeout=5, check=False)
            gpu = True
            gpu_type = "cuda"
        except Exception:
            pass

    return HardwareProfile(
        system=system,
        machine=machine,
        cpu_cores=cores,
        ram_gb=round(ram_gb, 1),
        has_gpu=gpu,
        gpu_type=gpu_type,
    )


# ---- 模型下载 ----

class ModelDownloader:
    """分块下载模型，支持断点续传 + 多镜像。"""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def model_path(self, model_id: str) -> Path:
        return self.cache_dir / f"{model_id}.gguf"

    def already_has(self, model_id: str) -> bool:
        p = self.model_path(model_id)
        return p.exists() and p.stat().st_size > 1024 * 1024  # >1MB 才算完整

    def download(self, model_id: str, on_progress=None, timeout_sec: int = 3600) -> Path:
        """同步下载，on_progress(done_bytes, total_bytes) 用于 UI。返回保存路径。"""
        if model_id not in MODEL_CATALOG:
            raise ValueError(f"未知模型: {model_id}")
        info = MODEL_CATALOG[model_id]
        save_path = self.model_path(model_id)

        if self.already_has(model_id):
            if on_progress:
                on_progress(int(save_path.stat().st_size), int(save_path.stat().st_size))
            return save_path

        start_time = time.time()
        last_error: Exception | None = None

        for mirror in DOWNLOAD_MIRRORS:
            url = mirror.format(repo=info["repo"], file=info["file"])
            try:
                self._download_once(url, save_path, on_progress, timeout_sec)
                elapsed = time.time() - start_time
                if on_progress:
                    on_progress(save_path.stat().st_size, save_path.stat().st_size)
                return save_path
            except Exception as e:
                last_error = e
                # 清理不完整的文件
                if save_path.exists():
                    save_path.unlink()

        raise RuntimeError(
            f"模型 {model_id} 下载失败，所有镜像均不可用。最后错误: {last_error}"
        )

    def _download_once(self, url: str, save_path: Path, on_progress, timeout_sec: int) -> None:
        # 支持断点续传：如果已有临时文件，从该位置继续
        tmp_path = save_path.with_suffix(".gguf.tmp")
        resume_pos = tmp_path.stat().st_size if tmp_path.exists() else 0

        headers = {}
        if resume_pos:
            headers["Range"] = f"bytes={resume_pos}-"

        with httpx.stream(
            "GET", url,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_sec, connect=30),
        ) as r:
            if r.status_code not in (200, 206):
                raise RuntimeError(f"HTTP {r.status_code}")

            total = int(r.headers.get("content-length", "0"))
            mode = "ab" if r.status_code == 206 else "wb"
            if mode == "wb":
                resume_pos = 0

            with open(tmp_path, mode) as f:
                downloaded = resume_pos
                for chunk in r.iter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total + resume_pos if total else downloaded)

        # 完成后改名为正式路径
        tmp_path.replace(save_path)


# ---- 本地 LLM 服务（基于 llama_cpp） ----

@dataclass
class RunningServer:
    host: str
    port: int
    model_id: str
    model_name: str
    process: subprocess.Popen | None = None
    started_at: float = field(default_factory=time.time)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def model_endpoint(self) -> str:
        return f"{self.base_url}/v1"

    def is_alive(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    async def wait_ready(self, timeout: int = 120) -> bool:
        """轮询 /health 直到可用。"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                r = httpx.get(f"{self.base_url}/docs", timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await _async_sleep(2)
        return False

    def stop(self) -> None:
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


async def _async_sleep(sec: float) -> None:
    # 小工具：支持 async sleep（不在 async 上下文也能跑）
    import asyncio
    try:
        await asyncio.sleep(sec)
    except RuntimeError:
        time.sleep(sec)


class LocalLLM:
    """封装 llama.cpp 的本地推理服务。

    生命周期：
        llm = LocalLLM(cache_dir)
        llm.download("qwen3-1.7b")      # 或跳过（已下载）
        server = llm.start("qwen3-1.7b") # 后台启动
        # 用 self.base_url 发送请求
        server.stop()
    """

    def __init__(self, cache_dir: Path | None = None, port: int = 18080) -> None:
        self.cache_dir = cache_dir or Path.home() / ".deep_research" / "models"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.downloader = ModelDownloader(self.cache_dir)
        self._current_server: RunningServer | None = None

    # ---- 依赖检查 ----

    def ensure_llama_cpp(self) -> bool:
        """确保 llama_cpp_python 已安装，不可用时自动安装。"""
        try:
            import llama_cpp  # noqa: F401
            return True
        except ImportError:
            pass

        # 自动安装
        cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python"]
        # 如有 GPU，额外加标志
        hw = detect_hardware()
        env = os.environ.copy()
        if hw.gpu_type == "metal":
            env["CMAKE_ARGS"] = "-DLLAMA_METAL=on"
        elif hw.gpu_type == "cuda":
            env["CMAKE_ARGS"] = "-DLLAMA_CUBLAS=on"

        try:
            subprocess.run(cmd, check=True, env=env, capture_output=False)
            return True
        except Exception:
            return False

    def list_models(self) -> list[dict[str, Any]]:
        """返回可用模型 + 本地已下载状态。"""
        result = []
        for mid, info in MODEL_CATALOG.items():
            result.append({
                "id": mid,
                "name": info["name"],
                "size_gb": info["size"],
                "min_ram": info["min_ram"],
                "lang": info["lang"],
                "recommended_for": info["recommended_for"],
                "downloaded": self.downloader.already_has(mid),
            })
        return result

    # ---- 下载 ----

    def download(self, model_id: str, on_progress=None) -> Path:
        return self.downloader.download(model_id, on_progress=on_progress)

    # ---- 启动 ----

    def start(self, model_id: str, *, n_ctx: int = 8192) -> RunningServer:
        """启动 llama_cpp.server，返回可调用的 RunningServer。

        接口：http://localhost:<port>/v1/chat/completions （与 OpenAI 兼容）
        """
        if not self.ensure_llama_cpp():
            raise RuntimeError("llama-cpp-python 安装失败，请手动安装后重试")

        model_path = self.downloader.model_path(model_id)
        if not model_path.exists():
            raise RuntimeError(f"模型文件不存在: {model_path}，请先 download()")

        # 如果已在跑，先停掉
        if self._current_server and self._current_server.is_alive():
            self._current_server.stop()

        # 启动
        hw = detect_hardware()
        n_threads = max(2, hw.cpu_cores - 1 if hw.cpu_cores else 4)

        # llama_cpp.server 的环境变量配置（避免命令行参数复杂）
        env = os.environ.copy()
        env["MODEL"] = str(model_path)
        env["N_CTX"] = str(n_ctx)
        env["N_THREADS"] = str(n_threads)
        env["HOST"] = "127.0.0.1"
        env["PORT"] = str(self.port)
        env["CHAT_FORMAT"] = MODEL_CATALOG[model_id]["chat_template"]
        env["VERBOSE"] = "false"

        cmd = [sys.executable, "-m", "llama_cpp.server"]
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        server = RunningServer(
            host="127.0.0.1",
            port=self.port,
            model_id=model_id,
            model_name=MODEL_CATALOG[model_id]["name"],
            process=proc,
        )
        self._current_server = server

        # ⭐ 关键：把本地服务 URL 写入环境变量，LLMClient 会自动切换到本地
        os.environ["LOCAL_LLM_BASE_URL"] = server.model_endpoint
        os.environ["LOCAL_LLM_NAME"] = server.model_name

        return server

    def stop(self) -> None:
        if self._current_server:
            self._current_server.stop()
            self._current_server = None
        # 清理环境变量（恢复默认行为）
        os.environ.pop("LOCAL_LLM_BASE_URL", None)
        os.environ.pop("LOCAL_LLM_NAME", None)


# 便捷函数
def get_default_llm(cache_dir: Path | None = None, port: int = 18080) -> LocalLLM:
    return LocalLLM(cache_dir=cache_dir, port=port)


def status_json(local_llm: LocalLLM | None, hw: HardwareProfile | None = None) -> dict:
    """给 Web UI 返回可读的状态字典。"""
    hw = hw or detect_hardware()
    return {
        "hardware": {
            "system": hw.system,
            "machine": hw.machine,
            "cpu_cores": hw.cpu_cores,
            "ram_gb": hw.ram_gb,
            "has_gpu": hw.has_gpu,
            "gpu_type": hw.gpu_type,
            "recommended_model": hw.recommend_model(),
        },
        "models": local_llm.list_models() if local_llm else [],
        "server": {
            "running": local_llm._current_server.is_alive() if local_llm and local_llm._current_server else False,
            "base_url": local_llm._current_server.model_endpoint if local_llm and local_llm._current_server else None,
            "model_name": local_llm._current_server.model_name if local_llm and local_llm._current_server else None,
        },
    }


__all__ = [
    "MODEL_CATALOG",
    "HardwareProfile",
    "detect_hardware",
    "ModelDownloader",
    "RunningServer",
    "LocalLLM",
    "get_default_llm",
    "status_json",
]
