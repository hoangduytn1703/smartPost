export type ClipStatus = "draft" | "queued" | "rendering" | "done" | "failed";

export interface Clip {
  id: number;
  job_id: number;
  part: number;
  start: number;
  end: number;
  title_line1: string;
  title_line2: string;
  title_vi: string;
  caption_en: string;
  caption_vi: string;
  brightness: number | null;
  contrast: number | null;
  saturation: number | null;
  status: ClipStatus;
  error: string;
  url: string;
  rendered_at: string | null;
  posted_at: string | null;
}

export interface Job {
  id: number;
  url: string;
  video_id: string;
  title: string;
  duration: number;
  status: "queued" | "fetching" | "planning" | "review" | "failed";
  download_status: "pending" | "running" | "done" | "failed";
  error: string;
  auto_render: boolean;
  plan_source: string;
  hashtags: string[];
  plan_warnings: string[];
  source_url: string;
  created_at: string;
  clips: Clip[];
}

export interface PhoneClip extends Clip {
  job_title: string;
  post_text: string;
}

export interface Style {
  font: string;
  font_size: number;
  line1_color: string;
  line2_color: string;
  outline: number;
  uppercase: boolean;
  brightness_jitter: number;
  contrast_jitter: number;
  saturation_jitter: number;
}

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(path, {
    ...rest,
    headers: json !== undefined ? { "content-type": "application/json" } : rest.headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
  }
  return data as T;
}

export const PART_MIN = 70;
export const PART_MAX = 90;

export function fmtTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  const whole = Math.floor(rest);
  const frac = Math.round((rest - whole) * 100);
  return `${m}:${String(whole).padStart(2, "0")}${frac ? "." + String(frac).padStart(2, "0") : ""}`;
}

export function parseTime(text: string): number | null {
  const parts = text.trim().split(":");
  if (!parts.length || parts.length > 3 || parts.some((p) => p === "" || isNaN(Number(p)))) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}

/** Copy that also works on plain http (the iPhone opens the app over the LAN, not https). */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fall through */
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  // iOS Safari will not select text in a readonly textarea; 16px avoids its focus zoom.
  area.style.fontSize = "16px";
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.focus();
  area.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(area);
  return ok;
}

export const JOB_STATUS: Record<Job["status"], string> = {
  queued: "Đang chờ",
  fetching: "Đang đọc video",
  planning: "AI đang chia đoạn",
  review: "Chờ duyệt",
  failed: "Lỗi",
};

export const CLIP_STATUS: Record<ClipStatus, string> = {
  draft: "Chưa render",
  queued: "Chờ render",
  rendering: "Đang render",
  done: "Xong",
  failed: "Lỗi",
};

export function isBusy(job: Job): boolean {
  return (
    ["queued", "fetching", "planning"].includes(job.status) ||
    ["pending", "running"].includes(job.download_status) ||
    job.clips.some((c) => c.status === "queued" || c.status === "rendering")
  );
}
