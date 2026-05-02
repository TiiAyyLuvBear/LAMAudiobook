import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pipeline.audiobook import AudiobookPipeline
from pipeline.config import PipelineConfig

async def run_test():
    print("--- STARTING PIPELINE ON book_pdf/3.epub ---")
    
    config = PipelineConfig(
        input_file="book_pdf/3.epub",
        output_dir="tests/mock_output_book",
        output_format="mp3"
    )
    
    pipeline = AudiobookPipeline(config)
    result = await pipeline.run()
    
    if result["success"]:
        print(f">>> Pipeline Succeeded!")
        print(f"Output: {result.get('output_path')}")
        print(f"Total Duration: {result.get('duration')}s")
    else:
        print(f">>> Pipeline Failed!")
        print(f"Error: {result.get('error')}")
        print(f"Stage: {result.get('stage')}")

if __name__ == "__main__":
    asyncio.run(run_test())
