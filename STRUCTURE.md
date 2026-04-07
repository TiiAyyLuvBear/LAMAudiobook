# Project Structure

This repository contains **three separate applications**:

1. **Audiobook Generation System** (Agentic AI)
2. **News Portal** (Web application)
3. **TTS Model Training** (ML training code)

---

## 📁 Structure Overview

```
project_root/
├── configs/              # Configuration files
├── data/                 # Data storage
├── models/               # Trained TTS models
├── tests/                # Test files
├── instructions.md       # Agentic system design document
└── src/
    ├── main.py                      # 🎧 AUDIOBOOK: CLI entry point
    │
    ├── agents/                      # 🎧 AUDIOBOOK: Agent implementations
    │   ├── base.py                  # BaseAgent class
    │   ├── planner/                 # Decides OCR, speaker mode, emotion
    │   ├── document/                # Parser, Cleaner, Chapter detector
    │   │   ├── parser/
    │   │   ├── cleaner/
    │   │   └── chapter_detector/
    │   ├── understanding/           # Narrative and Dialogue analysis
    │   │   ├── narrative/
    │   │   └── dialogue/
    │   ├── audio/                   # Audio generation and processing
    │   │   ├── voice_planner/
    │   │   ├── tts_generator/       # ⚠️ TTS calls happen HERE
    │   │   └── post_processing/
    │   ├── qc/                      # Quality control
    │   └── memory/                  # Speaker consistency
    │
    ├── workflows/                   # 🎧 AUDIOBOOK: Pipeline orchestration
    │   └── audiobook_pipeline.py    # Main workflow (calls all agents)
    │
    ├── services/                    # 🎧 AUDIOBOOK: Infrastructure services
    │   ├── storage/                 # File persistence
    │   ├── queue/                   # Job queue management
    │   └── logging/                 # Centralized logging
    │
    ├── api/                         # 🎧 AUDIOBOOK: API layer
    │   └── routes.py                # HTTP endpoints (NO business logic)
    │
    ├── utils/                       # 🎧 AUDIOBOOK: Shared utilities
    │   ├── text_utils.py
    │   ├── audio_utils.py
    │   └── file_utils.py
    │
    ├── ml_training/                 # 🧠 TTS MODEL TRAINING
    │   ├── model.py                 # TTS model architecture
    │   ├── train.py                 # Training script
    │   ├── preprocessing.py         # Data preprocessing
    │   ├── inference.py             # Model inference
    │   └── utils.py                 # Training utilities
    │
    ├── backend/                     # 📰 NEWS PORTAL: Backend
    │   ├── app.py                   # FastAPI application
    │   ├── models/                  # Database models
    │   ├── services/                # Business logic
    │   ├── routes/                  # API routes
    │   ├── controllers/             # Controllers
    │   ├── schemas/                 # Pydantic schemas
    │   └── seed_database.py         # Database seeding
    │
    └── frontend/                    # 📰 NEWS PORTAL: Frontend (React/Vue)
```

---

## 🎧 Audiobook System (Agentic AI)

### Design Principles

1. **Agents ≠ API**: Agents are internal execution units, API only accepts requests
2. **Organize by capability**: Not by function or endpoint
3. **Centralized orchestration**: Only workflows call agents, agents never call each other
4. **Clear I/O**: Each agent has `.run()` method with defined input/output

### Pipeline Flow

```
Planner → Parser → Cleaner → Chapter Detector → 
Narrative Analyzer → Dialogue Analyzer → Voice Planner → 
TTS Generator → QC → (Retry) → Post-processing
```

### Key Rules

- ✅ Only workflow calls agents
- ✅ Agents never call each other directly
- ✅ API layer has NO business logic
- ✅ TTS calls are in `agents/audio/tts_generator/` (NOT in API)
- ✅ Agents are modular and swappable

### Usage

```bash
# CLI usage
python -m src.main --input book.pdf --output ./output --format mp3

# API usage
# Start API server first, then:
POST /api/v1/audiobook/generate
GET /api/v1/audiobook/job/{job_id}
```

---

## 📰 News Portal

Web application for news management with FastAPI backend and React/Vue frontend.

### Running the News Portal

```bash
# Backend
cd src
python backend/app.py

# Frontend
cd src/frontend
npm install
npm run dev
```

---

## 🧠 TTS Model Training

Contains model training code for text-to-speech models.

### Training a Model

```bash
cd src/ml_training
python train.py --config path/to/config.yaml
```

---

## 📋 Success Criteria (from instructions.md)

- ✅ End-to-end pipeline works
- ✅ Agents are modular
- ✅ Easy to swap models
- ✅ No large monolithic scripts
- ✅ No agent-to-agent calls
- ✅ Workflow orchestration exists
- ✅ TTS in correct module

---

## 🔍 Checklist

- ✅ No large script files
- ✅ No agent-to-agent calls
- ✅ Centralized workflow exists
- ✅ TTS in correct module (`agents/audio/tts_generator/`)
- ✅ API has no business logic
- ✅ Clear separation of concerns

---

## 📚 Documentation

- `instructions.md` - Full agentic system design specification
- `BACKEND_STRUCTURE.md` - News Portal backend documentation
- `QUICK_START.md` - Quick start guide (if exists)

---

## 🚀 Getting Started

See the `instructions.md` file for detailed design principles and implementation guidelines for the Agentic Audiobook System.
