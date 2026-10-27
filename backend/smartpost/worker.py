"""In-process job queue: fetch -> (download || plan) -> review -> render clips.

Each stage has its own semaphore so many links can be pasted at once without
hammering YouTube, Gemini or the CPU.
"""

import asyncio
import logging
import re
from pathlib import Path

from sqlmodel import select

from . import config, db, settings
from .models import Clip, Job, now
from .services import fetch, planner, render
from .services.transcript import group_lines, parse_json3, to_text

log = logging.getLogger(__name__)

_sems: dict[str, asyncio.Semaphore] = {}
_tasks: set[asyncio.Task] = set()
_downloads: dict[int, asyncio.Task] = {}


def _sem(name: str) -> asyncio.Semaphore:
    if name not in _sems:
        limit = {"fetch": config.FETCH_PARALLEL, "plan": config.PLAN_PARALLEL, "render": config.RENDER_PARALLEL}
        _sems[name] = asyncio.Semaphore(limit[name])
    return _sems[name]


_loop: asyncio.AbstractEventLoop | None = None


def _spawn(coro) -> asyncio.Task:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Called from a sync FastAPI route (thread pool): hand the coroutine to the server loop.
        return asyncio.run_coroutine_threadsafe(_track(coro), _loop)
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def _track(coro):
    return await _spawn(coro)


def _update_job(job_id: int, **fields) -> Job | None:
    with db.session() as s:
        job = s.get(Job, job_id)
        if job is None:
            return None
        for k, v in fields.items():
            setattr(job, k, v)
        s.add(job)
        s.commit()
        return job


def _update_clip(clip_id: int, **fields) -> Clip | None:
    with db.session() as s:
        clip = s.get(Clip, clip_id)
        if clip is None:
            return None
        for k, v in fields.items():
            setattr(clip, k, v)
        s.add(clip)
        s.commit()
        return clip


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "video"


# ---------- job pipeline ----------

def start_job(job_id: int) -> None:
    _spawn(_run_job(job_id))


async def _run_job(job_id: int) -> None:
    try:
        async with _sem("fetch"):
            job = _update_job(job_id, status="fetching", error="")
            if job is None:
                return
            info = await asyncio.to_thread(fetch.probe, job.url)
            folder = config.job_dir(job_id)
            job = _update_job(
                job_id,
                video_id=info.get("id", ""),
                title=info.get("title", ""),
                duration=float(info.get("duration") or 0),
            )
            if job is None:
                return
            sub_path, sub_note = await _download_subtitles(job_id, job.url, info, folder)
            _update_job(job_id, status="planning")
        ensure_download(job_id)
        await _plan(job, sub_path)
        if sub_note:
            _update_job(job_id, error=sub_note)
    except Exception as exc:  # noqa: BLE001 - every failure is shown on the job card
        log.exception("job %s failed", job_id)
        _update_job(job_id, status="failed", error=str(exc)[:800])


async def _download_subtitles(job_id: int, url: str, info: dict, folder: Path) -> tuple[Path | None, str]:
    """Try each caption track. A 429 on a translated track must not fail the whole job."""
    candidates = fetch.subtitle_candidates(info)
    errors: list[str] = []
    for lang, auto in candidates:
        try:
            path = await asyncio.to_thread(fetch.download_subtitle, url, lang, auto, folder)
            if errors:
                log.info("job %s subtitles: using %s after %s", job_id, lang, errors)
            return path, ""
        except fetch.FetchError as exc:
            errors.append(f"{lang}: {exc}")
            log.warning("job %s subtitle %s failed: %s", job_id, lang, exc)
    if not candidates:
        return None, ""
    return None, (
        "Không tải được phụ đề (YouTube giới hạn). AI sẽ tự xem video, mốc giờ có thể lệch — hãy xem lại trước khi render."
    )


async def _plan(job: Job, sub_path: Path | None) -> None:
    cues = parse_json3(sub_path) if sub_path else []
    transcript = to_text(group_lines(cues)) if cues else None
    async with _sem("plan"):
        _update_job(job.id, status="planning", error="")
        result = await asyncio.to_thread(
            planner.make_plan, job.title, job.duration, transcript, cues, job.url
        )
    with db.session() as s:
        for old in s.exec(select(Clip).where(Clip.job_id == job.id)).all():
            s.delete(old)
        for i, p in enumerate(result["parts"], 1):
            s.add(Clip(job_id=job.id, part=i, **p))
        s.commit()
    job = _update_job(
        job.id,
        status="review",
        hashtags=result["hashtags"],
        plan_warnings=result["warnings"],
        plan_source=result["source"],
    )
    if job and job.auto_render and not result["warnings"]:
        render_job(job.id)


