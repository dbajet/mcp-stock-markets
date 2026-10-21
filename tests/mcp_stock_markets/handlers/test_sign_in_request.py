from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from mcp_stock_markets.handlers.sign_in_request import SignInRequest


def test_class() -> None:
    tested = SignInRequest
    result = {name: (field.annotation, field.default) for name, field in tested.model_fields.items()}
    expected = {"email": (str, PydanticUndefined)}
    assert result == expected


def test_class__the_email_is_required() -> None:
    tested = SignInRequest
    with pytest.raises(ValidationError) as exc_info:
        tested.model_validate({})
    result = [(error["type"], error["loc"]) for error in exc_info.value.errors()]
    expected = [("missing", ("email",))]
    assert result == expected
