"""
Audiobook Pipeline - Main workflow orchestrator.

Pipeline: Planner → Parser → Cleaner → Chapter → Narrative → Dialogue →
          Voice → TTS → QC → Retry → Post-process
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio

from ..agents.planner import PlannerAgent
from ..agents.document.parser import ParserAgent
from ..agents.document.cleaner import CleanerAgent
from ..agents.document.chapter_detector import ChapterDetectorAgent
from ..agents.understanding.narrative import NarrativeAgent
from ..agents.understanding.dialogue import DialogueAgent
from ..agents.audio.voice_planner import VoicePlannerAgent
from ..agents.audio.tts_generator import TTSGeneratorAgent
from ..agents.audio.post_processing import PostProcessingAgent
from ..agents.qc import QCAgent
from ..agents.memory import MemoryAgent


class PipelineStage(Enum):
    """Pipeline execution stages"""
    PLANNING = "planning"
    PARSING = "parsing"
    CLEANING = "cleaning"
    CHAPTER_DETECTION = "chapter_detection"
    NARRATIVE_ANALYSIS = "narrative_analysis"
    DIALOGUE_ANALYSIS = "dialogue_analysis"
    VOICE_PLANNING = "voice_planning"
    TTS_GENERATION = "tts_generation"
    QUALITY_CONTROL = "quality_control"
    POST_PROCESSING = "post_processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineState:
    """Current state of the pipeline"""
    stage: PipelineStage
    progress: float
    current_chapter: int
    total_chapters: int
    error: Optional[str] = None


@dataclass
class PipelineConfig:
    """Configuration for the audiobook pipeline"""
    input_file: str
    output_dir: str
    output_format: str = "mp3"
    max_retries: int = 3
    normalize_audio: bool = True
    add_chapters: bool = True


class AudiobookPipeline:
    """
    Main audiobook generation pipeline.
    
    Orchestrates all agents in sequence:
    1. Planner - Analyze document, decide strategy
    2. Parser - Extract text blocks
    3. Cleaner - Remove noise
    4. Chapter Detector - Split into chapters
    5. Narrative - Classify narration vs dialogue
    6. Dialogue - Identify speakers and emotions
    7. Voice Planner - Assign voices to speakers
    8. TTS Generator - Generate audio
    9. QC - Validate output
    10. Post-processing - Finalize audio
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = PipelineState(
            stage=PipelineStage.PLANNING,
            progress=0.0,
            current_chapter=0,
            total_chapters=0
        )
        
        # Initialize all agents
        self.planner = PlannerAgent()
        self.parser = ParserAgent()
        self.cleaner = CleanerAgent()
        self.chapter_detector = ChapterDetectorAgent()
        self.narrative = NarrativeAgent()
        self.dialogue = DialogueAgent()
        self.voice_planner = VoicePlannerAgent()
        self.tts_generator = TTSGeneratorAgent()
        self.qc = QCAgent()
        self.post_processing = PostProcessingAgent()
        self.memory = MemoryAgent()
    
    async def run(self) -> Dict[str, Any]:
        """
        Execute the full audiobook generation pipeline.
        
        Returns:
            Dict with success status and output information
        """
        try:
            # Stage 1: Planning
            self._update_stage(PipelineStage.PLANNING)
            plan_result = await self.planner.execute({
                "file_path": self.config.input_file,
                "file_type": self._get_file_type()
            })
            if not plan_result.success:
                raise Exception(f"Planning failed: {plan_result.error}")
            
            # Stage 2: Parsing
            self._update_stage(PipelineStage.PARSING)
            parse_result = await self.parser.execute({
                "file_path": self.config.input_file,
                "file_type": self._get_file_type(),
                "needs_ocr": plan_result.data.needs_ocr if plan_result.data else False
            })
            if not parse_result.success:
                raise Exception(f"Parsing failed: {parse_result.error}")
            
            # Stage 3: Cleaning
            self._update_stage(PipelineStage.CLEANING)
            clean_result = await self.cleaner.execute({
                "text_blocks": parse_result.data.blocks if parse_result.data else []
            })
            if not clean_result.success:
                raise Exception(f"Cleaning failed: {clean_result.error}")
            
            # Stage 4: Chapter Detection
            self._update_stage(PipelineStage.CHAPTER_DETECTION)
            chapter_result = await self.chapter_detector.execute({
                "text_blocks": clean_result.data.cleaned_blocks if clean_result.data else []
            })
            if not chapter_result.success:
                raise Exception(f"Chapter detection failed: {chapter_result.error}")
            
            chapters = chapter_result.data.chapters if chapter_result.data else []
            self.state.total_chapters = len(chapters)
            
            # Stage 5: Narrative Analysis
            self._update_stage(PipelineStage.NARRATIVE_ANALYSIS)
            narrative_result = await self.narrative.execute({
                "chapters": chapters
            })
            if not narrative_result.success:
                raise Exception(f"Narrative analysis failed: {narrative_result.error}")
            
            # Stage 6: Dialogue Analysis
            self._update_stage(PipelineStage.DIALOGUE_ANALYSIS)
            dialogue_result = await self.dialogue.execute({
                "annotated_chapters": narrative_result.data.annotated_chapters if narrative_result.data else [],
                "emotion_level": plan_result.data.emotion_level if plan_result.data else "basic"
            })
            if not dialogue_result.success:
                raise Exception(f"Dialogue analysis failed: {dialogue_result.error}")
            
            # Stage 7: Voice Planning
            self._update_stage(PipelineStage.VOICE_PLANNING)
            voice_result = await self.voice_planner.execute({
                "speakers": dialogue_result.data.speakers if dialogue_result.data else ["narrator"],
                "speaker_mode": plan_result.data.speaker_mode if plan_result.data else "single"
            })
            if not voice_result.success:
                raise Exception(f"Voice planning failed: {voice_result.error}")
            
            # Stage 8: TTS Generation
            self._update_stage(PipelineStage.TTS_GENERATION)
            tts_result = await self._generate_audio_with_retry(
                dialogue_result.data,
                voice_result.data
            )
            if not tts_result.success:
                raise Exception(f"TTS generation failed: {tts_result.error}")
            
            # Stage 9: Quality Control
            self._update_stage(PipelineStage.QUALITY_CONTROL)
            qc_result = await self.qc.execute({
                "audio_segments": tts_result.data.audio_segments if tts_result.data else [],
                "text_segments": []  # TODO: extract text segments
            })
            
            # Retry failed segments if needed
            if qc_result.data and qc_result.data.retry_segments:
                await self._retry_failed_segments(qc_result.data.retry_segments)
            
            # Stage 10: Post-processing
            self._update_stage(PipelineStage.POST_PROCESSING)
            final_result = await self.post_processing.execute({
                "audio_segments": tts_result.data.audio_segments if tts_result.data else [],
                "output_path": f"{self.config.output_dir}/audiobook.{self.config.output_format}",
                "normalize": self.config.normalize_audio,
                "add_chapter_markers": self.config.add_chapters,
                "output_format": self.config.output_format
            })
            if not final_result.success:
                raise Exception(f"Post-processing failed: {final_result.error}")
            
            self._update_stage(PipelineStage.COMPLETED)
            
            return {
                "success": True,
                "output_path": final_result.data.final_audio_path if final_result.data else None,
                "duration": final_result.data.total_duration if final_result.data else 0,
                "chapters": final_result.data.chapters if final_result.data else []
            }
            
        except Exception as e:
            self.state.stage = PipelineStage.FAILED
            self.state.error = str(e)
            return {
                "success": False,
                "error": str(e),
                "stage": self.state.stage.value
            }
    
    async def _generate_audio_with_retry(self, dialogue_data, voice_data):
        """Generate audio with retry for failed segments"""
        # TODO: Prepare TTS segments from dialogue and voice data
        segments = []
        
        return await self.tts_generator.execute({
            "segments": segments,
            "output_dir": self.config.output_dir,
            "format": "wav"
        })
    
    async def _retry_failed_segments(self, segment_indices):
        """Retry generating failed audio segments"""
        for attempt in range(self.config.max_retries):
            # TODO: Implement retry logic
            pass
    
    def _update_stage(self, stage: PipelineStage):
        """Update pipeline stage and progress"""
        stages = list(PipelineStage)
        stage_index = stages.index(stage)
        self.state.stage = stage
        self.state.progress = stage_index / (len(stages) - 2)  # Exclude COMPLETED and FAILED
    
    def _get_file_type(self) -> str:
        """Get file type from input file path"""
        return self.config.input_file.split(".")[-1].lower()
    
    def get_state(self) -> Dict[str, Any]:
        """Get current pipeline state"""
        return {
            "stage": self.state.stage.value,
            "progress": self.state.progress,
            "current_chapter": self.state.current_chapter,
            "total_chapters": self.state.total_chapters,
            "error": self.state.error
        }
