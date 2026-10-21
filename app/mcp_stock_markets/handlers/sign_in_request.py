from __future__ import annotations

from pydantic import BaseModel


class SignInRequest(BaseModel):
    email: str
