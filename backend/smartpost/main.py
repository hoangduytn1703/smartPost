import io
import logging
import shutil
import socket
import zipfile
from contextlib import asynccontextmanager
from typing import Any, Optional

import segno
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from . import config, db, settings, worker
from .models import Clip, Job, now
from .services.fetch import extract_youtube_url
from .services.render import DEFAULT_STYLE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.engine()
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    worker.resume()
    yield


app = FastAPI(title="smartPost", lifespan=lifespan)


# ---------- helpers ----------

def _clip_dict(c: Clip) -> dict:
    d = c.model_dump()
    d["url"] = f"/files/{c.file}" if c.file else ""
    return d


def _job_dict(job: Job, clips: list[Clip]) -> dict:
    d = job.model_dump()
    d["source_url"] = f"/files/{job.id}/source.mp4" if job.download_status == "done" else ""
    d["clips"] = [_clip_dict(c) for c in sorted(clips, key=lambda c: c.part)]
    return d


def _get_job(s, job_id: int) -> Job:
    job = s.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy video")
    return job


def _get_clip(s, clip_id: int) -> Clip:
    clip = s.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Không tìm thấy clip")
    return clip


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outgoing interface
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


# ---------- jobs ----------

class NewJobs(BaseModel):
    urls: list[str]
    auto_render: bool = False


@app.get("/api/jobs")
def list_jobs():
    with db.session() as s:
        jobs = s.exec(select(Job).order_by(Job.id.desc())).all()
        clips = s.exec(select(Clip)).all()
    by_job: dict[int, list[Clip]] = {}
    for c in clips:
        by_job.setdefault(c.job_id, []).append(c)
    return [_job_dict(j, by_job.get(j.id, [])) for j in jobs]


@app.post("/api/jobs")
def create_jobs(body: NewJobs):
    created, skipped = [], []
    with db.session() as s:
        for raw in body.urls:
            url = extract_youtube_url(raw)
            if not url:
                if raw.strip():
                    skipped.append(raw.strip())
                continue
            job = Job(url=url, auto_render=body.auto_render)
            s.add(job)
            s.commit()
            created.append(job.id)
    for job_id in created:
        worker.start_job(job_id)
    return {"created": created, "skipped": skipped}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    with db.session() as s:
        job = _get_job(s, job_id)
        clips = s.exec(select(Clip).where(Clip.job_id == job_id)).all()
    return _job_dict(job, clips)


class JobPatch(BaseModel):
    hashtags: Optional[list[str]] = None


