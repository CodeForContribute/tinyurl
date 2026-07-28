"""Request and response models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShortenRequest(BaseModel):
    # Validation is deliberately not done by pydantic's AnyHttpUrl: the rules in
    # app.validate are stricter (scheme allowlist, private-IP and credential
    # blocking) and produce messages worth showing the caller.
    url: str = Field(..., description="The URL to shorten", examples=["https://example.com/a/very/long/path"])


class ShortenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., examples=["aB3xY9z"])
    short_url: str = Field(..., examples=["https://sho.rt/aB3xY9z"])
    target_url: str
    created_at: datetime


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
