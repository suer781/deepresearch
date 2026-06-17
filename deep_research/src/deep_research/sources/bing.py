"""Bing 抓取源 - Playwright 直接抓取 cn.bing.com / www.bing.com。

绕过 JS 渲染，反检测，限速。
"""
from __future__ import annotations

import asyncio
from typing import Any

from ..config import get_settings
from . import SearchSource, register


@register
class BingScrapeSource(SearchSource):
    name = "bing_scrape"
    base_url = "https://cn.bing.com/search"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._playwright = None
        self._sem = asyncio.Semaphore(2)  # Bing 抓取并发限速

    async def _get_browser(self) -> Any:
        if self._playwright is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
        return self._playwright

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        locale = kwargs.get("locale", "zh-CN")
        base = "https://cn.bing.com/search" if locale.startswith("zh") else "https://www.bing.com/search"
        url = f"{base}?q={query}&count={top_k}"

        async with self._sem:
            return await self._scrape(url, top_k)

    async def _scrape(self, url: str, top_k: int) -> list[dict[str, Any]]:
        try:
            pw = await self._get_browser()
            browser = await pw.chromium.launch(
                headless=self.settings.playwright_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            # 隐藏 webdriver
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                # 等待结果区
                await page.wait_for_selector("li.b_algo, .b_result", timeout=10000)
            except Exception:
                await context.close()
                await browser.close()
                return []

            results = await page.evaluate("""
                () => {
                    const items = document.querySelectorAll('li.b_algo, .b_result');
                    const out = [];
                    for (const item of items) {
                        const a = item.querySelector('h2 a, a.tilk');
                        const snippet = item.querySelector('.b_caption p, .b_snippet');
                        if (a) {
                            out.push({
                                title: a.textContent.trim(),
                                url: a.href,
                                snippet: snippet ? snippet.textContent.trim() : ''
                            });
                        }
                    }
                    return out;
                }
            """)

            await context.close()
            await browser.close()

            out = []
            for r in results[:top_k]:
                out.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                    "source": "bing_scrape",
                    "raw": r,
                })
            return out
        except Exception:
            return []

    async def fetch_full_text(self, url: str) -> str:
        """抓取网页正文。"""
        try:
            pw = await self._get_browser()
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            text = await page.evaluate("() => document.body.innerText")
            await context.close()
            await browser.close()
            return text or ""
        except Exception:
            return ""


@register
class BingCnScrapeSource(BingScrapeSource):
    name = "bing_cn_scrape"
    base_url = "https://cn.bing.com/search"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        return await super().search(query, top_k=top_k, locale="zh-CN")


# 通用 web_scrape 别名（用于 ReaderAgent）
@register
class WebScrapeSource(BingScrapeSource):
    name = "web_scrape"
    base_url = "https://www.bing.com/search"
