# smartPost — ghi chú cho Claude (đọc đầu mỗi phiên)

Công cụ **local, một người dùng**: biến video YouTube dài thành 4 clip dọc 9:16 để đăng TikTok (thị trường Mỹ, khán giả 16–25).
Luồng: dán link YouTube → yt-dlp lấy phụ đề + video → Gemini (MASTER PROMPT) chọn 4 đoạn liền nhau + tiêu đề 2 dòng + caption + 5 hashtag
→ code kiểm tra luật → màn duyệt → ffmpeg render (nền mờ, chỉnh màu nhẹ, tiêu đề) → trang `/phone` trên iPhone (cùng wifi) để lưu video + copy caption.
**Tìm video viral và bấm đăng TikTok vẫn làm tay** (người dùng chọn đăng bằng iPhone).

## Quy ước
- Trả lời tiếng Việt; UI tiếng Việt; code + comment tiếng Anh. Chỉ commit/push khi được bảo.
- Code xong thì ghi vào **Nhật ký** cuối file này (ngày, làm gì, đã thử thật chưa) và cập nhật các mục bên dưới.

## Chạy
- Cần: Python 3.11+, `uv`, Node 20+, `yt-dlp`, `ffmpeg`/`ffprobe` trên PATH (Linux: `~/.local/bin`). yt-dlp gọi với `--js-runtimes node` (YouTube đòi JS runtime).
- `cp .env.example .env`, điền `GEMINI_API_KEYS` (nhiều key cách nhau dấu phẩy, gặp 429 thì thử key kế). `.env` không commit.
- `make install` → `make start` (build UI rồi chạy một server :8500 phục vụ cả UI lẫn API, nghe 0.0.0.0 cho iPhone).
  Dev: `make backend` (:8500, reload) + `make frontend` (Vite :5180, proxy /api /files).
- Test: `make test` (pytest, ~1 s; test render cần ffmpeg). Typecheck UI: `npm run typecheck --prefix frontend`.
- Server `make start` **không tự reload**: sửa backend xong phải khởi động lại; kiểm `/api/jobs` không còn clip `queued/rendering` trước
  (job đang chạy sẽ được `worker.resume()` chạy lại khi khởi động, nhưng render dở bị làm lại từ đầu).

## Chỗ cần biết trong code
- `backend/smartpost/`: `main.py` (routes `/api/jobs`, `/api/clips`, `/api/phone/clips`, `/api/lan` (QR), `/api/settings`, `/files/*` = `storage/jobs`,
  SPA fallback), `worker.py` (hàng đợi asyncio, semaphore fetch/plan/render từ `.env`; `_spawn` chuyển coroutine về loop của server khi gọi từ route
  sync), `models.py` (`Job`, `Clip`, `Setting`; SQLite `storage/smartpost.db`, `create_all`, chưa có migration — thêm cột thì phải tự ALTER hoặc xoá DB).
- `services/fetch.py`: probe, chọn phụ đề (Anh thủ công trước, rồi track gốc `vi-orig`/`en-orig` — **không** lấy auto `en` dịch của video tiếng khác vì YouTube trả 429), tải `source.mp4` ≤ 1080p, `extract_youtube_url`. Phụ đề lỗi thì job vẫn chạy: Gemini tự xem video.
- `services/transcript.py`: json3 → cue (auto caption: end = start của dòng kế; bỏ dòng chỉ có `\n`) → dòng ~câu (≤ 8 s) `m:ss text` cho AI.
- `services/planner.py`: Gemini REST `generateContent` + `responseSchema` JSON; không có phụ đề thì gửi link YouTube (`fileData`). Sai luật → gửi lại
  kèm lỗi cụ thể, tối đa 2 lần; vẫn sai → trả kèm `warnings` (UI hiện hộp vàng, người dùng sửa tay). Video < 4:40 → lỗi ngay, không gọi AI.
- `services/validate.py`: luật lấy từ MASTER PROMPT (4 part, mỗi part 70–90 s, tổng 280–360 s, liền nhau, 5 hashtag). Ký tự `? ! &` trong caption
  **code tự sửa**, không hỏi lại AI. `snap_to_cues` dời điểm cắt về đầu câu gần nhất (±2 s) nếu không phá luật độ dài.