@app.patch("/api/jobs/{job_id}")
def patch_job(job_id: int, body: JobPatch):
    from .services.validate import fix_hashtags

    with db.session() as s:
        job = _get_job(s, job_id)
        if body.hashtags is not None:
            job.hashtags = fix_hashtags(body.hashtags)
        s.add(job)
        s.commit()
    return get_job(job_id)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    with db.session() as s:
        job = _get_job(s, job_id)
        for c in s.exec(select(Clip).where(Clip.job_id == job_id)).all():
            s.delete(c)
        s.delete(job)
        s.commit()
    shutil.rmtree(config.JOBS_DIR / str(job_id), ignore_errors=True)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int):
    with db.session() as s:
        job = _get_job(s, job_id)
    if job.status == "failed":
        if job.title:
            worker.replan(job_id)
        else:
            worker.start_job(job_id)
    if job.download_status == "failed":
        worker._update_job(job_id, download_status="pending")
        worker.ensure_download(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/replan")
def replan_job(job_id: int):
    with db.session() as s:
        _get_job(s, job_id)
    worker.replan(job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/zip")
def download_job_zip(job_id: int):
    """One file with every rendered clip. Videos are already compressed, so the zip is stored, not re-compressed."""
    with db.session() as s:
        job = _get_job(s, job_id)
        clips = [
            c for c in s.exec(select(Clip).where(Clip.job_id == job_id)).all()
            if c.status == "done" and c.file
        ]
    buf = io.BytesIO()
    written = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as archive:
        for clip in sorted(clips, key=lambda c: c.part):
            path = config.JOBS_DIR / clip.file
            if path.exists():
                archive.write(path, path.name)
                written += 1
    if written == 0:
        raise HTTPException(400, "Chưa có clip nào render xong")
    buf.seek(0)
    filename = f"{worker.slug(job.title)}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/jobs/{job_id}/render")
def render_job(job_id: int):
    with db.session() as s:
        _get_job(s, job_id)
    return {"queued": worker.render_job(job_id)}


# ---------- clips ----------

class ClipPatch(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    title_line1: Optional[str] = None
    title_line2: Optional[str] = None
    title_vi: Optional[str] = None
    caption_en: Optional[str] = None
    caption_vi: Optional[str] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    saturation: Optional[float] = None


@app.patch("/api/clips/{clip_id}")
def patch_clip(clip_id: int, body: ClipPatch):
    with db.session() as s:
        clip = _get_clip(s, clip_id)
        job = _get_job(s, clip.job_id)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(clip, k, v)
        if clip.start < 0 or clip.end <= clip.start + 0.5:
            raise HTTPException(400, "Mốc kết thúc phải sau mốc bắt đầu")
        if job.duration and clip.end > job.duration + 1:
            raise HTTPException(400, "Mốc kết thúc vượt quá độ dài video")
        s.add(clip)
        s.commit()
    return _clip_dict(clip)


@app.post("/api/clips/{clip_id}/render")
def render_one(clip_id: int):
    with db.session() as s:
        _get_clip(s, clip_id)
    worker.render_clip(clip_id)
    return {"ok": True}


class Posted(BaseModel):
    posted: bool


@app.post("/api/clips/{clip_id}/posted")
def mark_posted(clip_id: int, body: Posted):
    with db.session() as s:
        clip = _get_clip(s, clip_id)
        clip.posted_at = now() if body.posted else None
        s.add(clip)
        s.commit()
    return _clip_dict(clip)


@app.get("/api/clips/{clip_id}/download")
def download_clip(clip_id: int):
    with db.session() as s:
        clip = _get_clip(s, clip_id)
    path = config.JOBS_DIR / clip.file if clip.file else None
    if not path or not path.exists():
        raise HTTPException(404, "Clip chưa render")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


# ---------- phone ----------

@app.get("/api/phone/clips")
def phone_clips():
    with db.session() as s:
        rows = s.exec(select(Clip, Job).where(Clip.job_id == Job.id, Clip.status == "done")).all()
    items = []
    for clip, job in rows:
        tags = " ".join(job.hashtags or [])
        items.append({
            **_clip_dict(clip),
            "job_title": job.title,
            "post_text": f"{clip.caption_en}\n\n{tags}".strip(),
        })
    # Not posted yet first (newest video first, parts in order), posted ones at the bottom
    items.sort(key=lambda i: (i["posted_at"] is not None, -i["job_id"], i["part"]))
    return items


@app.get("/api/lan")
def lan_info(job: int | None = None):
    url = f"http://{lan_ip()}:{config.PORT}/phone"
    if job:
        url += f"?job={job}"
    return {"url": url, "qr_svg": segno.make(url, error="m").svg_inline(scale=6, border=2)}


# ---------- settings ----------

@app.get("/api/settings")
def get_settings():
    return {
        "style": settings.get_style(),
        "defaults": DEFAULT_STYLE,
        "gemini_model": config.GEMINI_MODEL,
        "gemini_keys": len(config.gemini_keys()),
    }


@app.put("/api/settings")
def put_settings(body: dict[str, Any]):
    style = settings.set_style(body.get("style") or {})
    return {"style": style}


# ---------- files + frontend ----------

config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=config.JOBS_DIR), name="files")

if (config.FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    index = config.FRONTEND_DIST / "index.html"
    if not index.exists():
        return {"message": "Frontend chưa build: chạy `make build` (hoặc `make frontend` khi dev)"}
    return FileResponse(index)
