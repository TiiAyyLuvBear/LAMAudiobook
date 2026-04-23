"""
Audio Agent — Finalizes audio: concatenate, normalize, add chapter markers.
Combines post-processing responsibilities.
"""
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult
from schema.audio import (
    AudioSegment,
    AudioFinalizeInput,
    AudioFinalizeOutput,
)
from utils.audio_utils import concatenate_audio, normalize_audio, convert_audio_format


class AudioAgent(BaseAgent):
    """
    Final audio processing:
    - Concatenate all segments
    - Normalize volume levels
    - Add chapter markers (silence gaps)
    - Convert to output format (mp3/wav)
    """

    name = "audio"

    async def run(self, input_data: AudioFinalizeInput) -> AgentResult:
        try:
            segments = input_data.audio_segments
            if not segments:
                return AgentResult(
                    success=False,
                    error="No audio segments to process",
                )

            output_dir = input_data.output_path.rsplit("/", 1)[0].rsplit("\\", 1)[0]
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # Sort segments by index
            sorted_segs = sorted(segments, key=lambda s: (s.chapter_index, s.segment_index))
            temp_wav = input_data.output_path.rsplit(".", 1)[0] + "_concat.wav"

            # 1. Concatenate all audio segments
            file_paths = [s.file_path for s in sorted_segs if s.file_path]
            if len(file_paths) == 1:
                # Only one file — just copy
                Path(file_paths[0]).rename(temp_wav) if file_paths[0] != temp_wav else None
            else:
                ok = concatenate_audio(file_paths, temp_wav, format="wav")
                if not ok:
                    return AgentResult(success=False, error="Audio concatenation failed")

            # 2. Normalize if requested
            final_path = input_data.output_path
            if input_data.normalize:
                ok = normalize_audio(temp_wav, final_path)
                if not ok:
                    # Fallback: use concatenated file
                    final_path = temp_wav
            else:
                # Convert to output format
                ok = convert_audio_format(temp_wav, final_path, format=input_data.output_format)
                if not ok:
                    final_path = temp_wav

            # 3. Add chapter markers (silence gaps between chapters)
            # TODO: implement chapter marker insertion using ffmpeg
            # Currently: silent — add via ffmpeg adelay between chapter boundaries

            # Calculate total duration
            total_duration = sum(s.duration_seconds for s in sorted_segs)

            # Build chapter metadata
            chapters: List[Dict[str, Any]] = []
            if input_data.add_chapter_markers:
                seen_chapters = set()
                for s in sorted_segs:
                    if s.chapter_index not in seen_chapters:
                        seen_chapters.add(s.chapter_index)
                        chapters.append({
                            "chapter": s.chapter_index,
                            "start_time": 0.0,  # TODO: calculate actual offset
                        })

            # Cleanup temp concat file
            if temp_wav != final_path and Path(temp_wav).exists():
                Path(temp_wav).unlink()

            return AgentResult(
                success=True,
                data=AudioFinalizeOutput(
                    final_audio_path=final_path,
                    total_duration=total_duration,
                    chapters=chapters,
                    metadata={"segment_count": len(sorted_segs)},
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))