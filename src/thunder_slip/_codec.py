"""Dataclass wire conversion with separate absent and null values."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
import types
from typing import Any, Literal, TypeVar, Union, cast, get_args, get_origin, get_type_hints

from ._base_error import SDKError


class UnsetType(Enum):
    """An absent JSON field, distinct from an explicit null."""

    UNSET = 0


UNSET = UnsetType.UNSET


class DecodeError(SDKError):
    """The response does not match the expected model."""


T = TypeVar("T")


def decode(model: type[T], value: object) -> T:
    """Decode a JSON object into a dataclass without flattening nested models."""
    return cast(T, _decode(model, value))


def _decode(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if annotation is Any:
        return value
    if origin in (Union, types.UnionType):
        for candidate in args:
            if candidate is UnsetType:
                continue
            try:
                return _decode(candidate, value)
            except DecodeError:
                pass
        raise DecodeError("Response field has an unexpected type")
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in args):
            return value
        raise DecodeError("Response field has an unexpected value")
    if annotation is type(None):
        if value is None:
            return None
        raise DecodeError("Expected a null response field")
    if is_dataclass(annotation):
        if not isinstance(value, dict):
            raise DecodeError("Expected a response object")
        hints = get_type_hints(annotation)
        kwargs: dict[str, Any] = {}
        for item in fields(annotation):
            if not item.init:
                continue
            key = item.metadata.get("wire", item.name)
            if key in value:
                kwargs[item.name] = _decode(hints[item.name], value[key])
            elif item.default is MISSING and item.default_factory is MISSING:
                raise DecodeError(f"Missing response field: {item.name}")
        return cast(Callable[..., Any], annotation)(**kwargs)
    if origin is list:
        if not isinstance(value, list):
            raise DecodeError("Expected a response array")
        return [_decode(args[0], item) for item in value]
    if origin is dict:
        if not isinstance(value, dict):
            raise DecodeError("Expected a response object")
        return {_decode(args[0], key): _decode(args[1], item) for key, item in value.items()}
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise DecodeError("Response field has an unexpected type")
        return value
    if annotation is float and type(value) in (int, float):
        return float(value)
    raise DecodeError("Unsupported response field type")


def encode(value: object) -> Any:
    """Encode dataclasses, omitting absent fields and preserving explicit nulls."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.metadata.get("wire", item.name): encode(getattr(value, item.name))
            for item in fields(value)
            if not item.metadata.get("ignore") and getattr(value, item.name) is not UNSET
        }
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items() if item is not UNSET}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value
