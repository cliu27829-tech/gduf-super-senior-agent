"""只读部署前检查：不修改全局 Git 配置，不自动初始化仓库。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REQUIRED_FILES = ("app.py", "requirements.txt", ".streamlit/config.toml")
PYTHON_SOURCES = (
    "app.py",
    "config.py",
    "core",
    "services",
    "tools",
    "rag",
    "ui",
    "pages",
    "deploy.py",
)


def run_check(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return True, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, str(exc)


def main() -> int:
    missing = [filename for filename in REQUIRED_FILES if not Path(filename).exists()]
    git_ok, git_version = run_check(["git", "--version"])
    compile_ok, compile_output = run_check(
        [sys.executable, "-m", "compileall", "-q", *PYTHON_SOURCES]
    )
    print(f"Git: {'OK' if git_ok else 'FAIL'} {git_version}")
    print(f"必需文件: {'OK' if not missing else 'FAIL ' + ', '.join(missing)}")
    print(f"Python 编译: {'OK' if compile_ok else 'FAIL'} {compile_output}")
    print("提示：API Key 请通过部署平台 Secrets 注入，不要写入仓库。")
    return 0 if git_ok and not missing and compile_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
