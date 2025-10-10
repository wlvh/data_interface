"""数据画像缓存 Store，确保集中管理。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from apps.backend.contracts.dataset_profile import DatasetProfile


@dataclass
class DatasetStore:
    """维护数据集画像的内存缓存。"""

    _profiles: Dict[str, DatasetProfile] = field(default_factory=dict)

    def save(self, dataset_id: str, profile: DatasetProfile) -> None:
        """写入画像。

        Parameters
        ----------
        dataset_id: str
            数据集标识。
        profile: DatasetProfile
            需要缓存的画像。
        """

        self._profiles[dataset_id] = profile

    def require(self, dataset_id: str) -> DatasetProfile:
        """读取画像，不存在时立即失败。

        Parameters
        ----------
        dataset_id: str
            数据集标识。

        Returns
        -------
        DatasetProfile
            已缓存的画像对象。
        """

        if dataset_id not in self._profiles:
            message = f"dataset_id={dataset_id} 未找到画像，请先执行扫描。"
            raise KeyError(message)
        return self._profiles[dataset_id]

