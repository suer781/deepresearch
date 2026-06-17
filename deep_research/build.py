"""
Deep Research 构建辅助脚本 —— 一键打包各平台安装包

用法:
    # 列出当前平台可用的打包方式
    python build.py --help

    # Windows EXE (需在 Windows 下运行)
    python build.py exe

    # macOS .app (需在 macOS 下运行)
    python build.py macos

    # Linux AppImage (需在 Linux 下运行)
    python build.py linux

    # Android APK (推荐在 Linux/macOS 上，或 WSL)
    python build.py apk

    # 一次全部（本机平台）
    python build.py all

环境要求:
    Windows: python >= 3.10 + pip install pyinstaller
    macOS:   python >= 3.10 + pip install pyinstaller
    Linux:   python >= 3.10 + pip install pyinstaller
    Android: buildozer + Cython + JDK 17 + Android SDK
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)


# ---------- 辅助工具 ----------

def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"\n[CMD] {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(cwd or ROOT))


def _ensure_pip(pkg: str) -> None:
    try:
        __import__(pkg)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


def _banner(text: str) -> None:
    bar = "=" * max(len(text) + 4, 50)
    print(f"\n{bar}")
    print(f"  {text}")
    print(f"{bar}\n")


# ---------- 各平台构建 ----------

def build_exe() -> int:
    """Windows: 生成单文件 DeepResearch.exe"""
    if platform.system() != "Windows":
        print("[warn] 建议在 Windows 上构建 EXE（当前平台可能会生成 Linux/macOS 可执行程序）")
    _banner("构建 Windows EXE / Linux/macOS 单文件可执行程序")
    _ensure_pip("pyinstaller")
    return _run([sys.executable, "-m", "PyInstaller", "--clean",
                 "--noconfirm", "deep_research.spec"])


def build_macos() -> int:
    """macOS: 生成 .app 包"""
    if platform.system() != "Darwin":
        print("[error] 构建 .app 必须在 macOS 下执行")
        return 2
    _banner("构建 macOS .app 包")
    _ensure_pip("pyinstaller")
    return _run([sys.executable, "-m", "PyInstaller", "--clean",
                 "--noconfirm", "deep_research.spec"])


def build_linux() -> int:
    """Linux: 单文件可执行程序 + 可选 AppImage"""
    if platform.system() != "Linux":
        print("[warn] 建议在 Linux 上构建；当前会使用 PyInstaller 生成二进制")
    _banner("构建 Linux 可执行程序")
    _ensure_pip("pyinstaller")
    rc = _run([sys.executable, "-m", "PyInstaller", "--clean",
               "--noconfirm", "deep_research.spec"])

    # 可选：若安装了 linuxdeploy / appimagetool，生成 AppImage
    if rc == 0 and shutil.which("linuxdeploy") and shutil.which("appimagetool"):
        _banner("生成 AppImage")
        appdir = DIST / "DeepResearch.AppDir"
        appdir.mkdir(parents=True, exist_ok=True)
        # 拷贝二进制
        exe_path = DIST / "DeepResearch"
        if exe_path.exists():
            shutil.copy(exe_path, appdir / "usr" / "bin" / "DeepResearch")
        # 调用 linuxdeploy
        rc = _run(["linuxdeploy", "--appdir", str(appdir),
                   "--output", "appimage", "-d", "/dev/null"])
    return rc


def build_apk() -> int:
    """Android APK: 使用 Buildozer 打包"""
    if shutil.which("buildozer") is None:
        print("[info] buildozer 未安装，正在自动安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "buildozer", "Cython"])
    _banner("构建 Android APK")

    # 需要 JDK 17 + Android SDK，buildozer 会自动下载
    env = os.environ.copy()
    env.setdefault("ANDROID_HOME", str(Path.home() / ".buildozer" / "android"))
    env.setdefault("ANDROID_NDK_HOME", env["ANDROID_HOME"] + "/ndk")

    # Buildozer 默认会在当前目录下创建 .buildozer
    rc = _run(["buildozer", "android", "debug"])
    if rc == 0:
        # buildozer 产物默认在 ./bin/ 下
        bin_dir = ROOT / "bin"
        if bin_dir.exists():
            for apk in bin_dir.glob("*.apk"):
                target = DIST / apk.name
                shutil.copy(apk, target)
                print(f"  ✓ APK 已复制到: {target}")
    return rc


# ---------- 主入口 ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deep Research 多平台打包脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python build.py exe    # Windows 可执行程序\n"
               "  python build.py macos  # macOS .app\n"
               "  python build.py linux  # Linux 单文件\n"
               "  python build.py apk    # Android APK\n"
               "  python build.py all    # 当前平台对应构建\n",
    )
    parser.add_argument(
        "target",
        choices=["exe", "macos", "linux", "apk", "all", "clean"],
        help="构建目标",
    )
    args = parser.parse_args()

    if args.target == "clean":
        for d in ["dist", "build", ".buildozer", "__pycache__"]:
            p = ROOT / d
            if p.exists():
                print(f"清理: {p}")
                shutil.rmtree(p, ignore_errors=True)
        return 0

    if args.target == "all":
        system = platform.system()
        if system == "Windows":
            return build_exe()
        if system == "Darwin":
            return build_macos()
        # Linux → 同时尝试 linux + apk
        rc = build_linux()
        if rc == 0:
            build_apk()
        return rc

    dispatcher = {
        "exe": build_exe,
        "macos": build_macos,
        "linux": build_linux,
        "apk": build_apk,
    }
    return dispatcher[args.target]()


if __name__ == "__main__":
    sys.exit(main())
