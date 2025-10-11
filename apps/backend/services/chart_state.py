"""图表状态与补丁应用工具。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Tuple, Union

from apps.backend.compat import model_dump
from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.encoding_patch import EncodingPatch, EncodingPatchOp


def compute_chart_hash(*, chart_spec: ChartSpec) -> str:
    """计算 ChartSpec 的稳定哈希值，用于状态一致性校验。

    Parameters
    ----------
    chart_spec: ChartSpec
        需要计算哈希的图表规范。

    Returns
    -------
    str
        经过排序后的 SHA256 哈希字符串。
    """

    # 序列化时按键排序，确保不同运行环境得到一致字符串。
    payload = model_dump(chart_spec, mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest


def apply_encoding_patch(*, chart_spec: ChartSpec, patch: EncodingPatch) -> ChartSpec:
    """将 EncodingPatch 应用于指定 ChartSpec，并返回新的 ChartSpec。

    Parameters
    ----------
    chart_spec: ChartSpec
        当前图表规范。
    patch: EncodingPatch
        需要应用的编码补丁。

    Returns
    -------
    ChartSpec
        应用补丁后的新图表规范。
    """

    if chart_spec.chart_id != patch.target_chart_id:
        message = (
            f"补丁目标 {patch.target_chart_id} 与当前图表 {chart_spec.chart_id} 不一致。"
        )
        raise ValueError(message)
    resolved = _apply_ops(payload=model_dump(chart_spec, mode="json"), ops=patch.ops)
    updated = ChartSpec.model_validate(resolved)
    return updated


def replay_patch_history(*, base_chart: ChartSpec, patches: Iterable[EncodingPatch]) -> ChartSpec:
    """在基础 ChartSpec 上依次重放补丁序列，返回最终图表。

    Parameters
    ----------
    base_chart: ChartSpec
        流程生成的起始图表。
    patches: Iterable[EncodingPatch]
        需按顺序应用的补丁集合。

    Returns
    -------
    ChartSpec
        重放所有补丁后的最新图表规范。
    """

    current = base_chart
    for patch in patches:
        current = apply_encoding_patch(chart_spec=current, patch=patch)
    return current


def _apply_ops(*, payload: Dict[str, Any], ops: List[EncodingPatchOp]) -> Dict[str, Any]:
    """在原始 dict 上依次应用补丁操作。"""

    current = deepcopy(payload)
    for operation in ops:
        if operation.op_type == "add":
            _apply_add(target=current, path=operation.path, value=operation.value)
            continue
        if operation.op_type == "replace":
            _apply_replace(target=current, path=operation.path, value=operation.value)
            continue
        if operation.op_type == "remove":
            _apply_remove(target=current, path=operation.path)
            continue
        message = f"未支持的操作类型: {operation.op_type}"
        raise ValueError(message)
    return current


def _apply_add(*, target: Dict[str, Any], path: List[str], value: Any) -> None:
    """处理 add 操作，按需创建缺失字典层级。"""

    parent, key = _resolve_parent(target=target, path=path, allow_create=True)
    if isinstance(parent, dict):
        # 针对字典，要求键不存在，否则 add 将破坏语义。
        if isinstance(key, str) and key in parent:
            message = f"路径 {'/'.join(path)} 已存在，无法执行 add。"
            raise ValueError(message)
        if isinstance(key, str):
            parent[key] = value
            return
    if isinstance(parent, list):
        # 针对列表，仅允许在尾部追加，避免中间插入导致索引漂移。
        index = _ensure_index(index_token=key, upper=len(parent) + 1)
        if index == len(parent):
            parent.append(value)
            return
        message = "仅允许在列表尾部追加元素。"
        raise ValueError(message)
    message = f"add 操作的父节点类型非法: {type(parent).__name__}"
    raise TypeError(message)


def _apply_replace(*, target: Dict[str, Any], path: List[str], value: Any) -> None:
    """处理 replace 操作，要求目标已存在。"""

    parent, key = _resolve_parent(target=target, path=path, allow_create=False)
    if isinstance(parent, dict):
        # replace 必须先确认键存在，避免静默创建新字段。
        if key not in parent:
            message = f"路径 {'/'.join(path)} 不存在，无法 replace。"
            raise KeyError(message)
        parent[key] = value
        return
    if isinstance(parent, list):
        # 列表分支直接更新对应索引。
        index = _ensure_index(index_token=key, upper=len(parent))
        parent[index] = value
        return
    message = f"replace 操作的父节点类型非法: {type(parent).__name__}"
    raise TypeError(message)


def _apply_remove(*, target: Dict[str, Any], path: List[str]) -> None:
    """处理 remove 操作，要求目标存在。"""

    parent, key = _resolve_parent(target=target, path=path, allow_create=False)
    if isinstance(parent, dict):
        # 针对字典，缺失即视为非法请求。
        if key not in parent:
            message = f"路径 {'/'.join(path)} 不存在，无法 remove。"
            raise KeyError(message)
        del parent[key]
        return
    if isinstance(parent, list):
        # 列表通过 pop 删除指定索引。
        index = _ensure_index(index_token=key, upper=len(parent))
        parent.pop(index)
        return
    message = f"remove 操作的父节点类型非法: {type(parent).__name__}"
    raise TypeError(message)


def _resolve_parent(
    *,
    target: Dict[str, Any],
    path: List[str],
    allow_create: bool,
) -> Tuple[Union[Dict[str, Any], List[Any]], Union[str, int]]:
    """返回路径的父节点和最终键值。"""

    if not path:
        raise ValueError("补丁路径不能为空。")
    current: Union[Dict[str, Any], List[Any]] = target
    for token in path[:-1]:
        parsed = _parse_token(token=token)
        if isinstance(current, dict):
            if parsed not in current:
                if allow_create:
                    current[parsed] = {}
                else:
                    message = f"路径 {'/'.join(path)} 中的 {parsed} 不存在。"
                    raise KeyError(message)
            current = current[parsed]
            continue
        if isinstance(current, list):
            index = _ensure_index(index_token=parsed, upper=len(current))
            current = current[index]
            continue
        message = f"路径 {'/'.join(path)} 到达非容器类型 {type(current).__name__}。"
        raise TypeError(message)
    final_token = _parse_token(token=path[-1])
    return current, final_token


def _parse_token(*, token: str) -> Union[str, int]:
    """将路径片段解析为字典键或列表索引。"""

    if token.isdigit():
        return int(token)
    return token


def _ensure_index(*, index_token: Union[str, int], upper: int) -> int:
    """校验并返回合法的列表索引。"""

    if isinstance(index_token, str):
        if not index_token.isdigit():
            message = f"列表索引 {index_token} 非数字。"
            raise TypeError(message)
        index = int(index_token)
    else:
        index = index_token
    if index < 0 or index >= upper:
        message = f"索引 {index} 超出范围 0..{upper - 1}。"
        raise IndexError(message)
    return index
