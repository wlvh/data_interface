"""轻量级 Pydantic 兼容层。

由于执行环境无法直接安装官方 Pydantic 包，这里实现了一个满足项目
当前需求的最小子集，包含以下能力：

* ``BaseModel``：基于类型注解的初始化校验、嵌套模型支持、额外字段拦截。
* ``Field``：描述字段元数据（默认值、取值范围、长度约束等）。
* ``model_validator``：在模型实例化完成后执行的校验钩子。
* ``ConfigDict`` 与 ``ValidationError``：保持接口兼容。
* ``model_json_schema``：根据注解生成 JSONSchema，用于契约镜像校验。

该实现仅覆盖本项目中使用的特性，并不完整等价于官方库。如需更复杂的
校验能力，可以在未来替换为正式依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type, TypeVar, Union, get_args, get_origin, Literal, get_type_hints

__all__ = [
    "BaseModel",
    "ConfigDict",
    "Field",
    "ValidationError",
    "model_validator",
]


class ValidationError(ValueError):
    """模型校验失败时抛出的异常。"""


class ConfigDict(dict):
    """用于模拟 Pydantic 的配置字典。"""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


@dataclass
class _FieldInfo:
    """保存字段元数据。"""

    default: Any
    default_factory: Optional[Callable[[], Any]]
    description: Optional[str]
    ge: Optional[float]
    le: Optional[float]
    min_length: Optional[int]
    max_length: Optional[int]
    min_items: Optional[int]
    max_items: Optional[int]
    annotation: Any = None

    @property
    def has_default(self) -> bool:
        return self.default is not _UNSET or self.default_factory is not None


class _Unset:
    """内部标记：字段未提供默认值。"""


_UNSET = _Unset()


def Field(
    *,
    default: Any = _UNSET,
    default_factory: Optional[Callable[[], Any]] = None,
    description: Optional[str] = None,
    ge: Optional[float] = None,
    le: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
) -> _FieldInfo:
    """创建字段元信息对象。"""

    return _FieldInfo(
        default=default,
        default_factory=default_factory,
        description=description,
        ge=ge,
        le=le,
        min_length=min_length,
        max_length=max_length,
        min_items=min_items,
        max_items=max_items,
    )


def model_validator(*, mode: str = "after") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """注册模型级校验器。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        cm = classmethod(func)
        setattr(cm, "__pydantic_validator__", {"mode": mode, "function": func})
        return cm

    return decorator


T = TypeVar("T", bound="BaseModel")


class BaseModel:
    """简化版的 Pydantic BaseModel。"""

    model_config: ConfigDict = ConfigDict()

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        module_globals = vars(__import__(cls.__module__, fromlist=["*"]))
        annotations = get_type_hints(cls, globalns=module_globals, localns=module_globals)
        cls.__field_info__: Dict[str, _FieldInfo] = {}
        cls.__field_required__: Dict[str, bool] = {}
        cls.__model_validators__: List[Tuple[str, Callable[..., Any]]] = []

        for name, value in cls.__dict__.items():
            validator_conf = getattr(value, "__pydantic_validator__", None)
            if validator_conf is not None:
                cls.__model_validators__.append((validator_conf["mode"], validator_conf["function"]))

        for field_name, annotation in annotations.items():
            if field_name == "model_config":
                continue
            default = getattr(cls, field_name, _UNSET)
            if isinstance(default, _FieldInfo):
                field_info = default
            else:
                field_info = Field(default=default)
            field_info.annotation = annotation
            cls.__field_info__[field_name] = field_info
            cls.__field_required__[field_name] = not field_info.has_default
            # 清理类属性，防止 FieldInfo 泄漏到实例。
            if field_info.has_default:
                if field_info.default is not _UNSET:
                    setattr(cls, field_name, field_info.default)
                else:
                    setattr(cls, field_name, None)
            else:
                if hasattr(cls, field_name):
                    delattr(cls, field_name)

    def __init__(self, **data: Any) -> None:
        self._apply_data(data=data)
        self._run_validators()

    def _apply_data(self, *, data: Dict[str, Any]) -> None:
        allowed = set(self.__field_info__.keys())
        extra_keys = set(data.keys()) - allowed
        extra_policy = None
        if "extra" in self.model_config:
            extra_policy = self.model_config["extra"]
        if extra_policy == "forbid" and extra_keys:
            raise ValidationError(f"检测到未定义字段: {sorted(extra_keys)}")

        for name, field_info in self.__field_info__.items():
            if name in data:
                raw_value = data[name]
            elif field_info.default_factory is not None:
                raw_value = field_info.default_factory()
            elif field_info.default is not _UNSET:
                raw_value = field_info.default
            else:
                raise ValidationError(f"字段 {name} 为必填项。")
            value = _coerce_value(
                value=raw_value,
                annotation=field_info.annotation,
                field_info=field_info,
                field_name=name,
            )
            setattr(self, name, value)

    def _run_validators(self) -> None:
        for mode, validator in self.__model_validators__:
            if mode != "after":
                continue
            try:
                result = validator(self.__class__, self)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            if result is not None and not isinstance(result, self.__class__):
                raise ValidationError("model_validator 必须返回模型实例或 None。")

    @classmethod
    def model_json_schema(cls) -> Dict[str, Any]:
        """根据类型注解生成 JSONSchema。"""

        context = _SchemaContext()
        schema = context.build_model_schema(cls)
        if context.definitions:
            schema["$defs"] = context.definitions
        return schema


