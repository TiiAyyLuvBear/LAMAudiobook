# Audiobook AI Service

Audiobook AI Service là hệ thống sinh audiobook từ sách điện tử bằng pipeline nhiều agent. Luồng demo chính hiện tại:

```text
Streamlit frontend -> FastAPI backend -> SQLite job queue
-> Audiobook pipeline -> TTS -> audio + EPUB3 chapter artifacts
```

Đầu ra gồm file audio tổng (`mp3` hoặc `wav`) và các artifact EPUB3 theo chương, trong đó mỗi câu/segment có audio riêng để nghe trong trình đọc hỗ trợ EPUB3.
Mỗi job cũng ghi debug outputs theo stage vào `storage/jobs/{job_id}/outputs/` để quan sát dữ liệu các agent tạo ra trong pipeline.

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
# Bật giao diện debug khi cần xem model/log chi tiết:
streamlit run src/frontend/streamlit_app.py --server.port 8501 -- -debug
```

Mở `http://localhost:8501`, upload EPUB, đợi job hoàn tất rồi tải audio hoặc EPUB3 chapter artifact.

### Share Web Qua Cloudflare

Nếu muốn gửi web cho đồng đội test nhanh, cài `cloudflared` rồi chạy script:

```powershell
winget install --id Cloudflare.cloudflared
.\scripts\share_cloudflare.ps1
```

Script sẽ khởi động FastAPI/Streamlit local nếu cần và mở Cloudflare quick tunnel cho Streamlit. Gửi URL `https://...trycloudflare.com` mà script in ra cho đồng đội; giữ terminal chạy script mở cho tới khi muốn dừng chia sẻ.

### Local CPU Với VieNeu

Nếu muốn kiểm tra TTS thật bằng CPU, cấu hình `.env` hoặc biến môi trường:

```env
TTS_ENGINE=vieneu
TTS_DEVICE=cpu
VIENEU_DEVICE=cpu
VIENEU_MODEL_NAME=pnnbao-ump/VieNeu-TTS-v2
VIENEU_LORA_ADAPTER=
VIENEU_MODE=standard
VIENEU_EMOTION=storytelling
VIENEU_ENABLE_VOICE_CLONING=0
```

Nếu dùng LoRA finetune, giữ `VIENEU_MODEL_NAME` là VieNeu base PyTorch model và đặt adapter vào `VIENEU_LORA_ADAPTER`, ví dụ:

```env
VIENEU_MODEL_NAME=pnnbao-ump/VieNeu-TTS-v2
VIENEU_LORA_ADAPTER=anyu205/VieNeu-TTS-v2-lora
```

LoRA adapter không chạy với GGUF; nếu muốn chạy GGUF trên CPU thì cần merge/export model hoàn chỉnh trước.

### Chọn Requirements Theo TTS Engine

`requirements.txt` chỉ chứa dependency chung cho API/UI/pipeline và đủ để chạy `TTS_ENGINE=mock`. Hai engine thật cần profile riêng vì chúng cần version `transformers`/`tokenizers` khác nhau:

```powershell
# XTTS GPU
pip install -U -r requirements-xtts.txt
$env:TTS_ENGINE="xtts_gpu"

# VieNeu preset voices
pip install -U -r requirements-vieneu.txt
$env:TTS_ENGINE="vieneu"

# VieNeu voice cloning, when switching from XTTS in the same .venv
pip uninstall -y gruut gruut-ipa gruut-lang-de gruut-lang-en gruut-lang-es gruut-lang-fr
$env:VIENEU_ENABLE_VOICE_CLONING="1"
$env:VIENEU_CODEC_REPO="neuphonic/neucodec"
```

Không cài chồng requirements của XTTS runtime repo bằng lệnh riêng. App chỉ nên clone runtime repo; dependency XTTS phải lấy từ `requirements-xtts.txt`. Mặc định `XTTS_AUTO_INSTALL_REQUIREMENTS=0` để tránh runtime repo kéo `numpy==1.22.0` trên Python 3.10 và làm lệch SciPy/Streamlit. Nếu đổi engine trong cùng một `.venv`, hãy chạy lại đúng file requirements của engine mới rồi restart backend/frontend. Với VieNeu voice cloning, `vieneu[gpu]` kéo `neucodec` và cần `numpy>=2`; nếu trước đó đã cài XTTS, gỡ nhóm `gruut*` như lệnh trên để `pip check` sạch. Khi quay lại XTTS, `requirements-xtts.txt` sẽ cài lại `gruut` và đưa `numpy` về `<2`. Conflict đã xác nhận:

- XTTS cần `transformers<4.50` vì XTTS `GPT2InferenceModel` còn phụ thuộc `generate()`.
- VieNeu/Qwen3 cần `transformers>=4.51` để nhận `model_type=qwen3`.
- VieNeu voice cloning cần `neuphonic/neucodec`, không dùng `neuphonic/neucodec-onnx-decoder-int8` vì ONNX decoder chỉ phù hợp preset voices.

System dependency chung cho audio/codec:

```bash
apt-get install -y ffmpeg
```

VieNeu trên Linux có thể cần thêm `espeak-ng` tùy backend/phonemizer:

```bash
apt-get install -y espeak-ng
```

Khi chưa cài `ffmpeg`, trong Streamlit nên chọn:

- Định dạng âm thanh: `wav`
- Tắt `Chuẩn hóa âm lượng`

EPUB3 theo chương và EPUB3 tổng vẫn được tạo từ các audio segment đã sinh. File audio tổng cũng tạo được ở dạng WAV nếu không bật normalize.

### Normalize Audio

Tùy chọn `Chuẩn hóa âm lượng` chạy hậu xử lý bằng `ffmpeg` sau khi TTS đã sinh xong các file WAV segment. Pipeline sẽ ghép segment thành `audiobook_concat.wav`, chuẩn hóa âm lượng, rồi xuất file cuối theo định dạng đã chọn.

Mục đích là làm âm lượng giữa các đoạn/chương đều hơn. Nếu bật normalize hoặc chọn xuất `mp3`, máy local phải có `ffmpeg`/`ffprobe` trong `PATH`; nếu thiếu, job có thể fail ở bước audio finalization với lỗi `ffmpeg not found`.

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
