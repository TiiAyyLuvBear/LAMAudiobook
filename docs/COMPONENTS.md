# Component Guide

Tài liệu này mô tả cách chạy từng thành phần của Audiobook AI Service sau khi repo được gom lại quanh pipeline audiobook.

## 1. Cài Đặt Chung

Tạo/activate virtual environment rồi cài dependency từ root:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Cài thêm dependency hệ điều hành:

```text
ffmpeg / ffprobe
```

Trên Colab/Linux, notebook `scripts/colab_runner.ipynb` tự cài `ffmpeg` và các gói cần thiết.

## 2. Biến Môi Trường

Ví dụ `.env` local:

```env
API_BASE_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
STORAGE_DIR=./storage
MAX_UPLOAD_MB=200
MAX_CONCURRENT_JOBS=1

TTS_ENGINE=mock
TTS_DEVICE=auto

XTTS_MODEL_NAME_OR_PATH=aiMy144/XTTSv2VietAudiobook
XTTS_RUNTIME_DIR=models/XTTSv2-Finetuning-for-New-Languages
XTTS_VOICE_DIR=data/voice_samples
XTTS_CONFIG_PATH=
XTTS_VOCAB_PATH=
HF_TOKEN=
```

Engine thường dùng:

- `mock`: smoke test nhanh, không cần GPU.
- `xtts_gpu`: XTTS production trên CUDA.
- `xtts_cpu`: XTTS CPU, chậm và chỉ nên dùng để debug.
- `vieneu`: VieNeu engine nếu đã cài dependency hệ thống và package tương ứng.

## 3. Backend FastAPI

Entrypoint chính:

```text
src/backend/app.py
```

Chạy local:

```powershell
uvicorn src.backend.app:app --host 0.0.0.0 --port 8000
```

Health check:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
```

Endpoint chính:

- `POST /api/v1/audiobook/jobs`: upload EPUB và tạo job.
- `GET /api/v1/audiobook/jobs`: liệt kê jobs.
- `GET /api/v1/audiobook/jobs/{job_id}`: trạng thái, progress, logs gần nhất.
- `GET /api/v1/audiobook/jobs/{job_id}/download`: tải audio tổng.
- `GET /api/v1/audiobook/jobs/{job_id}/chapters/{chapter_index}/download`: tải EPUB3 chapter artifact.
- `DELETE /api/v1/audiobook/jobs/{job_id}`: hủy job pending/running.

Output mỗi job:

```text
storage/jobs/{job_id}/input/book.epub
storage/jobs/{job_id}/output/audiobook.mp3
storage/jobs/{job_id}/output/chapters/
storage/jobs/{job_id}/outputs/
storage/jobs/{job_id}/metadata.json
storage/jobs/{job_id}/logs/logs.txt
```

Debug outputs theo stage:

```text
outputs/
  01_parse/parser.json
  01_parse/blocks.txt
  02_clean/cleaner.json
  02_clean/plain_text.txt
  02_clean/chapters.json
  03_summarize/summarizer.json
  03_summarize/summary.txt
  04_classify/classifier.json
  05_voice/voice.json
  06_tts/segments.json
  06_tts/audio_segments.json
  06_tts/failed_segments.json
  07_qc/qc.json
  08_audio/audio.json
```

Các file này chỉ phục vụ debug/quan sát pipeline nội bộ; API/UI hiện không expose riêng chúng.

## 4. Frontend Streamlit

Entrypoint chính:

```text
src/frontend/streamlit_app.py
```

Chạy local:

```powershell
$env:API_BASE_URL="http://localhost:8000"
streamlit run src/frontend/streamlit_app.py --server.port 8501
```

Frontend hỗ trợ:

- Upload EPUB.
- Chọn output `mp3` hoặc `wav`.
- Bật/tắt normalize audio và chapter metadata.
- Theo dõi progress/stage/logs.
- Preview và download audio tổng.
- Download EPUB3 artifact theo chương khi chương đã package xong.

## 5. Pipeline CLI

CLI entrypoint:

```text
src/main.py
```

Ví dụ:

```powershell
$env:TTS_ENGINE="mock"
python -m src.main --input book_pdf/4.epub --output storage/manual_run --format mp3
```

CLI hữu ích để debug pipeline không qua API/UI. API hiện chỉ nhận EPUB upload; nếu muốn PDF upload qua UI/API cần mở rộng validation route trước.

## 6. Colab GPU Runner

Notebook:

```text
scripts/colab_runner.ipynb
```

Notebook hiện chạy đúng layout mới:

```text
uvicorn src.backend.app:app
streamlit run src/frontend/streamlit_app.py
```

Notebook thực hiện:

- Kiểm tra GPU/CUDA.
- Cài dependency root từ `requirements.txt`.
- Cài `ffmpeg` và dependency build khi cần.
- Clone/cài XTTS runtime nếu dùng XTTS.
- Tải model từ Hugging Face hoặc dùng model local.
- Tạo `.env`.
- Chạy FastAPI và Streamlit.
- Mở Cloudflare quick tunnel cho API/UI.

## 7. TTS Microservice Tùy Chọn

Thư mục:

```text
src/tts-service/
```

Mục đích: chạy TTS qua FastAPI + Redis/RQ worker thay vì direct engine trong pipeline.

Chạy bằng Docker Compose:

```powershell
docker compose up --build redis tts-api tts-worker
```

Ghi chú:

- Root demo Colab hiện dùng direct engine trong pipeline, không bắt buộc microservice.
- `src/tts-service/requirements.txt` là subset riêng cho container service.

## 8. Kiểm Tra Sau Khi Thay Đổi

Chạy các kiểm tra tối thiểu:

```powershell
python -m compileall src streamlit_app.py
$env:PYTHONPATH="src"; python -c "import src.backend.app; import src.app; print('backend ok')"
$env:PYTHONPATH="src"; python -c "from pipeline import AudiobookPipeline, PipelineConfig; print('pipeline ok')"
$env:PYTHONPATH="src"; pytest tests/test_text_cleaning.py
```

Kiểm notebook entrypoints:

```powershell
rg -n "src\\.backend\\.app:app|src/frontend/streamlit_app.py|src\\.app:app|streamlit run streamlit_app.py" scripts/colab_runner.ipynb
```
