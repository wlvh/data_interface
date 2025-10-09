"""测试前置配置。"""

from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    """确保仓库根目录位于 Python 模块搜索路径。"""

    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

