from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class MeResponse(BaseModel):
    user_id: str
    email: str | None
