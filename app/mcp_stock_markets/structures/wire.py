from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


class Wire:
    """How the structures read a value that arrives either as itself (a
    database row) or as its JSON form (a dictionary the structure wrote):
    money as Decimal from its exact string, never through a float, and
    moments and days from their ISO form."""

    @classmethod
    def money(cls, value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, float):
            raise TypeError("money never travels as a float")
        return Decimal(str(value))

    @classmethod
    def moment(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    @classmethod
    def day(cls, value: Any) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))
