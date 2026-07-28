"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"

    # SQLite only auto-increments INTEGER PRIMARY KEY, never BIGINT, so the
    # test database needs the narrower type. Postgres still gets bigint.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )

    # The unique constraint is what makes collision handling correct: two
    # concurrent inserts racing on the same random code cannot both win.
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)

    target_url: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    created_by_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Soft delete. A disabled link stops redirecting immediately but the row is
    # retained: an abusive link is evidence, and keeping it also guarantees the
    # code is never handed out to somebody else later.
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_links_code", "code", unique=True),)

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Link code={self.code!r}>"
