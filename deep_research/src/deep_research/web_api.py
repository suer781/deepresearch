"""Web API - FastAPI 后端。

路由：
  /                                → Web UI
  /status                           → 硬件/模型/搜索源状态
  /models                           → 模型目录 + 下载状态
  /models/download/{model_id}       → GET/POST 下载进度/开始下载
  /models/start/{model_id}          → POST 启动本地 LLM
  /models/stop                      → POST 停止服务
  /models/health                    → 健康检查
  /research                         → POST 开始研究
  /research/{run_id}                → GET 结果
  /research/{run_id}/events         → SSE 进度
  /sandbox/search?q=                → 直接测试搜索沙箱
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .model_manager import (
    MODEL_CATALOG,
    LocalLLM,
    detect_hardware,
    get_default_llm,
    status_json,
)
from .sandbox import get_sandbox
from .types import Question, Report
from .web_ui import INDEX_HTML


# ---- 状态模型 ----

class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class RunState:
    id: str
    status: RunStatus = RunStatus.IDLE
    progress_steps: list[dict] = field(default_factory=list)
    report: Report | None = None
    error: str | None = None
    _subscribers: list[asyncio.Queue] = field(default_factory=list)

    def push(self, event: dict) -> None:
        for q in self._subscribers:
            q.put_nowait(event)

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)


_RUNS: dict[str, RunState] = {}


# ---- 请求模型 ----

class StartRequest(BaseModel):
    question: str
    depth: str = "normal"
    locale: str = "zh-CN"
    local_mode: bool = True


# ---- 全局下载状态 ----

@dataclass
class DownloadState:
    model_id: str
    started_at: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    done: bool = False
    error: str | None = None
    thread: threading.Thread | None = None


_DOWNLOADS: dict[str, DownloadState] = {}


# ---- 全局 LLM 管理器（懒加载） ----

class _Global:
    llm: LocalLLM | None = None
    lock: threading.Lock = threading.Lock()


_G = _Global()


def get_llm_manager() -> LocalLLM:
    with _G.lock:
        if _G.llm is None:
            _G.llm = get_default_llm()
        return _G.llm


# ============================================================
#                        FastAPI App
# ============================================================

app = FastAPI(title="Deep Research API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
#                    根路由 & 环境状态
# ============================================================

@app.get("/")
async def root_index() -> HTMLResponse:
    """内置 Web UI。"""
    return HTMLResponse(INDEX_HTML)


@app.get("/status")
async def api_status():
    """环境状态（硬件 / 模型 / 搜索源）。"""
    from .sources import available_sources, filter_to_local, get_default_sources

    hw = detect_hardware()
    manager = get_llm_manager()

    models_list = manager.list_models()
    rec = hw.recommend_model()

    # 转换：UI 期望的字段格式
    models_ui = []
    for m in models_list:
        models_ui.append({
            "id": m["id"],
            "name": m["name"],
            "description": f"{m['lang']} · {m['recommended_for']}",
            "param_size": f"{m['size_gb']}GB (Q4)",
            "size_bytes": int(m["size_gb"] * 1024 * 1024 * 1024),
            "downloaded": bool(m["downloaded"]),
            "recommended": m["id"] == rec,
        })

    running = bool(manager._current_server and manager._current_server.is_alive())
    running_url = manager._current_server.model_endpoint if running else None
    running_model = manager._current_server.model_name if running else None

    return {
        "hardware": {
            "system": hw.system,
            "machine": hw.machine,
            "cpu_cores": hw.cpu_cores,
            "ram_gb": hw.ram_gb,
            "has_gpu": hw.has_gpu,
            "gpu_type": hw.gpu_type,
            "gpu_names": hw.gpu_names,
            "has_npu": hw.has_npu,
            "npu_type": hw.npu_type,
            "npu_brand": hw.npu_brand,
            "npu_tops": hw.npu_tops,
            "npu_arch": hw.npu_arch,
            "platform": f"{hw.system} ({hw.machine})",
            "cpu_count": hw.cpu_cores,
        },
        "recommended_model": rec,
        "models_available": models_ui,
        "local_llm_running": running,
        "local_llm_url": running_url,
        "local_llm_model": running_model,
        "available_sources": available_sources(),
        "local_sources": filter_to_local(available_sources()),
        "default_local_sources": get_default_sources(local_mode=True),
    }


# ============================================================
#                      模型管理路由
# ============================================================

@app.get("/models")
async def list_models():
    return status_json(get_llm_manager(), detect_hardware())


@app.get("/models/download/{model_id}")
async def model_download_stream(model_id: str):
    """SSE 推送该模型的下载进度。"""
    if model_id not in MODEL_CATALOG:
        raise HTTPException(404, "Unknown model")

    state = _DOWNLOADS.get(model_id)

    async def gen():
        if state is None:
            # 检查是否已下载
            manager = get_llm_manager()
            if manager.downloader.already_has(model_id):
                yield f"data: {json.dumps({'type': 'already_downloaded', 'model': model_id})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'not_started', 'model': model_id})}\n\n"
            return

        while not state.done:
            yield f"data: {json.dumps({
                'type': 'progress',
                'model': model_id,
                'bytes': state.downloaded_bytes,
                'total': state.total_bytes,
                'mb_done': round(state.downloaded_bytes / 1024 / 1024, 1),
                'mb_total': round(state.total_bytes / 1024 / 1024, 1),
                'percent': round(100 * state.downloaded_bytes / max(1, state.total_bytes), 1),
                'elapsed_sec': round(time.time() - state.started_at, 1),
            })}\n\n"
            await asyncio.sleep(1)

        if state.error:
            yield f"data: {json.dumps({'type': 'error', 'model': model_id, 'error': state.error})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'model': model_id})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/models/download/{model_id}")
async def start_model_download(model_id: str):
    """后台线程下载模型。"""
    if model_id not in MODEL_CATALOG:
        raise HTTPException(404, "Unknown model")

    llm_manager = get_llm_manager()
    if llm_manager.downloader.already_has(model_id):
        return {"status": "already_downloaded", "model": model_id,
                "info": MODEL_CATALOG[model_id]["name"]}

    if model_id in _DOWNLOADS and not _DOWNLOADS[model_id].done:
        return {"status": "already_downloading", "model": model_id}

    state = DownloadState(model_id=model_id, started_at=time.time())
    _DOWNLOADS[model_id] = state

    def _thread():
        def _progress(downloaded, total):
            state.downloaded_bytes = int(downloaded)
            state.total_bytes = int(total)
        try:
            llm_manager.download(model_id, on_progress=_progress)
            state.done = True
        except Exception as e:
            state.done = True
            state.error = str(e)

    state.thread = threading.Thread(target=_thread, daemon=True)
    state.thread.start()
    return {"status": "started", "model": model_id,
            "name": MODEL_CATALOG[model_id]["name"]}


@app.post("/models/start/{model_id}")
async def start_model_server(
    model_id: str,
    backend: str = "auto",
):
    """启动本地 LLM 服务（llama_cpp.server + OpenAI 兼容）。

    backend（推理后端）:
      - auto : 自动选择（GPU > NPU > CPU）
      - cpu  : 纯 CPU 推理
      - gpu  : GPU 加速（CUDA / Metal / Vulkan）
      - npu  : 骁龙 Hexagon NPU 加速
    """
    VALID_BACKENDS = {
        "auto", "cpu",
        "cuda", "rocm", "metal", "vulkan",
        "snapdragon", "intel_npu", "ascend", "openvino",
    }
    if backend not in VALID_BACKENDS:
        raise HTTPException(400, f"Invalid backend. Must be one of: {VALID_BACKENDS}")

    if model_id not in MODEL_CATALOG:
        raise HTTPException(404, "Unknown model")

    llm_manager = get_llm_manager()
    if not llm_manager.downloader.already_has(model_id):
        raise HTTPException(400, "Model not downloaded. Call POST /models/download/{model_id} first.")

    try:
        server = llm_manager.start(model_id, backend=backend)
    except Exception as e:
        raise HTTPException(500, f"Failed to start: {e}")

    # 等待服务 ready
    ready = await server.wait_ready(timeout=180)
    if not ready:
        raise HTTPException(500, "Model failed to become ready within timeout")

    return {
        "status": "started",
        "model_id": model_id,
        "model_name": server.model_name,
        "backend": backend,
        "base_url": server.model_endpoint,
        "chat_endpoint": f"{server.model_endpoint}/chat/completions",
    }


@app.post("/models/stop")
async def stop_model_server():
    get_llm_manager().stop()
    return {"status": "stopped"}


@app.get("/models/health")
async def model_health():
    """本地 LLM 是否正在运行。"""
    manager = get_llm_manager()
    if manager._current_server and manager._current_server.is_alive():
        return {"status": "running",
                "model": manager._current_server.model_name,
                "base_url": manager._current_server.model_endpoint,
                "port": manager._current_server.port}
    return {"status": "not_running"}


# ============================================================
#                       研究路由
# ============================================================

@app.post("/research")
async def start_research(req: StartRequest):
    run_id = str(uuid.uuid4())[:8]
    state = RunState(id=run_id)
    _RUNS[run_id] = state
    asyncio.create_task(_run_research(run_id, req))
    return {"run_id": run_id}


@app.get("/research/{run_id}")
async def get_result(run_id: str):
    if run_id not in _RUNS:
        raise HTTPException(404, "Run not found")
    s = _RUNS[run_id]
    return {
        "status": s.status.value,
        "progress_steps": s.progress_steps,
        "report": s.report.model_dump(mode="json") if s.report else None,
        "error": s.error,
    }


@app.get("/research/{run_id}/events")
async def sse_events(run_id: str):
    if run_id not in _RUNS:
        raise HTTPException(404, "Run not found")

    state = _RUNS[run_id]
    queue = await state.subscribe()

    async def event_stream():
        yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        state.unsubscribe(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ============================================================
#                       沙箱调试路由
# ============================================================

@app.get("/sandbox/search")
async def sandbox_search(q: str, sources: str = ""):
    src_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    run = await get_sandbox().search(q, sources=src_list)
    return {
        "query": q,
        "successful_sources": run.successful_sources,
        "failed_sources": run.failed_sources,
        "total_items": run.total_items,
        "items": run.to_agent_format(),
        "details": [
            {
                "source": r.source,
                "ok": r.ok,
                "count": len(r.items),
                "duration_ms": round(r.duration_ms),
                "error": r.error,
            }
            for r in run.results
        ],
    }


# ============================================================
#                       内部执行流
# ============================================================

async def _run_research(run_id: str, req: StartRequest) -> None:
    from .orchestrator import Orchestrator

    state = _RUNS[run_id]

    def emit(step: str, message: str, done: bool = False) -> None:
        state.progress_steps.append({"step": step, "message": message})
        state.push({
            "type": "progress",
            "step": step,
            "message": message,
            "done": done,
            "total_steps": len(state.progress_steps),
        })

    try:
        state.status = RunStatus.RUNNING
        emit("queued", "任务已排队")

        orch = Orchestrator(local_mode=req.local_mode)

        emit("clarify", "🔍 引导补全中...")
        eq = await orch.clarify(Question(text=req.question, locale=req.locale, depth_hint=req.depth))
        emit("clarify", f"✓ 补全完成：{len(eq.sub_questions)} 个子问题", done=True)

        emit("plan", "📋 制定研究计划...")
        p = await orch.plan(eq)
        emit("plan", f"✓ 计划：{len(p.sub_tasks)} 个子任务", done=True)

        emit("debate", "⚖️ 方案辩论中...")
        p = await orch.debate_plan(p)
        emit("debate", "✓ 方案通过", done=True)

        emit("search", f"🚀 并行搜索 {len(p.sub_tasks)} 个子任务（沙箱）...")
        await orch.execute_subtasks(p)
        emit("search", f"✓ 获得 {len(orch.store)} 条证据", done=True)

        emit("verify", "🔎 验证 + 反例搜索...")
        await orch.verify_and_adversarial()
        emit("verify", "✓ 验证完成", done=True)

        emit("write", "✍️ 综合写作中...")
        report = await orch.synthesize(req.question)
        emit("write", f"✓ 报告：{report.title}", done=True)

        emit("review", "🔍 质量审查...")
        await orch.review(report)
        emit("review", "✓ 审查完成", done=True)

        state.report = report
        state.status = RunStatus.DONE
        state.push({"type": "done", "report": report.model_dump(mode="json")})

    except Exception as e:
        state.status = RunStatus.ERROR
        state.error = str(e)
        state.push({"type": "error", "error": str(e)})
