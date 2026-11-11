#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NetOps Toolkit - 打包脚本（v4.0 分发版：onedir）
- 纯英文构建区（%LOCALAPPDATA%\\NetOpsBuild），避开中文路径的 PyInstaller 坑
- onedir：启动快、少杀软误报；整个文件夹分发给同事，双击 NetOps-Toolkit.exe
- 排除开发数据（config/secret.key/devices.json/settings、audit、backups、templates 自定义模板），
  分发版首次启动自动在 exe 同目录建 config/、templates/ 等可写目录（见 utils/app_paths.py）
"""
import os
import shutil
import subprocess
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "NetOpsBuild")
SRC_COPY = os.path.join(BUILD_ROOT, "src")
DIST = os.path.join(BUILD_ROOT, "dist")
VENDOR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "NetOpsVendor")
APP_NAME = "NetOps-Toolkit"
PARAMIKO_PIN = "3.5.1"   # 老 H3C/华为只支持 ssh-rsa/SHA1 签名，paramiko 5.x 已移除


def _ensure_vendor():
    """构建依赖目录（与用户环境隔离）：确保 paramiko 钉在 3.5.1。
    PyInstaller --paths 前置 vendor，分析时优先收集这里的版本。"""
    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'%s'); import paramiko; print(paramiko.__version__)" % VENDOR],
        capture_output=True, text=True)
    if probe.returncode == 0 and probe.stdout.strip().startswith(PARAMIKO_PIN):
        print(f"vendor 就绪：paramiko {PARAMIKO_PIN}")
        return
    print(f"准备 vendor：paramiko=={PARAMIKO_PIN}（不污染系统环境）…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--target", VENDOR,
                           f"paramiko=={PARAMIKO_PIN}", "--quiet", "--disable-pip-version-check"])

_EXCLUDE = {".git", "__pycache__", ".workbuddy", "dist", "build", ".temp",
            "config", "audit", "backups", "templates"}


def _ignore(_dir, names):
    return [n for n in names if n in _EXCLUDE or n.endswith(".pyc")]


def build_exe():
    print("=" * 60)
    print("NetOps Toolkit - 打包（onedir 分发版）")
    print("=" * 60)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("正在安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    _ensure_vendor()

    # 1) 复制源码到纯英文构建区
    if os.path.isdir(BUILD_ROOT):
        shutil.rmtree(BUILD_ROOT)
    shutil.copytree(SRC, SRC_COPY, ignore=_ignore)
    print(f"源码副本: {SRC_COPY}")

    # 2) 打包
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        f"--name={APP_NAME}",
        "--icon=NONE",
        "--upx-dir", "",
        "--clean",
        "--noconfirm",
        "--paths", VENDOR,
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD_ROOT, "work"),
        "--specpath", BUILD_ROOT,
        os.path.join(SRC_COPY, "main.py"),
    ]
    print("开始打包…")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        print("\n打包失败！错误尾部：")
        print((result.stderr or "")[-3000:])
        return False

    # 3) 产物回搬项目 dist/
    out_dir = os.path.join(SRC, "dist")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(os.path.join(DIST, APP_NAME), os.path.join(out_dir, APP_NAME))

    exe_path = os.path.join(out_dir, APP_NAME, f"{APP_NAME}.exe")
    if not os.path.exists(exe_path):
        print("打包成功但未找到 exe，请检查 dist 目录")
        return False

    total = 0
    for root, _, files in os.walk(os.path.join(out_dir, APP_NAME)):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    print("\n打包成功！")
    print(f"产物: {exe_path}")
    print(f"目录总大小: {total / 1024 / 1024:.1f} MB")
    print("\n分发方式：整个 dist\\NetOps-Toolkit 文件夹压缩发给同事，解压后双击 exe。")
    return True


if __name__ == "__main__":
    sys.exit(0 if build_exe() else 1)