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

# 加速器类型枚举（后端映射到具体驱动/SDK）
ACCEL_KIND_GPU = "gpu"
ACCEL_KIND_NPU = "npu"

# 所有已知加速器
ACCEL_SUBTYPE_CUDA = "cuda"          # NVIDIA CUDA (NVIDIA GPU)
ACCEL_SUBTYPE_ROCM = "rocm"          # AMD ROCm (AMD RDNA/Ryzen AI)
ACCEL_SUBTYPE_METAL = "metal"        # Apple Metal (Apple Silicon GPU + ANE)
ACCEL_SUBTYPE_VULKAN = "vulkan"      # Vulkan (Adreno/Intel Arc)
ACCEL_SUBTYPE_INTEL_NPU = "intel_npu"   # Intel Core Ultra NPU (Meteor Lake / Arrow Lake)
ACCEL_SUBTYPE_SNAPDRAGON = "snapdragon" # Qualcomm Hexagon NPU
ACCEL_SUBTYPE_ASCEND = "ascend"      # Huawei 昇腾 (CANN/atb)
ACCEL_SUBTYPE_OPENVINO = "openvino"    # Intel OpenVINO (兜底)


@dataclass
class Accelerator:
    """一个加速器信息。"""
    kind: str                      # "gpu" 或 "npu"
    subtype: str                     # 具体后端类型（cuda/rocm/metal/vulkan/intel_npu/snapdragon/ascend）
    name: str                      # 产品名，如 "NVIDIA GeForce RTX 4090"
    brand: str                     # 品牌
    tops: float | None = None           # 估算 TOPS 算力
    arch: str | None = None       # 架构/代际代号
    memory_gb: float | None = None # 显存/内存


@dataclass
class HardwareProfile:
    system: str
    machine: str  # x86_64 / arm64 / aarch64
    cpu_cores: int
    ram_gb: float
    gpu_names: list[str] = field(default_factory=list)
    # 通用加速器列表（按优先级排序：GPU > NPU，同组内按 TOPS 降序）
    accelerators: list[Accelerator] = field(default_factory=list)

    @property
    def has_gpu(self) -> bool:
        return any(a.kind == ACCEL_KIND_GPU for a in self.accelerators)

    @property
    def has_npu(self) -> bool:
        return any(a.kind == ACCEL_KIND_NPU for a in self.accelerators)

    @property
    def best_gpu(self) -> Accelerator | None:
        gpus = [a for a in self.accelerators if a.kind == ACCEL_KIND_GPU]
        return gpus[0] if gpus else None

    @property
    def best_npu(self) -> Accelerator | None:
        npus = [a for a in self.accelerators if a.kind == ACCEL_KIND_NPU]
        return npus[0] if npus else None

    def recommend_model(self) -> str:
        """根据内存推荐最合适的模型 ID。"""
        if self.ram_gb >= 18:
            return "qwen3-14b"
        if self.ram_gb >= 10:
            return "qwen3-7b"
        if self.ram_gb >= 4:
            return "qwen3-1.7b"
        return "smollm-1.7b"

    def recommend_deployment_mode(self) -> str:
        """根据机器算力自动推荐部署模式：'api' 或 'local'。

        推荐本地部署的条件（需同时满足）：
          1. 有 GPU 或 NPU（TOPS >= 3）
          2. 内存 >= 4 GB
        否则推荐 API 模式（无需下载模型，速度更快）。

        规则说明：
          - 手机 / 低配机器：API 优先（省电省内存）
          - 有 NPU/GPU + 内存 >= 4GB：本地部署（保护隐私 + 离线可用）
          - 纯 CPU + 内存 < 8GB：强烈推荐 API（本地推理极慢）
          - 服务器 / 台式机 + 强加速器：本地部署（可跑更大模型）
        """
        # 基础门槛：内存不足 4GB → 不适合本地
        if self.ram_gb < 4:
            return "api"

        # 有加速器（GPU 或 NPU）且 TOPS >= 3 → 本地优先
        best_acc = self.accelerators[0] if self.accelerators else None
        if best_acc and (best_acc.tops or 0) >= 3:
            return "local"

        # 无加速器：纯 CPU 推理
        if not best_acc:
            # 内存 >= 8GB 且核心 >= 4 → 本地勉强可用（但很慢）
            if self.ram_gb >= 8 and self.cpu_cores >= 4:
                return "local"
            # 否则 → API
            return "api"

        # 有加速器但 TOPS < 3 → 降级到 API
        return "api"

    def best_accelerator_for_backend(self, backend: str) -> Accelerator | None:
        """按后端名查找最合适的加速器。"""
        for a in self.accelerators:
            if a.subtype == backend:
                return a
        return None

    def detected_backends(self) -> list[str]:
        """返回当前机器上实际检测到的后端类型列表（去重，保留顺序）。"""
        seen: set[str] = set()
        result: list[str] = []
        for a in self.accelerators:
            if a.subtype not in seen:
                seen.add(a.subtype)
                result.append(a.subtype)
        return result


