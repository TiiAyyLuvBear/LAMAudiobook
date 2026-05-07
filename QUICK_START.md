# Quick Start

Install dependencies:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Run locally with mock TTS:

```powershell
$env:TTS_ENGINE="mock"
uvicorn src.app:app --host 0.0.0.0 --port 8000
```

In another terminal:

```powershell
$env:API_BASE_URL="http://localhost:8000"
streamlit run streamlit_app.py --server.port 8501
```

Open `http://localhost:8501`, upload an EPUB, and wait for the queued job to complete.

For production GPU XTTS:

```powershell
$env:TTS_ENGINE="xtts_gpu"
$env:XTTS_MODEL_NAME_OR_PATH="aiMy144/XTTSv2VietAudiobook"
```

The service expects CUDA, Coqui TTS, and reference WAV files in `data/voice_samples`.

For a local checkpoint folder:

```powershell
$env:XTTS_MODEL_NAME_OR_PATH="models/model"
```

That folder needs `config.json` plus a `.pth` checkpoint. If the weight is still a DVC pointer, run `dvc pull` first.
