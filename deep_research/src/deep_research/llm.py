"""LLM 客户端 — 云端 + 本地双模式。

本地模式走 OpenAI 兼容协议（Ollama / LM Studio / vLLM / llama-cpp-python-server 都支持），
不依赖 `openai` Python 包，直接用 httpx，避免模型不支持 JSON Mode 时崩溃。
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import get_settings


class LLMClient:
    """统一 LLM 客户端，自动切换云端/本地。"""

    def __init__(self) -> None:
        s = get_settings()
        self.local = s.use_local_model
        self.base_url = s.local_model_url.rstrip("/") if self.local else s.openai_base_url.rstrip("/")
        api_key = "" if self.local else (s.openai_api_key or "sk-placeholder")

        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=httpx.Timeout(300.0, connect=30.0),
        )

        if self.local:
            self.primary = s.local_model_name
            self.debater = s.local_model_name
            self.critic = s.local_model_name
            self.ctx = s.local_model_ctx
        else:
            self.primary = s.primary
            self.debater = s.debater_model
            self.critic = s.critic_model
            self.ctx = 128000

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """文本补全，本地模型无 JSON Mode 也能跑。"""
        model = model or self.primary
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": min(max_tokens, self.ctx // 2),
            "stream": False,
        }
        # 云端才能可靠启用 response_format；本地默认不用
        if not self.local:
            body["response_format"] = {"type": "text"}

        try:
            resp = await self._http.post("/chat/completions", json=body)
            if resp.status_code != 200:
                return f"[LLM 错误 HTTP{resp.status_code}: {resp.text[:200]}]"
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            return f"[LLM 异常: {type(e).__name__}: {e}]"

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """结构化输出。本地模型强 prompt 引导 + 宽松解析兜底。"""
        prompt_json = (
            user
            + "\n\n必须严格输出一个合法 JSON 对象，不要包含 markdown 代码块、不要有解释文字、不要有 '下面是 JSON' 之类内容。"
            + ("如果字段缺失就用 null 或空数组占位。" if self.local else "")
        )

        for attempt in range(max_retries + 1):
            text = await self.complete(
                system + ("\n你的所有输出必须是合法 JSON。" if self.local else ""),
                prompt_json,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = _parse_json_relaxed(text)
            if result is not None:
                return result
            # 失败时提示重试
            prompt_json += f"\n\n上一次输出不是合法 JSON。请重试，只输出纯 JSON。错误片段: {text[:120]!r}"

        return {"_raw": text[:500], "_parse_failed": True}

    async def close(self) -> None:
        await self._http.aclose()


# ---------- JSON 宽松解析（为本地模型准备） ----------

_JSON_BLOCK_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_JSON_FALLBACK_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")


def _parse_json_relaxed(text: str) -> dict[str, Any] | None:
    """本地模型经常套 ```json ... ```，或带前后说明，此函数尽量挖出 JSON。"""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None

    # 1) 整串直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2) 代码块里挖
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # 3) 找最外层 { ... } 或 [ ... ]
    #    用栈匹配，允许嵌套
    start = text.find("{")
    if start >= 0:
        depth = 0
        end = -1
        in_str = False
        esc = False
        for i, ch in enumerate(text[start:], start=start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            try:
                return json.loads(text[start:end])
            except Exception:
                pass

    # 4) 最后兜底：非贪婪找第一个 {...}
    for m in _JSON_FALLBACK_RE.finditer(text):
        try:
            return json.loads(m.group(0))
        except Exception:
            continue

    return None


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
