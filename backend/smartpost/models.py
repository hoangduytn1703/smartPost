from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    video_id: str = ""
    title: str = ""
    duration: float = 0
    width: int = 0
    height: int = 0
    # queued | fetching | planning | review | failed
    status: str = "queued"
    # pending | running | done | failed
    download_status: str = "pending"
    error: str = ""
    auto_render: bool = False
    # "transcript" | "youtube" (no subtitles: Gemini watched the video itself)
    plan_source: str = ""
    hashtags: list = Field(default_factory=list, sa_column=Column(JSON))
    plan_warnings: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Clip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    part: int
    start: float
    end: float
    title_line1: str = ""
    title_line2: str = ""
    title_vi: str = ""
    caption_en: str = ""
    caption_vi: str = ""
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    saturation: Optional[float] = None
    # draft | queued | rendering | done | failed
    status: str = "draft"
    error: str = ""
    file: str = ""
    rendered_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict = Field(default_factory=dict, sa_column=Column(JSON))