- `services/render.py`: một lệnh ffmpeg/clip — nền = bản thu nhỏ 1/4 + boxblur rồi phóng lên 1080×1920, video gốc rộng 1080 ở giữa, `eq` chỉnh màu
  (ngẫu nhiên ± jitter trong Cài đặt, lưu lại trên clip để render lại giữ màu), tiêu đề ASS (`\an2\pos`, ngay trên video; video dọc thì y=420),
  cỡ chữ tự thu theo dòng dài nhất (`GLYPH_WIDTH` 0,55). ffmpeg chạy với cwd = thư mục clip để `ass=` nhận tên file trơn.
- `prompts/master_prompt.md`: chép mục 1–6 của `docs/MASTER PROMPT.txt` (file gốc bị cụt ở "## 7. CẤ") + mục 7 mới yêu cầu JSON. Sửa prompt ở đây.
- Frontend `frontend/src/`: `pages/JobsPage` (dán nhiều link, tự render tuỳ chọn), `ReviewPage` (mỗi part: xem đúng đoạn trên video gốc, sửa mốc giờ,
  "lấy mốc đang xem", tiêu đề, caption, màu; Render tự lưu trước), `SettingsPage` (QR iPhone, kiểu chữ, jitter màu), `PhonePage` (`/phone`, không có nav).
- iPhone mở qua **HTTP** trong LAN → không có clipboard API/Web Share: copy dùng textarea + `execCommand` (không `readonly`, iOS mới chọn được chữ);
  "Lưu video" = tải file (`Content-Disposition: attachment`) vào app Tệp. Muốn lưu thẳng vào Ảnh cần HTTPS (ví dụ `cloudflared`), chưa làm.
  Nút "Tải hết & sang iPhone" (`GET /api/jobs/{id}/zip`, rồi mở `/phone?job=`) tải một file zip mọi clip đã render.
  TikTok không nhận caption từ share sheet, nên trên iPhone mỗi clip có nút copy **cả nội dung lẫn hashtag** để dán vào ô mô tả.

## Việc đang dở / chưa kiểm chứng
- **Chưa thử `/phone` trên iPhone thật** (lưu video, copy caption qua HTTP). Máy dev thấy IP LAN `10.1.12.190`.
- Chưa thử video **không có phụ đề** (đường gửi link YouTube cho Gemini) với API thật — mới có test giả.
- Chưa có cách xoá file `source.mp4` cũ ngoài nút Xoá cả video.

## Nhật ký
- 27/10: danh sách video thành lưới thẻ (ảnh trên, chữ dưới), trang iPhone 2 cột trên màn rộng. Chưa nhờ người dùng test lại.
- 27/10: chỉnh lại giao diện (nền tối, nút chính màu sáng, thẻ video và màn duyệt chia cột). Chưa nhờ người dùng test lại.
- 27/10: nút "Tải hết & sang iPhone" (zip mọi clip đã render, mở `/phone?job=`). Copy trên iPhone gồm caption + hashtag; TikTok không lấy chữ từ nút chia sẻ nên phải dán.
- 27/10: phụ đề video tiếng Việt bị 429 (YouTube chặn bản dịch `en`, track gốc `vi-orig` tải được). Giờ ưu tiên phụ đề gốc; hết cách thì AI tự xem video, job không fail. Đã thử tải `vi-orig` của WDWwYdKFWVg.
- 27/10: dựng toàn bộ bản đầu (backend FastAPI + worker + yt-dlp + Gemini + ffmpeg, frontend React, trang iPhone). Đã chạy thật: 4 video
  (The Egg, Amy Cuddy, Ken Robinson, Steve Jobs) — AI chia đúng luật ngay lần đầu (~13 s/video), 3 link chạy song song, render 4 clip
  1080×1920 thời lượng khớp mốc cắt (~14 s/clip 85 s), sửa mốc + tiêu đề trên UI rồi render lại đúng. 21 test pass.
