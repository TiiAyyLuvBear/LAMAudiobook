# LAMAudiobook

> AI-powered platform for converting ebooks into audiobooks automatically.

LAMAudiobook là hệ thống chuyển đổi sách điện tử thành audiobook bằng AI.  
Người dùng chỉ cần tải sách lên, hệ thống sẽ tự động:

- Phân tích nội dung
- Chia chương
- Làm sạch văn bản
- Chọn giọng đọc phù hợp
- Sinh giọng nói dựa trên nội dung sách
- Xuất audio và audiobook tích hợp âm thanh

---

## Demo

### Workflow

```text
Upload sách
    ↓
AI phân tích nội dung
    ↓
AI chọn giọng + cảm xúc
    ↓
Tạo audiobook
    ↓
Nghe hoặc tải xuống
```

### Screenshots

TODO: thêm ảnh upload UI

TODO: thêm ảnh theo dõi tiến trình

TODO: thêm ảnh trang kết quả

TODO: thêm GIF/video demo

---

## Tính năng

### Tính năng cốt lõi

Upload sách:

- EPUB
- PDF
- TXT

Kiến trúc đa tác nhân (Multi-agent) tự động:

- Phân tích nội dung
- Chia chương
- Làm sạch dữ liệu
- Tạo audiobook

Hỗ trợ nhiều mô hình Text-to-Speech (TTS):

- XTTSv2 - hỗ trợ tốt trên GPU
- VieNeu - thích hợp triển khai trên CPU/GPU

Đặc trưng giọng nói:

- Cá nhân hóa: Tự chọn giọng đọc phù hợp với nội dung sách bằng cách upload mẫu giọng.
- Đề xuất giọng dựa trên nội dung sách.
- Kiểm soát cảm xúc: Tự động điều chỉnh cảm xúc giọng đọc theo nội dung.

Sản phẩm cuối:

- File âm thanh (định dạng `.mp3`, `wav`)
- Audiobook tích hợp âm thanh (định dạng `.epub3`)

Giao diện trực quan:

- Upload sách và giọng tham chiếu dễ dàng
- Theo dõi trạng thái các cuốn sách được xử lí
- Xem trước được sản phẩm trước khi có Audiobook hoàn chỉnh

---

## Use Cases

### Xuất bản

Tự động tạo audiobook cho nhà xuất bản, hỗ trợ cho việc fast-production, giảm thiểu chi phí vận hành.

### Giáo dục

Chuyển giáo trình thành audiobook.

### Khả năng tiếp cận

Hỗ trợ người khiếm thị hoặc khó đọc văn bản.

### Sử dụng cá nhân

Nghe sách thay vì đọc.

### Tích hợp vào các platform EPUB

Tích hợp như một AI microservice vào hệ thống đọc sách.

---

## Kiến trúc hệ thống

### Quy trình nghiệp vụ

```text
Frontend
    ↓
Backend API
    ↓
Job Queue
    ↓
Audiobook Pipeline
    ↓
AI Agents
    ↓
TTS Engine
    ↓
Audio + EPUB3
```

### Kiến trúc kỹ thuật

```text
Streamlit frontend
        ↓

FastAPI backend
        ↓

SQLite Queue
        ↓

Pipeline Orchestrator
        ↓

Agents

├── Parser
├── Text Cleaner
├── Mood Detection
├── Voice Selection
├── TTS
├── Quality Control
└── Audio Finalizer

        ↓

Output Storage
```

---

## Cấu trúc hệ thống

```text
src/

├── backend/          
│   └── FastAPI application
│
├── frontend/         
│   └── Streamlit UI
│
├── api/              
│   └── HTTP routes
│
├── pipeline/         
│   └── Pipeline orchestration
│
├── agents/           
│   ├── Parser
│   ├── Cleaner
│   ├── Summarizer
│   ├── Classifier
│   ├── Voice
│   ├── TTS
│   └── QC
│
├── schema/           
│   └── Shared models
│
├── services/         
│   └── Queue + Storage
│
├── utils/            
│   └── Audio/EPUB helpers
│
└── tts-service/      
    └── Optional TTS microservice

scripts/

data/
```

---

## Khởi động nhanh

### Clone repository

```bash
git clone LAMAudiobook

cd LAMAudiobook
```

### Tạo môi trường ảo

Windows:

```powershell
python -m venv .venv

.\.venv\Scripts\activate
```

Linux:

```bash
python -m venv .venv

source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Run Application

Start backend:

```bash
uvicorn src.backend.app:app --host 0.0.0.0 --port 8000
```

Start frontend:

```bash
streamlit run src/frontend/streamlit_app.py
```

Open:

```text
http://localhost:8501
```

---

## Supported TTS Engines

| Engine | CPU | GPU | Voice Clone |
|----------|------|------|-------------|
| XTTS | ❌ | ✅ | ✅ |
| VieNeu | ✅ | ✅ | ✅ |

---

## Configuration

Environment variables:

```env
TTS_ENGINE=vieneu

TTS_DEVICE=cpu

VIENEU_MODEL_NAME=pnnbao-ump/VieNeu-TTS-v2

VIENEU_MODE=standard

VIENEU_EMOTION=storytelling
```

TODO: thêm toàn bộ danh sách environment variables

---

## Deployment

### Local

Supported:

- Windows
- Linux

### Cloud

Possible deployment:

- Docker
- Vast.ai
- Modal
- RunPod
- AWS
- GCP

TODO: thêm hướng dẫn deployment

TODO: thêm Docker image

TODO: thêm docker-compose

TODO: thêm Kubernetes deployment

---

## API Documentation

TODO: thêm API endpoints

Ví dụ:

### Create Job

```http
POST /jobs
```

### Check Job Status

```http
GET /jobs/{job_id}
```

### Download Result

```http
GET /jobs/{job_id}/download
```

---

## Performance

TODO: benchmark

Ví dụ:

| Input | Duration | Device |
|---------|----------|---------|
| 10 pages | TODO | CPU |
| 50 pages | TODO | T4 |
| 200 pages | TODO | RTX 4080 |

---

## Roadmap

### Current

- [x] EPUB parsing
- [x] TXT parsing
- [x] TTS generation
- [x] Voice selection
- [x] Queue system
- [x] EPUB3 output

### Future

- [ ] PDF production support
- [ ] Multi-language support
- [ ] Voice recommendation model
- [ ] Multi-agent optimization
- [ ] Distributed workers
- [ ] Cloud deployment
- [ ] User authentication
- [ ] User dashboard

---

## Known Limitations

- PDF production workflow chưa hoàn thiện
- XTTS cần GPU CUDA
- ffmpeg phải cài hệ thống
- Một số TTS model có conflict dependency

---

## Troubleshooting

### ffmpeg not found

Linux:

```bash
apt-get install -y ffmpeg
```

Windows:

TODO: thêm hướng dẫn

---

### espeak-ng missing

Linux:

```bash
apt-get install -y espeak-ng
```

---

## Documentation

Xem thêm:

```text
docs/COMPONENTS.md
```

TODO: thêm:

- architecture.md
- deployment.md
- api.md
- training.md

---

## Contributors

TODO

---

## License

TODO
