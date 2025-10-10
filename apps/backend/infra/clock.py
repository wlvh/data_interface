"""提供统一的 UTC 时钟接口，避免直接调用 datetime.now。"""

from __future__ import annotations

from datetime import datetime, timezone


class UtcClock:
    """UTC 时钟，用于统一时间获取方式。"""

    def now(self) -> datetime:
        """返回当前 UTC 时间。

        Returns
        -------
        datetime
            带有 UTC 时区信息的当前时间。
        """

        # 使用 timezone.utc 确保附带时区信息，避免后续校验失败。
        current = datetime.now(timezone.utc)
        return current

