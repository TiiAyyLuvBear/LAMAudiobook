from pathlib import Path
import sys
import zipfile

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from schema.audio import AudioSegment  # noqa: E402
from utils.epub3_packager import package_chapter_epub  # noqa: E402


def test_package_chapter_epub_uses_windows_safe_chapter_paths(tmp_path):
    source_audio = tmp_path / "segment.wav"
    source_audio.write_bytes(b"not-a-real-wav")
    long_title = "28.-T-I-C-G-P-B-C-N-U-NH-" + ("very-long-" * 30) + "..."

    result = package_chapter_epub(
        output_dir=tmp_path,
        chapter_index=28,
        title=long_title,
        paragraphs=["Noi dung chuong"],
        audio_segments=[
            AudioSegment(
                file_path=str(source_audio),
                duration_seconds=1.0,
                segment_index=1,
                chapter_index=28,
                text="Noi dung chuong",
            )
        ],
    )

    epub_path = Path(result.epub_path)
    assert epub_path.exists()
    assert epub_path.name.startswith("chapter_0028_")
    assert not epub_path.stem.endswith(".")
    assert len(epub_path.stem) < 120

    with zipfile.ZipFile(epub_path) as zf:
        assert "OEBPS/audio/seg_0001.wav" in zf.namelist()
