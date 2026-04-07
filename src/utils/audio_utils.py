"""
Audio utilities for audio processing.
"""

import subprocess
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
) -> bool:
    """
    Convert audio to different format.
    
    Uses ffmpeg for conversion.
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
        return True
    except Exception:
        return False


def normalize_audio(
    input_path: str,
    output_path: str,
    target_loudness: float = -16.0
) -> bool:
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
        return True
    except Exception:
        return False


def concatenate_audio(
    input_files: list,
    output_path: str,
    format: str = "wav"
) -> bool:
    """
    Concatenate multiple audio files.
    """
    try:
        # Create concat file list
        list_path = Path(output_path).parent / "concat_list.txt"
        with open(list_path, "w") as f:
            for file_path in input_files:
                f.write(f"file '{file_path}'\n")
        
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
        
        # Cleanup
        list_path.unlink()
        return True
        
    except Exception:
        return False
