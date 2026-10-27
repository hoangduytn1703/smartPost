import { useEffect, useState } from "react";
import { api, Style } from "../api";

interface Settings {
  style: Style;
  defaults: Style;
  gemini_model: string;
  gemini_keys: number;
}

export default function SettingsPage() {
  const [data, setData] = useState<Settings | null>(null);
  const [style, setStyle] = useState<Style | null>(null);
  const [lan, setLan] = useState<{ url: string; qr_svg: string } | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    api<Settings>("/api/settings").then((d) => {
      setData(d);
      setStyle(d.style);
    });
    api<{ url: string; qr_svg: string }>("/api/lan").then(setLan);
  }, []);

  if (!data || !style) return <p className="muted">Đang tải…</p>;

  const num = (k: keyof Style) => (e: { target: { value: string } }) =>
    setStyle({ ...style, [k]: Number(e.target.value) });
  const str = (k: keyof Style) => (e: { target: { value: string } }) => setStyle({ ...style, [k]: e.target.value });

  async function save(next: Style) {
    const res = await api<{ style: Style }>("/api/settings", { method: "PUT", json: { style: next } });
    setStyle(res.style);
    setNote("Đã lưu. Áp dụng cho các lần render sau.");
  }

  return (
    <div className="page">
      <header className="page__head">
        <h1>Cài đặt</h1>
        <p className="lede">Kiểu chữ trên video, chỉnh màu, và cách mở trang đăng trên iPhone.</p>
      </header>

      <section className="card phone-qr">
        <div>
          <h2>Mở trên iPhone</h2>
          <p>
            iPhone và máy tính phải dùng <strong>chung wifi</strong>. Quét mã bằng Camera, hoặc gõ địa chỉ vào Safari:
          </p>
          <p>
            <code>{lan?.url}</code>
          </p>
          <p className="muted">
            Trên iPhone: bấm "Lưu video" → video vào app Tệp (Files) → mở video → nút Chia sẻ → "Lưu video" để vào
            Ảnh. Hoặc bấm "Xem" → nút Chia sẻ của trình phát → "Lưu video".
          </p>
          <p className="muted">Không mở được: kiểm tra tường lửa máy tính cho phép cổng 8500.</p>
        </div>
        {lan && <div className="qr" dangerouslySetInnerHTML={{ __html: lan.qr_svg }} />}
      </section>

      <section className="card">
        <h2>Tiêu đề trên video</h2>
        <div className="grid">
          <label className="field">
            <span>Cỡ chữ tối đa (tự thu nhỏ khi dòng dài)</span>
            <input className="input" type="number" value={style.font_size} onChange={num("font_size")} />
          </label>
          <label className="field">
            <span>Font</span>
            <input className="input" value={style.font} onChange={str("font")} />
          </label>
          <label className="field">
            <span>Màu dòng 1</span>
            <input type="color" value={style.line1_color} onChange={str("line1_color")} />
          </label>
          <label className="field">
            <span>Màu dòng 2</span>
            <input type="color" value={style.line2_color} onChange={str("line2_color")} />
          </label>
          <label className="field">
            <span>Độ dày viền đen</span>
            <input className="input" type="number" value={style.outline} onChange={num("outline")} />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={style.uppercase}
              onChange={(e) => setStyle({ ...style, uppercase: e.target.checked })}
            />
            Viết IN HOA
          </label>
        </div>

        <h2>Chỉnh màu ngẫu nhiên mỗi clip</h2>
        <p className="muted">Mỗi lần render chọn ngẫu nhiên trong khoảng ± các giá trị này. Đặt 0 để tắt.</p>
        <div className="grid">
          <label className="field">
            <span>Độ sáng ±</span>
            <input className="input" type="number" step="0.01" value={style.brightness_jitter} onChange={num("brightness_jitter")} />
          </label>
          <label className="field">
            <span>Tương phản ±</span>
            <input className="input" type="number" step="0.01" value={style.contrast_jitter} onChange={num("contrast_jitter")} />
          </label>
          <label className="field">
            <span>Bão hoà ±</span>
            <input className="input" type="number" step="0.01" value={style.saturation_jitter} onChange={num("saturation_jitter")} />
          </label>
        </div>
        <div className="row">
          <button className="btn btn--primary" onClick={() => save(style)}>
            Lưu
          </button>
          <button className="btn" onClick={() => save(data.defaults)}>
            Về mặc định
          </button>
          {note && <span className="muted">{note}</span>}
        </div>
      </section>

      <section className="card">
        <h2>AI</h2>
        <p>
          Model: <code>{data.gemini_model}</code> · Số key Gemini: <strong>{data.gemini_keys}</strong>
        </p>
        {data.gemini_keys === 0 && (
          <p className="error">Chưa có key. Thêm GEMINI_API_KEYS vào file .env rồi khởi động lại.</p>
        )}
        <p className="muted">Prompt chia đoạn: backend/smartpost/prompts/master_prompt.md</p>
      </section>
    </div>
  );
}