def _coerce_value(
    *,
    value: Any,
    annotation: Any,
    field_info: _FieldInfo,
    field_name: str,
) -> Any:
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        if type(None) in args:
            non_none_args = [item for item in args if item is not type(None)]  # noqa: E721
            if value is None:
                return None
            if len(non_none_args) == 1:
                return _coerce_value(
                    value=value,
                    annotation=non_none_args[0],
                    field_info=field_info,
                    field_name=field_name,
                )
        for candidate in args:
            try:
                return _coerce_value(
                    value=value,
                    annotation=candidate,
                    field_info=field_info,
                    field_name=field_name,
                )
            except ValidationError:
                continue
        raise ValidationError(f"字段 {field_name} 的取值不符合声明的联合类型。")

    if origin in (list, List):
        if not isinstance(value, list):
            raise ValidationError(f"字段 {field_name} 需要列表。")
        item_type = get_args(annotation)[0]
        result_list = [
            _coerce_value(
                value=item,
                annotation=item_type,
                field_info=field_info,
                field_name=field_name,
            )
            for item in value
        ]
        _check_length_constraints(value=result_list, field_info=field_info, field_name=field_name)
        return result_list

    if origin in (dict, Dict):
        if not isinstance(value, dict):
            raise ValidationError(f"字段 {field_name} 需要字典。")
        key_type, value_type = get_args(annotation)
        validated: Dict[Any, Any] = {}
        for key, item in value.items():
            validated_key = _coerce_value(
                value=key,
                annotation=key_type,
                field_info=field_info,
                field_name=field_name,
            )
            validated_value = _coerce_value(
                value=item,
                annotation=value_type,
                field_info=field_info,
                field_name=field_name,
            )
            validated[validated_key] = validated_value
        _check_length_constraints(value=list(validated), field_info=field_info, field_name=field_name)
        return validated

    if origin is Literal:
        allowed = get_args(annotation)
        if value not in allowed:
            raise ValidationError(f"字段 {field_name} 取值必须在 {allowed} 中。")
        return value

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if isinstance(value, annotation):
            return value
        if isinstance(value, dict):
            return annotation(**value)
        raise ValidationError(f"字段 {field_name} 需要 {annotation.__name__} 类型的数据。")

    if annotation is datetime:
        if isinstance(value, datetime):
            result_dt = value
        elif isinstance(value, str):
            try:
                result_dt = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValidationError(f"字段 {field_name} 无法解析为 datetime。") from exc
        else:
            raise ValidationError(f"字段 {field_name} 无法解析为 datetime。")
        return result_dt

    python_type = _resolve_python_type(annotation)
    if python_type is object:
        return value
    if not isinstance(value, python_type):
        raise ValidationError(f"字段 {field_name} 需要 {python_type.__name__} 类型。")
    if python_type in (int, float):
        _check_numeric_constraints(value=float(value), field_info=field_info, field_name=field_name)
    if python_type is str:
        _check_length_constraints(value=value, field_info=field_info, field_name=field_name)
    if python_type is list:
        _check_length_constraints(value=value, field_info=field_info, field_name=field_name)
    return value


def _resolve_python_type(annotation: Any) -> Type[Any]:
    if annotation in (Any, object):
        return object
    if isinstance(annotation, type):
        return annotation
    return object