def replan(job_id: int) -> None:
    async def run():
        try:
            with db.session() as s:
                job = s.get(Job, job_id)
            folder = config.job_dir(job_id)
            subs = sorted(folder.glob("subs.*.json3"))
            await _plan(job, subs[0] if subs else None)
        except Exception as exc:  # noqa: BLE001
            log.exception("replan %s failed", job_id)
            _update_job(job_id, status="failed", error=str(exc)[:800])

    _update_job(job_id, status="planning", error="")
    _spawn(run())


# ---------- source download ----------

def source_path(job_id: int) -> Path:
    return config.JOBS_DIR / str(job_id) / "source.mp4"


def ensure_download(job_id: int) -> asyncio.Task | None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run_coroutine_threadsafe(_await_download(job_id), _loop)
        return None
    task = _downloads.get(job_id)
    if task and not task.done():
        return task
    task = _spawn(_download(job_id))
    _downloads[job_id] = task
    return task


async def _await_download(job_id: int) -> None:
    await ensure_download(job_id)


async def _download(job_id: int) -> None:
    path = source_path(job_id)
    if path.exists():
        w, h, _ = await asyncio.to_thread(fetch.probe_file, path)
        _update_job(job_id, download_status="done", width=w, height=h)
        return
    with db.session() as s:
        job = s.get(Job, job_id)
    if job is None:
        return
    try:
        async with _sem("fetch"):
            _update_job(job_id, download_status="running")
            await asyncio.to_thread(fetch.download_video, job.url, path.parent)
        w, h, _ = await asyncio.to_thread(fetch.probe_file, path)
        _update_job(job_id, download_status="done", width=w, height=h)
    except Exception as exc:  # noqa: BLE001
        log.exception("download %s failed", job_id)
        _update_job(job_id, download_status="failed", error=f"Tải video lỗi: {exc}"[:800])


# ---------- render ----------

def render_job(job_id: int) -> int:
    with db.session() as s:
        ids = [c.id for c in s.exec(select(Clip).where(Clip.job_id == job_id)).all()]
    for cid in ids:
        render_clip(cid)
    return len(ids)


def render_clip(clip_id: int) -> None:
    clip = _update_clip(clip_id, status="queued", error="")
    if clip:
        _spawn(_render(clip_id))


async def _render(clip_id: int) -> None:
    with db.session() as s:
        clip = s.get(Clip, clip_id)
        job = s.get(Job, clip.job_id) if clip else None
    if clip is None or job is None:
        return
    try:
        await ensure_download(job.id)
        with db.session() as s:
            job = s.get(Job, job.id)
        if job.download_status != "done":
            raise RuntimeError(job.error or "Chưa tải được video gốc")
        style = settings.get_style()
        nudge = render.random_nudge(style)
        if clip.brightness is not None:
            nudge = render.ColorNudge(clip.brightness, clip.contrast, clip.saturation)
        async with _sem("render"):
            _update_clip(clip_id, status="rendering")
            out = config.job_dir(job.id) / "clips" / f"{slug(job.title)}_part{clip.part}.mp4"
            await asyncio.to_thread(
                render.render_clip,
                source_path(job.id), out, clip.start, clip.end,
                clip.title_line1, clip.title_line2,
                (job.width, job.height), nudge, style,
            )
        _update_clip(
            clip_id, status="done", file=str(out.relative_to(config.JOBS_DIR)), rendered_at=now(),
            brightness=nudge.brightness, contrast=nudge.contrast, saturation=nudge.saturation,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("render clip %s failed", clip_id)
        _update_clip(clip_id, status="failed", error=str(exc)[:800])


# ---------- startup ----------

def resume() -> None:
    """Remember the server loop and pick up work that was interrupted by a restart."""
    global _loop
    _loop = asyncio.get_running_loop()
    with db.session() as s:
        jobs = s.exec(select(Job)).all()
        clips = s.exec(select(Clip).where(Clip.status.in_(["queued", "rendering"]))).all()
    for job in jobs:
        if job.status in ("queued", "fetching"):
            start_job(job.id)
        elif job.status == "planning":
            replan(job.id)
        elif job.download_status in ("pending", "running") and job.status == "review":
            ensure_download(job.id)
    for clip in clips:
        render_clip(clip.id)
