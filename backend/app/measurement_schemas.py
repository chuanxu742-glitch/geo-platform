from datetime import date as calendar_date
import re
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, TypeAdapter, field_validator

from .schemas import Payload


MAX_IMPORT_ROWS = 1000
# Keep individual counts exactly representable by browser clients and SQL bigint.
Count = Annotated[int, Field(strict=True, ge=0, le=9_007_199_254_740_991)]
HTTP_URL = TypeAdapter(HttpUrl)


class MeasurementRow(Payload):
    date: str = Field(min_length=10, max_length=10)
    page_url: str = Field(min_length=1, max_length=2048)
    channel: Literal["seo", "geo", "other"]
    query: str = Field(default="", max_length=2000)
    impressions: Count | None = None
    clicks: Count | None = None
    leads: Count | None = None
    orders: Count | None = None

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("date must be YYYY-MM-DD")
        calendar_date.fromisoformat(value)
        return value

    @field_validator("page_url")
    @classmethod
    def valid_url(cls, value):
        if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
            raise ValueError("page_url must be an HTTP(S) URL without whitespace")
        parsed = HTTP_URL.validate_python(value)
        if not value.lower().startswith(("http://", "https://")) or parsed.username or parsed.password:
            raise ValueError("page_url must be an absolute HTTP(S) URL without credentials")
        return value


class MeasurementImport(Payload):
    source_label: str = Field(min_length=1, max_length=200)
    rows: list[MeasurementRow] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)

    @field_validator("source_label")
    @classmethod
    def nonblank_source(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("source_label must not be blank")
        return value