def _check_numeric_constraints(*, value: float, field_info: _FieldInfo, field_name: str) -> None:
    if field_info.ge is not None and value < field_info.ge:
        raise ValidationError(f"字段 {field_name} 的值必须大于等于 {field_info.ge}。")
    if field_info.le is not None and value > field_info.le:
        raise ValidationError(f"字段 {field_name} 的值必须小于等于 {field_info.le}。")


def _check_length_constraints(*, value: Union[str, Iterable[Any]], field_info: _FieldInfo, field_name: str) -> None:
    if isinstance(value, str):
        length = len(value)
    else:
        value_list = list(value)
        length = len(value_list)
    if field_info.min_length is not None and length < field_info.min_length:
        raise ValidationError(f"字段 {field_name} 的长度不能小于 {field_info.min_length}。")
    if field_info.max_length is not None and length > field_info.max_length:
        raise ValidationError(f"字段 {field_name} 的长度不能大于 {field_info.max_length}。")
    if field_info.min_items is not None and length < field_info.min_items:
        raise ValidationError(f"字段 {field_name} 的元素数量不能小于 {field_info.min_items}。")
    if field_info.max_items is not None and length > field_info.max_items:
        raise ValidationError(f"字段 {field_name} 的元素数量不能大于 {field_info.max_items}。")


class _SchemaContext:
    """负责生成 JSONSchema 并维护 $defs。"""

    def __init__(self) -> None:
        self.definitions: Dict[str, Dict[str, Any]] = {}
        self._visited: Dict[Type[Any], str] = {}

    def build_model_schema(self, model: Type[BaseModel]) -> Dict[str, Any]:
        name = model.__name__
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for field_name, info in model.__field_info__.items():
            field_schema = self._schema_for_annotation(
                annotation=info.annotation,
                field_info=info,
            )
            if info.description:
                field_schema["description"] = info.description
            properties[field_name] = field_schema
            if not info.has_default:
                required.append(field_name)
        schema: Dict[str, Any] = {
            "title": name,
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    def _schema_for_annotation(self, *, annotation: Any, field_info: _FieldInfo) -> Dict[str, Any]:
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            schemas = [
                self._schema_for_annotation(annotation=arg, field_info=field_info)
                for arg in args
            ]
            return {"anyOf": schemas}
        if origin in (list, List):
            item_schema = self._schema_for_annotation(
                annotation=get_args(annotation)[0],
                field_info=field_info,
            )
            schema: Dict[str, Any] = {"type": "array", "items": item_schema}
            if field_info.min_items is not None:
                schema["minItems"] = field_info.min_items
            if field_info.max_items is not None:
                schema["maxItems"] = field_info.max_items
            return schema
        if origin in (dict, Dict):
            key_schema = self._schema_for_annotation(
                annotation=get_args(annotation)[0],
                field_info=field_info,
            )
            value_schema = self._schema_for_annotation(
                annotation=get_args(annotation)[1],
                field_info=field_info,
            )
            schema = {"type": "object", "propertyNames": key_schema, "additionalProperties": value_schema}
            return schema
        if origin is Literal:
            values = list(get_args(annotation))
            schema = {"enum": values}
            if values:
                schema["type"] = _schema_type_from_python(type(values[0]))
            return schema
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            ref_name = annotation.__name__
            if annotation not in self._visited:
                self._visited[annotation] = ref_name
                self.definitions[ref_name] = self.build_model_schema(annotation)
            return {"$ref": f"#/$defs/{ref_name}"}
        if annotation is datetime:
            return {"type": "string", "format": "date-time"}
        python_type = _resolve_python_type(annotation)
        schema_type = _schema_type_from_python(python_type)
        schema: Dict[str, Any] = {}
        if schema_type:
            schema["type"] = schema_type
        if python_type is str:
            if field_info.min_length is not None:
                schema["minLength"] = field_info.min_length
            if field_info.max_length is not None:
                schema["maxLength"] = field_info.max_length
        if python_type in (int, float):
            if field_info.ge is not None:
                schema["minimum"] = field_info.ge
            if field_info.le is not None:
                schema["maximum"] = field_info.le
        return schema


def _schema_type_from_python(python_type: Type[Any]) -> Optional[str]:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    if python_type in mapping:
        return mapping[python_type]
    return None

