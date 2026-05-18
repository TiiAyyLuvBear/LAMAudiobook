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



@dataclass
class BookEpubResult:
    epub_path: str
    chapter_count: int
    segment_count: int
    audio_files: List[str]


def _sentence_player_script() -> str:
    return '''
  <script>
  //<![CDATA[
  document.addEventListener("DOMContentLoaded", function () {
    var player = document.getElementById("sentence-player");
    var active = null;
    function playSentence(node, event) {
      if (event) { event.preventDefault(); }
      if (active) { active.classList.remove("playing"); }
      active = node;
      active.classList.add("playing");
      player.src = node.getAttribute("data-audio");
      player.currentTime = 0;
      player.play();
    }
    document.querySelectorAll(".sentence").forEach(function (node) {
      node.addEventListener("click", function (event) { playSentence(node, event); });
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { playSentence(node, event); }
      });
    });
    player.addEventListener("ended", function () {
      if (active) { active.classList.remove("playing"); }
      active = null;
    });
  });
  //]]>
  </script>
'''


def _chapter_xhtml(
    *,
    title: str,
    chapter_index: int,
    audio_segments: List[AudioSegment],
    audio_prefix: str,
    chapter_audio_name: str,
    paragraphs: Iterable[str],
) -> str:
    escaped_title = html.escape(title.strip() or f"Chapter {chapter_index}")
    sentence_spans: List[str] = []
    for segment in sorted(audio_segments, key=lambda s: s.segment_index):
        audio_name = f"seg_{segment.segment_index:04d}.wav"
        href = f"{audio_prefix}/{audio_name}"
        sentence_spans.append(
            f'<a class="sentence" href="{html.escape(href)}" '
            f'data-audio="{html.escape(href)}">'
            f"{html.escape(segment.text)}</a>"
        )
    text_blocks = (
        f"<p>{' '.join(sentence_spans)}</p>"
        if sentence_spans
        else "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs if p.strip())
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
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
{_sentence_player_script()}
</head>
<body>
  <h1>{escaped_title}</h1>
  <div class="audio-bar" aria-label="Chapter audio">
    <span class="audio-label">Chapter audio</span>
    <audio id="chapter-player" controls="controls" preload="metadata" src="{html.escape(audio_prefix)}/{html.escape(chapter_audio_name)}"></audio>
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
'''


def package_book_epub(
    *,
    output_dir: str | Path,
    title: str,
    chapters: Iterable[object],
    audio_segments: Iterable[AudioSegment],
    output_filename: str | None = None,
) -> BookEpubResult:
    """Create one EPUB3 containing every generated chapter and all sentence/chapter audio."""
    output_dir = Path(output_dir)
    book_dir = output_dir / "book_epub3"
    audio_root = book_dir / "audio"
    if book_dir.exists():
        shutil.rmtree(book_dir)
    audio_root.mkdir(parents=True, exist_ok=True)

    chapter_lookup = {int(getattr(chapter, "index", 0)) + 1: chapter for chapter in chapters}
    segments_by_chapter: dict[int, List[AudioSegment]] = {}
    for segment in audio_segments:
        source = Path(segment.file_path)
        if not source.exists():
            raise RuntimeError(f"Missing audio segment for full EPUB3: {source}")
        segments_by_chapter.setdefault(int(segment.chapter_index or 1), []).append(segment)
    if not segments_by_chapter:
        raise RuntimeError("No audio segments available for full EPUB3")

    book_title = title.strip() or "Audiobook"
    escaped_book_title = html.escape(book_title)
    book_id = f"urn:uuid:{uuid.uuid4()}"
    manifest_items = ['    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
    spine_items: List[str] = []
    nav_items: List[str] = []
    xhtml_files: dict[str, str] = {}
    audio_files: List[Path] = []

    for chapter_index in sorted(segments_by_chapter):
        chapter = chapter_lookup.get(chapter_index)
        chapter_title = getattr(chapter, "title", None) or getattr(chapter, "chapter_title", None) or f"Chapter {chapter_index}"
        paragraphs = getattr(chapter, "paragraphs", []) if chapter else []
        chapter_segments = sorted(segments_by_chapter[chapter_index], key=lambda s: s.segment_index)
        chapter_audio_dir = audio_root / f"chapter_{chapter_index:04d}"
        chapter_audio_dir.mkdir(parents=True, exist_ok=True)

        copied_paths: List[str] = []
        for segment in chapter_segments:
            audio_name = f"seg_{segment.segment_index:04d}.wav"
            target = chapter_audio_dir / audio_name
            shutil.copyfile(segment.file_path, target)
            copied_paths.append(str(target))
            audio_files.append(target)
            manifest_items.append(
                f'    <item id="audio-c{chapter_index:04d}-s{segment.segment_index:04d}" href="audio/chapter_{chapter_index:04d}/{audio_name}" media-type="audio/wav"/>'
            )

        chapter_audio_name = f"chapter_{chapter_index:04d}.wav"
        chapter_audio_path = chapter_audio_dir / chapter_audio_name
        if len(copied_paths) == 1:
            shutil.copyfile(copied_paths[0], chapter_audio_path)
        else:
            ok, err = concatenate_audio(copied_paths, str(chapter_audio_path), format="wav")
            if not ok:
                raise RuntimeError(f"Full EPUB3 chapter audio concatenation failed for chapter {chapter_index}: {err}")
        audio_files.append(chapter_audio_path)
        manifest_items.append(
            f'    <item id="audio-c{chapter_index:04d}-chapter" href="audio/chapter_{chapter_index:04d}/{chapter_audio_name}" media-type="audio/wav"/>'
        )

        chapter_file = f"chapter_{chapter_index:04d}.xhtml"
        chapter_id = f"chapter-{chapter_index:04d}"
        manifest_items.append(f'    <item id="{chapter_id}" href="{chapter_file}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'    <itemref idref="{chapter_id}"/>')
        nav_items.append(f'      <li><a href="{chapter_file}">{html.escape(str(chapter_title))}</a></li>')
        xhtml_files[chapter_file] = _chapter_xhtml(
            title=str(chapter_title),
            chapter_index=chapter_index,
            audio_segments=chapter_segments,
            audio_prefix=f"audio/chapter_{chapter_index:04d}",
            chapter_audio_name=chapter_audio_name,
            paragraphs=paragraphs,
        )

    nav = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head><title>{escaped_book_title}</title><meta charset="utf-8"/></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{escaped_book_title}</h1>
    <ol>
{chr(10).join(nav_items)}
    </ol>
  </nav>
</body>
</html>
'''
    opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="vi">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{escaped_book_title}</dc:title>
    <dc:language>vi</dc:language>
  </metadata>
  <manifest>
{chr(10).join(manifest_items)}
  </manifest>
  <spine>
{chr(10).join(spine_items)}
  </spine>
</package>
'''

    epub_name = _epub_filename(output_filename, _slug(book_title, 'audiobook'))
    epub_path = output_dir / epub_name
    tmp_path = epub_path.with_suffix(epub_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
'''
    with zipfile.ZipFile(tmp_path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/package.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        for chapter_file, chapter_xhtml in xhtml_files.items():
            zf.writestr(f"OEBPS/{chapter_file}", chapter_xhtml)
        for audio_file in sorted(audio_files):
            zf.write(audio_file, f"OEBPS/audio/{audio_file.parent.name}/{audio_file.name}")
    shutil.move(str(tmp_path), str(epub_path))
    embedded_audio_files = [f"OEBPS/audio/{audio_file.parent.name}/{audio_file.name}" for audio_file in audio_files]
    shutil.rmtree(book_dir, ignore_errors=True)

    return BookEpubResult(
        epub_path=str(epub_path),
        chapter_count=len(segments_by_chapter),
        segment_count=sum(len(v) for v in segments_by_chapter.values()),
        audio_files=embedded_audio_files,
    )

def _epub_filename(filename: str | None, fallback_stem: str) -> str:
    if filename:
        path = Path(filename).name.strip()
        if path:
            return str(Path(path).with_suffix(".epub"))
    return f"{fallback_stem}.epub"


def _slug(value: str, fallback: str, max_length: int = 80) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._ ")
    value = re.sub(r"-{2,}", "-", value)
    value = re.sub(r"\.{2,}", ".", value)
    value = value[:max_length].rstrip("-._ ")
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
