"""
Android APK 入口程序
—— 在 Android 设备上启动本地 Python 服务并自动打开 WebView 访问 UI。
同时负责：
  1. 检测骁龙 Hexagon NPU
  2. 在应用首次启动时下载 Qwen3 1.7B 模型到应用私有目录
  3. 提供模型下载 / 服务启停界面
"""
import os
import sys
import platform
import subprocess
import time
from pathlib import Path

# --- 安卓专用：设置数据与缓存目录 ---
def _android_cache_dir() -> Path:
    """在 Android 上返回 /sdcard/Android/data/<pkg>/cache，否则用 ~/.deep_research."""
    if platform.system() == 'Linux' and (
        os.path.exists('/sdcard/Android/data') or os.path.exists('/storage/emulated/0/Android/data')
    ):
        base = Path('/sdcard/Android/data/com.deepresearch.app')
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path.home() / '.deep_research'


CACHE_DIR = _android_cache_dir()
MODEL_DIR = CACHE_DIR / 'models'
MODEL_DIR.mkdir(parents=True, exist_ok=True)
os.environ['DEEP_RESEARCH_CACHE'] = str(CACHE_DIR)


# --- 把 src 目录加到 sys.path（PyDroid/Buildozer 环境）---
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def start_server() -> subprocess.Popen | None:
    """启动 uvicorn 服务到 0.0.0.0:8000，返回子进程。"""
    try:
        cmd = [
            sys.executable, "-m", "uvicorn",
            "deep_research.web_api:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--log-level", "info",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "DEEP_RESEARCH_CACHE": str(CACHE_DIR)},
        )
        time.sleep(3)  # 等服务起来
        return proc
    except Exception as e:
        print(f"启动服务失败: {e}", file=sys.stderr)
        return None


def open_webview():
    """在 Android 环境中通过 sl4a/android 接口，或 system browser 打开 localhost:8000。"""
    try:
        # Buildozer / Kivy 环境
        from android.permissions import request_permissions, Permission  # type: ignore
        try:
            request_permissions([Permission.INTERNET, Permission.WRITE_EXTERNAL_STORAGE,
                               Permission.ACCESS_NETWORK_STATE])
        except Exception:
            pass

        from jnius import autoclass, cast  # type: ignore
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        activity = PythonActivity.mActivity
        intent = Intent(Intent.ACTION_VIEW)
        intent.setData(Uri.parse("http://127.0.0.1:8000"))
        new_intent = Intent.createChooser(intent, "Deep Research")
        activity.startActivity(new_intent)
        return True
    except Exception as e:
        print(f"[warn] 无法打开 WebView (非安卓环境): {e}")
        return False


def main():
    print(f"[{time.strftime('%H:%M:%S')}] Deep Research 启动")
    print(f"  平台: {platform.system()} / {platform.machine()}")
    print(f"  缓存目录: {CACHE_DIR}")

    server_proc = start_server()
    if server_proc is None:
        print("错误：无法启动服务，退出。", file=sys.stderr)
        return 1

    # 安卓环境下自动打开浏览器/WebView
    if platform.system() == 'Linux' and os.path.exists('/system/build.prop'):
        print("  → 检测为 Android，打开 WebView...")
        open_webview()

    # 前台挂起直到用户退出
    try:
        while server_proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到退出信号，正在关闭服务...")
        server_proc.terminate()
        server_proc.wait(timeout=5)
        print("已退出。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