# ---- 通用加速器检测：多品牌扫描 ----

# Snapdragon NPU (Hexagon) 映射表（按芯片型号 → 代际/TOPS）
SNAPDRAGON_NPU_TABLE = [
    # (pattern, npu_type(nsp/hvx), arch, tops)
    ("Snapdragon X Elite",      "hexagon_nsp", "v75", 45.0),
    ("Snapdragon X Plus",       "hexagon_nsp", "v75", 38.0),
    ("Snapdragon 8 Gen 3",      "hexagon_nsp", "v73", 33.0),
    ("Snapdragon 8 Gen 2",      "hexagon_nsp", "v69", 27.0),
    ("Snapdragon 8 Gen 1",      "hexagon_nsp", "v68", 18.0),
    ("Snapdragon 7[^,\n]*Gen",  "hexagon_nsp", "v66", 10.0),
    ("Snapdragon 6[^,\n]*Gen",  "hexagon_hvx", "v65",  4.0),
    ("Snapdragon 865",          "hexagon_hvx", "v62",  5.0),
    ("Snapdragon 855",          "hexagon_hvx", "v60",  4.0),
    ("Snapdragon 8cx",          "hexagon_hvx", "v60",  5.0),
]


def _detect_nvidia_gpus() -> list[Accelerator]:
    """通过 nvidia-smi 检测 NVIDIA GPU。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, timeout=10, check=False,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        accs: list[Accelerator] = []
        for line in r.stdout.decode(errors="ignore").strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 1:
                name = parts[0] or "NVIDIA GPU"
                mem_gb: float | None = None
                if len(parts) >= 2 and parts[1]:
                    try:
                        mem_mb = int(parts[1].split()[0])
                        mem_gb = round(mem_mb / 1024, 1)
                    except Exception:
                        pass
                accs.append(Accelerator(
                    kind=ACCEL_KIND_GPU,
                    subtype=ACCEL_SUBTYPE_CUDA,
                    name=name,
                    brand="NVIDIA",
                    memory_gb=mem_gb,
                    # 粗略估算 TOPS（不精确，只用于排序参考）
                    tops=mem_gb * 25 if mem_gb else None,
                ))
        return accs
    except Exception:
        return []


def _detect_amd_gpus() -> list[Accelerator]:
    """通过 rocm-smi 检测 AMD GPU / ROCm。"""
    try:
        # 优先 rocm-smi，无则退回 lspci
        r = subprocess.run(
            ["rocm-smi", "--showproductname", "--json"],
            capture_output=True, timeout=15, check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                data = json.loads(r.stdout)
                accs: list[Accelerator] = []
                for key, info in data.items():
                    name = info.get("Card series", "") or info.get("Card SKU", "") or "AMD Radeon GPU"
                    mem = info.get("VRAM (MB)", 0) or 0
                    try:
                        mem_gb = round(float(mem) / 1024, 1)
                    except Exception:
                        mem_gb = None
                    accs.append(Accelerator(
                        kind=ACCEL_KIND_GPU,
                        subtype=ACCEL_SUBTYPE_ROCM,
                        name=name,
                        brand="AMD",
                        memory_gb=mem_gb,
                        tops=mem_gb * 20 if mem_gb else None,
                    ))
                return accs
            except Exception:
                pass
    except Exception:
        pass

    # fallback: lspci 扫描 "AMD/ATI Radeon" / "AMD Instinct"
    accs: list[Accelerator] = []
    try:
        r = subprocess.run(["lspci"], capture_output=True, timeout=8, check=False)
        if r.returncode == 0:
            for line in r.stdout.decode(errors="ignore").splitlines():
                low = line.lower()
                if ("amd" in low or "radeon" in low) and ("3d" in low or "display" in low):
                    name = line.split(":")[-1].strip() if ":" in line else line.strip()
                    accs.append(Accelerator(
                        kind=ACCEL_KIND_GPU,
                        subtype=ACCEL_SUBTYPE_ROCM,
                        name=name,
                        brand="AMD",
                        tops=30.0,
                    ))
    except Exception:
        pass
    return accs


def _detect_intel_arc_or_npu() -> tuple[list[Accelerator], list[Accelerator]]:
    """检测 Intel Arc GPU 和 Intel Core Ultra NPU (Meteor Lake / Arrow Lake)。

    返回: (arc_gpus, intel_npus)
    """
    import re
    gpus: list[Accelerator] = []
    npus: list[Accelerator] = []

    # --- 方法 1: lspci（Linux） ---
    try:
        r = subprocess.run(["lspci"], capture_output=True, timeout=8, check=False)
        if r.returncode == 0:
            for line in r.stdout.decode(errors="ignore").splitlines():
                low = line.lower()
                # Intel Arc GPU
                if "intel" in low and ("iris" in low or "arc" in low or "xe" in low):
                    name = line.split(":")[-1].strip() if ":" in line else line.strip()
                    gpus.append(Accelerator(
                        kind=ACCEL_KIND_GPU,
                        subtype=ACCEL_SUBTYPE_VULKAN,
                        name=name,
                        brand="Intel",
                        tops=10.0,
                    ))
                # Intel NPU (Meteor Lake NPU, PCI device class 0b40)
                if "0b40" in line or ("npu" in low and "intel" in low) or "neural processing" in low:
                    name = "Intel Core Ultra NPU"
                    if ":" in line:
                        name = line.split(":")[-1].strip()
                    npus.append(Accelerator(
                        kind=ACCEL_KIND_NPU,
                        subtype=ACCEL_SUBTYPE_INTEL_NPU,
                        name=name,
                        brand="Intel",
                        tops=10.0,
                        arch="Meteor Lake / Arrow Lake",
                    ))
    except Exception:
        pass

    # --- 方法 2: /sys/class/accel (Linux 通用 NPU 子系统) ---
    try:
        import glob as _glob
        for accel_path in _glob.glob("/sys/class/accel/accel*/"):
            try:
                name_file = accel_path + "device/name"
                vendor_file = accel_path + "device/vendor"
                device_file = accel_path + "device/device"
                name = "Unknown Accelerator"
                if os.path.exists(name_file):
                    name = open(name_file).read().strip()
                # 读取 vendor ID
                vendor = ""
                if os.path.exists(vendor_file):
                    vendor = open(vendor_file).read().strip()
                if os.path.exists(device_file):
                    dev = open(device_file).read().strip()
                    # 0x8086 = Intel
                    if "8086" in vendor or "intel" in name.lower():
                        npus.append(Accelerator(
                            kind=ACCEL_KIND_NPU,
                            subtype=ACCEL_SUBTYPE_INTEL_NPU,
                            name=name,
                            brand="Intel",
                            tops=10.0,
                            arch="Core Ultra NPU",
                        ))
                    # 0x19e5 = 华为昇腾 (HiSilicon)
                    elif "19e5" in vendor or "ascend" in name.lower() or "huawei" in name.lower():
                        npus.append(Accelerator(
                            kind=ACCEL_KIND_NPU,
                            subtype=ACCEL_SUBTYPE_ASCEND,
                            name=name,
                            brand="Huawei Ascend",
                            tops=16.0,
                            arch="昇腾",
                        ))
            except Exception:
                pass
    except Exception:
        pass

    return gpus, npus


def _detect_snapdragon_npu() -> list[Accelerator]:
    """检测 Qualcomm Snapdragon Hexagon NPU（移动端 SoC / X Elite）。"""
    import re
    accs: list[Accelerator] = []

    # --- 1. /proc/cpuinfo 中的 Qualcomm / Kryo 签名 ---
    cpuinfo = ""
    try:
        with open("/proc/cpuinfo") as f:
            cpuinfo = f.read()
    except Exception:
        pass

    is_qualcomm = bool(
        re.search(r"Hardware\s*[:=]\s*.*[Qq]ualcomm", cpuinfo) or
        re.search(r"model name\s*[:=]\s*Kryo", cpuinfo) or
        re.search(r"CPU architecture.*AArch64.*Qualcomm", cpuinfo)
    )

    npu_brand: str | None = None
    for pattern in [
        r"(Snapdragon\s+X\s*Elite)",
        r"(Snapdragon\s+X\s*Plus)",
        r"(Snapdragon\s+8\s*Gen\s*\d)",
        r"(Snapdragon\s+7[^\s,\n]*\s*Gen\s*\d?)",
        r"(Snapdragon\s+6[^\s,\n]*\s*Gen\s*\d?)",
        r"(Snapdragon\s+865)",
        r"(Snapdragon\s+855)",
        r"(Snapdragon\s+8cx)",
    ]:
        m = re.search(pattern, cpuinfo, re.IGNORECASE)
        if m:
            npu_brand = m.group(1).strip()
            break

    # --- 2. Hexagon HVX 协处理器设备节点 ---
    try:
        import os as _os
        has_hvx = (
            _os.path.exists("/dev/hvx") or
            _os.path.exists("/dev/qvr-hvx") or
            _os.path.exists("/dev/adsprpc")
        )
    except Exception:
        has_hvx = False

    # --- 3. /sys/devices/soc0/ 路径 ---
    soc_family = ""
    try:
        for sp in ["/sys/devices/soc0/", "/sys/firmware/devicetree/base/"]:
            for fname in ["family", "machine"]:
                for attempt in [f"{sp}{fname}", f"{sp}@{fname}"]:
                    try:
                        val = open(attempt).read().strip()[:64]
                        if val and ("qcom" in val.lower() or "qualcomm" in val.lower()):
                            soc_family = val
                    except Exception:
                        pass
    except Exception:
        pass

    if not is_qualcomm and not npu_brand and not soc_family:
        return accs

    # --- 4. 查表推断代际 ---
    selected_ntype = "hexagon_hvx"
    selected_arch = "v60"
    selected_tops = 3.5
    if npu_brand:
        for pattern, ntype, arch, tops in SNAPDRAGON_NPU_TABLE:
            if re.search(pattern, npu_brand, re.IGNORECASE):
                selected_ntype = ntype
                selected_arch = arch
                selected_tops = tops
                break

    # Adreno GPU（骁龙自带）
    try:
        import glob as _glob
        for d in _glob.glob("/sys/class/drm/card*/device/name"):
            try:
                name = open(d).read().strip()
                if "adreno" in name.lower():
                    accs.append(Accelerator(
                        kind=ACCEL_KIND_GPU,
                        subtype=ACCEL_SUBTYPE_VULKAN,
                        name=name,
                        brand="Qualcomm",
                        tops=2.5,
                    ))
            except Exception:
                pass
    except Exception:
        pass

    accs.append(Accelerator(
        kind=ACCEL_KIND_NPU,
        subtype=ACCEL_SUBTYPE_SNAPDRAGON,
        name="Qualcomm Hexagon NPU " + (npu_brand or ""),
        brand="Qualcomm",
        tops=selected_tops,
        arch=selected_arch,
    ))
    return accs


def _detect_ascend_npus() -> list[Accelerator]:
    """检测华为昇腾 (Ascend) NPU / AI Accelerator。"""
    accs: list[Accelerator] = []

    # --- 1. npu-smi (官方 CLI) ---
    try:
        r = subprocess.run(["npu-smi", "info", "-l"], capture_output=True, timeout=10, check=False)
        if r.returncode == 0 and r.stdout.strip():
            text = r.stdout.decode(errors="ignore")
            for line in text.splitlines():
                if "npu" in line.lower() or "chip" in line.lower() or "type" in line.lower():
                    accs.append(Accelerator(
                        kind=ACCEL_KIND_NPU,
                        subtype=ACCEL_SUBTYPE_ASCEND,
                        name="Huawei Ascend NPU " + line.strip(),
                        brand="Huawei Ascend",
                        tops=16.0,
                        arch="Ascend 310 / 910",
                    ))
    except Exception:
        pass

    # --- 2. /sys/class/cann / /sys/class/npu 路径（华为 CANN 驱动） ---
    try:
        import glob as _glob
        for npu_path in _glob.glob("/sys/class/npu/npu*/"):
            try:
                name_file = npu_path + "device/name"
                name = "Ascend NPU"
                if os.path.exists(name_file):
                    name = open(name_file).read().strip()
                accs.append(Accelerator(
                    kind=ACCEL_KIND_NPU,
                    subtype=ACCEL_SUBTYPE_ASCEND,
                    name=name,
                    brand="Huawei Ascend",
                    tops=16.0,
                    arch="Ascend",
                ))
            except Exception:
                pass
        for npu_path in _glob.glob("/sys/class/cann/*/"):
            try:
                name_file = npu_path + "device/name"
                name = "Ascend NPU (CANN)"
                if os.path.exists(name_file):
                    name = open(name_file).read().strip()
                accs.append(Accelerator(
                    kind=ACCEL_KIND_NPU,
                    subtype=ACCEL_SUBTYPE_ASCEND,
                    name=name,
                    brand="Huawei Ascend",
                    tops=16.0,
                    arch="Ascend CANN",
                ))
            except Exception:
                pass
    except Exception:
        pass

    # --- 3. lsascend ---
    try:
        r = subprocess.run(["lsascend"], capture_output=True, timeout=8, check=False)
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.decode(errors="ignore").splitlines():
                accs.append(Accelerator(
                    kind=ACCEL_KIND_NPU,
                    subtype=ACCEL_SUBTYPE_ASCEND,
                    name="Ascend " + line.strip(),
                    brand="Huawei Ascend",
                    tops=16.0,
                    arch="Ascend",
                ))
    except Exception:
        pass

    return accs


def _detect_apple_metal() -> list[Accelerator]:
    """macOS 上检测 Apple Silicon（用 Metal 加速 GPU+ANE）。"""
    if platform.system() != "Darwin":
        return []

    # sysctl 查询 chip 信息
    chip_name = "Apple Silicon"
    try:
        r = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                         capture_output=True, timeout=5, check=False)
        if r.stdout.strip():
            chip_name = r.stdout.decode(errors="ignore").strip()
    except Exception:
        pass

    try:
        # hw.memsize
        r = subprocess.run(["sysctl", "-n", "hw.memsize"],
                         capture_output=True, timeout=5, check=False)
        if r.stdout.strip():
            mem_bytes = int(r.stdout.decode().strip())
            ram_gb_hint = round(mem_bytes / (1024**3), 1)
        else:
            ram_gb_hint = 16.0
    except Exception:
        ram_gb_hint = 16.0

    # TOPS 粗略估算（MacBook Pro M3 ≈ 15-25 TOPS）
    tops_estimate = ram_gb_hint * 1.5

    return [Accelerator(
        kind=ACCEL_KIND_GPU,
        subtype=ACCEL_SUBTYPE_METAL,
        name=chip_name + " (Metal GPU + ANE)",
        brand="Apple",
        tops=tops_estimate,
        memory_gb=ram_gb_hint,
    )]


def _sort_accelerators(accs: list[Accelerator]) -> list[Accelerator]:
    """GPU 优先于 NPU；同组内按 TOPS 降序。"""
    def sort_key(a):
        kind_prio = 0 if a.kind == ACCEL_KIND_GPU else 1
        tops_prio = -(a.tops or 0.0)
        return (kind_prio, tops_prio)
    return sorted(accs, key=sort_key)


def detect_hardware() -> HardwareProfile:
    """检测 CPU / 内存 / 所有加速器（GPU + NPU 多品牌）。"""
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

    # --- 并行扫描所有加速器品牌 ---
    all_accs: list[Accelerator] = []

    # 1. Apple Metal
    if system == "Darwin":
        all_accs.extend(_detect_apple_metal())

    # 2. NVIDIA CUDA
    all_accs.extend(_detect_nvidia_gpus())

    # 3. AMD ROCm
    all_accs.extend(_detect_amd_gpus())

    # 4. Intel Arc + Intel Core Ultra NPU
    intel_gpus, intel_npus = _detect_intel_arc_or_npu()
    all_accs.extend(intel_gpus)
    all_accs.extend(intel_npus)

    # 5. Qualcomm Snapdragon Hexagon NPU + Adreno
    all_accs.extend(_detect_snapdragon_npu())

    # 6. Huawei Ascend
    all_accs.extend(_detect_ascend_npus())

    # 7. 去重（相同 brand+name 只保留一个）
    seen = set()
    unique_accs: list[Accelerator] = []
    for a in all_accs:
        key = (a.brand, a.name)
        if key in seen:
            continue
        seen.add(key)
        unique_accs.append(a)

    # 8. 排序（GPU > NPU，按 TOPS）
    sorted_accs = _sort_accelerators(unique_accs)
    gpu_names = [a.name for a in sorted_accs if a.kind == ACCEL_KIND_GPU]

    return HardwareProfile(
        system=system,
        machine=machine,
        cpu_cores=cores,
        ram_gb=round(ram_gb, 1),
        gpu_names=gpu_names,
        accelerators=sorted_accs,
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
        # 如有加速器，额外加 CMAKE 标志
        hw = detect_hardware()
        env = os.environ.copy()
        cmake_args: list[str] = []

        if hw.gpu_type == "metal":
            cmake_args.append("-DLLAMA_METAL=on")
        elif hw.gpu_type == "cuda":
            cmake_args.append("-DLLAMA_CUBLAS=on")
        elif hw.gpu_type == "adreno":
            cmake_args.append("-DLLAMA_VULKAN=on")
        # ---- 骁龙 Hexagon NPU ----
        elif hw.has_npu and hw.npu_type:
            if hw.npu_type == "hexagon_nsp":
                # 新代 Hexagon NSP（X Elite / 8 Gen3）：用 Vulkan + Hexagon 后端
                cmake_args.append("-DLLAMA_VULKAN=on")
                cmake_args.append("-DLLAMA_HIPBLAS=on")
                cmake_args.append(f"-DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc")
                cmake_args.append(f"-DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++")
            elif hw.npu_type == "hexagon_hvx":
                # HVX DSP：尽量用 HIP 或 Vulkan
                cmake_args.append("-DLLAMA_VULKAN=on")

        if cmake_args:
            env["CMAKE_ARGS"] = " ".join(cmake_args)
            # 告诉 llama.cpp server 用哪种后端
            if hw.has_npu and hw.npu_type == "hexagon_nsp":
                env["LLAMA_BACKEND"] = "vulkan"
            elif hw.has_npu and hw.npu_type == "hexagon_hvx":
                env["LLAMA_BACKEND"] = "vulkan"

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

    def _configure_backend_env(self, backend: str, hw: HardwareProfile) -> dict[str, str]:
        """根据用户选择的推理后端配置环境变量，返回 env dict。

        backend 可接受：
          - "auto" / "cpu"
          - "cuda"  / "rocm" / "metal" / "vulkan"
          - "intel_npu" / "snapdragon" / "ascend"
          - "openvino"
        """
        env = os.environ.copy()

        def clear_acc_flags(target_env: dict):
            for key in ["GGML_CUDA", "GGML_METAL", "GGML_VULKAN", "GGML_HVX",
                        "GGML_NPU", "GGML_CPU_ONLY", "GGML_SYCL", "GGML_OPENCL",
                        "LLAMA_CUDA", "LLAMA_METAL", "LLAMA_VULKAN"]:
                target_env.pop(key, None)

        clear_acc_flags(env)

        if backend == "cpu":
            env["GGML_CPU_ONLY"] = "1"

        elif backend == "auto":
            # 选列表第一个加速器
            best = hw.accelerators[0] if hw.accelerators else None
            if best is None:
                env["GGML_CPU_ONLY"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_CUDA:
                env["GGML_CUDA"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_METAL:
                env["GGML_METAL"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_ROCM:
                # AMD ROCm：目前用 HIPBLAS + Vulkan 路径
                env["GGML_VULKAN"] = "1"
                env["LLAMA_VULKAN"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_VULKAN:
                env["GGML_VULKAN"] = "1"
                env["LLAMA_VULKAN"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_SNAPDRAGON:
                env["GGML_VULKAN"] = "1"
                env["GGML_HVX"] = "1"
                env["GGML_NPU"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_INTEL_NPU:
                env["GGML_VULKAN"] = "1"
                env["GGML_SYCL"] = "1"
            elif best.subtype == ACCEL_SUBTYPE_ASCEND:
                env["GGML_VULKAN"] = "1"
                env["GGML_SYCL"] = "1"
            else:
                env["GGML_CPU_ONLY"] = "1"

        # ---- GPU 后端 ----
        elif backend == "cuda":
            env["GGML_CUDA"] = "1"
            env["LLAMA_CUDA"] = "1"

        elif backend == "rocm":
            env["GGML_VULKAN"] = "1"
            env["LLAMA_VULKAN"] = "1"

        elif backend == "metal":
            env["GGML_METAL"] = "1"
            env["LLAMA_METAL"] = "1"

        elif backend == "vulkan":
            env["GGML_VULKAN"] = "1"
            env["LLAMA_VULKAN"] = "1"

        # ---- NPU 后端 ----
        elif backend == "snapdragon":
            env["GGML_VULKAN"] = "1"
            env["GGML_HVX"] = "1"
            env["GGML_NPU"] = "1"

        elif backend == "intel_npu":
            env["GGML_VULKAN"] = "1"
            env["GGML_SYCL"] = "1"

        elif backend == "ascend":
            env["GGML_VULKAN"] = "1"
            env["GGML_SYCL"] = "1"

        # ---- 兜底后端 ----
        elif backend == "openvino":
            env["GGML_SYCL"] = "1"

        else:
            # 未知后端 → 退回 CPU
            env["GGML_CPU_ONLY"] = "1"

        return env

    def start(
        self,
        model_id: str,
        *,
        n_ctx: int = 8192,
        backend: str = "auto",
    ) -> RunningServer:
        """启动 llama_cpp.server，返回可调用的 RunningServer。

        backend 可接受：
          - "auto" / "cpu"
          - "cuda" / "rocm" / "metal" / "vulkan"
          - "intel_npu" / "snapdragon" / "ascend"
          - "openvino"

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

        hw = detect_hardware()
        n_threads = max(2, hw.cpu_cores - 1 if hw.cpu_cores else 4)

        # 基础环境变量
        env = os.environ.copy()
        env["MODEL"] = str(model_path)
        env["N_CTX"] = str(n_ctx)
        env["N_THREADS"] = str(n_threads)
        env["HOST"] = "127.0.0.1"
        env["PORT"] = str(self.port)
        env["CHAT_FORMAT"] = MODEL_CATALOG[model_id]["chat_template"]
        env["VERBOSE"] = "false"

        # 应用用户选择的后端
        env = self._configure_backend_env(backend, hw)
        # 同时设置 LLAMA_SERVER_BACKEND 方便 llama_cpp.server 读取
        env["LLAMA_SERVER_BACKEND"] = backend

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
        os.environ["LOCAL_LLM_BACKEND"] = backend  # 记录当前后端

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
    """给 Web UI 返回可读的状态字典（包含完整的加速器列表）。"""
    hw = hw or detect_hardware()

    # 把 accelerators 转成前端可读取的 list[dict]
    accel_dicts = []
    for a in hw.accelerators:
        accel_dicts.append({
            "kind": a.kind,           # "gpu" 或 "npu"
            "subtype": a.subtype,     # "cuda" / "rocm" / "metal" / "snapdragon" / ...
            "name": a.name,
            "brand": a.brand,
            "tops": a.tops,
            "arch": a.arch,
            "memory_gb": a.memory_gb,
        })

    return {
        "hardware": {
            "system": hw.system,
            "machine": hw.machine,
            "cpu_cores": hw.cpu_cores,
            "ram_gb": hw.ram_gb,
            "has_gpu": hw.has_gpu,
            "has_npu": hw.has_npu,
            "gpu_names": hw.gpu_names,
            "accelerators": accel_dicts,
            "detected_backends": hw.detected_backends(),
            "recommended_model": hw.recommend_model(),
            # ---- 新增：推荐部署模式 ----
            "recommended_deployment_mode": hw.recommend_deployment_mode(),
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
