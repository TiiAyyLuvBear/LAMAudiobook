# Quick Start

Tài liệu này được viết theo hướng vận hành nhanh:

- Phần đầu dành cho người dùng không chuyên kỹ thuật hoặc bộ phận business.
- Phần sau dành cho người triển khai, kiểm thử và vận hành hệ thống.
- Các phần có lệnh hoặc biến môi trường được trình bày rõ ràng để dễ thực hiện.

---

## 1. Mục Tiêu Sử Dụng Nhanh

Hệ thống LAMAudiobook dùng để chuyển đổi ebook/pdf/txt thành audiobook theo quy trình tự động:

1. Người dùng tải sách lên.
2. Hệ thống phân tích và xử lý nội dung.
3. Hệ thống sinh audio và đóng gói thành audiobook.
4. Người dùng nghe trực tiếp hoặc tải kết quả về.

Kết quả đầu ra có thể bao gồm:

- File âm thanh tổng hợp, thường là `mp3` hoặc `wav`.
- Tệp audiobook tích hợp chương, định dạng `EPUB3`.
- Các artifact trung gian phục vụ kiểm tra và đối soát kết quả xử lý.

---

## 2. Dành Cho Người Dùng Phổ Thông / Non-Technical

Nếu mục tiêu của bạn là xem sản phẩm chạy được như một ứng dụng hoàn chỉnh, cách làm ngắn nhất là:

1. Cài môi trường theo hướng dẫn ở mục 3.
2. Khởi động backend và giao diện web theo hướng dẫn ở mục 4.
3. Mở giao diện Streamlit tại `http://localhost:8501`.
4. Tải tệp sách lên và chờ hệ thống xử lý.
5. Tải file âm thanh hoặc audiobook đầu ra khi hoàn tất.

Trong trường hợp cần chia sẻ cho người dùng hoặc khách hàng nội bộ mà không mở cổng mạng trực tiếp, có thể dùng script Cloudflare Tunnel ở mục 6.

---

## 3. Chuẩn Bị Môi Trường

### 3.1. Tạo virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 3.2. Cài thư viện Python

```powershell
pip install -r requirements.txt
```

### 3.3. Cài thư viện hệ thống

Hệ thống cần `ffmpeg` và `ffprobe` để xử lý âm thanh.

Trên Windows, nếu máy chưa có, cần cài riêng theo môi trường tổ chức đang dùng.
Trên Linux hoặc Colab, có thể cài thêm bằng công cụ hệ điều hành tương ứng.

---

## 4. Chạy Bản Demo Nhanh

Mục này phù hợp khi cần kiểm tra luồng xử lý mà không phụ thuộc vào GPU hay model lớn.

### 4.1. Mở terminal 1: chạy backend

```powershell
$env:TTS_ENGINE="mock"
uvicorn src.backend.app:app --host 127.0.0.1 --port 8000
```

### 4.2. Mở terminal 2: chạy giao diện

```powershell
$env:API_BASE_URL="http://localhost:8000"
streamlit run src/frontend/streamlit_app.py --server.port 8501
```

### 4.3. Sử dụng

Mở trình duyệt tại:

```text
http://localhost:8501
```

Sau đó:

- Tải sách lên qua giao diện.
- Theo dõi tiến trình xử lý.
- Tải kết quả âm thanh hoặc audiobook khi job hoàn tất.

Chế độ `mock` chỉ dùng để kiểm tra luồng ứng dụng và giao diện, không tạo giọng đọc thật.

---

## 5. Cấu Hình Sản Xuất

Repo hiện hỗ trợ hai backend TTS chính:

- `XTTS`
- `VieNeu`

Hai backend này dùng bộ phụ thuộc khác nhau, vì vậy cần cài đúng profile trước khi chạy.

### 5.1. XTTSv2

```powershell
pip install -U -r requirements-xtts.txt

$env:TTS_ENGINE="xtts_gpu"
$env:XTTS_MODEL_NAME_OR_PATH="aiMy144/XTTSv2VietAudiobook"
$env:XTTS_RUNTIME_DIR="models/XTTSv2-Finetuning-for-New-Languages"
$env:XTTS_VOICE_DIR="data/voice_samples"
```

Ghi chú kỹ thuật:

