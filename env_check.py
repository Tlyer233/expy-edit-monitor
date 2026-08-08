#!/usr/bin/env python3
"""
5_edit_monitor 环境检测脚本
expy deploy 调用此脚本验证环境是否满足运行条件
约定：exit 0 = 通过, exit != 0 = 失败（需用户修复后重试）
terminal 中执行时可直接看到 print 输出，支持交互式引导
"""
import os  # 环境变量
import sys  # exit
import shutil  # which
import subprocess  # 执行命令
import platform  # 检测 OS

# ─── 检测函数（每个返回 bool，独立、原子）──────────────────


def check_platform() -> bool:
    """检查操作系统是否为 macOS（eslogger 仅 macOS 可用）"""
    ok = platform.system() == "Darwin"  # macOS 返回 "Darwin"
    if ok:
        print("[✓] macOS 环境")
    else:
        print("[✘] 此插件仅支持 macOS（当前: {}）".format(platform.system()))
    return ok


def check_eslogger() -> bool:
    """检查 eslogger 命令是否可用（macOS 10.15+ 内置）"""
    path = shutil.which("eslogger")  # 在 PATH 中查找
    if path:
        print("[✓] eslogger: {}".format(path))
        return True
    else:
        print("[✘] eslogger 未找到（需要 macOS ≥ 10.15）")
        return False


def check_sudo() -> bool:
    """检查 sudo 权限（eslogger 需要 root 才能捕获内核文件事件）"""
    # 方案 1：环境变量 HERMES_SUDO_PASSWORD（expy 推荐方式）
    if os.environ.get("HERMES_SUDO_PASSWORD", ""):
        print("[✓] sudo: HERMES_SUDO_PASSWORD 已设置")
        return True
    # 方案 2：免密码 sudo（用户已配置 NOPASSWD）
    r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
    if r.returncode == 0:
        print("[✓] sudo: 免密码可用")
        return True
    # 两种都不可用 → 打印配置引导
    print("[✘] sudo 不可用")
    print()
    print("  eslogger 需要 root 权限，请配置以下任一方式：")
    print()
    print("  方式 1（推荐）：设置环境变量")
    print("    echo 'export HERMES_SUDO_PASSWORD=\"你的Mac登录密码\"' >> ~/.zshrc")
    print("    source ~/.zshrc")
    print()
    print("  方式 2：配置免密码 sudo")
    print("    sudo visudo")
    print("    添加一行：你的用户名 ALL=(ALL) NOPASSWD: ALL")
    print()
    return False


# ─── 主流程 ──────────────────────────────────────────────

def main():
    print("5_edit_monitor 环境检测")
    print("=" * 40)

    errors = []  # 收集所有未通过的项

    if not check_platform():
        errors.append("platform")  # 平台不匹配
    if not check_eslogger():
        errors.append("eslogger")  # eslogger 不可用
    if not check_sudo():
        errors.append("sudo")  # sudo 未配置

    print("=" * 40)
    if errors:
        print("[✘] 未通过: {}".format(", ".join(errors)))
        print("请修复以上问题后重新运行 expy deploy")
        sys.exit(1)
    else:
        print("[✓] 全部通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
