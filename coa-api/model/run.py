"""ORM classes for the trace store: one Run, many Steps."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # "agent" | "baseline"
    pdf_id: Mapped[str] = mapped_column(String(32))
    phase: Mapped[str] = mapped_column(String(16), default="running")
    pending_question: Mapped[dict | None] = mapped_column(JSON, default=None)
    result: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    # Dense per run, from 1. It is the SSE event id.
    seq: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str | None] = mapped_column(String(64), default=None)
    input: Mapped[dict | None] = mapped_column(JSON, default=None)
    output: Mapped[dict | str | None] = mapped_column(JSON, default=None)
    reasoning: Mapped[str | None] = mapped_column(Text, default=None)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