- XTTS dùng tốt nhất khi máy có CUDA.
- Nếu dùng checkpoint local, cần bảo đảm có đầy đủ file mô hình, config và vocab hợp lệ.
- Thư mục `data/voice_samples` phải có ít nhất một file WAV tham chiếu nếu muốn chạy chế độ dùng giọng mẫu.

### 5.2. VieNeu

```powershell
pip install -U -r requirements-vieneu.txt

$env:TTS_ENGINE="vieneu"
$env:VIENEU_MODEL_NAME="pnnbao-ump/VieNeu-TTS-0.3B"
$env:VIENEU_MODE="standard"
$env:VIENEU_DEVICE="auto"
```

Nếu bật voice cloning:

```powershell
$env:VIENEU_ENABLE_VOICE_CLONING="1"
$env:VIENEU_CODEC_REPO="neuphonic/neucodec"
```

Ghi chú kỹ thuật:

- VieNeu có thể chạy theo chế độ `auto`, `cuda` hoặc `cpu`.
- Nếu bật voice cloning, cần thêm codec repository tương ứng.
- Khi chuyển qua lại giữa XTTS và VieNeu trong cùng một `.venv`, phải cài đúng bộ phụ thuộc tương ứng.

---

## 6. Chia Sẻ Ứng Dụng Qua Cloudflare

Nếu cần chia giao diện cho người dùng hoặc khách hàng nội bộ mà không cấu hình reverse proxy riêng, dùng script:

```powershell
.\scripts\share_cloudflare.ps1
```

Script này sẽ:

- kiểm tra backend `FastAPI`,
- kiểm tra giao diện `Streamlit`,
- tạo Cloudflare quick tunnel,
- in ra URL công khai để chia sẻ.

Cần cài `cloudflared` trước nếu máy chưa có:

Trong quá trình chia sẻ, cần giữ terminal đang chạy script mở liên tục.

---

## 7. Tệp Cấu Hình Quan Trọng

Các tệp và biến cấu hình thường dùng trong repo:

- `requirements.txt`: phụ thuộc chung.
- `requirements-xtts.txt`: phụ thuộc cho backend XTTS.
- `requirements-vieneu.txt`: phụ thuộc cho backend VieNeu.
- `src/backend/app.py`: entrypoint của backend FastAPI.
- `src/frontend/streamlit_app.py`: entrypoint của giao diện Streamlit.
- `src/main.py`: entrypoint CLI/pipeline.
- `src/tts-service/`: service TTS tùy chọn.

Biến môi trường thường gặp:

- `API_BASE_URL`: địa chỉ backend cho giao diện Streamlit.
- `TTS_ENGINE`: chọn engine `mock`, `xtts_gpu`, `xtts_cpu`, hoặc `vieneu`.
- `XTTS_MODEL_NAME_OR_PATH`: đường dẫn hoặc repo model XTTS.
- `XTTS_RUNTIME_DIR`: thư mục runtime XTTS.
- `XTTS_VOICE_DIR`: thư mục chứa giọng tham chiếu.
- `VIENEU_MODEL_NAME`: tên model VieNeu.
- `VIENEU_MODE`: chế độ khởi chạy VieNeu.
- `VIENEU_DEVICE`: thiết bị thực thi.

---

## 8. Kiểm Tra Sau Khi Chạy

Sau khi khởi động hệ thống, có thể kiểm tra nhanh:

- Backend sống tại: `http://localhost:8000/health`
- Giao diện web sống tại: `http://localhost:8501`

Nếu gặp lỗi, kiểm tra các nguồn sau:

- Log của `uvicorn` ở terminal backend.
- Log của `Streamlit` ở terminal giao diện.
- Các file log trong thư mục `storage/` nếu chạy qua script chia sẻ hoặc pipeline có ghi log.

---

## 9. Ghi Chú Thực Tế Khi Vận Hành

- Bản demo nhanh nên dùng `TTS_ENGINE=mock` để kiểm tra luồng end-to-end trước khi chuyển sang model thật.
- XTTS và VieNeu dùng các bộ phụ thuộc khác nhau, nên không nên cấu hình tùy tiện trong cùng một môi trường nếu chưa kiểm tra kỹ.
- Nếu mục tiêu là trình diễn cho business, nên ưu tiên: giao diện web, trạng thái xử lý, và file đầu ra cuối cùng.
- Nếu mục tiêu là kiểm thử kỹ thuật, nên ưu tiên: log backend, artefact trung gian và cấu hình mô hình.

