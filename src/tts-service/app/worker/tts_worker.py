import os
from typing import Dict, Any
from ..engines.base import BaseTTSEngine

_engine_instance = None

def get_engine() -> BaseTTSEngine:
    global _engine_instance
    if _engine_instance is None:
        engine_type = os.getenv("ENGINE_TYPE", "vieneu").lower()
        if engine_type == "xtts":
            from ..engines.xtts import XTTSEngine
            _engine_instance = XTTSEngine()
        else:
            from ..engines.vieneu import VieNeuEngine
            _engine_instance = VieNeuEngine()
    return _engine_instance

def synthesize_batch(request_dict: Dict[str, Any]) -> Dict[str, Any]:
    engine = get_engine()
    segments = request_dict.get("segments", [])
    
    results = []
    failed = []
    
    for seg in segments:
        try:
            output_path = seg["output_path"]
            engine.synthesize(
                text=seg["text"],
                voice_id=seg["voice_id"],
                speed=seg.get("speed", 1.0),
                pitch=seg.get("pitch", 1.0),
                output_path=output_path
            )
            
            duration = 1.0
            import wave
            import contextlib
            try:
                with contextlib.closing(wave.open(output_path, 'r')) as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    duration = frames / float(rate) if rate > 0 else 1.0
            except Exception:
                pass
                
            results.append({
                "file_path": output_path,
                "duration_seconds": duration,
                "segment_index": seg["segment_index"],
                "chapter_index": seg["chapter_index"],
                "text": seg["text"][:50],
                "voice_id": seg["voice_id"]
            })
        except Exception as e:
            failed.append(seg["segment_index"])
            print(f"Failed to synthesize segment {seg['segment_index']}: {e}")

    total_duration = sum(s["duration_seconds"] for s in results)
    
    return {
        "audio_segments": results,
        "total_duration": total_duration,
        "failed_segments": failed,
        "metadata": {"segment_count": len(segments)}
    }
