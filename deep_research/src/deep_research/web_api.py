"""Web API - FastAPI 后端，提供研究接口 + SSE 实时进度推送。"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import get_settings
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


# 全局运行状态
_RUNS: dict[str, RunState] = {}


# ---- 请求/响应模型 ----

class StartRequest(BaseModel):
    question: str
    depth: str = "normal"
    locale: str = "zh-CN"
    local_mode: bool | None = None


class StatusResponse(BaseModel):
    local_llm_available: bool
    local_llm_url: str
    local_llm_model: str
    available_sources: list[str]
    version: str


# ---- FastAPI App ----

app = FastAPI(title="Deep Research API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index() -> HTMLResponse:
    """内置 Web UI。"""
    return HTMLResponse(INDEX_HTML)


@app.get("/status")
async def get_status() -> StatusResponse:
    """环境状态检查。"""
    s = get_settings()
    local_llm_ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                s.local_model_url.rstrip("/") + "/chat/completions",
                json={"model": s.local_model_name, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                headers={"Content-Type": "application/json"},
            )
            local_llm_ok = r.status_code < 500
    except Exception:
        pass

    from .sources import available_sources
    return StatusResponse(
        local_llm_available=local_llm_ok,
        local_llm_url=s.local_model_url,
        local_llm_model=s.local_model_name,
        available_sources=available_sources(),
        version="0.1.0",
    )


@app.post("/research")
async def start_research(req: StartRequest) -> dict:
    """启动一次研究任务。"""
    run_id = str(uuid.uuid4())[:8]
    state = RunState(id=run_id)
    _RUNS[run_id] = state

    # 异步启动，不阻塞 HTTP
    asyncio.create_task(_run_research(run_id, req))

    return {"run_id": run_id, "status_url": f"/research/{run_id}/events"}


@app.get("/research/{run_id}")
async def get_result(run_id: str) -> dict:
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
    """SSE 流：实时推送研究进度。"""
    if run_id not in _RUNS:
        raise HTTPException(404, "Run not found")

    import asyncio
    from fastapi.responses import StreamingResponse

    state = _RUNS[run_id]
    queue = await state.subscribe()

    async def event_stream():
        # 先发一个 ping
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


# ---- 内部：跑研究流程 ----

async def _run_research(run_id: str, req: StartRequest) -> None:
    from .orchestrator import Orchestrator  # noqa: F401 延迟导入避免循环

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

        q = Question(text=req.question, locale=req.locale, depth_hint=req.depth)
        orch = Orchestrator(local_mode=req.local_mode)

        # ---- 替换 orchestrator 的 console 输出为 SSE push ----
        # 由于 orchestrator 直接 print，这里用一个 proxy 方式：
        # 重定向 console 到 SSE，方法是 monkeypatch rich.Console
        _patch_console(orch, emit)

        emit("clarify", "🔍 引导补全中...")
        eq = await orch.clarify(q)
        emit("clarify", f"✓ 补全完成：{len(eq.sub_questions)} 个子问题", done=True)

        emit("plan", "📋 制定研究计划...")
        p = await orch.plan(eq)
        emit("plan", f"✓ 计划：{len(p.sub_tasks)} 个子任务（估算 {p.estimated_duration_min} 分钟）", done=True)

        emit("debate", "⚖️ 方案辩论中...")
        p = await orch.debate_plan(p)
        emit("debate", "✓ 方案通过", done=True)

        emit("search", f"🚀 并行搜索 {len(p.sub_tasks)} 个子任务...")
        await orch.execute_subtasks(p)
        emit("search", f"✓ 获得 {len(orch.store)} 条证据", done=True)

        emit("verify", "🔎 验证 + 反例搜索...")
        await orch.verify_and_adversarial()
        emit("verify", "✓ 验证完成", done=True)

        emit("write", "✍️ 综合写作中...")
        report = await orch.synthesize(req.question)
        emit("write", f"✓ 报告：{report.title}", done=True)

        emit("review", "🔍 质量审查中...")
        await orch.review(report)
        emit("review", "✓ 审查完成", done=True)

        state.report = report
        state.status = RunStatus.DONE
        state.push({
            "type": "done",
            "report": report.model_dump(mode="json"),
        })

    except Exception as e:
        state.status = RunStatus.ERROR
        state.error = str(e)
        state.push({"type": "error", "error": str(e)})


# ---- rich.Console monkeypatch：把 orchestrator 的 print 重定向到 SSE ----

def _patch_console(orch: Orchestrator, emit) -> None:
    """把 orchestrator 的 timeline.mark 替换为 SSE push（无感知）。"""
    orig_mark = orch.timeline.mark

    def patched_mark(name: str) -> None:
        orig_mark(name)
        emit("step", f"[{name}]", done=False)

    orch.timeline.mark = patched_mark
