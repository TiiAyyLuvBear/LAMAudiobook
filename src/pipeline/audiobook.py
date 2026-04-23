"""
Audiobook Pipeline — 4-phase parallel pipeline orchestrator.
"""
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents import (
    PlannerAgent, PlannerInput,
    ParserAgent, ParserInput,
    CleanerAgent, CleanerInput,
    SplitterAgent, SplitterInput,
    ClassifierAgent, ClassifierInput,
    VoiceAgent, VoiceInput,
    TTSAgent, TTSGeneratorInput,
    AudioAgent, AudioFinalizeInput,
    QCAgent, QCInput,
    MemoryAgent, MemoryInput,
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
        self.planner = PlannerAgent()
        self.parser = ParserAgent()
        self.cleaner = CleanerAgent()
        self.splitter = SplitterAgent()
        self.classifier = ClassifierAgent()
        self.voice = VoiceAgent()
        self.tts = TTSAgent()
        self.audio = AudioAgent()
        self.qc = QCAgent()
        self.memory = MemoryAgent()

    # ─────────────────────────────────────────────
    # PHASE 1: Parse  (sequential)
    # ─────────────────────────────────────────────

    async def _phase1_parse(self) -> Dict[str, Any]:
        """Planner → Parser → Cleaner → Splitter (sequential)."""
        self.state.set_stage(PipelineStage.PLANNING)

        # Step 1.1: Planner
        plan_result = await self.executor.execute_single(
            "planner",
            self.planner,
            PlannerInput(
                file_path=self.config.input_file,
                file_type=self._get_file_type(),
            ),
        )
        if not plan_result.success:
            raise RuntimeError(f"Planner failed: {plan_result.error}")

        plan = plan_result.data
        self.state.set_stage(PipelineStage.PARSING)

        # Step 1.2: Parser
        parse_result = await self.executor.execute_single(
            "parser",
            self.parser,
            ParserInput(
                file_path=self.config.input_file,
                file_type=self._get_file_type(),
                needs_ocr=getattr(plan, "needs_ocr", False),
            ),
        )
        if not parse_result.success:
            raise RuntimeError(f"Parser failed: {parse_result.error}")

        parse = parse_result.data
        self.state.set_stage(PipelineStage.CLEANING)

        # Step 1.3: Cleaner
        clean_result = await self.executor.execute_single(
            "cleaner",
            self.cleaner,
            CleanerInput(text_blocks=parse.blocks),
        )
        if not clean_result.success:
            raise RuntimeError(f"Cleaner failed: {clean_result.error}")

        clean = clean_result.data
        self.state.set_stage(PipelineStage.SPLITTING)

        # Step 1.4: Splitter
        split_result = await self.executor.execute_single(
            "splitter",
            self.splitter,
            SplitterInput(text_blocks=clean.cleaned_blocks),
        )
        if not split_result.success:
            raise RuntimeError(f"Splitter failed: {split_result.error}")

        split = split_result.data
        chapters = split.chapters if hasattr(split, "chapters") else []
        self.state.set_chapters(len(chapters))

        return {
            "chapters": chapters,
            "metadata": parse.metadata,
            "plan": plan,
        }

    # ─────────────────────────────────────────────
    # PHASE 2: Analyze  (parallel)
    # ─────────────────────────────────────────────

    async def _phase2_analyze(self, parse_data: Dict[str, Any]) -> Dict[str, Any]:
        """Classifier + Voice + Memory run concurrently."""
        self.state.set_stage(PipelineStage.ANALYZING)

        chapters = parse_data["chapters"]
        plan = parse_data["plan"]
        emotion_level = getattr(plan, "emotion_level", "basic")

        results = await self.executor.execute_group(
            agents=[
                ("classifier", self.classifier),
                ("voice", self.voice),
                ("memory", self.memory),
            ],
            input_data={
                "classifier": ClassifierInput(chapters=chapters, emotion_level=emotion_level),
                "voice": VoiceInput(
                    speakers=["narrator"],  # TODO: extract from classifier
                    speaker_mode=getattr(plan, "speaker_mode", "single"),
                ),
                "memory": MemoryInput(action="clear"),
            },
            raise_on_error=False,
        )

        classifier_result = results.get("classifier")
        voice_result = results.get("voice")
        memory_result = results.get("memory")

        if not classifier_result or not classifier_result.success:
            raise RuntimeError(f"Classifier failed: {classifier_result.error if classifier_result else 'No result'}")

        return {
            "classifier": classifier_result.data,
            "voice": voice_result.data if voice_result else None,
            "memory": memory_result.data if memory_result else None,
        }

    # ─────────────────────────────────────────────
    # PHASE 3: Generate  (parallel)
    # ─────────────────────────────────────────────

    async def _phase3_generate(self, analyze_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build TTS segments → run TTS agent (currently sequential, extensible to batch parallel)."""
        self.state.set_stage(PipelineStage.GENERATING)

        classifier_data = analyze_data["classifier"]
        voice_data = analyze_data["voice"]

        sentences = classifier_data.sentences if hasattr(classifier_data, "sentences") else []
        voice_assignments = voice_data.voice_assignments if voice_data else []

        # Build voice lookup
        voice_map: Dict[str, str] = {}
        for va in voice_assignments:
            voice_map[va.speaker] = va.voice_id

        # Build TTS segments
        segments = []
        for i, sent in enumerate(sentences):
            segments.append(
                TTSSegment(
                    text=sent.text,
                    voice_id=voice_map.get(sent.speaker, "narrator_vi_female"),
                    emotion=sent.emotion,
                    speed=1.0,
                    chapter_index=sent.chapter_index,
                    segment_index=i,
                    speaker=sent.speaker,
                )
            )

        # TODO: chunk into batches and run batched TTS in parallel
        # For now: single TTS call with all segments
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
        audio_segments = tts_data.audio_segments if hasattr(tts_data, "audio_segments") else []

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
        output_path = str(Path(self.config.output_dir) / f"audiobook.{self.config.output_format}")

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
            gen_data = await self._phase3_generate(analyze_data)

            # PHASE 4: Finalize (sequential)
            finalize_data = await self._phase4_finalize(gen_data)

            self.state.set_stage(PipelineStage.COMPLETED)
            audio_out = finalize_data["audio"]

            return {
                "success": True,
                "output_path": audio_out.final_audio_path if hasattr(audio_out, "final_audio_path") else None,
                "duration": audio_out.total_duration if hasattr(audio_out, "total_duration") else 0,
                "chapters": audio_out.chapters if hasattr(audio_out, "chapters") else [],
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
