import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, CLIP_STATUS, isBusy, Job, JOB_STATUS } from "../api";
import { handoffToPhone } from "../handoff";
import { usePolling } from "../usePolling";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [links, setLinks] = useState("");
  const [autoRender, setAutoRender] = useState(false);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(() => api<Job[]>("/api/jobs").then(setJobs), []);
  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, !!jobs?.some(isBusy));

  async function submit() {
    setSending(true);
    setMessage("");
    try {
      const res = await api<{ created: number[]; skipped: string[] }>("/api/jobs", {
        method: "POST",
        json: { urls: links.split("\n"), auto_render: autoRender },
      });
      setMessage(
        `Đã thêm ${res.created.length} video.` +
          (res.skipped.length ? ` Bỏ qua ${res.skipped.length} dòng không phải link YouTube.` : ""),
      );
      if (res.created.length) setLinks("");
      load();
    } catch (e) {
      setMessage(String((e as Error).message));
    } finally {
      setSending(false);
    }
  }

  async function act(job: Job, action: "render" | "retry" | "delete") {
    if (action === "delete" && !confirm(`Xoá "${job.title || job.url}" và mọi clip đã render?`)) return;
    try {
      if (action === "delete") await api(`/api/jobs/${job.id}`, { method: "DELETE" });
      else await api(`/api/jobs/${job.id}/${action}`, { method: "POST" });
    } catch (e) {
      alert((e as Error).message);
    }
    load();
  }

  return (
    <div className="page">
      <header className="page__head">
        <h1>Video</h1>
        <p className="lede">Dán link YouTube. Mỗi video thành 4 clip dọc, kèm tiêu đề và caption để đăng TikTok.</p>
      </header>
      <section className="card composer">
        <label className="label" htmlFor="links">
          Dán link YouTube, mỗi dòng một link
        </label>
        <textarea
          id="links"
          className="input"
          rows={4}
          placeholder="https://www.youtube.com/watch?v=..."
          value={links}
          onChange={(e) => setLinks(e.target.value)}
        />
        <div className="row">
          <label className="check">
            <input type="checkbox" checked={autoRender} onChange={(e) => setAutoRender(e.target.checked)} />
            Tự render luôn, không cần duyệt
          </label>
          <button className="btn btn--primary" disabled={sending || !links.trim()} onClick={submit}>
            {sending ? "Đang thêm…" : "Bắt đầu"}
          </button>
        </div>
        {message && <p className="muted">{message}</p>}
      </section>

      {jobs === null ? (
        <p className="muted">Đang tải…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">Chưa có video nào. Dán link ở trên để bắt đầu.</p>
      ) : (
        <div className="jobs">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onAction={(a) => act(job, a)}
              onHandoff={() => handoffToPhone(job.id, navigate)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function JobCard({
  job,
  onAction,
  onHandoff,
}: {
  job: Job;
  onAction: (a: "render" | "retry" | "delete") => void;
  onHandoff: () => void;
}) {
  const done = job.clips.filter((c) => c.status === "done").length;
  const failed = job.status === "failed" || job.download_status === "failed";
  return (
    <article className={`card job ${failed ? "job--failed" : ""}`}>
      <Link to={`/jobs/${job.id}`} className="job__media">
        {job.video_id ? (
          <img className="job__thumb" src={`https://i.ytimg.com/vi/${job.video_id}/mqdefault.jpg`} alt="" />
        ) : (
          <div className="job__thumb job__thumb--empty" />
        )}
      </Link>
      <div className="job__body">
        <Link to={`/jobs/${job.id}`} className="job__title">
          {job.title || job.url}
        </Link>
        <div className="job__meta">
          <span className={`badge badge--${job.status}`}>
            {job.status === "review" && job.clips.length > 0 && done === job.clips.length
              ? "Đã render xong"
              : JOB_STATUS[job.status]}
          </span>
          {job.clips.length > 0 && (
            <span className="muted">
              {done}/{job.clips.length}
            </span>
          )}
        </div>
        {job.clips.length > 0 && (
          <div className="job__clips" title={job.clips.map((c) => `Part ${c.part}: ${CLIP_STATUS[c.status]}`).join(", ")}>
            {job.clips.map((c) => (
              <span key={c.id} className={`job__dot job__dot--${c.status}`} />
            ))}
          </div>
        )}
        {job.error && <p className="error">{job.error}</p>}
      </div>
      <div className="job__actions">
        {failed && (
          <button className="btn btn--small" onClick={() => onAction("retry")}>
            Thử lại
          </button>
        )}
        {job.status === "review" && (
          <Link className="btn btn--small" to={`/jobs/${job.id}`}>
            Duyệt
          </Link>
        )}
        {done > 0 && (
          <button className="btn btn--small btn--primary" onClick={onHandoff}>
            Tải hết
          </button>
        )}
        {job.status === "review" && done < job.clips.length && (
          <button className="btn btn--small" onClick={() => onAction("render")}>
            Render
          </button>
        )}
        <button className="btn btn--small btn--danger" onClick={() => onAction("delete")}>
          Xoá
        </button>
      </div>
    </article>
  );
}
