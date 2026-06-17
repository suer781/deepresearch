# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — 生成单文件可执行程序
用法：
    pip install pyinstaller
    pyinstaller deep_research.spec
产物：
    Windows: dist/DeepResearch.exe
    macOS:   dist/DeepResearch.app
    Linux:   dist/DeepResearch
"""
import os
import sys

block_cipher = None

project_root = os.path.abspath('.')
src_dir = os.path.join(project_root, 'src')

# 收集所有数据文件（示例配置等）
datas = []

if os.path.exists(os.path.join(project_root, 'config')):
    datas.append((os.path.join(project_root, 'config'), 'config'))

if os.path.exists(os.path.join(project_root, 'README.md')):
    datas.append((os.path.join(project_root, 'README.md'), '.'))


a = Analysis(
    [os.path.join(project_root, 'run.py')],
    pathex=[src_dir, project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # FastAPI / uvicorn
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # 搜索源
        'duckduckgo_search',
        'wikipedia',
        'arxiv',
        'httpx',
        'bs4',
        'lxml',
        # LLM
        'openai',
        'anthropic',
        # 数据
        'networkx',
        'sqlalchemy',
        'aiosqlite',
        'pydantic',
        'pydantic_settings',
        'dotenv',
        # CLI
        'click',
        'rich',
        # 本地模型
        'huggingface_hub',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 可选：排除不常用包以减小体积
        'matplotlib',
        'pandas',
        'scipy',
        'tkinter',
        'pytest',
        'pytest-asyncio',
        'ruff',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DeepResearch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # 开启 UPX 压缩（若系统有安装）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # 显示终端窗口以便看到日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,         # 可自行准备 deep_research.ico 或 .icns
)

# macOS：额外生成 .app 包
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='DeepResearch.app',
        icon=None,
        bundle_identifier='com.deepresearch.app',
        info_plist={
            'CFBundleShortVersionString': '0.1.0',
            'NSHighResolutionCapable': 'True',
            'LSApplicationCategoryType': 'public.app-category.productivity',
        },
    )
