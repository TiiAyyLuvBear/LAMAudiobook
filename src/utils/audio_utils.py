"""
Audio utilities for audio processing.
"""

import subprocess
import wave
from pathlib import Path
from typing import Optional


def get_audio_duration(file_path: str) -> float:
    """
    Get duration of audio file in seconds.
    
    Uses ffprobe if available, otherwise returns 0.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            capture_output=True,
            text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def convert_audio_format(
    input_path: str,
    output_path: str,
    format: str = "mp3",
    bitrate: str = "192k"
) -> tuple[bool, Optional[str]]:
    """
    Convert audio to different format.
    """
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-b:a", bitrate,
                "-y",
                output_path
            ],
            capture_output=True,
            check=True
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, f"ffmpeg conversion failed: {e.stderr.decode() if e.stderr else str(e)}"
    except FileNotFoundError:
        return False, "ffmpeg not found"
    except Exception as e:
        return False, str(e)


def normalize_audio(
    input_path: str,
    output_path: str,
    target_loudness: float = -16.0
) -> tuple[bool, Optional[str]]:
    """
    Normalize audio volume using loudnorm filter.
    """
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-af", f"loudnorm=I={target_loudness}:TP=-1.5:LRA=11",
                "-y",
                output_path
            ],
            capture_output=True,
            check=True
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, f"ffmpeg normalization failed: {e.stderr.decode() if e.stderr else str(e)}"
    except FileNotFoundError:
        return False, "ffmpeg not found"
    except Exception as e:
        return False, str(e)


def concatenate_audio(
    input_files: list,
    output_path: str,
    format: str = "wav"
) -> tuple[bool, Optional[str]]:
    """
    Concatenate multiple audio files.
    Returns (success, error_message).
    """
    list_path = Path(output_path).parent / "concat_list.txt"
    def _concat_wav_fallback() -> tuple[bool, Optional[str]]:
        try:
            params = None
            with wave.open(output_path, "wb") as out_wav:
                for index, input_file in enumerate(input_files):
                    with wave.open(str(input_file), "rb") as in_wav:
                        if index == 0:
                            params = in_wav.getparams()
                            out_wav.setparams(params)
                        elif in_wav.getparams()[:3] != params[:3]:
                            return False, "WAV fallback requires matching channels, sample width, and frame rate"
                        out_wav.writeframes(in_wav.readframes(in_wav.getnframes()))
            return True, None
        except Exception as exc:
            return False, str(exc)

    try:
        # Create concat file list with forward slashes for ffmpeg compatibility
        with open(list_path, "w", encoding="utf-8") as f:
            for file_path in input_files:
                # Convert to absolute path and use forward slashes
                p = Path(file_path).absolute().as_posix()
                f.write(f"file '{p}'\n")
        
        # Try fast concatenation with stream copy
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(list_path),
                    "-c", "copy",
                    "-y",
                    output_path
                ],
                capture_output=True,
                check=True
            )
            return True, None
        except subprocess.CalledProcessError as e:
            # Fallback: re-encode if stream copy fails
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", str(list_path),
                        "-y",
                        output_path
                    ],
                    capture_output=True,
                    check=True
                )
                return True, None
            except subprocess.CalledProcessError as e2:
                return False, f"ffmpeg failed: {e2.stderr.decode() if e2.stderr else str(e2)}"
        except FileNotFoundError:
            if format == "wav":
                return _concat_wav_fallback()
            return False, "ffmpeg command not found. Please install ffmpeg."
            
    except Exception as e:
        return False, str(e)
    finally:
        if list_path.exists():
            list_path.unlink()
