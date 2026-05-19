# Quick Start

## Local Smoke Test

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:TTS_ENGINE="mock"
uvicorn src.backend.app:app --host 0.0.0.0 --port 8000
```

Terminal khác:

```powershell
$env:API_BASE_URL="http://localhost:8000"
streamlit run src/frontend/streamlit_app.py --server.port 8501
```

Mở `http://localhost:8501`, upload EPUB, đợi job hoàn tất rồi tải audio hoặc EPUB3 chapter artifact.

## Share Web Qua Cloudflare

Cài `cloudflared` một lần nếu máy chưa có:

```powershell
winget install --id Cloudflare.cloudflared
```

Chạy script chia sẻ UI cho đồng đội:

```powershell
.\scripts\share_cloudflare.ps1
```

Script sẽ khởi động FastAPI/Streamlit local nếu cần, mở Cloudflare quick tunnel cho Streamlit, rồi in URL dạng `https://...trycloudflare.com`. Giữ terminal đó mở trong lúc đồng đội dùng web.

## Production XTTS

```powershell
$env:TTS_ENGINE="xtts_gpu"
$env:XTTS_MODEL_NAME_OR_PATH="aiMy144/XTTSv2VietAudiobook"
$env:XTTS_RUNTIME_DIR="models/XTTSv2-Finetuning-for-New-Languages"
$env:XTTS_VOICE_DIR="data/voice_samples"
```

XTTS cần CUDA, runtime XTTS theo `models/XTTSv2.ipynb`, checkpoint/config/vocab hợp lệ và ít nhất một reference WAV trong `data/voice_samples`.

Chi tiết từng component nằm ở [docs/COMPONENTS.md](docs/COMPONENTS.md).
