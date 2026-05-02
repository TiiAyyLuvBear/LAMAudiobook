import asyncio
import sys
import os

# To avoid namespace collision with python's built-in "types" module, 
# we need to be careful with sys.path. 
# We'll just run it and let the standard exception happen if the folder is still 'types'.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.voice import VoiceAgent, VoiceInput
from agents.tts import TTSAgent
from schema.audio import TTSSegment, TTSGeneratorInput
from utils.tts_engine import RealXTTSEngine

async def run_test():
    print("--- STARTING PIPELINE TEST ---")
    
    # 1. Test VoiceAgent
    print("\n[1] Testing Voice Agent (Qdrant Vector Matching)")
    voice_agent = VoiceAgent()
    
    # Simulating Phase 1 Output
    speakers = ["narrator", "Thỏ Ngọc", "Rùa Con"]
    char_emotions = {
        "Thỏ Ngọc": "nhẹ nhàng, vui vẻ",
        "Rùa Con": "trầm ấm, chậm rãi"
    }
    
    # Test multi-speaker semantic mapping
    v_input_multi = VoiceInput(
        speakers=speakers, 
        speaker_mode="multi",
        book_summary="Một câu chuyện cổ tích thiếu nhi về cuộc thi chạy giữa Thỏ và Rùa.",
        book_mood="vui tươi, thiếu nhi",
        character_emotions=char_emotions
    )
    v_out_multi = await voice_agent.run(v_input_multi)
    
    if v_out_multi.success:
        print(">> Multi-Mode Output (Vector Matching):")
        for va in v_out_multi.data.voice_assignments:
            print(f"   Speaker: {va.speaker:15} -> Voice ID: {va.voice_id}")
    else:
        print(f"   VoiceAgent Multi failed: {v_out_multi.error}")

    # 2. Test TTSAgent
    print("\n[2] Testing TTS Agent (RealXTTSEngine Linking & Caching)")
    tts_agent = TTSAgent(engine=RealXTTSEngine(voice_dir="data/voice_samples"))
    
    # Simulating segments with different emotions

    segments = [
        TTSSegment(
            text="Trời hôm nay thật đẹp!", 
            voice_id="female_hcm_02", 
            emotion="happy", 
            intensity=1.0,
            chapter_index=1, 
            segment_index=1
        ),
        TTSSegment(
            text="Nhưng sao mình cảm thấy chậm quá...", 
            voice_id="male_hn_01", 
            emotion="sad", 
            intensity=0.8,
            chapter_index=1, 
            segment_index=2
        ),
        # Test Cache Hit (same data)
        TTSSegment(
            text="Trời hôm nay thật đẹp!", 
            voice_id="female_hcm_02", 
            emotion="happy", 
            intensity=1.0,
            chapter_index=1, 
            segment_index=3
        ),
    ]
    
    tts_input = TTSGeneratorInput(segments=segments, output_dir="tests/mock_output")
    tts_out = await tts_agent.run(tts_input)
    
    if tts_out.success:
        print(">> TTS Agent Output:")
        for a in tts_out.data.audio_segments:
            print(f"   [Ch{a.chapter_index}-Seg{a.segment_index}] File: {a.file_path} | Text: '{a.text}' | Duration: {a.duration_seconds:.2f}s")
        print(f"   Total Duration: {tts_out.data.total_duration:.2f}s | Success Rate: {tts_out.data.metadata['success_rate']*100}%")
    else:
        print(f"   [!] TTSAgent failed: {tts_out.error}")

if __name__ == "__main__":
    asyncio.run(run_test())
