import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journey: Mapped[str] = mapped_column(String(64), nullable=False, default="pd_checkout", index=True)
    window_start: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    window_end: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    failed_stage: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, index=True
    )
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    updated_by: Mapped[str] = mapped_column(String(64), default="system")

    snapshots: Mapped[list["FunnelSnapshot"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    findings: Mapped[list["DropOffFinding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["RunArtifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class FunnelSnapshot(Base):
    __tablename__ = "funnel_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    segment: Mapped[str] = mapped_column(String(128), nullable=False)
    entered: Mapped[int] = mapped_column(Integer, nullable=False)
    converted: Mapped[int] = mapped_column(Integer, nullable=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    window: Mapped[str] = mapped_column(String(10), default="current")  # current | previous

    run: Mapped["AnalysisRun"] = relationship(back_populates="snapshots")


class DropOffFinding(Base):
    __tablename__ = "drop_off_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="warehouse")
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)  # high | medium | low
    confirm_via: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped["AnalysisRun"] = relationship(back_populates="findings")


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # report_md | prd_md
    uri: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped["AnalysisRun"] = relationship(back_populates="artifacts")
