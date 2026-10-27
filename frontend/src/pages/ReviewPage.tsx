import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  Clip,
  CLIP_STATUS,
  copyText,
  fmtTime,
  isBusy,
  Job,
  JOB_STATUS,
  parseTime,
  PART_MAX,
  PART_MIN,
} from "../api";
import { handoffToPhone } from "../handoff";
import { usePolling } from "../usePolling";

export default function ReviewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(
    () =>
      api<Job>(`/api/jobs/${id}`)
        .then(setJob)
        .catch((e) => setError(e.message)),
    [id],
  );
  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, !!job && isBusy(job));

  if (error) return <p className="error">{error}</p>;
  if (!job) return <p className="muted">Đang tải…</p>;

  async function renderAll() {
    await api(`/api/jobs/${job!.id}/render`, { method: "POST" });
    load();
  }

  async function replan() {
    if (!confirm("Cho AI chia lại từ đầu? Mọi chỉnh sửa tiêu đề/mốc giờ hiện tại sẽ mất.")) return;
    await api(`/api/jobs/${job!.id}/replan`, { method: "POST" });
    load();
  }

  return (
    <div className="page">
      <header className="page__head">
        <Link to="/" className="back">
          ← Danh sách
        </Link>
        <h1>{job.title || job.url}</h1>
      </header>
      <div className="toolbar">
        <span className={`badge badge--${job.status}`}>{JOB_STATUS[job.status]}</span>
        {job.download_status !== "done" && (
          <span className="badge">
            {job.download_status === "failed" ? "Tải video gốc lỗi" : "Đang tải video gốc…"}
          </span>
        )}
        {job.plan_source === "youtube" && (
          <span className="badge">Không có phụ đề: AI tự xem video, mốc giờ có thể lệch</span>
        )}
        <a className="muted" href={job.url} target="_blank" rel="noreferrer">
          Mở trên YouTube ↗
        </a>
        <span className="spacer" />
        {job.status === "review" && (
          <>
            <button className="btn" onClick={replan}>
              Cho AI chia lại
            </button>
            <button
              className={job.clips.some((c) => c.status === "done") ? "btn" : "btn btn--primary"}
              onClick={renderAll}
            >
              Render cả {job.clips.length} part
            </button>
          </>
        )}
        {job.clips.some((c) => c.status === "done") && (
          <button className="btn btn--primary" onClick={() => handoffToPhone(job.id, navigate)}>
            Tải hết &amp; sang iPhone
          </button>
        )}
      </div>
      {job.error && <p className="error">{job.error}</p>}
      {job.plan_warnings.length > 0 && (
        <div className="warn">
          <strong>AI chưa đáp ứng đủ luật sau 3 lần thử — hãy sửa tay trước khi render:</strong>
          <ul>
            {job.plan_warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {job.clips.length > 0 && <Hashtags job={job} onSaved={setJob} />}

      <div className="clips">
        {job.clips.map((clip, i) => (
          <ClipEditor
            key={clip.id}
            clip={clip}
            prev={job.clips[i - 1]}
            sourceUrl={job.source_url}
            onChange={load}
          />
        ))}
      </div>
    </div>
  );
}

function Hashtags({ job, onSaved }: { job: Job; onSaved: (j: Job) => void }) {
  const [text, setText] = useState(job.hashtags.join(" "));
  const [note, setNote] = useState("");
  const dirty = text.trim() !== job.hashtags.join(" ");

  async function save() {
    const saved = await api<Job>(`/api/jobs/${job.id}`, {
      method: "PATCH",
      json: { hashtags: text.split(/\s+/) },
    });
    onSaved(saved);
    setText(saved.hashtags.join(" "));
    setNote("Đã lưu");
  }

  return (
    <section className="card">
      <label className="label">Hashtag chung cho cả {job.clips.length} part</label>
      <div className="row">
        <input className="input grow" value={text} onChange={(e) => setText(e.target.value)} />
        {dirty && (
          <button className="btn btn--primary" onClick={save}>
            Lưu
          </button>
        )}
        <button className="btn" onClick={async () => setNote((await copyText(text)) ? "Đã copy" : "Copy lỗi")}>
          Copy
        </button>
        {note && <span className="muted">{note}</span>}
      </div>
    </section>
  );
}

type Draft = {
  start: string;
  end: string;
  title_line1: string;
  title_line2: string;
  title_vi: string;
  caption_en: string;
  caption_vi: string;
  brightness: string;
  contrast: string;
  saturation: string;
};

function toDraft(c: Clip): Draft {
  const num = (v: number | null) => (v === null ? "" : String(v));
  return {
    start: fmtTime(c.start),
    end: fmtTime(c.end),
    title_line1: c.title_line1,
    title_line2: c.title_line2,
    title_vi: c.title_vi,
    caption_en: c.caption_en,
    caption_vi: c.caption_vi,
    brightness: num(c.brightness),
    contrast: num(c.contrast),
    saturation: num(c.saturation),
  };
}

function ClipEditor({
  clip,
  prev,
  sourceUrl,
  onChange,
}: {
  clip: Clip;
  prev?: Clip;
  sourceUrl: string;
  onChange: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(clip));
  const [saved, setSaved] = useState<Draft>(() => toDraft(clip));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);

  // A render stores the colour values it used; pick them up unless the user is mid-edit.
  useEffect(() => {
    if (dirty) return;
    const next = toDraft(clip);
    setDraft(next);
    setSaved(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clip.rendered_at]);

  const start = parseTime(draft.start);
  const end = parseTime(draft.end);
  const length = start !== null && end !== null ? end - start : null;
  const lengthOk = length !== null && length >= PART_MIN && length <= PART_MAX;
  const gap = prev && start !== null ? start - prev.end : 0;

  const set = (k: keyof Draft) => (e: { target: { value: string } }) => setDraft({ ...draft, [k]: e.target.value });

  function playSegment() {
    const v = video.current;
    if (!v || start === null) return;
    v.currentTime = start;
    stopAt.current = end;
    v.play();
  }

  function takeTime(k: "start" | "end") {
    const v = video.current;
    if (v) setDraft({ ...draft, [k]: fmtTime(Math.round(v.currentTime * 100) / 100) });
  }

  async function save(): Promise<boolean> {
    if (start === null || end === null) {
      setError("Mốc giờ phải có dạng m:ss, ví dụ 1:23 hoặc 1:23.5");
      return false;
    }
    const num = (v: string) => (v.trim() === "" ? null : Number(v));
    try {
      const res = await api<Clip>(`/api/clips/${clip.id}`, {
        method: "PATCH",
        json: {
          start,
          end,
          title_line1: draft.title_line1,
          title_line2: draft.title_line2,
          title_vi: draft.title_vi,
          caption_en: draft.caption_en,
          caption_vi: draft.caption_vi,
          brightness: num(draft.brightness),
          contrast: num(draft.contrast),
          saturation: num(draft.saturation),
        },
      });
      const next = toDraft(res);
      setDraft(next);
      setSaved(next);
      setError("");
      onChange();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  }

  async function render() {
    setBusy(true);
    try {
      if (dirty && !(await save())) return;
      await api(`/api/clips/${clip.id}/render`, { method: "POST" });
      onChange();
    } finally {
      setBusy(false);
    }
  }

  const rendering = clip.status === "queued" || clip.status === "rendering";

  return (
    <section className="card clip">
      <header className="clip__head">
        <h2>Part {clip.part}</h2>
        <span className={`chip chip--${clip.status}`}>{CLIP_STATUS[clip.status]}</span>
        {clip.posted_at && <span className="chip chip--done">Đã đăng</span>}
        <span className="spacer" />
        {dirty && (
          <button className="btn" onClick={save}>
            Lưu
          </button>
        )}
        <button className="btn btn--primary" disabled={busy || rendering} onClick={render}>
          {rendering ? "Đang render…" : clip.status === "done" ? "Render lại" : "Render"}
        </button>
      </header>
      {error && <p className="error">{error}</p>}
      {clip.status === "failed" && clip.error && <p className="error">{clip.error}</p>}

      <div className="clip__body">
        <div className="clip__source">
          <h3 className="col-label">Video gốc</h3>
          {sourceUrl ? (
            <video
              ref={video}
              src={sourceUrl}
              controls
              preload="metadata"
              onTimeUpdate={(e) => {
                const v = e.currentTarget;
                if (stopAt.current !== null && v.currentTime >= stopAt.current) {
                  v.pause();
                  stopAt.current = null;
                }
              }}
            />
          ) : (
            <div className="placeholder">Video gốc đang tải…</div>
          )}
          <div className="row">
            <button className="btn btn--small" disabled={!sourceUrl} onClick={playSegment}>
              ▶ Xem đoạn này
            </button>
            <button className="btn btn--small" disabled={!sourceUrl} onClick={() => takeTime("start")}>
              Lấy mốc đang xem làm Bắt đầu
            </button>
            <button className="btn btn--small" disabled={!sourceUrl} onClick={() => takeTime("end")}>
              … làm Kết thúc
            </button>
          </div>
        </div>

        <div className="clip__form">
          <h3 className="col-label">Nội dung</h3>
          <div className="row">
            <label className="field">
              <span>Bắt đầu</span>
              <input className="input" value={draft.start} onChange={set("start")} />
            </label>
            <label className="field">
              <span>Kết thúc</span>
              <input className="input" value={draft.end} onChange={set("end")} />
            </label>
            <div className={`field duration ${lengthOk ? "" : "duration--bad"}`}>
              <span>Thời lượng</span>
              <strong>{length === null ? "?" : `${length.toFixed(1)} s`}</strong>
              {!lengthOk && <small>nên {PART_MIN}–{PART_MAX} s</small>}
            </div>
          </div>
          {prev && Math.abs(gap) > 0.05 && (
            <p className="warn-inline">
              {gap > 0 ? "Hở" : "Chồng lên"} {Math.abs(gap).toFixed(1)} s so với Part {prev.part} (kết thúc{" "}
              {fmtTime(prev.end)})
            </p>
          )}
          <label className="field">
            <span>Tiêu đề dòng 1</span>
            <input className="input" value={draft.title_line1} onChange={set("title_line1")} />
          </label>
          <label className="field">
            <span>Tiêu đề dòng 2</span>
            <input className="input" value={draft.title_line2} onChange={set("title_line2")} />
          </label>
          <label className="field">
            <span>Dịch tiêu đề</span>
            <input className="input" value={draft.title_vi} onChange={set("title_vi")} />
          </label>
          <label className="field">
            <span>Caption (English)</span>
            <textarea className="input" rows={2} value={draft.caption_en} onChange={set("caption_en")} />
          </label>
          <label className="field">
            <span>Dịch caption</span>
            <textarea className="input" rows={2} value={draft.caption_vi} onChange={set("caption_vi")} />
          </label>
          <details>
            <summary className="muted">Màu (để trống = ngẫu nhiên nhẹ mỗi lần render)</summary>
            <div className="row">
              <label className="field">
                <span>Độ sáng (0 = giữ)</span>
                <input className="input" value={draft.brightness} onChange={set("brightness")} />
              </label>
              <label className="field">
                <span>Tương phản (1 = giữ)</span>
                <input className="input" value={draft.contrast} onChange={set("contrast")} />
              </label>
              <label className="field">
                <span>Bão hoà (1 = giữ)</span>
                <input className="input" value={draft.saturation} onChange={set("saturation")} />
              </label>
            </div>
          </details>
        </div>

        {clip.url && (
          <div className="clip__result">
            <h3 className="col-label">Clip đã render</h3>
            <video src={`${clip.url}?v=${clip.rendered_at ?? ""}`} controls preload="metadata" />
            <a className="btn btn--small" href={`/api/clips/${clip.id}/download`}>
              Tải về
            </a>
          </div>
        )}
      </div>
    </section>
  );
}
