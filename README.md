# Audiobook AI Service

Multiagent audiobook runtime:

`Streamlit UI -> FastAPI API -> SQLite job queue -> Audiobook pipeline -> audio download`

V1 outputs `mp3` or `wav` audio files. EPUB3 audiobook packaging is left for a later phase.

## Quick Start

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

For local smoke tests without GPU:

```powershell
$env:TTS_ENGINE="mock"
```

For production XTTS, keep the default:

```powershell
$env:TTS_ENGINE="xtts_gpu"
```

`xtts_gpu` fails clearly if CUDA, Coqui TTS, or a reference voice file is missing. Mock audio is only used when `TTS_ENGINE=mock`.

The default production model is the uploaded Hugging Face repo `aiMy144/XTTSv2VietAudiobook`.
Override it by setting `XTTS_MODEL_NAME_OR_PATH`:

```env
TTS_ENGINE=xtts_gpu
XTTS_MODEL_NAME_OR_PATH=aiMy144/XTTSv2VietAudiobook
XTTS_VOICE_DIR=data/voice_samples
```

For a local model folder:

```env
XTTS_MODEL_NAME_OR_PATH=models/model
```

The folder should contain at least `config.json` and a checkpoint such as `model.pth` or `best_model*.pth`. If the checkpoint is managed by DVC, run `dvc pull` first or point `XTTS_MODEL_NAME_OR_PATH` directly to the downloaded `.pth`.

Start the API:

```powershell
uvicorn src.app:app --host 0.0.0.0 --port 8000
```

Start the UI:

```powershell
streamlit run streamlit_app.py --server.port 8501
```

## Environment

Create or update `.env`:

```env
API_BASE_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
STORAGE_DIR=./storage
MAX_UPLOAD_MB=200
MAX_CONCURRENT_JOBS=1
TTS_ENGINE=xtts_gpu
XTTS_MODEL_NAME_OR_PATH=aiMy144/XTTSv2VietAudiobook
XTTS_CONFIG_PATH=
XTTS_VOCAB_PATH=
XTTS_VOICE_DIR=data/voice_samples
HF_TOKEN=
```

## API

- `POST /api/v1/audiobook/jobs` uploads an EPUB and returns `job_id`.
- `GET /api/v1/audiobook/jobs/{job_id}` returns status, progress, stage, chapter counters, errors, and recent logs.
- `GET /api/v1/audiobook/jobs/{job_id}/download` downloads the completed audio file.
- `DELETE /api/v1/audiobook/jobs/{job_id}` cancels pending jobs.
- `GET /health` checks service health and queue stats.

Each job is stored under:

```text
storage/jobs/{job_id}/input/book.epub
storage/jobs/{job_id}/output/audiobook.mp3
storage/jobs/{job_id}/metadata.json
storage/jobs/{job_id}/logs/logs.txt
```

Job metadata is persisted in `storage/jobs.sqlite`.

## Cloudflare Tunnel

Typical public routing:

```text
audiobook.example.com     -> http://localhost:8501
api-audiobook.example.com -> http://localhost:8000
```

Set:

```env
API_BASE_URL=https://api-audiobook.example.com
CORS_ORIGINS=https://audiobook.example.com
```

## Colab GPU Runner

Use [scripts/colab_runner.ipynb](scripts/colab_runner.ipynb) when you want Colab GPU for XTTS.

The notebook:

- checks CUDA/GPU,
- installs runtime dependencies and `ffmpeg`,
- installs Coqui `TTS`,
- downloads the fine-tuned XTTSv2 model from `aiMy144/XTTSv2VietAudiobook`,
- starts FastAPI on port `8000`,
- creates a Cloudflare quick tunnel for the API,
- starts Streamlit on port `8501`,
- creates a second Cloudflare quick tunnel for the UI.

Open the Streamlit tunnel URL printed by the final setup cell, upload an EPUB, and download the completed audio.

Coqui TTS/XTTS is sensitive to Python version. If Colab is on Python 3.12 and `pip install TTS==0.22.0` fails, use a Python 3.10/3.11 GPU runtime or a GPU VM instead.
