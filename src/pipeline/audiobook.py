"""
Audiobook Pipeline — 4-phase parallel pipeline orchestrator.
"""

import logging
import asyncio
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents import (
    ParserAgent,
    ParserInput,
    CleanerAgent,
    CleanerInput,
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
from utils.epub3_packager import package_book_epub, package_chapter_epub
from .config import PipelineConfig, PipelineStage
from .progress import SegmentProgress
from .state import StateManager
from .executor import ParallelExecutor


logger = logging.getLogger(__name__)


class AudiobookPipeline:
    """
    Main audiobook generation pipeline with 4-phase execution.

    PHASE 1 — Parse  (sequential): Parser → Cleaner → Summarizer → Classifier
    PHASE 2 — Analyze (parallel): Classifier + Voice + Memory
    PHASE 3 — Generate (parallel): TTS segment batches
    PHASE 4 — Finalize (sequential): QC → Audio concat
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = StateManager()
        self.executor = ParallelExecutor()
        self._cancel_requested = False
        self._stage_timings: Dict[str, float] = {}
        self._chapter_timings: List[Dict[str, Any]] = []
        self._segment_timings: List[Dict[str, Any]] = []
        self._tts_device_diagnostics: Dict[str, Any] = {}

        # Initialize agents
        self.parser = ParserAgent()
        self.cleaner = CleanerAgent()
        self.classifier = ClassifierAgent()
        self.summarizer = SummarizerAgent()
        self.voice = VoiceAgent(config={"voice_dir": config.xtts_voice_dir})
        self.tts = TTSAgent(
            config={
                "tts_engine": config.tts_engine,
                "tts_device": config.tts_device,
                "tts_service_url": "http://localhost:8001",
                "xtts_model_name_or_path": config.xtts_model_name_or_path,
                "xtts_config_path": config.xtts_config_path,
                "xtts_vocab_path": config.xtts_vocab_path,
                "xtts_voice_dir": config.xtts_voice_dir,
                "vieneu_model_name": config.vieneu_model_name,
                "vieneu_mode": config.vieneu_mode,
                "vieneu_emotion": config.vieneu_emotion,
                "vieneu_api_base": config.vieneu_api_base,
                "vieneu_device": config.vieneu_device,
                "vieneu_lora_adapter": config.vieneu_lora_adapter,
                "progress_callback": self._on_tts_progress,
            }
        )
        self.audio = AudioAgent()
        self.qc = QCAgent()
        self.memory = MemoryAgent()

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.state.set_status("Cancellation requested")

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested:
            raise asyncio.CancelledError()

    def _to_jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return self._to_jsonable(asdict(value))
        if isinstance(value, dict):
            return {str(k): self._to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_jsonable(item) for item in value]
        if hasattr(value, "__dict__"):
            return {
                key: self._to_jsonable(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return str(value)

    def _record_stage_output(self, stage: str, filename: str, data: Any) -> None:
        callback = self.config.stage_output_callback
        if not callback:
            return
        try:
            payload = data if isinstance(data, str) else self._to_jsonable(data)
            callback(stage, filename, payload)
        except Exception as exc:
            logger.warning("Failed to record %s/%s debug output: %s", stage, filename, exc)

    @staticmethod
    def _blocks_to_text(blocks: List[Any]) -> str:
        lines: List[str] = []
        for index, block in enumerate(blocks, start=1):
            page = getattr(block, "page", "?")
            block_type = getattr(block, "block_type", "block")
            text = getattr(block, "text", str(block)).strip()
            lines.append(f"[{index:04d}] page={page} type={block_type}\n{text}")
        return "\n\n".join(lines)

    @staticmethod
    def _chapter_summary(chapter: Any) -> Dict[str, Any]:
        paragraphs = getattr(chapter, "paragraphs", []) or []
        plain_text = getattr(chapter, "plain_text", "\n".join(paragraphs))
        return {
            "index": getattr(chapter, "index", None),
            "title": getattr(chapter, "title", None) or getattr(chapter, "chapter_title", None),
            "paragraph_count": len(paragraphs),
            "word_count": len(plain_text.split()),
        }

    @staticmethod
    def _tts_segment_summary(segment: TTSSegment) -> Dict[str, Any]:
        return {
            "segment_index": segment.segment_index,
            "chapter_index": segment.chapter_index,
            "voice_id": segment.voice_id,
            "speaker": segment.speaker,
            "emotion": segment.emotion,
            "intensity": segment.intensity,
            "speed": segment.speed,
            "text": segment.text,
        }

    @staticmethod
    def _audio_segment_summary(segment: AudioSegment) -> Dict[str, Any]:
        return {
            "segment_index": segment.segment_index,
            "chapter_index": segment.chapter_index,
            "voice_id": segment.voice_id,
            "duration_seconds": segment.duration_seconds,
            "file_path": segment.file_path,
            "text": segment.text,
        }

    @staticmethod
    def _count_sentences(text: str) -> int:
        import re

        pattern = r"[^.!?。！？]+[.!?。！？]+(?:[\"'”’)]*)|[^.!?。！？]+$"
        return len([item.group(0).strip() for item in re.finditer(pattern, (text or "").strip()) if item.group(0).strip()])

    @staticmethod
    def _rtf_summary(segment_timings: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid = [item for item in segment_timings if isinstance(item.get("rtf"), (int, float))]
        if not valid:
            return {"avg_segment_rtf": None, "max_segment_rtf": None, "slowest_segment": None}
        slowest = max(valid, key=lambda item: float(item.get("rtf") or 0.0))
        avg = sum(float(item["rtf"]) for item in valid) / len(valid)
        return {
            "avg_segment_rtf": round(avg, 3),
            "max_segment_rtf": round(float(slowest.get("rtf") or 0.0), 3),
            "slowest_segment": {
                "segment_index": slowest.get("segment_index"),
                "chapter_index": slowest.get("chapter_index"),
                "rtf": slowest.get("rtf"),
                "tts_wall_seconds": slowest.get("tts_wall_seconds"),
                "audio_duration_seconds": slowest.get("audio_duration_seconds"),
                "text_preview": str(slowest.get("text_preview") or "")[:120],
            },
        }

    def _build_pipeline_stats(
        self,
        parse_data: Dict[str, Any],
        gen_data: Dict[str, Any],
        finalize_data: Dict[str, Any],
        total_wall_seconds: float,
    ) -> Dict[str, Any]:
        plain_text = parse_data.get("plain_text") or ""
        chapters = parse_data.get("chapters") or []
        segments = gen_data.get("segments") or []
        audio_out = finalize_data.get("audio")
        source_filename = self.config.source_filename or Path(self.config.input_file).name
        metadata = parse_data.get("metadata") or {}
        engine_name = (self.config.tts_engine or "").lower()
        is_vieneu = engine_name in {"vieneu", "vieneu_tts", "direct_vieneu"}

        return {
            "execution": {
                "total_wall_seconds": round(total_wall_seconds, 3),
                "stage_wall_seconds": {key: round(value, 3) for key, value in self._stage_timings.items()},
            },
            "book": {
                "source_filename": source_filename,
                "input_format": self._get_file_type(),
                "output_format": self.config.output_format,
                "title": metadata.get("title") or Path(source_filename).stem,
                "chapter_count": len(chapters),
                "paragraph_count": sum(len(getattr(chapter, "paragraphs", []) or []) for chapter in chapters),
                "sentence_count": len(segments) or self._count_sentences(plain_text),
                "word_count": len(plain_text.split()),
                "character_count": len(plain_text),
            },
            "tts": {
                "engine": self.config.tts_engine,
                "device": self._tts_device_diagnostics.get("resolved_device")
                or (self.config.vieneu_device if is_vieneu else self.config.tts_device),
                "requested_device": self._tts_device_diagnostics.get("requested_device")
                or (self.config.vieneu_device if is_vieneu else self.config.tts_device),
                "model": self.config.vieneu_model_name if is_vieneu else self.config.xtts_model_name_or_path,
                "lora_adapter": self.config.vieneu_lora_adapter,
                "segment_count": len(segments),
                "audio_duration_seconds": round(float(getattr(audio_out, "total_duration", 0.0) or 0.0), 3),
                "device_diagnostics": self._tts_device_diagnostics,
                "segment_timings": self._segment_timings,
                "rtf_summary": self._rtf_summary(self._segment_timings),
            },
            "chapters": self._chapter_timings,
        }

    # ─────────────────────────────────────────────
    # PHASE 1: Parse  (sequential)
    # ─────────────────────────────────────────────

    async def _phase1_parse(self) -> Dict[str, Any]:
        """Parser → Cleaner → Summarizer → Classifier (sequential)."""
        self.state.set_stage(PipelineStage.PARSING)
        self._raise_if_cancelled()

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
        self._record_stage_output(
            "parse",
            "parser.json",
            {
                "metadata": getattr(parse_data, "metadata", {}),
                "total_pages": getattr(parse_data, "total_pages", 0),
                "block_count": len(getattr(parse_data, "blocks", []) or []),
            },
        )
        self._record_stage_output(
            "parse",
            "blocks.txt",
            self._blocks_to_text(getattr(parse_data, "blocks", []) or []),
        )
        self.state.set_stage(PipelineStage.CLEANING)
        self._raise_if_cancelled()

        # Step 2: Cleaner
        clean_result = await self.executor.execute_single(
            "cleaner",
            self.cleaner,
            CleanerInput(text_blocks=parse_data.blocks),
        )
        if not clean_result.success:
            raise RuntimeError(f"Cleaner failed: {clean_result.error}")

        clean_data = clean_result.data
        self._record_stage_output(
            "clean",
            "cleaner.json",
            {
                "removed_count": getattr(clean_data, "removed_count", 0),
                "metadata": getattr(clean_data, "metadata", {}),
                "cleaned_block_count": len(getattr(clean_data, "cleaned_blocks", []) or []),
                "chapter_count": len(getattr(clean_data, "chapters", []) or []),
            },
        )
        self._record_stage_output("clean", "plain_text.txt", getattr(clean_data, "plain_text", "") or "")
        self._record_stage_output(
            "clean",
            "chapters.json",
            [self._chapter_summary(chapter) for chapter in getattr(clean_data, "chapters", []) or []],
        )
        self.state.set_stage(PipelineStage.ANALYZING)
        self._raise_if_cancelled()

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
            self._record_stage_output(
                "summarize",
                "summarizer.json",
                {
                    "keywords": getattr(ctx, "keywords", []),
                    "entities": getattr(ctx, "entities", []),
                    "chapter_summaries": getattr(ctx, "chapter_summaries", []),
                    "primary_mood": getattr(ctx, "primary_mood", ""),
                    "summary_word_count": len((getattr(ctx, "summary", "") or "").split()),
                },
            )
            self._record_stage_output("summarize", "summary.txt", getattr(ctx, "summary", "") or "")
            self._raise_if_cancelled()

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
            self._record_stage_output(
                "classify",
                "classifier.json",
                {
                    "genre": getattr(class_data, "genre", None),
                    "mood": getattr(class_data, "mood", None),
                    "dialogue_ratio": getattr(class_data, "dialogue_ratio", 0.0),
                    "recommended_voice_style": getattr(class_data, "recommended_voice_style", None),
                    "sentences": getattr(class_data, "sentences", []),
                },
            )
            self._raise_if_cancelled()

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
        self._raise_if_cancelled()
        
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
                    speaker_mode=self.config.tts_speaker_mode,
                    book_summary=(ctx.summary if ctx else ""),
                    book_mood=(getattr(classifier_data, "recommended_voice_style", None) if classifier_data else None) or (ctx.primary_mood if ctx else "neutral"),
                    character_emotions=char_emotions,
                    narrator_voice_override=self.config.narrator_voice_override,
                ),
                "memory": MemoryInput(action="clear"),
            },
            raise_on_error=False,
        )

        voice_result = results.get("voice")
        memory_result = results.get("memory")
        voice_data = voice_result.data if voice_result and voice_result.success else None
        self._record_stage_output(
            "voice",
            "voice.json",
            {
                "narrator_voice": getattr(voice_data, "narrator_voice", None),
                "voice_assignments": getattr(voice_data, "voice_assignments", []),
                "speaker_mode": self.config.tts_speaker_mode,
                "voice_mode": self.config.voice_mode,
                "narrator_voice_override": self.config.narrator_voice_override,
                "character_emotions": char_emotions,
            },
        )

        return {
            "classifier": classifier_data,
            "voice": voice_data,
            "memory": memory_result.data if memory_result and memory_result.success else None,
            "context": ctx,
        }

    # ─────────────────────────────────────────────
    # PHASE 3: Generate  (parallel)
    # ─────────────────────────────────────────────

    def _on_tts_progress(self, event: Dict[str, Any]) -> None:
        self.state.set_stage(PipelineStage.GENERATING)
        self._raise_if_cancelled()
        chapter_index = int(event.get("chapter_index") or 0)
        chapter_current = int(event.get("chapter_segment_current") or 0)
        chapter_total = int(event.get("chapter_segment_total") or 0)
        global_current = int(event.get("global_segment_current") or 0)
        global_total = int(event.get("global_segment_total") or 0)
        progress = SegmentProgress(
            chapter_index=chapter_index,
            total_chapters=self.state.state.total_chapters,
            chapter_completed_segments=chapter_current,
            chapter_total_segments=chapter_total,
            completed_segments=global_current,
            total_segments=global_total,
        )
        self.state.set_global_segments(global_total)
        self.state.update_global_segment(global_current)
        self.state.set_chapter_segments(chapter_total)
        self.state.update_chapter_segment(chapter_current)
        self.state.update_chapter(chapter_index)
        self.state.set_status(progress.status())
        self.state.set_progress(progress.generation_progress())

    def _split_tts_text(self, text: str, max_chars: Optional[int] = None) -> List[str]:
        import re

        text = (text or "").strip()
        if not text:
            return []
        pattern = r"[^.!?。！？]+[.!?。！？]+(?:[\"'”’)]*)|[^.!?。！？]+$"
        sentences = [match.group(0).strip() for match in re.finditer(pattern, text)]
        return [sentence for sentence in sentences if sentence] or [text]

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
                    voice_id = narrator_voice if self.config.tts_speaker_mode == "single" else voice_map.get(speaker, narrator_voice)
                    segments.append(
                        TTSSegment(
                            text=chunk,
                            voice_id=voice_id,
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
        """Build TTS segments, synthesize chapter by chapter, and publish chapter EPUBs early."""
        self.state.set_stage(PipelineStage.GENERATING)

        segments = self._build_tts_segments(parse_data, analyze_data)
        if not segments:
            raise RuntimeError("No TTS segments were produced from cleaned text")
        self._record_stage_output(
            "tts",
            "segments.json",
            [self._tts_segment_summary(segment) for segment in segments],
        )

        total_chapters = parse_data.get("chapter_count") or max((s.chapter_index for s in segments), default=0)
        self.state.set_chapters(total_chapters)
        self.state.set_global_segments(len(segments))
        self.state.update_global_segment(0)
        self.state.set_chapter_segments(0)
        self.state.update_chapter_segment(0)
        self.state.update_chapter(segments[0].chapter_index if segments else 0)
        self.state.set_status(f"Preparing TTS for {len(segments)} segments across {total_chapters} chapters")

        chapters_by_index = {
            int(getattr(chapter, "index", 0)) + 1: chapter
            for chapter in parse_data.get("chapters") or []
        }
        segments_by_chapter: Dict[int, List[TTSSegment]] = {}
        for segment in segments:
            segments_by_chapter.setdefault(segment.chapter_index, []).append(segment)

        all_audio_segments: List[AudioSegment] = []
        all_failed_segments: List[int] = []
        chapter_epubs: List[Dict[str, Any]] = []
        completed_segment_count = 0

        for chapter_index in sorted(segments_by_chapter):
            self._raise_if_cancelled()
            chapter_started = time.perf_counter()
            chapter_segments = sorted(segments_by_chapter[chapter_index], key=lambda s: s.segment_index)
            self.state.update_chapter(chapter_index)
            self.state.set_chapter_segments(len(chapter_segments))
            self.state.update_chapter_segment(0)
            self.state.set_status(
                f"Generating chapter {chapter_index}/{total_chapters} "
                f"({len(chapter_segments)} segments)"
            )

            tts_result = await self.executor.execute_single(
                "tts",
                self.tts,
                TTSGeneratorInput(
                    segments=chapter_segments,
                    output_dir=self.config.output_dir,
                    global_total_segments=len(segments),
                    completed_segment_offset=completed_segment_count,
                    chapter_total_segments=len(chapter_segments),
                ),
            )

            if not tts_result.success:
                raise RuntimeError(f"TTS generation failed for chapter {chapter_index}: {tts_result.error}")
            self._raise_if_cancelled()

            tts_data = tts_result.data
            tts_metadata = getattr(tts_data, "metadata", {}) or {}
            for timing in tts_metadata.get("segment_timings", []) or []:
                segment_lookup = {segment.segment_index: segment for segment in chapter_segments}
                segment = segment_lookup.get(timing.get("segment_index"))
                if segment:
                    timing = {**timing, "text_preview": segment.text[:120]}
                self._segment_timings.append(timing)
            if tts_metadata.get("device_diagnostics"):
                self._tts_device_diagnostics = tts_metadata["device_diagnostics"]
            chapter_audio_segments = (
                tts_data.audio_segments if hasattr(tts_data, "audio_segments") else []
            )
            all_audio_segments.extend(chapter_audio_segments)
            all_failed_segments.extend(getattr(tts_data, "failed_segments", []) or [])
            completed_segment_count += len(chapter_segments)
            self.state.update_global_segment(completed_segment_count)
            self.state.update_chapter_segment(len(chapter_segments))
            chapter_audio_duration = sum(segment.duration_seconds for segment in chapter_audio_segments)
            chapter = chapters_by_index.get(chapter_index)
            chapter_title = (
                getattr(chapter, "title", None)
                or getattr(chapter, "chapter_title", None)
                or f"Chapter {chapter_index}"
            )
            chapter_timing = {
                "chapter_index": chapter_index,
                "title": chapter_title,
                "segment_count": len(chapter_segments),
                "audio_segment_count": len(chapter_audio_segments),
                "word_count": sum(len(segment.text.split()) for segment in chapter_segments),
                "audio_duration_seconds": round(chapter_audio_duration, 3),
                "tts_wall_seconds": round(time.perf_counter() - chapter_started, 3),
                "status": "completed",
            }

            generated_indexes = {segment.segment_index for segment in chapter_audio_segments}
            expected_indexes = {segment.segment_index for segment in chapter_segments}
            if generated_indexes >= expected_indexes:
                title = (
                    getattr(chapter, "title", None)
                    or getattr(chapter, "chapter_title", None)
                    or f"Chapter {chapter_index}"
                )
                paragraphs = getattr(chapter, "paragraphs", []) if chapter else []
                artifact = package_chapter_epub(
                    output_dir=self.config.output_dir,
                    chapter_index=chapter_index,
                    title=title,
                    paragraphs=paragraphs,
                    audio_segments=chapter_audio_segments,
                )
                artifact_data = {
                    "type": "chapter_epub",
                    "chapter_index": artifact.chapter_index,
                    "title": artifact.title,
                    "path": artifact.epub_path,
                    "chapter_audio_path": artifact.chapter_audio_path,
                    "segment_count": artifact.segment_count,
                }
                chapter_epubs.append(artifact_data)
                self.state.add_artifact(artifact_data)
                self.state.set_status(
                    f"Chapter {chapter_index}/{total_chapters} EPUB ready: {Path(artifact.epub_path).name}"
                )
            else:
                missing = sorted(expected_indexes - generated_indexes)
                all_failed_segments.extend(missing)
                chapter_timing["status"] = "missing_audio"
                chapter_timing["missing_segments"] = missing
                self.state.set_status(
                    f"Chapter {chapter_index}/{total_chapters} has missing audio segments: {missing}"
                )
            self._chapter_timings.append(chapter_timing)

            self.state.set_progress(
                SegmentProgress(
                    chapter_index=chapter_index,
                    total_chapters=total_chapters,
                    chapter_completed_segments=len(chapter_segments),
                    chapter_total_segments=len(chapter_segments),
                    completed_segments=completed_segment_count,
                    total_segments=len(segments),
                ).generation_progress()
            )

        total_duration = sum(segment.duration_seconds for segment in all_audio_segments)
        self._record_stage_output(
            "tts",
            "audio_segments.json",
            [self._audio_segment_summary(segment) for segment in all_audio_segments],
        )
        self._record_stage_output(
            "tts",
            "failed_segments.json",
            {
                "failed_segments": sorted(set(all_failed_segments)),
                "chapter_epubs": chapter_epubs,
                "total_duration": total_duration,
                "chapter_timings": self._chapter_timings,
                "segment_timings": self._segment_timings,
            },
        )
        tts_output = type(
            "ChapteredTTSOutput",
            (),
            {
                "audio_segments": all_audio_segments,
                "total_duration": total_duration,
                "failed_segments": all_failed_segments,
                "metadata": {
                    "chapter_epubs": chapter_epubs,
                    "segment_count": len(segments),
                    "chapter_timings": self._chapter_timings,
                    "segment_timings": self._segment_timings,
                    "device_diagnostics": self._tts_device_diagnostics,
                },
            },
        )()

        return {
            "tts": tts_output,
            "segments": segments,
            "chapters": parse_data.get("chapters") or [],
            "book_title": (parse_data.get("metadata") or {}).get("title") or Path(self.config.input_file).stem,
            "chapter_epubs": chapter_epubs,
            "chapter_timings": self._chapter_timings,
        }

    # ─────────────────────────────────────────────
    # PHASE 4: Finalize  (sequential)
    # ─────────────────────────────────────────────

    async def _phase4_finalize(self, gen_data: Dict[str, Any]) -> Dict[str, Any]:
        """QC → Audio concat (sequential)."""
        self.state.set_stage(PipelineStage.FINALIZING)
        self._raise_if_cancelled()

        tts_data = gen_data["tts"]
        segments = gen_data["segments"]
        audio_segments = (
            tts_data.audio_segments if hasattr(tts_data, "audio_segments") else []
        )
        book_title = gen_data.get("book_title") or Path(self.config.input_file).stem or "Audiobook"
        source_filename = self.config.source_filename or Path(self.config.input_file).name
        book_epub = package_book_epub(
            output_dir=self.config.output_dir,
            title=book_title,
            chapters=gen_data.get("chapters", []),
            audio_segments=audio_segments,
            output_filename=source_filename,
        )
        book_epub_data = {
            "type": "book_epub",
            "path": book_epub.epub_path,
            "chapter_count": book_epub.chapter_count,
            "segment_count": book_epub.segment_count,
        }
        self.state.add_artifact(book_epub_data)
        self.state.set_status(f"Book EPUB3 artifact ready: {Path(book_epub.epub_path).name}")

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
            self._record_stage_output(
                "qc",
                "qc.json",
                {
                    "passed": getattr(qc_out, "passed", None),
                    "issues": getattr(qc_out, "issues", []),
                    "retry_segments": retry_segments,
                    "quality_score": getattr(qc_out, "quality_score", None),
                },
            )

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
        self._raise_if_cancelled()
        final_audio_path = getattr(audio_result.data, "final_audio_path", output_path)
        self.state.set_status(self._final_audio_message(final_audio_path))

        self._cleanup_temp_segment_audio(audio_segments, keep_paths=set())
        self._record_stage_output(
            "audio",
            "audio.json",
            {
                "final_audio_path": getattr(audio_result.data, "final_audio_path", None),
                "total_duration": getattr(audio_result.data, "total_duration", None),
                "chapters": getattr(audio_result.data, "chapters", []),
                "metadata": getattr(audio_result.data, "metadata", {}),
                "chapter_epubs": gen_data.get("chapter_epubs", []),
                "book_epub": book_epub_data,
            },
        )

        return {
            "qc": qc_result.data if qc_result else None,
            "audio": audio_result.data,
            "chapter_epubs": gen_data.get("chapter_epubs", []),
            "book_epub": book_epub_data,
        }

    def _final_audio_message(self, output_path: str) -> str:
        suffix = Path(output_path).suffix.lower().lstrip(".")
        if suffix == "mp3":
            return f"MP3 audiobook ready: {Path(output_path).name}"
        if suffix == "wav":
            return f"WAV audiobook ready: {Path(output_path).name}"
        return f"Audiobook ready: {Path(output_path).name}"

    def _cleanup_temp_segment_audio(self, audio_segments: List[AudioSegment], keep_paths: set[str]) -> None:
        keep_resolved = {str(Path(path).resolve()) for path in keep_paths}
        for segment in audio_segments:
            path = Path(segment.file_path)
            try:
                if not path.exists() or str(path.resolve()) in keep_resolved:
                    continue
                if path.parent.resolve() != Path(self.config.output_dir).resolve():
                    continue
                if path.name.startswith("seg_") and path.suffix.lower() == ".wav":
                    path.unlink()
            except Exception as exc:
                logger.warning("Failed to clean temp audio %s: %s", path, exc)

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
        pipeline_started = time.perf_counter()
        try:
            # PHASE 1: Parse (sequential)
            self._raise_if_cancelled()
            phase_started = time.perf_counter()
            parse_data = await self._phase1_parse()
            self._stage_timings["parse_analyze_text"] = time.perf_counter() - phase_started

            # PHASE 2: Analyze (parallel)
            self._raise_if_cancelled()
            phase_started = time.perf_counter()
            analyze_data = await self._phase2_analyze(parse_data)
            self._stage_timings["voice_memory"] = time.perf_counter() - phase_started

            # PHASE 3: Generate (parallel)
            self._raise_if_cancelled()
            phase_started = time.perf_counter()
            gen_data = await self._phase3_generate(parse_data, analyze_data)
            self._stage_timings["tts_generation"] = time.perf_counter() - phase_started

            # PHASE 4: Finalize (sequential)
            self._raise_if_cancelled()
            phase_started = time.perf_counter()
            finalize_data = await self._phase4_finalize(gen_data)
            self._stage_timings["finalize"] = time.perf_counter() - phase_started

            self.state.set_stage(PipelineStage.COMPLETED)
            audio_out = finalize_data["audio"]
            total_wall_seconds = time.perf_counter() - pipeline_started
            pipeline_stats = self._build_pipeline_stats(
                parse_data=parse_data,
                gen_data=gen_data,
                finalize_data=finalize_data,
                total_wall_seconds=total_wall_seconds,
            )

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
                "chapter_epubs": finalize_data.get("chapter_epubs", []),
                "book_epub": finalize_data.get("book_epub"),
                "chapters": parse_data["chapters"],
                "classify": analyze_data["classifier"],
                "summarize": analyze_data["context"],
                "chapter_count": parse_data["chapter_count"],
                "pipeline_stats": pipeline_stats,
            }

        except asyncio.CancelledError:
            self.state.set_stage(PipelineStage.FAILED)
            self.state.set_status("Cancelled")
            return {
                "success": False,
                "cancelled": True,
                "error": "Cancelled",
                "stage": "cancelled",
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
