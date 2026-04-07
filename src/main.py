"""
Audiobook Generation System - Main Entry Point

Usage:
    python -m src.main --input book.pdf --output ./output
"""

import asyncio
import argparse
from pathlib import Path

from .workflows import AudiobookPipeline
from .workflows.audiobook_pipeline import PipelineConfig
from .services.logging import LoggingService


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Generate audiobook from document"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input document path (PDF, EPUB, TXT)"
    )
    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Output directory"
    )
    parser.add_argument(
        "--format", "-f",
        default="mp3",
        choices=["mp3", "wav", "flac"],
        help="Output audio format"
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Skip audio normalization"
    )
    parser.add_argument(
        "--no-chapters",
        action="store_true",
        help="Don't add chapter markers"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_args()
    
    # Initialize logging
    logger = LoggingService()
    logger.info("Starting audiobook generation", input=args.input)
    
    # Validate input
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure pipeline
    config = PipelineConfig(
        input_file=str(input_path),
        output_dir=str(output_dir),
        output_format=args.format,
        normalize_audio=not args.no_normalize,
        add_chapters=not args.no_chapters
    )
    
    # Run pipeline
    pipeline = AudiobookPipeline(config)
    result = await pipeline.run()
    
    if result["success"]:
        logger.info(
            "Audiobook generation completed",
            output=result.get("output_path"),
            duration=result.get("duration")
        )
        return 0
    else:
        logger.error(
            "Audiobook generation failed",
            error=result.get("error"),
            stage=result.get("stage")
        )
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
