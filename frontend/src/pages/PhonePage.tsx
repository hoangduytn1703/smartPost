import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, copyText, PhoneClip } from "../api";

export default function PhonePage() {
  const [params] = useSearchParams();
  const jobId = params.get("job");
  const [clips, setClips] = useState<PhoneClip[] | null>(null);
  const [showPosted, setShowPosted] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  const [lan, setLan] = useState<{ url: string; qr_svg: string } | null>(null);

  const load = useCallback(() => api<PhoneClip[]>("/api/phone/clips").then(setClips), []);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const query = jobId ? `?job=${jobId}` : "";
    api<{ url: string; qr_svg: string }>(`/api/lan${query}`).then(setLan);
  }, [jobId]);

  async function copy(clip: PhoneClip) {
    if (await copyText(clip.post_text)) {
      setCopied(clip.id);
    } else {
      alert("Không copy được. Giữ tay vào đoạn chữ bên trên rồi chọn Sao chép.");
    }
  }

  async function togglePosted(clip: PhoneClip) {
    await api(`/api/clips/${clip.id}/posted`, { method: "POST", json: { posted: !clip.posted_at } });
    load();
  }

  async function share(clip: PhoneClip) {
    await copy(clip);
    try {
      const blob = await (await fetch(clip.url)).blob();
      const file = new File([blob], `part${clip.part}.mp4`, { type: "video/mp4" });
      const payload = { files: [file], text: clip.post_text };
      if (navigator.share && navigator.canShare?.(payload)) {
        await navigator.share(payload);
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        /* the caption is already copied; saving the file is the other button */
      }
    }
  }

  const ofJob = (clips ?? []).filter((c) => !jobId || String(c.job_id) === jobId);
  const list = ofJob.filter((c) => showPosted || !c.posted_at);
  const postedCount = ofJob.filter((c) => c.posted_at).length;
  const canShare = typeof navigator !== "undefined" && !!navigator.share && window.isSecureContext;

  return (
    <div className="phone">
      <header className="phone__head">
        <h1>{jobId ? "Đăng TikTok" : "Clip chờ đăng"}</h1>
        <button className="btn btn--small" onClick={load}>
          Tải lại
        </button>
      </header>

      {lan && (
        <section className="card phone-handoff">
          <div>
            <h2>Mở trang này trên iPhone</h2>
            <p>Máy tính và iPhone cùng wifi. Quét mã, rồi với từng clip:</p>
            <ol>
              <li>Lưu video (vào Tệp → Chia sẻ → Lưu video để vào Ảnh)</li>
              <li>Copy nội dung + hashtag</li>
              <li>Mở TikTok, chọn đúng video, dán và đăng</li>
            </ol>
            <p className="muted">
              TikTok không nhận caption từ nút chia sẻ của iPhone, nên chữ phải dán. Nút Copy đã gồm cả nội dung lẫn
              hashtag.
            </p>
          </div>
          <div className="qr" dangerouslySetInnerHTML={{ __html: lan.qr_svg }} />
        </section>
      )}

      <p className="phone__steps">Mỗi clip: Lưu video → Copy nội dung + hashtag → dán vào TikTok → Đã đăng.</p>

      {postedCount > 0 && (
        <label className="check">
          <input type="checkbox" checked={showPosted} onChange={(e) => setShowPosted(e.target.checked)} />
          Hiện cả {postedCount} clip đã đăng
        </label>
      )}
      {clips === null ? (
        <p className="muted">Đang tải…</p>
      ) : list.length === 0 ? (
        <p className="muted">Chưa có clip nào render xong.</p>
      ) : (
        <div className="phone__list">
        {list.map((clip) => (
          <article key={clip.id} className={`card phone__clip ${clip.posted_at ? "phone__clip--posted" : ""}`}>
            <div className="phone__title">
              <strong>Part {clip.part}</strong> · {clip.job_title}
            </div>
            <div className="phone__overlay">
              {clip.title_line1}
              <br />
              {clip.title_line2}
            </div>
            {playing === clip.id ? (
              <video src={clip.url} controls playsInline autoPlay className="phone__video" />
            ) : (
              <button className="btn" onClick={() => setPlaying(clip.id)}>
                ▶ Xem
              </button>
            )}
            <pre className="phone__text">{clip.post_text}</pre>
            <div className="phone__actions">
              <a className="btn" href={`/api/clips/${clip.id}/download`} download>
                Lưu video
              </a>
              <button className="btn btn--primary" onClick={() => copy(clip)}>
                {copied === clip.id ? "Đã copy — dán vào TikTok" : "Copy nội dung + hashtag"}
              </button>
              {canShare && (
                <button className="btn" onClick={() => share(clip)}>
                  Chia sẻ video
                </button>
              )}
              <button className="btn" onClick={() => togglePosted(clip)}>
                {clip.posted_at ? "Bỏ đánh dấu đã đăng" : "Đã đăng"}
              </button>
            </div>
          </article>
        ))}
        </div>
      )}
    </div>
  );
}
