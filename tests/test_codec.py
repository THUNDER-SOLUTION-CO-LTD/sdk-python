from dataclasses import dataclass, field

import pytest

from thunder_slip._codec import UNSET, DecodeError, UnsetType, decode, encode


@dataclass(frozen=True)
class Nested:
    name: str


@dataclass(frozen=True)
class Fixture:
    account_id: int = field(metadata={"wire": "accountId"})
    nested: Nested | None | UnsetType = UNSET
    children: list[Nested] = field(default_factory=list)


def test_absent_and_null_are_distinct_with_typed_nested_values():
    missing = decode(Fixture, {"accountId": 1})
    null = decode(Fixture, {"accountId": 1, "nested": None})
    present = decode(
        Fixture, {"accountId": 1, "nested": {"name": "test"}, "children": [{"name": "child"}]}
    )
    assert missing.nested is UNSET
    assert null.nested is None
    assert present.nested == Nested("test")
    assert present.children == [Nested("child")]
    assert encode(missing) == {"accountId": 1, "children": []}
    assert encode(null) == {"accountId": 1, "nested": None, "children": []}


def test_missing_required_and_wrong_nested_types_have_safe_errors():
    for value in [
        {},
        {"accountId": True},
        {"accountId": 1, "nested": {"name": 42}},
        {"accountId": 1, "children": "bad"},
    ]:
        with pytest.raises(DecodeError):
            decode(Fixture, value)
