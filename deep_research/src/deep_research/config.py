"""配置管理。"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DR_",
        extra="ignore",
    )

    # LLM - 云端
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    primary_model: str = "gpt-4o"
    debater_model: str = "gpt-4o-mini"
    critic_model: str = "gpt-4o-mini"

    # LLM - 本地（Ollama / LM Studio / vLLM 等 OpenAI 兼容服务）
    use_local_model: bool = False
    # Ollama 默认 http://localhost:11434/v1 ；LM Studio 默认 http://localhost:1234/v1
    local_model_url: str = "http://localhost:11434/v1"
    local_model_name: str = "qwen3:8b"
    local_model_ctx: int = 8192

    # 搜索 API
    tavily_api_key: str = ""
    brave_api_key: str = ""
    exa_api_key: str = ""
    serper_api_key: str = ""
    serpapi_api_key: str = ""
    searlo_api_key: str = ""
    parallel_api_key: str = ""

    # 国内
    zhihu_api_key: str = ""
    aliyun_search_api_key: str = ""
    aliyun_search_host: str = ""
    tikhub_api_key: str = ""

    # 抓取
    playwright_headless: bool = True
    scrape_rate_limit_per_sec: float = 1.0
    proxy_url: str = ""

    # 运行时
    max_parallel_subtasks: int = 8
    max_debate_rounds: int = 3
    evidence_per_subtask: int = 10
    storage_dir: Path = Path("./storage")

    # 调试
    debug: bool = False
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    """全局单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
