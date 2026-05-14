"""
Minimal EPUB3 chapter packager.
"""

from __future__ import annotations

import html
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from schema.audio import AudioSegment
from utils.audio_utils import concatenate_audio


@dataclass
class ChapterEpubResult:
    chapter_index: int
    title: str
    epub_path: str
    segment_count: int
    chapter_audio_path: str
    audio_files: List[str]


def _slug(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return value or fallback


def _write_epub_file(epub_path: Path, files_dir: Path, opf: str, nav: str, chapter_xhtml: str) -> None:
    epub_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = epub_path.with_suffix(epub_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    with zipfile.ZipFile(tmp_path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/package.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/chapter.xhtml", chapter_xhtml)
        for audio_file in sorted(files_dir.glob("*.wav")):
            zf.write(audio_file, f"OEBPS/audio/{audio_file.name}")

    shutil.move(str(tmp_path), str(epub_path))


def package_chapter_epub(
    *,
    output_dir: str | Path,
    chapter_index: int,
    title: str,
    paragraphs: Iterable[str],
    audio_segments: Iterable[AudioSegment],
) -> ChapterEpubResult:
    """
    Create an EPUB3 file for one completed chapter.

    The EPUB contains one XHTML page. Each generated sentence/segment is rendered as
    clickable inline text, with audio bound to that sentence. A chapter-level
    WAV is also bundled for consumers that want a single audio file per chapter.
    """
    base_dir = Path(output_dir) / "chapters"
    chapter_slug = f"chapter_{chapter_index:04d}_{_slug(title, 'untitled')}"
    chapter_dir = base_dir / chapter_slug
    audio_dir = chapter_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    sorted_segments = sorted(audio_segments, key=lambda s: s.segment_index)
    copied_audio: List[str] = []
    sentence_spans: List[str] = []
    for segment in sorted_segments:
        source = Path(segment.file_path)
        if not source.exists():
            continue
        audio_name = f"seg_{segment.segment_index:04d}.wav"
        target = audio_dir / audio_name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        copied_audio.append(audio_name)
        sentence_spans.append(
            f'<a class="sentence" href="audio/{html.escape(audio_name)}" '
            f'data-audio="audio/{html.escape(audio_name)}">'
            f"{html.escape(segment.text)}</a>"
        )

    safe_title = title.strip() or f"Chapter {chapter_index}"
    escaped_title = html.escape(safe_title)
    chapter_audio_name = f"chapter_{chapter_index:04d}.wav"
    chapter_audio_path = audio_dir / chapter_audio_name
    copied_paths = [str(audio_dir / name) for name in copied_audio]
    if copied_paths:
        if len(copied_paths) == 1:
            shutil.copyfile(copied_paths[0], chapter_audio_path)
        else:
            ok, err = concatenate_audio(copied_paths, str(chapter_audio_path), format="wav")
            if not ok:
                raise RuntimeError(f"Chapter audio concatenation failed: {err}")

    if sentence_spans:
        text_blocks = f"<p>{' '.join(sentence_spans)}</p>"
    else:
        text_blocks = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs if p.strip())

    chapter_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head>
  <title>{escaped_title}</title>
  <meta charset="utf-8"/>
  <style>
    body {{ font-family: serif; line-height: 1.55; }}
    .sentence {{ cursor: pointer; border-bottom: 1px dotted #777; }}
    .sentence:focus, .sentence:hover {{ background: #fff3b0; outline: none; }}
    .sentence.playing {{ background: #d9f0ff; }}
    .audio-bar {{ display: flex; gap: 0.75rem; align-items: center; margin: 1rem 0; }}
    .audio-label {{ font-family: sans-serif; font-size: 0.9rem; }}
    audio {{ width: 100%; max-width: 42rem; }}
  </style>
  <script>
  //<![CDATA[
  document.addEventListener("DOMContentLoaded", function () {{
    var player = document.getElementById("sentence-player");
    var active = null;
    function playSentence(node, event) {{
      if (event) {{
        event.preventDefault();
      }}
      if (active) {{
        active.classList.remove("playing");
      }}
      active = node;
      active.classList.add("playing");
      player.src = node.getAttribute("data-audio");
      player.currentTime = 0;
      player.play();
    }}
    document.querySelectorAll(".sentence").forEach(function (node) {{
      node.addEventListener("click", function (event) {{ playSentence(node, event); }});
      node.addEventListener("keydown", function (event) {{
        if (event.key === "Enter" || event.key === " ") {{
          playSentence(node, event);
        }}
      }});
    }});
    player.addEventListener("ended", function () {{
      if (active) {{
        active.classList.remove("playing");
      }}
      active = null;
    }});
  }});
  //]]>
  </script>
</head>
<body>
  <h1>{escaped_title}</h1>
  <div class="audio-bar" aria-label="Chapter audio">
    <span class="audio-label">Chapter audio</span>
    <audio id="chapter-player" controls="controls" preload="metadata" src="audio/{html.escape(chapter_audio_name)}"></audio>
  </div>
  <div class="audio-bar" aria-label="Sentence audio">
    <span class="audio-label">Sentence audio</span>
    <audio id="sentence-player" controls="controls" preload="none"></audio>
  </div>
  <section epub:type="chapter">
    {text_blocks}
  </section>
</body>
</html>
"""

    nav = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head><title>Navigation</title><meta charset="utf-8"/></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Contents</h1>
    <ol><li><a href="chapter.xhtml">{escaped_title}</a></li></ol>
  </nav>
</body>
</html>
"""

    manifest_audio = "\n".join(
        f'    <item id="audio-{idx}" href="audio/{html.escape(name)}" media-type="audio/wav"/>'
        for idx, name in enumerate(copied_audio)
    )
    manifest_chapter_audio = (
        f'    <item id="chapter-audio" href="audio/{html.escape(chapter_audio_name)}" media-type="audio/wav"/>'
        if chapter_audio_path.exists()
        else ""
    )
    book_id = f"urn:uuid:{uuid.uuid4()}"
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="vi">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{escaped_title}</dc:title>
    <dc:language>vi</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
{manifest_chapter_audio}
{manifest_audio}
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>
"""

    epub_path = base_dir / f"{chapter_slug}.epub"
    _write_epub_file(epub_path, audio_dir, opf, nav, chapter_xhtml)

    return ChapterEpubResult(
        chapter_index=chapter_index,
        title=safe_title,
        epub_path=str(epub_path),
        segment_count=len(sorted_segments),
        chapter_audio_path=str(chapter_audio_path),
        audio_files=[str(audio_dir / name) for name in [chapter_audio_name, *copied_audio]],
    )
