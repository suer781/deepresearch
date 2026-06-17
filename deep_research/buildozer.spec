[app]
# 基础信息
title = Deep Research
package.name = deepresearch
package.domain = com.deepresearch
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,md,html,css,js
source.include_patterns = src/*,config/*
source.exclude_dirs = tests, dist, build, .git, __pycache__, .pytest_cache
source.exclude_patterns = requirements*.txt, .env.example

version = 0.1.0
requirements = python3, uvicorn, fastapi, httpx, pydantic, pydantic-settings, python-dotenv, networkx, sqlalchemy, aiosqlite, beautifulsoup4, lxml, duckduckgo-search, wikipedia, arxiv, tavily-python, huggingface_hub, click, rich, openai, anthropic, tenacity, asyncio-throttle

# Python for Android (p4a) 编译环境
#  最低 Android SDK 版本 (4.4+)；推荐 21+
android.api = 33
android.archs = arm64-v8a, armeabi-v7a
android.gradle_dependencies =
android.allow_backup = True
android.meta_data =
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# 应用图标与闪屏 —— 用户可自行替换（建议 512x512 PNG）
# icon.filename = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/presplash.png

# 入口脚本 —— Buildozer 会以这个文件作为启动
entrypoint = main.py

# 启动方式：全屏 activity + WebView
orientation = portrait
fullscreen = 0

# 日志与调试
log_level = 2
presplash_color = #0f172a

# Android 最低/目标 SDK
android.minapi = 24
android.targetapi = 34
android.ndk_api = 24

# 签名（Release 版需要修改）
android.archs.release = arm64-v8a
android.debug_keystore = ~/.android/debug.keystore
# android.release_keystore = ~/.android/release.keystore
# android.release_alias = alias
# android.release_keystore_password = your_password
# android.release_key_password = your_password


[buildozer]
log_level = 2
warn_on_root = 1
# 在 macOS / Linux 上可生成 APK； Windows 上需用 WSL
android_builddir = .buildozer/android/platform/build-armeabi-v7a
bin_dir = bin
build_dir = .buildozer

# iOS（仅在 macOS 上构建）
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master
ios.ios_developer_code = ""
ios.ios_signing_key = ""
ios.certificate_file = ""
ios.app_storeid = ""
ios.apple_team_id = ""


[p4a]
# 可选：使用本地缓存的 p4a 仓库以加速重复构建
dist_name = deepresearch
use_setup = False
requirements.source.kivy = https://github.com/kivy/kivy/archive/refs/heads/master.zip
