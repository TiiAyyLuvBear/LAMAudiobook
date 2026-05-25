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
pip install -U -r requirements-xtts.txt
$env:TTS_ENGINE="xtts_gpu"
$env:XTTS_MODEL_NAME_OR_PATH="aiMy144/XTTSv2VietAudiobook"
$env:XTTS_RUNTIME_DIR="models/XTTSv2-Finetuning-for-New-Languages"
$env:XTTS_VOICE_DIR="data/voice_samples"
```

XTTS cần CUDA, runtime XTTS theo `models/XTTSv2.ipynb`, checkpoint/config/vocab hợp lệ và ít nhất một reference WAV trong `data/voice_samples`.

## Production VieNeu

```powershell
pip install -U -r requirements-vieneu.txt
$env:TTS_ENGINE="vieneu"
$env:VIENEU_MODEL_NAME="pnnbao-ump/VieNeu-TTS-0.3B"
$env:VIENEU_MODE="standard"
$env:VIENEU_DEVICE="auto"

# Nếu bật voice cloning và vừa chuyển từ XTTS trong cùng .venv
pip uninstall -y gruut gruut-ipa gruut-lang-de gruut-lang-en gruut-lang-es gruut-lang-fr
$env:VIENEU_ENABLE_VOICE_CLONING="1"
$env:VIENEU_CODEC_REPO="neuphonic/neucodec"
```

XTTS và VieNeu cần profile requirements riêng vì conflict `transformers`/`tokenizers`: XTTS dùng `transformers<4.50`, VieNeu/Qwen3 dùng `transformers>=4.51`. VieNeu voice cloning dùng `vieneu[gpu]`/`neucodec` và `numpy>=2`, còn XTTS cài `gruut` cần `numpy<2`; nếu đổi engine trong cùng `.venv`, chạy đúng profile, gỡ `gruut*` khi sang VieNeu voice cloning, rồi restart backend/frontend.

Chi tiết từng component nằm ở [docs/COMPONENTS.md](docs/COMPONENTS.md).
