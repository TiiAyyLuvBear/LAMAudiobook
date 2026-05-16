"""
Audio Agent — Finalizes audio: concatenate, normalize, add chapter markers.
Combines post-processing responsibilities.
"""
from typing import Any, Dict, List, Optional
from pathlib import Path
import shutil
import subprocess

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
    - Add chapter metadata markers when the output container supports them
    - Convert to output format (mp3/wav)
    """

    name = "audio"

    def __init__(self, config=None):
        super().__init__(name=self.name, config=config)

    @staticmethod
    def _escape_ffmetadata(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("=", "\\=")
            .replace(";", "\\;")
            .replace("#", "\\#")
            .replace("\n", " ")
        )

    def _build_chapter_metadata(self, sorted_segments: List[AudioSegment]) -> List[Dict[str, Any]]:
        chapters: List[Dict[str, Any]] = []
        current_chapter: Optional[int] = None
        current_start = 0.0
        elapsed = 0.0

        for segment in sorted_segments:
            chapter_index = int(segment.chapter_index or 1)
            if current_chapter is None:
                current_chapter = chapter_index
                current_start = elapsed
            elif chapter_index != current_chapter:
                chapters.append(
                    {
                        "chapter": current_chapter,
                        "title": f"Chapter {current_chapter}",
                        "start_time": current_start,
                        "end_time": elapsed,
                    }
                )
                current_chapter = chapter_index
                current_start = elapsed
            elapsed += max(float(segment.duration_seconds or 0.0), 0.0)

        if current_chapter is not None:
            chapters.append(
                {
                    "chapter": current_chapter,
                    "title": f"Chapter {current_chapter}",
                    "start_time": current_start,
                    "end_time": elapsed,
                }
            )
        return chapters

    def _write_ffmetadata(self, metadata_path: Path, chapters: List[Dict[str, Any]]) -> None:
        lines = [";FFMETADATA1"]
        for chapter in chapters:
            start_ms = int(round(float(chapter["start_time"]) * 1000))
            end_ms = int(round(float(chapter["end_time"]) * 1000))
            if end_ms <= start_ms:
                continue
            title = str(chapter.get("title") or f"Chapter {chapter.get('chapter')}")
            lines.extend(
                [
                    "[CHAPTER]",
                    "TIMEBASE=1/1000",
                    f"START={start_ms}",
                    f"END={end_ms}",
                    f"title={self._escape_ffmetadata(title)}",
                ]
            )
        metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _embed_chapter_markers(self, audio_path: Path, chapters: List[Dict[str, Any]]) -> tuple[bool, Optional[str]]:
        if audio_path.suffix.lower() not in {".mp3", ".m4a", ".m4b"}:
            return False, f"Chapter markers are not embedded for {audio_path.suffix or 'this'} output"
        if not chapters:
            return False, "No chapter metadata to embed"

        metadata_path = audio_path.with_suffix(audio_path.suffix + ".chapters.txt")
        temp_path = audio_path.with_suffix(audio_path.suffix + ".with_chapters" + audio_path.suffix)
        try:
            self._write_ffmetadata(metadata_path, chapters)
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(audio_path),
                    "-i",
                    str(metadata_path),
                    "-map_metadata",
                    "1",
                    "-codec",
                    "copy",
                    "-y",
                    str(temp_path),
                ],
                capture_output=True,
                check=True,
            )
            shutil.move(str(temp_path), str(audio_path))
            return True, None
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
            return False, f"ffmpeg chapter metadata failed: {stderr}"
        except FileNotFoundError:
            return False, "ffmpeg not found"
        except Exception as exc:
            return False, str(exc)
        finally:
            if metadata_path.exists():
                metadata_path.unlink()
            if temp_path.exists():
                temp_path.unlink()

    async def run(self, input_data: AudioFinalizeInput) -> AgentResult:
        try:
            segments = input_data.audio_segments
            if not segments:
                return AgentResult(
                    success=False,
                    error="No audio segments to process",
                )

            output_path = Path(input_data.output_path)
            output_dir = output_path.parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # Sort segments by index
            sorted_segs = sorted(segments, key=lambda s: (s.chapter_index, s.segment_index))
            temp_wav = str(output_dir / f"{output_path.stem}_concat.wav")

            # 1. Concatenate all audio segments
            file_paths = [s.file_path for s in sorted_segs if s.file_path]
            if not file_paths:
                return AgentResult(success=False, error="No valid file paths found in segments")

            if len(file_paths) == 1:
                # Only one file — just copy
                import shutil
                if str(Path(file_paths[0]).absolute()) != str(Path(temp_wav).absolute()):
                    shutil.copy(file_paths[0], temp_wav)
            else:
                ok, err = concatenate_audio(file_paths, temp_wav, format="wav")
                if not ok:
                    return AgentResult(success=False, error=f"Audio concatenation failed: {err}")

            # 2. Normalize if requested
            final_path = str(output_path)
            if input_data.normalize:
                ok, err = normalize_audio(temp_wav, final_path)
                if not ok:
                    if input_data.output_format != "wav":
                        return AgentResult(success=False, error=err or "Audio normalization failed")
                    final_path = temp_wav
            else:
                import shutil
                if input_data.output_format == "wav":
                    if str(Path(temp_wav).absolute()) != str(Path(final_path).absolute()):
                        shutil.copy(temp_wav, final_path)
                else:
                    ok, err = convert_audio_format(temp_wav, final_path, format=input_data.output_format)
                    if not ok:
                        return AgentResult(success=False, error=err or "Audio conversion failed")

            # 3. Add chapter metadata markers after the final encoding step.
            total_duration = sum(s.duration_seconds for s in sorted_segs)
            chapters: List[Dict[str, Any]] = self._build_chapter_metadata(sorted_segs)
            marker_embedded = False
            marker_error = None
            if input_data.add_chapter_markers:
                marker_embedded, marker_error = self._embed_chapter_markers(Path(final_path), chapters)

            # Cleanup temp concat file
            if temp_wav != final_path and Path(temp_wav).exists():
                Path(temp_wav).unlink()

            return AgentResult(
                success=True,
                data=AudioFinalizeOutput(
                    final_audio_path=final_path,
                    total_duration=total_duration,
                    chapters=chapters,
                    metadata={
                        "segment_count": len(sorted_segs),
                        "chapter_markers_embedded": marker_embedded,
                        "chapter_marker_error": marker_error,
                    },
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))
