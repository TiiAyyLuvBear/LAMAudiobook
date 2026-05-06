"""
Audiobook Generation System — Full Pipeline Streamlit App
EPUB → Parse → Clean → Summarize → Classify → Voice → TTS → QC → Audio
"""
from __future__ import annotations

import io
import os
import sys
import re
import time
import logging
import tempfile
import asyncio
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from collections import deque, Counter

# ── Path setup ──────────────────────────────────────────────────────────────
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import streamlit as st

# ── Constants ────────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB = 100
OUTPUT_DIR = "temp_output"

# ── Logging buffer ───────────────────────────────────────────────────────────
class _StreamlitLogHandler(logging.Handler):
    def __init__(self, buf: deque, max_lines: int = 300):
        super().__init__()
        self.buf = buf
        self.max_lines = max_lines

    def emit(self, record: logging.LogRecord):
        self.buf.append(self.format(record))
        if len(self.buf) > self.max_lines:
            self.buf.popleft()


def _attach_log_handler(buf: deque) -> _StreamlitLogHandler:
    handler = _StreamlitLogHandler(buf)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", "%H:%M:%S"))
    handler.setLevel(logging.INFO)
    for name in ("", "agents.summarizer", "agents.classifier", "pipeline.audiobook"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        if not any(isinstance(h, _StreamlitLogHandler) for h in lg.handlers):
            lg.addHandler(handler)
    return handler


# ── EPUB helpers ─────────────────────────────────────────────────────────────
def _inspect_epub(data: bytes) -> dict:
    stats = {"entries": 0, "chapter_like_files": 0, "has_opf": False}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        stats["entries"] = len(names)
        stats["chapter_like_files"] = sum(1 for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
        stats["has_opf"] = any(n.lower().endswith(".opf") for n in names)
    return stats


# ── CSS ──────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    min-height: 100vh;
}

/* Main header */
.hero-title {
    text-align: center;
    padding: 2rem 0 1rem;
    background: linear-gradient(90deg, #a78bfa, #818cf8, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.8rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.hero-subtitle {
    text-align: center;
    color: #94a3b8;
    font-size: 1.1rem;
    margin-bottom: 2rem;
}

/* Pipeline stage cards */
.pipeline-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
    backdrop-filter: blur(10px);
    transition: all 0.3s ease;
}

.pipeline-card.active {
    border-color: #818cf8;
    background: rgba(129,140,248,0.1);
    box-shadow: 0 0 20px rgba(129,140,248,0.2);
}

.pipeline-card.done {
    border-color: #34d399;
    background: rgba(52,211,153,0.08);
}

/* Stage badge */
.stage-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.badge-active { background: rgba(129,140,248,0.3); color: #818cf8; }
.badge-done   { background: rgba(52,211,153,0.3);  color: #34d399; }
.badge-wait   { background: rgba(100,116,139,0.3); color: #94a3b8; }

/* Metric cards */
.metric-glass {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px;
    padding: 1rem;
    text-align: center;
    backdrop-filter: blur(8px);
}

.metric-glass .value {
    font-size: 1.8rem;
    font-weight: 700;
    background: linear-gradient(90deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.metric-glass .label {
    color: #94a3b8;
    font-size: 0.85rem;
    margin-top: 2px;
}

/* Sidebar */
.css-1d391kg, [data-testid="stSidebar"] {
    background: rgba(15,12,41,0.9) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}

/* Upload zone */
[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.04);
    border-radius: 12px;
    border: 2px dashed rgba(129,140,248,0.4);
    padding: 1rem;
}

/* Progress bar */
.stProgress > div > div {
    background: linear-gradient(90deg, #818cf8, #60a5fa) !important;
}

/* Buttons */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #818cf8, #60a5fa) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.3s ease !important;
}

.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(129,140,248,0.4) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
    padding: 4px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 6px;
    color: #94a3b8;
}

.stTabs [aria-selected="true"] {
    background: rgba(129,140,248,0.2) !important;
    color: #a78bfa !important;
}

/* Table */
[data-testid="stTable"] {
    border-radius: 8px;
    overflow: hidden;
}

/* Expander */
.streamlit-expanderHeader {
    background: rgba(255,255,255,0.04) !important;
    border-radius: 8px !important;
}
</style>
"""

# ── Pipeline stage definitions ───────────────────────────────────────────────
PIPELINE_STAGES = [
    ("🔍", "Parse",     "Trích xuất text từ EPUB"),
    ("🧹", "Clean",     "Làm sạch & phân chương"),
    ("📝", "Summarize", "Tóm tắt & trích xuất thực thể"),
    ("🎭", "Classify",  "Phân loại cảm xúc & thoại"),
    ("🎙️", "Voice",     "Gán giọng đọc cho nhân vật"),
    ("🔊", "TTS",       "Tổng hợp giọng nói"),
    ("✅", "QC",        "Kiểm tra chất lượng audio"),
    ("🎵", "Finalize",  "Ghép & chuẩn hoá audio"),
]

STAGE_MAP = {
    "planning": 0, "parsing": 0, "cleaning": 1,
    "analyzing": 3, "generating": 5, "finalizing": 7, "completed": 8,
}


def render_pipeline_stages(current_stage: str, progress: float):
    stage_idx = STAGE_MAP.get(current_stage, -1)
    cols = st.columns(len(PIPELINE_STAGES))
    for i, (icon, name, desc) in enumerate(PIPELINE_STAGES):
        with cols[i]:
            if i < stage_idx:
                st.markdown(f'<div style="text-align:center;color:#34d399;font-size:1.4rem">{icon}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;font-size:0.7rem;color:#34d399;font-weight:600">{name}</div>', unsafe_allow_html=True)
            elif i == stage_idx:
                st.markdown(f'<div style="text-align:center;font-size:1.4rem;animation:pulse 1s infinite">{icon}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;font-size:0.7rem;color:#818cf8;font-weight:700">{name}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="text-align:center;color:#475569;font-size:1.4rem">{icon}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;font-size:0.7rem;color:#475569">{name}</div>', unsafe_allow_html=True)


# ── Results display ───────────────────────────────────────────────────────────
def render_analysis_results(result: dict, duration: float):
    class_res = result["classify"]
    ctx = result["summarize"]
    chapters = result.get("chapters", [])

    st.success("✅ Pipeline hoàn tất!")

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎭 Mood chủ đạo", getattr(class_res, "mood", "N/A"))
    m2.metric("💬 Tỉ lệ thoại", f"{getattr(class_res, 'dialogue_ratio', 0):.1%}")
    m3.metric("📚 Số chương", result.get("chapter_count", "N/A"))
    m4.metric("⏱ Thời gian", f"{duration:.1f}s")

    voice_style = getattr(class_res, "recommended_voice_style", None)
    if voice_style:
        st.info(f"🎙️ **Phong cách giọng đọc đề xuất:** {voice_style}")

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Tổng quan", "📚 Chương", "🔍 Câu văn", "🏷️ Thực thể"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Tóm tắt tác phẩm:**")
            st.info(ctx.summary if ctx.summary else "_(Chưa có)_")
        with c2:
            sentences = getattr(class_res, "sentences", [])
            if sentences:
                emotions = [s["emotion"] for s in sentences]
                emo_counts = Counter(emotions)
                total = len(sentences)
                st.write("**Phân bổ cảm xúc:**")
                for emo, cnt in emo_counts.most_common(6):
                    pct = cnt / total
                    st.progress(pct, text=f"{emo}: {pct:.1%}")

    with tab2:
        chapter_summaries = getattr(ctx, "chapter_summaries", [])
        if chapter_summaries:
            for i, ch_sum in enumerate(chapter_summaries):
                ch_title = chapters[i].title if i < len(chapters) else f"Chương {i+1}"
                with st.expander(f"📖 {ch_title}"):
                    st.write(ch_sum or "_Không có nội dung._")
        else:
            st.info("Không có tóm tắt chương.")

    with tab3:
        sentences = getattr(class_res, "sentences", [])
        if sentences:
            sent_data = []
            for s in sentences[:50]:
                sent_data.append({
                    "Câu văn": (s["text"][:90] + "…") if len(s["text"]) > 90 else s["text"],
                    "Loại": "💬 Thoại" if s["type"] == "dialogue" else "📖 Kể",
                    "Cảm xúc": s["emotion"],
                    "Nhân vật": s["speaker"],
                })
            st.dataframe(sent_data, use_container_width=True)
        else:
            st.info("Không có dữ liệu phân loại.")

    with tab4:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Nhân vật / Thực thể:**")
            for e in (ctx.entities or []):
                st.markdown(f"- 👤 {e}")
        with c2:
            st.write("**Từ khóa:**")
            for kw in (ctx.keywords[:10] if ctx.keywords else []):
                st.markdown(f"- 🔑 {kw}")


def render_audio_results(result: dict, output_dir: str):
    """Show audio download if TTS completed."""
    audio_path = result.get("output_path")
    if audio_path and Path(audio_path).exists():
        st.subheader("🎵 Audio Output")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        st.audio(audio_bytes, format="audio/wav")
        st.download_button(
            label="⬇️ Tải xuống Audiobook",
            data=audio_bytes,
            file_name=Path(audio_path).name,
            mime="audio/wav",
            use_container_width=True,
        )
        duration = result.get("duration", 0)
        if duration:
            st.caption(f"⏱ Tổng thời lượng: {duration:.1f}s")
    else:
        st.info("ℹ️ TTS đang dùng Mock engine — audio stub được tạo nhưng không có nội dung thật. Cần GPU + XTTSv2 để tạo audio thật.")


# ── Main app ─────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="AudioBook AI – Pipeline",
        page_icon="🎧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero-title">🎧 AudioBook AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">Pipeline Agentic: EPUB → Phân tích → TTS → Audio</div>', unsafe_allow_html=True)

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚙️ Cấu hình Pipeline")

        st.markdown("### 🎛️ Giai đoạn chạy")
        run_full = st.radio(
            "Chế độ",
            ["🔬 Phân tích (Phase 1-2)", "🚀 Full Pipeline (Phase 1-4)"],
            index=0,
            help="Phase 1-2: Parse+Clean+Summarize+Classify+Voice (nhanh). Full: bao gồm TTS+Audio (cần GPU hoặc dùng Mock).",
        )
        full_pipeline = "Full" in run_full

        st.markdown("### 🔊 Cài đặt Audio")
        normalize_audio = st.checkbox("Chuẩn hoá âm lượng (loudnorm)", value=True)
        add_chapters = st.checkbox("Thêm chapter markers", value=True)
        output_format = st.selectbox("Định dạng output", ["wav", "mp3"], index=0)

        st.markdown("### 🤖 TTS Engine")
        tts_mode = st.radio("Engine", ["🧪 Mock (Stub, nhanh)", "🎙️ Real XTTS (cần GPU)"], index=0)
        use_real_tts = "Real" in tts_mode

        st.divider()
        st.markdown("### 📋 Pipeline Flow")
        for icon, name, desc in PIPELINE_STAGES:
            st.markdown(f"**{icon} {name}** — _{desc}_")

        st.divider()
        st.caption("CSC15012 – Audiobook Generation System")

    # ── Upload ───────────────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "📂 Tải lên file EPUB (tiếng Việt)",
        type=["epub"],
        help=f"Tối đa {MAX_FILE_SIZE_MB} MB. Chỉ hỗ trợ EPUB tiếng Việt.",
    )

    if not uploaded:
        st.markdown("---")
        st.markdown(
            """
            <div style="text-align:center;padding:3rem;color:#475569">
                <div style="font-size:4rem">📖</div>
                <div style="font-size:1.2rem;margin-top:1rem">Tải lên file EPUB để bắt đầu</div>
                <div style="font-size:0.9rem;margin-top:0.5rem">Pipeline sẽ tự động Parse → Clean → Summarize → Classify → Voice → TTS → Audio</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # File info
    file_bytes = uploaded.getvalue()
    file_mb = len(file_bytes) / 1024 / 1024

    if file_mb > MAX_FILE_SIZE_MB:
        st.error(f"❌ File quá lớn ({file_mb:.1f} MB). Giới hạn {MAX_FILE_SIZE_MB} MB.")
        return

    col_info, col_btn = st.columns([3, 1])
    with col_info:
        try:
            stats = _inspect_epub(file_bytes)
            st.info(
                f"📘 **{uploaded.name}** — {file_mb:.2f} MB | "
                f"{stats['chapter_like_files']} file nội dung | "
                f"{'✅ Có OPF' if stats['has_opf'] else '⚠️ Không có OPF'}"
            )
        except Exception:
            st.info(f"📘 **{uploaded.name}** — {file_mb:.2f} MB")

    with col_btn:
        run_btn = st.button("🚀 Chạy Pipeline", type="primary", use_container_width=True)

    if not run_btn:
        return

    # ── Run pipeline ─────────────────────────────────────────────────────────
    # Write temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Import pipeline
        try:
            from pipeline import AudiobookPipeline
            from pipeline.config import PipelineConfig
        except ImportError as e:
            st.error(f"❌ Không import được pipeline: {e}")
            return

        # Import TTS engine
        try:
            from utils.tts_engine import RealXTTSEngine, MockXTTSEngine
            tts_engine = RealXTTSEngine(voice_dir="data/voice_samples") if use_real_tts else MockXTTSEngine()
        except Exception:
            from utils.tts_engine import MockXTTSEngine
            tts_engine = MockXTTSEngine()

        config = PipelineConfig(
            input_file=tmp_path,
            output_dir=OUTPUT_DIR,
            output_format=output_format,
            normalize_audio=normalize_audio,
            add_chapters=add_chapters,
        )
        pipeline = AudiobookPipeline(config)
        # Override TTS engine
        pipeline.tts.engine = tts_engine

        # Log buffer
        log_buf: deque = deque()
        _attach_log_handler(log_buf)

        # UI placeholders
        st.markdown("---")
        st.markdown("### 🔄 Đang xử lý…")
        stage_container = st.empty()
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        log_exp = st.expander("📜 Log chi tiết", expanded=False)
        log_placeholder = log_exp.empty()

        def _refresh_ui(state_dict: dict):
            stage = state_dict.get("stage", "")
            progress = min(1.0, state_dict.get("progress", 0.0))
            msg = state_dict.get("status_message", "")
            curr_ch = state_dict.get("current_chapter", 0)
            total_ch = state_dict.get("total_chapters", 0)

            progress_bar.progress(progress)
            with stage_container.container():
                render_pipeline_stages(stage, progress)

            status_md = f"**Giai đoạn:** `{stage.upper()}`"
            if msg:
                status_md += f" — {msg}"
            if total_ch > 0:
                status_md += f" | Chương {curr_ch}/{total_ch}"
            status_text.markdown(status_md)

            if log_buf:
                log_placeholder.code("\n".join(log_buf), language="")

        # Async polling runner
        async def run_with_poll():
            if full_pipeline:
                task = asyncio.create_task(pipeline.run())
            else:
                task = asyncio.create_task(pipeline.run_analysis())

            while not task.done():
                _refresh_ui(pipeline.state.to_dict())
                await asyncio.sleep(0.25)

            _refresh_ui(pipeline.state.to_dict())
            if log_buf:
                log_placeholder.code("\n".join(log_buf), language="")
            return await task

        start_time = time.time()
        result = asyncio.run(run_with_poll())
        elapsed = time.time() - start_time

        progress_bar.progress(1.0)
        status_text.empty()

        if not result.get("success"):
            err = result.get("error", "")
            if "LANGUAGE_ERROR:" in str(err):
                lang = str(err).split("LANGUAGE_ERROR:")[-1].strip()
                st.error(f"🚫 Tệp EPUB được phát hiện là **{lang}**. Hệ thống chỉ hỗ trợ tiếng Việt.")
            else:
                st.error(f"❌ Pipeline thất bại: {err}")
            return

        st.markdown("---")
        st.markdown("### 🎯 Kết quả")

        if full_pipeline:
            # Show analysis + audio
            col_l, col_r = st.columns([3, 2])
            with col_l:
                render_analysis_results(result, elapsed)
            with col_r:
                render_audio_results(result, OUTPUT_DIR)
        else:
            render_analysis_results(result, elapsed)

            # Show prompt to run full
            st.divider()
            st.info(
                "💡 Đây là kết quả Phase 1-2 (Phân tích). "
                "Chọn **Full Pipeline** ở sidebar để tiếp tục tổng hợp TTS → Audio."
            )

    except Exception as e:
        import traceback
        st.error(f"❌ Lỗi không mong đợi: {e}")
        st.code(traceback.format_exc())
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
