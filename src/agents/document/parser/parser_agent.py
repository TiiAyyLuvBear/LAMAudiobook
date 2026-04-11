# """
# Parser Agent - Extracts text blocks from various document formats.
# """

# from typing import Any, Dict, List, Optional
# from dataclasses import dataclass

# from ...base import BaseAgent, AgentResult


# @dataclass
# class TextBlock:
#     """A block of text extracted from document"""
#     text: str
#     page: int
#     block_type: str  # "paragraph", "heading", "list", etc.
#     position: Optional[Dict[str, int]] = None


# @dataclass
# class ParserInput:
#     """Input for Parser Agent"""
#     file_path: str
#     file_type: str
#     needs_ocr: bool = False


# @dataclass
# class ParserOutput:
#     """Output from Parser Agent"""
#     blocks: List[TextBlock]
#     total_pages: int
#     metadata: Dict[str, Any]


# class ParserAgent(BaseAgent):
#     """
#     Extracts text blocks from documents (PDF, EPUB, TXT).
    
#     Handles:
#     - PDF parsing (with optional OCR)
#     - EPUB extraction
#     - Plain text processing
#     """
    
#     def __init__(self, config: Optional[Dict[str, Any]] = None):
#         super().__init__(name="parser", config=config)
    
#     async def run(self, input_data: ParserInput) -> AgentResult:
#         """
#         Parse document and extract text blocks.
        
#         Args:
#             input_data: ParserInput with file path and type
            
#         Returns:
#             AgentResult with ParserOutput containing text blocks
#         """
#         try:
#             # TODO: Implement actual parsing logic
#             # - PDF: use PyMuPDF or pdfplumber
#             # - EPUB: use ebooklib
#             # - OCR: use pytesseract if needed
            
#             blocks = []
            
#             return AgentResult(
#                 success=True,
#                 data=ParserOutput(
#                     blocks=blocks,
#                     total_pages=0,
#                     metadata={"file": input_data.file_path}
#                 )
#             )
            
#         except Exception as e:
#             return AgentResult(success=False, error=str(e))

# TA test code for audio_preprocess.py, which is used by ParserAgent to preprocess PDF files into structured chapters and paragraphs.
"""
Parser Agent - Extracts text blocks from various document formats.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from ...base import BaseAgent, AgentResult
from .audio_preprocess import preprocess_pdf


@dataclass
class TextBlock:
    """A block of text extracted from document"""
    text: str
    page: int
    block_type: str  # "paragraph", "heading", "list", etc.
    position: Optional[Dict[str, int]] = None


@dataclass
class ParserInput:
    """Input for Parser Agent"""
    file_path: str
    file_type: str
    needs_ocr: bool = False


@dataclass
class ParserOutput:
    """Output from Parser Agent"""
    blocks: List[TextBlock]
    total_pages: int
    metadata: Dict[str, Any]


class ParserAgent(BaseAgent):
    """
    Extracts text blocks from documents (PDF, EPUB, TXT).
    
    Handles:
    - PDF parsing (with optional OCR)
    - EPUB extraction
    - Plain text processing
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="parser", config=config)

    def _to_parser_input(self, input_data: Any) -> ParserInput:
        """Support both dataclass and dict inputs from workflow."""
        if isinstance(input_data, ParserInput):
            return input_data
        if isinstance(input_data, dict):
            return ParserInput(
                file_path=input_data.get("file_path", ""),
                file_type=input_data.get("file_type", ""),
                needs_ocr=bool(input_data.get("needs_ocr", False)),
            )
        raise ValueError("ParserInput must be ParserInput or dict")

    def _parse_txt_file(self, file_path: str) -> List[TextBlock]:
        """Minimal TXT fallback parser."""
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [
            TextBlock(text=paragraph, page=1, block_type="paragraph")
            for paragraph in paragraphs
        ]

    def _parse_epub_fallback(self, file_path: str) -> List[TextBlock]:
        """Minimal EPUB fallback parser when ebooklib is not installed."""
        path = Path(file_path)
        raw = path.read_text(encoding="utf-8", errors="ignore")
        chunks = [c.strip() for c in raw.split("\n\n") if c.strip()]
        return [TextBlock(text=chunk, page=1, block_type="paragraph") for chunk in chunks]
    
    async def run(self, input_data: ParserInput) -> AgentResult:
        """
        Parse document and extract text blocks.
        
        Args:
            input_data: ParserInput with file path and type
            
        Returns:
            AgentResult with ParserOutput containing text blocks
        """
        try:
            parsed_input = self._to_parser_input(input_data)
            file_type = parsed_input.file_type.lower()
            blocks: List[TextBlock] = []
            metadata: Dict[str, Any] = {
                "file": parsed_input.file_path,
                "file_type": file_type,
                "needs_ocr": parsed_input.needs_ocr,
            }

            if file_type == "pdf":
                chapters = preprocess_pdf(parsed_input.file_path)
                for chapter in chapters:
                    chapter_title = chapter.get("chapter_title", "")
                    for paragraph in chapter.get("paragraphs", []):
                        paragraph_text = paragraph.get("text", "").strip()
                        if not paragraph_text:
                            continue

                        page = int(paragraph.get("page_start", 1))
                        block_type = "heading" if paragraph_text == chapter_title else "paragraph"
                        blocks.append(
                            TextBlock(
                                text=paragraph_text,
                                page=page,
                                block_type=block_type,
                                position=None,
                            )
                        )

                metadata["chapters"] = chapters
                metadata["total_chapters"] = len(chapters)

            elif file_type == "txt":
                blocks = self._parse_txt_file(parsed_input.file_path)
                metadata["total_chapters"] = 1

            elif file_type == "epub":
                blocks = self._parse_epub_fallback(parsed_input.file_path)
                metadata["total_chapters"] = 1

            else:
                raise ValueError(f"Unsupported file_type: {file_type}")

            total_pages = max((block.page for block in blocks), default=0)
            
            return AgentResult(
                success=True,
                data=ParserOutput(
                    blocks=blocks,
                    total_pages=total_pages,
                    metadata=metadata,
                )
            )
            
        except Exception as e:
            return AgentResult(success=False, error=str(e))
