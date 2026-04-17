"""
CLI entry point for audiobook generation.

Usage:
    python -m src.main --input book.pdf --output ./output
    python -m src.main -i book.pdf -o ./output -f mp3 --no-normalize
"""
import argparse
import asyncio
import logging
from pathlib import Path

from pipeline import AudiobookPipeline, PipelineConfig


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Audiobook Generation Pipeline")
    parser.add_argument(
        "-i", "--input", required=True,
        help="Input file (PDF, EPUB, TXT)",
    )
    parser.add_argument(
        "-o", "--output", default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "-f", "--format", default="mp3",
        choices=["mp3", "wav", "m4a"],
        help="Output audio format (default: mp3)",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Skip audio normalization",
    )
    parser.add_argument(
        "--no-chapters",
        action="store_true",
        help="Skip chapter markers",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        log.error(f"Input file not found: {args.input}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        input_file=str(input_path.resolve()),
        output_dir=str(output_dir.resolve()),
        output_format=args.format,
        normalize_audio=not args.no_normalize,
        add_chapters=not args.no_chapters,
    )

    pipeline = AudiobookPipeline(config)
    log.info(f"Starting pipeline: {input_path.name}")

    result = await pipeline.run()

    if result["success"]:
        log.info(f"✅ Audiobook generated: {result['output_path']}")
        log.info(f"   Duration: {result['duration']:.1f}s")
        log.info(f"   Chapters: {len(result.get('chapters', []))}")
        return 0
    else:
        log.error(f"❌ Pipeline failed: {result.get('error')}")
        log.error(f"   Stage: {result.get('stage')}")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))