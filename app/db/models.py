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

    # Panels the UI needs that don't warrant their own table (small, run-scoped,
    # never queried independently): Code Scout's gaps, the VoC block, and the
    # Analyst's drill-down trail. Was previously computed but never persisted —
    # the API had nothing to serve for 4 of 6 UI panels (screen-2 review, Pritom).
    code_gaps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    voc: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    drilldown_trail: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

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

    # Mirrors of the remaining app.schemas.contracts.Finding fields — were
    # computed by the Analyst but dropped on the way into this table (only
    # the warehouse-origin fields above were ever persisted), so a voc-origin
    # finding lost its theme/review_count/quotes and rendered as "0 reviews
    # · theme: —" in the UI no matter what the pipeline actually found.
    journey_events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    drilldown_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    theme: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    theme_search_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    top_quotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    run: Mapped["AnalysisRun"] = relationship(back_populates="findings")


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # report_md | prd_md
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL for report_md (one per run); the finding a prd_md belongs to when a
    # run produces more than one PRD (up to MAX_PRDS_PER_RUN, one per finding).
    finding_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edited_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    run: Mapped["AnalysisRun"] = relationship(back_populates="artifacts")
