# Audiobook AI Service

Audiobook AI Service là hệ thống sinh audiobook từ sách điện tử bằng pipeline nhiều agent. Luồng demo chính hiện tại:

```text
Streamlit frontend -> FastAPI backend -> SQLite job queue
-> Audiobook pipeline -> TTS -> audio + EPUB3 chapter artifacts
```

Đầu ra gồm file audio tổng (`mp3` hoặc `wav`) và các artifact EPUB3 theo chương, trong đó mỗi câu/segment có audio riêng để nghe trong trình đọc hỗ trợ EPUB3.

## Thành Phần Chính

- **Frontend**: Streamlit UI tại `src/frontend/streamlit_app.py`, dùng để upload EPUB, theo dõi job, nghe/tải audio và tải EPUB3 theo chương.
- **Backend**: FastAPI app tại `src/backend/app.py`, cung cấp API tạo job, theo dõi trạng thái, hủy job và tải output.
- **Pipeline**: `src/pipeline/` điều phối parse/clean/summarize/classify/voice/TTS/QC/audio/package.
- **Agents**: `src/agents/` chứa các agent xử lý văn bản, mood/voice, TTS, QC và audio finalize.
- **TTS engines**: direct XTTS/VieNeu chạy trong pipeline; `src/tts-service/` được giữ cho hướng microservice/worker.
- **Colab runner**: `scripts/colab_runner.ipynb` tự cài dependency, chuẩn bị model, chạy FastAPI + Streamlit và mở tunnel.

## Cấu Trúc Rút Gọn

```text
src/
  backend/          FastAPI entrypoint
  frontend/         Streamlit entrypoint
  api/              Audiobook HTTP routes
  pipeline/         Pipeline orchestration
  agents/           Parser, cleaner, summarizer, classifier, voice, TTS, QC, audio
  schema/           Shared data models
  services/         Queue, storage, logging helpers
  utils/            Audio and EPUB3 packaging utilities
  tts-service/      Optional Redis/RQ TTS microservice
scripts/
  colab_runner.ipynb
data/
  voice_samples/
  qdrant_voice_db/
```

## Chạy Nhanh Local

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:TTS_ENGINE="mock"
uvicorn src.backend.app:app --host 0.0.0.0 --port 8000
```

Mở terminal khác:

```powershell
$env:API_BASE_URL="http://localhost:8000"
streamlit run src/frontend/streamlit_app.py --server.port 8501
```

Mở `http://localhost:8501`, upload EPUB, đợi job hoàn tất rồi tải audio hoặc EPUB3 chapter artifact.

## Tài Liệu Theo Component

Xem hướng dẫn chi tiết tại [docs/COMPONENTS.md](docs/COMPONENTS.md):

- Cài đặt dependency và biến môi trường.
- Chạy frontend/backend/pipeline CLI.
- Chạy Colab GPU.
- Chạy TTS microservice.
- API endpoints và layout output.

## Lưu Ý Hiện Trạng

- API upload hiện validate file `.epub`. Pipeline có parser cho PDF/EPUB/TXT, nhưng PDF qua API cần mở rộng route upload trước khi dùng như production path.
- XTTS production cần CUDA, checkpoint/config/vocab hợp lệ và runtime `XTTSv2-Finetuning-for-New-Languages`.
- `ffmpeg`/`ffprobe` là dependency hệ điều hành, không được cài bằng `pip`.
