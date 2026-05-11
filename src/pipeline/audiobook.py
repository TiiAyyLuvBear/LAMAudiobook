"""
Audiobook Pipeline — 4-phase parallel pipeline orchestrator.
"""

import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents import (
    PlannerAgent,
    PlannerInput,
    ParserAgent,
    ParserInput,
    CleanerAgent,
    CleanerInput,
    SplitterAgent,
    SplitterInput,
    ClassifierAgent,
    ClassifierInput,
    VoiceAgent,
    VoiceInput,
    TTSAgent,
    TTSGeneratorInput,
    AudioAgent,
    AudioFinalizeInput,
    QCAgent,
    QCInput,
    MemoryAgent,
    MemoryInput,
    SummarizerAgent,
    SummarizerInput,
)
from schema.audio import TTSSegment, AudioSegment
from schema.pipeline import Chapter
from .config import PipelineConfig, PipelineStage
from .state import StateManager
from .executor import ParallelExecutor


logger = logging.getLogger(__name__)


class AudiobookPipeline:
    """
    Main audiobook generation pipeline with 4-phase execution.

    PHASE 1 — Parse  (sequential): Planner → Parser → Cleaner → Splitter
    PHASE 2 — Analyze (parallel): Classifier + Voice + Memory
    PHASE 3 — Generate (parallel): TTS segment batches
    PHASE 4 — Finalize (sequential): QC → Audio concat
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = StateManager()
        self.executor = ParallelExecutor()

        # Initialize agents
        self.parser = ParserAgent()
        self.cleaner = CleanerAgent()
        self.classifier = ClassifierAgent()
        self.summarizer = SummarizerAgent()
        # self.planner = PlannerAgent()
        self.splitter = SplitterAgent()
        self.voice = VoiceAgent(config={"voice_dir": config.xtts_voice_dir})
        self.tts = TTSAgent(
            config={
                "tts_engine": config.tts_engine,
                "tts_service_url": "http://localhost:8001",
                "xtts_model_name_or_path": config.xtts_model_name_or_path,
                "xtts_config_path": config.xtts_config_path,
                "xtts_vocab_path": config.xtts_vocab_path,
                "xtts_voice_dir": config.xtts_voice_dir,
                "progress_callback": self._on_tts_progress,
            }
        )
        self.audio = AudioAgent()
        self.qc = QCAgent()
        self.memory = MemoryAgent()

    # ─────────────────────────────────────────────
    # PHASE 1: Parse  (sequential)
    # ─────────────────────────────────────────────

    async def _phase1_parse(self) -> Dict[str, Any]:
        """Parser → Cleaner → Summarizer → Classifier (sequential)."""
        self.state.set_stage(PipelineStage.PARSING)

        # Step 1: Parser
        parse_result = await self.executor.execute_single(
            "parser",
            self.parser,
            ParserInput(
                file_path=self.config.input_file,
                file_type=self._get_file_type(),
                needs_ocr=False,
            ),
        )
        if not parse_result.success:
            raise RuntimeError(f"Parser failed: {parse_result.error}")

        parse_data = parse_result.data
        self.state.set_stage(PipelineStage.CLEANING)

        # Step 2: Cleaner
        clean_result = await self.executor.execute_single(
            "cleaner",
            self.cleaner,
            CleanerInput(text_blocks=parse_data.blocks),
        )
        if not clean_result.success:
            raise RuntimeError(f"Cleaner failed: {clean_result.error}")

        clean_data = clean_result.data
        self.state.set_stage(PipelineStage.ANALYZING)

        def _summarizer_status(msg: str, current: int, total: int):
            self.state.set_status(msg)
            self.state.update_chapter(current)
            self.state.set_chapters(total)

        ctx = None
        class_data = None
        if self.config.analysis_enabled:
            # Step 3: Summarizer — chapter-aware mode
            summarize_result = await self.executor.execute_single(
                "summarizer",
                self.summarizer,
                SummarizerInput(
                    text=clean_data.plain_text,
                    chapters=clean_data.chapters,
                    status_callback=_summarizer_status,
                ),
            )
            if not summarize_result.success:
                raise RuntimeError(f"Summarizer failed: {summarize_result.error}")

            ctx = summarize_result.data

            # Step 4: Classifier samples the book for metadata only.
            class_result = await self.executor.execute_single(
                "classifier",
                self.classifier,
                ClassifierInput(
                    context_buffer=ctx,
                    text=clean_data.plain_text,
                    chapters=clean_data.chapters,
                ),
            )
            if not class_result.success:
                raise RuntimeError(f"Classifier failed: {class_result.error}")
            class_data = class_result.data

        return {
            "parse": parse_data,
            "clean": clean_data,
            "summarize": ctx,
            "classify": class_data,
            "plain_text": clean_data.plain_text,
            "chapters": clean_data.chapters,
            "chapter_count": len(clean_data.chapters),
            "metadata": getattr(parse_data, "metadata", {}),
        }

    # ─────────────────────────────────────────────
    # PHASE 2: Analyze  (parallel)
    # ─────────────────────────────────────────────

    async def _phase2_analyze(self, parse_data: Dict[str, Any]) -> Dict[str, Any]:
        """Voice + Memory run concurrently using data from Phase 1."""
        self.state.set_stage(PipelineStage.ANALYZING)
        
        ctx = parse_data["summarize"]
        classifier_data = parse_data["classify"]
        
        # Extract character emotions for VoiceAgent
        char_emotions = {}
        if classifier_data and hasattr(classifier_data, "sentences"):
            for s in classifier_data.sentences:
                spk = s.get("speaker")
                emo = s.get("emotion")
                if spk and emo and spk != "Người kể chuyện":
                    if spk not in char_emotions:
                        char_emotions[spk] = []
                    char_emotions[spk].append(emo)
        
        # Get dominant emotion per character
        from collections import Counter
        for spk in char_emotions:
            char_emotions[spk] = Counter(char_emotions[spk]).most_common(1)[0][0]

        # Step 2: Voice + Memory (parallel)
        results = await self.executor.execute_group(
            agents=[
                ("voice", self.voice),
                ("memory", self.memory),
            ],
            input_data={
                "voice": VoiceInput(
                    speakers=(ctx.entities if ctx else ["narrator"]),
                    speaker_mode="multi",
                    book_summary=(ctx.summary if ctx else ""),
                    book_mood=(getattr(classifier_data, "recommended_voice_style", None) if classifier_data else None) or (ctx.primary_mood if ctx else "neutral"),
                    character_emotions=char_emotions
                ),
                "memory": MemoryInput(action="clear"),
            },
            raise_on_error=False,
        )

        voice_result = results.get("voice")
        memory_result = results.get("memory")

        return {
            "classifier": classifier_data,
            "voice": voice_result.data if voice_result and voice_result.success else None,
            "memory": memory_result.data if memory_result and memory_result.success else None,
            "context": ctx,
        }

    # ─────────────────────────────────────────────
    # PHASE 3: Generate  (parallel)
    # ─────────────────────────────────────────────

    def _on_tts_progress(self, current_segment: int, total_segments: int, chapter_index: int) -> None:
        self.state.set_stage(PipelineStage.GENERATING)
        self.state.set_segments(total_segments)
        self.state.update_segment(current_segment)
        self.state.update_chapter(chapter_index)
        self.state.set_status(
            f"Generating TTS segment {current_segment}/{total_segments} "
            f"(chapter {chapter_index}/{self.state.state.total_chapters or '?'})"
        )
        # Keep stage-level progress between analyzing and finalizing while TTS runs.
        base = 0.72
        span = 0.18
        self.state.set_progress(base + span * (current_segment / max(1, total_segments)))

    def _split_tts_text(self, text: str, max_chars: int = 280) -> List[str]:
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        for sentence in [s.strip() for s in sentences if s.strip()]:
            if current and current_len + len(sentence) + 1 > max_chars:
                chunks.append(" ".join(current))
                current = []
                current_len = 0
            if len(sentence) > max_chars:
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i : i + max_chars].strip())
                continue
            current.append(sentence)
            current_len += len(sentence) + 1
        if current:
            chunks.append(" ".join(current))
        return chunks

    def _build_tts_segments(self, parse_data: Dict[str, Any], analyze_data: Dict[str, Any]) -> List[TTSSegment]:
        voice_data = analyze_data["voice"]
        classifier_data = analyze_data.get("classifier")
        voice_assignments = voice_data.voice_assignments if voice_data else []

        voice_map: Dict[str, str] = {va.speaker: va.voice_id for va in voice_assignments}
        narrator_voice = getattr(voice_data, "narrator_voice", "female_hn_01") if voice_data else "female_hn_01"

        classifier_lookup: Dict[str, Dict[str, Any]] = {}
        if classifier_data and hasattr(classifier_data, "sentences"):
            for sent in classifier_data.sentences:
                text = (sent.get("text") or "").strip()
                if text:
                    classifier_lookup[text] = sent

        segments: List[TTSSegment] = []
        global_index = 0
        for chapter in parse_data.get("chapters") or []:
            chapter_index = int(getattr(chapter, "index", 0)) + 1
            paragraphs = getattr(chapter, "paragraphs", []) or []
            for paragraph in paragraphs:
                for chunk in self._split_tts_text(paragraph):
                    meta = classifier_lookup.get(chunk, {})
                    speaker = meta.get("speaker") or "narrator"
                    segments.append(
                        TTSSegment(
                            text=chunk,
                            voice_id=voice_map.get(speaker, narrator_voice),
                            emotion=meta.get("emotion", "neutral"),
                            intensity=float(meta.get("intensity", 1.0) or 1.0),
                            speed=1.0,
                            chapter_index=chapter_index,
                            segment_index=global_index,
                            speaker=speaker,
                        )
                    )
                    global_index += 1
        return segments

    async def _phase3_generate(self, parse_data: Dict[str, Any], analyze_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build TTS segments from the full cleaned book, then synthesize them."""
        self.state.set_stage(PipelineStage.GENERATING)

        segments = self._build_tts_segments(parse_data, analyze_data)
        if not segments:
            raise RuntimeError("No TTS segments were produced from cleaned text")

        total_chapters = parse_data.get("chapter_count") or max((s.chapter_index for s in segments), default=0)
        self.state.set_chapters(total_chapters)
        self.state.set_segments(len(segments))
        self.state.update_segment(0)
        self.state.update_chapter(segments[0].chapter_index if segments else 0)
        self.state.set_status(f"Preparing TTS for {len(segments)} segments across {total_chapters} chapters")

        tts_result = await self.executor.execute_single(
            "tts",
            self.tts,
            TTSGeneratorInput(segments=segments, output_dir=self.config.output_dir),
        )

        if not tts_result.success:
            raise RuntimeError(f"TTS generation failed: {tts_result.error}")

        return {"tts": tts_result.data, "segments": segments}

    # ─────────────────────────────────────────────
    # PHASE 4: Finalize  (sequential)
    # ─────────────────────────────────────────────

    async def _phase4_finalize(self, gen_data: Dict[str, Any]) -> Dict[str, Any]:
        """QC → Audio concat (sequential)."""
        self.state.set_stage(PipelineStage.FINALIZING)

        tts_data = gen_data["tts"]
        segments = gen_data["segments"]
        audio_segments = (
            tts_data.audio_segments if hasattr(tts_data, "audio_segments") else []
        )

        # Step 4.1: QC
        qc_result = await self.executor.execute_single(
            "qc",
            self.qc,
            QCInput(
                audio_segments=audio_segments,
                text_segments=[s.text for s in segments],
                quality_threshold=0.8,
            ),
        )

        # TODO: retry failed segments if any
        retry_segments = []
        if qc_result.success and qc_result.data:
            qc_out = qc_result.data
            retry_segments = list(getattr(qc_out, "retry_segments", []) or [])

        # Step 4.2: Audio finalization
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        output_path = str(
            Path(self.config.output_dir) / f"audiobook.{self.config.output_format}"
        )

        audio_result = await self.executor.execute_single(
            "audio",
            self.audio,
            AudioFinalizeInput(
                audio_segments=audio_segments,
                output_path=output_path,
                normalize=self.config.normalize_audio,
                add_chapter_markers=self.config.add_chapters,
                output_format=self.config.output_format,
            ),
        )

        if not audio_result.success:
            raise RuntimeError(f"Audio finalization failed: {audio_result.error}")

        return {
            "qc": qc_result.data if qc_result else None,
            "audio": audio_result.data,
        }

    async def run_analysis(self) -> Dict[str, Any]:
        """Run only the analysis stages (Parse + Clean + Summarize + Classify). Useful for demos."""
        try:
            # Phase 1 now contains the full analysis pipeline for demo
            results = await self._phase1_parse()

            return {
                "success": True,
                "parse": results["parse"],
                "clean": results["clean"],
                "summarize": results["summarize"],
                "classify": results["classify"],
                "chapters": results.get("chapters"),
                "chapter_count": results.get("chapter_count"),
            }
        except Exception as e:
            logger.exception("Analysis failed")
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────
    # Public run()
    # ─────────────────────────────────────────────

    async def run(self) -> Dict[str, Any]:
        """Execute the full 4-phase pipeline."""
        try:
            # PHASE 1: Parse (sequential)
            parse_data = await self._phase1_parse()

            # PHASE 2: Analyze (parallel)
            analyze_data = await self._phase2_analyze(parse_data)

            # PHASE 3: Generate (parallel)
            gen_data = await self._phase3_generate(parse_data, analyze_data)

            # PHASE 4: Finalize (sequential)
            finalize_data = await self._phase4_finalize(gen_data)

            self.state.set_stage(PipelineStage.COMPLETED)
            audio_out = finalize_data["audio"]

            return {
                "success": True,
                "output_path": (
                    audio_out.final_audio_path
                    if hasattr(audio_out, "final_audio_path")
                    else None
                ),
                "duration": (
                    audio_out.total_duration
                    if hasattr(audio_out, "total_duration")
                    else 0
                ),
                "chapters": parse_data["chapters"],
                "classify": analyze_data["classifier"],
                "summarize": analyze_data["context"],
                "chapter_count": parse_data["chapter_count"],
            }

        except Exception as e:
            logger.exception("Pipeline failed")
            self.state.set_error(str(e))
            return {
                "success": False,
                "error": str(e),
                "stage": self.state.state.stage.value,
            }

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        return self.state.state.to_dict()

    def _get_file_type(self) -> str:
        return Path(self.config.input_file).suffix.lstrip(".").lower()
