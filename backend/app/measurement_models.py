"""Manually imported observations; never inferred conversion metrics."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, now


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint", name="uq_measurements_project_fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_label: Mapped[str] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(30), default="manual_import")
    date: Mapped[str] = mapped_column(String(10))
    page_url: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(10))
    query: Mapped[str] = mapped_column(Text, default="")
    impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    clicks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    leads: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    orders: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Hash of source/date/URL/channel/query; project scope is in the unique constraint.
    fingerprint: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
