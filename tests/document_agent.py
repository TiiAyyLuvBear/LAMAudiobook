"""
Document Processing Pipeline - Chuyển đổi PDF/EPUB thành JSON chuẩn hóa + SSML cho TTS
Theo 5 Phase: Models -> Extractors -> TextCleaner -> TTSFormatter -> CLI
"""

from __future__ import annotations

import re
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

# ─── Phase 1: Pydantic Models (dùng dataclass thuần vì khônng cần pydantic nặng) ───

class BlockType(str, Enum):
    CHAPTER = "chapter"          # Heading level 1
    SUBTITLE = "subtitle"        # Heading level 2
    BODY = "body"               # Nội dung thường
    TABLE_OF_CONTENT = "table_of_content"  # Mục lục

@dataclass
class DocumentBlock:
    """Một khối nội dung trong tài liệu"""
    level: int                  # 0 = body, 1-3 = heading
    type: BlockType            # enum: chapter/subtitle/body/table_of_content
    text: str
    page: Optional[int] = None
    font_size: Optional[float] = None
    is_bold: bool = False
    source_ref: Optional[str] = None  # path/to/file:page

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "type": self.type.value,
            "text": self.text,
            "page": self.page,
            "font_size": self.font_size,
            "is_bold": self.is_bold,
            "source_ref": self.source_ref,
        }

@dataclass
class ParsedDocument:
    """Tài liệu đã được parse, gồm list các DocumentBlock"""
    blocks: list[DocumentBlock] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "blocks": [b.to_dict() for b in self.blocks],
        }

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def add_block(self, block: DocumentBlock) -> None:
        self.blocks.append(block)


# ─── Phase 2: Base Extractor ───

class BaseExtractor(ABC):
    """Abstract base class cho các extractor"""

    @abstractmethod
    def extract(self, file_path: str) -> ParsedDocument:
        """Trích xuất nội dung từ file"""
        pass

    def _clean_text(self, text: str) -> str:
        """Làm sạch text cơ bản"""
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\S+@\S+\.\S+', '', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\u200b', '', text)  # Zero-width space
        return text.strip()

    def _is_noise_line(self, text: str) -> bool:
        """Kiểm tra dòng có phải noise không"""
        # URL/Link trang web
        if re.search(r'https?://', text): return True
        if re.search(r'www\.|\.com|\.org|\.net', text) and len(text) > 20: return True

        # Số trang đơn lẻ
        if re.fullmatch(r'\s*\d{1,5}\s*', text): return True
        # Dòng kẻ
        if re.fullmatch(r'[-–—_=~]{3,}', text): return True
        # Text quá ngắn không có chữ
        if len(text) <= 2 and not re.search(r'[a-zA-Zà-žÀ-Ž]', text): return True
        # Dòng mục lục: "Tiêu đề .... số_trang"
        if re.search(r'\.{3,}\s*\d+\s*$', text): return True
        return False

    def _strip_dots(self, text: str) -> str:
        """Xóa chuỗi dots và số trang khỏi text"""
        text = re.sub(r'\.{3,}\s*\d+\s*$', '', text)
        text = re.sub(r'\.{3,}\s*$', '', text)
        return text.strip()

    def _is_sentence_ending(self, text: str) -> bool:
        """Kiểm tra text có kết thúc bằng dấu câu không"""
        text = text.strip()
        if not text: return False
        return text[-1] in '.?!。"'

    def _merge_paragraph(self, sentences: list[str]) -> str:
        """Nối các câu lại thành đoạn văn"""
        merged = ' '.join(sentences)
        merged = re.sub(r'\s+', ' ', merged).strip()
        return merged


# ─── Phase 2: PDF Extractor ───

class PDFExtractor(BaseExtractor):
    """
    Trích xuất nội dung từ PDF dùng PyMuPDF (fitz).
    BẮT BUỘC dùng get_text("dict") để lấy metadata font.
    """

    def __init__(
        self,
        top_margin_pct: float = 0.08,
        bottom_margin_pct: float = 0.92,
        body_font_threshold: float = 12.0,  # Font nhỏ hơn = body
        heading_font_min: float = 14.0,      # Font lớn hơn = heading
    ):
        self.top_margin_pct = top_margin_pct
        self.bottom_margin_pct = bottom_margin_pct
        self.body_font_threshold = body_font_threshold
        self.heading_font_min = heading_font_min

        # Pattern nhận diện tiêu đề chương
        self.chapter_pattern = re.compile(
            r'^(Chương\s+[\dIVXLCDM]+[\s:.)]*|'
            r'Chapter\s+[\dIVXLCDM]+[\s:.)]*|'
            r'PHẦN\s+[\w\s]+:|Part\s+[\w\s]+:|'
            r'PHỤ LỤC|MỤC LỤC|LỜI NÓI ĐẦU|LỜI TỰA)',
            re.IGNORECASE,
        )

    def extract(self, file_path: str) -> ParsedDocument:
        """Trích xuất toàn bộ nội dung từ PDF"""
        import fitz  # PyMuPDF

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        doc = fitz.open(file_path)
        document = ParsedDocument()
        document.metadata["source"] = file_path
        document.metadata["total_pages"] = len(doc)

        # Thu thập tất cả items để tính font trung bình
        all_items = self._read_all_items(doc)

        # Tính font trung bình để xác định body
        avg_font = self._calculate_avg_font(all_items)
        print(f"  [PDF] Font trung bình: {avg_font:.1f}pt")

        # Xác định ngưỡng font động dựa trên avg_font
        body_threshold = max(self.body_font_threshold, avg_font * 0.95)
        heading_min = max(self.heading_font_min, avg_font * 1.2)

        total_pages = len(doc)
        # Trích xuất blocks
        raw_blocks = self._extract_blocks(doc, all_items, body_threshold, heading_min)

        # Lọc noise và xóa header/footer
        for block in raw_blocks:
            if self._is_noise_line(block.text):
                continue
            document.add_block(block)

        doc.close()
        print(f"  [PDF] Trích xuất {len(document.blocks)} blocks từ {total_pages} trang")
        return document

    def _read_all_items(self, doc) -> list[dict]:
        """Đọc tất cả items từ PDF"""
        items: list[dict] = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_height = page.rect.height
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        raw_text = span["text"].strip()
                        if not raw_text:
                            continue

                        # Kiểm tra margin
                        y0, y1 = span["bbox"][1], span["bbox"][3]
                        if y0 < page_height * self.top_margin_pct or \
                           y1 > page_height * self.bottom_margin_pct:
                            continue

                        clean = self._clean_text(raw_text)
                        if clean:
                            items.append({
                                "text": clean,
                                "font_size": span["size"],
                                "flags": span.get("flags", 0),
                                "page": page_num + 1,
                                "y0": y0,
                            })
        return items

    def _calculate_avg_font(self, items: list[dict]) -> float:
        """Tính font trung bình của body text (loại bỏ outliers)"""
        if not items:
            return 11.0

        fonts = [item["font_size"] for item in items]
        fonts.sort()
        # Loại bỏ 10% outliers ở cả hai đầu
        trim = len(fonts) // 10
        if trim > 0:
            fonts = fonts[trim:-trim]

        return sum(fonts) / len(fonts) if fonts else 11.0

    def _is_bold(self, flags: int) -> bool:
        """Kiểm tra span có bold không (bit 1 trong flags)"""
        return bool(flags & 1)

    def _classify_level(
        self,
        text: str,
        font_size: float,
        is_bold: bool,
        body_threshold: float,
        heading_min: float,
    ) -> tuple[int, BlockType]:
        """
        Phân loại level dựa trên font size và nội dung.
        Trả về (level, BlockType)
        """
        # Tiêu đề chương đặc biệt
        if self.chapter_pattern.match(text):
            if re.match(r'^(PHẦN|Part)', text, re.IGNORECASE):
                return 1, BlockType.CHAPTER
            return 1, BlockType.CHAPTER

        # Font rất lớn + bold = heading level 1
        if font_size >= heading_min and is_bold:
            if len(text) < 80 and not self._is_sentence_ending(text):
                return 1, BlockType.CHAPTER

        # Font lớn hơn body = heading level 2
        if font_size >= body_threshold * 1.1:
            if len(text) < 80 and not self._is_sentence_ending(text):
                return 2, BlockType.SUBTITLE

        return 0, BlockType.BODY

    def _extract_blocks(
        self,
        doc,
        all_items: list[dict],
        body_threshold: float,
        heading_min: float,
    ) -> list[DocumentBlock]:
        """Trích xuất và phân loại blocks"""
        blocks: list[DocumentBlock] = []
        seen_titles: set[str] = set()  # Tránh trùng tiêu đề

        for item in all_items:
            text = item["text"]
            font_size = item["font_size"]
            flags = item["flags"]
            page = item["page"]

            level, block_type = self._classify_level(
                text, font_size, self._is_bold(flags),
                body_threshold, heading_min
            )

            # Loại bỏ mục lục (TOC)
            if '........' in text and re.search(r'\.+\s*$', text):
                continue

            block = DocumentBlock(
                level=level,
                type=block_type,
                text=text,
                page=page,
                font_size=font_size,
                is_bold=self._is_bold(flags),
                source_ref=f"{doc.name}:{page}" if hasattr(doc, 'name') else f":{page}",
            )
            blocks.append(block)

        return blocks


# ─── Phase 2: EPUB Extractor ───

class EPUBExtractor(BaseExtractor):
    """
    Trích xuất nội dung từ EPUB dùng EbookLib + BeautifulSoup4.
    Map HTML tags: <h1>, <h2>, <h3> -> level 1,2,3; <p> -> level 0 (body)
    """

    def __init__(self):
        self.heading_map = {
            'h1': (1, BlockType.CHAPTER),
            'h2': (2, BlockType.SUBTITLE),
            'h3': (3, BlockType.SUBTITLE),
            'h4': (3, BlockType.SUBTITLE),
            'h5': (3, BlockType.SUBTITLE),
            'h6': (3, BlockType.SUBTITLE),
        }

    def extract(self, file_path: str) -> ParsedDocument:
        """Trích xuất toàn bộ nội dung từ EPUB"""
        from ebooklib import epub
        from bs4 import BeautifulSoup

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        document = ParsedDocument()
        document.metadata["source"] = file_path

        book = epub.read_epub(file_path)

        # Lấy metadata
        try:
            meta = book.get_metadata('DC', 'title')
            if meta:
                document.metadata["title"] = meta[0][0] if meta[0] else ""
        except:
            pass

        # Các loại item có thể chứa text (XHTML/HTML/XML)
        text_types = {1, 7, 8, 9}  # XHTML, HTML, XML, và cả type 9

        # Lặp qua các item trong EPUB
        items_found = 0
        blocks_found = 0
        for item in book.get_items():
            item_type = item.get_type()
            if item_type not in text_types:
                continue

            # Skip nav/cover/titlepage
            name = item.get_name().lower()
            if any(x in name for x in ['nav', 'cover', 'titlepage', 'toc', 'page']):
                continue

            try:
                content = item.get_content()
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='replace')
                elif not isinstance(content, str):
                    content = str(content, 'utf-8', errors='replace')

                soup = BeautifulSoup(content, 'html.parser')

                # Tìm tất cả headings và paragraphs
                for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'span']):
                    text = tag.get_text(separator=' ', strip=True)
                    text = self._clean_text(text)
                    if not text or len(text) < 3:
                        continue

                    tag_name = tag.name.lower()
                    if tag_name in self.heading_map:
                        level, block_type = self.heading_map[tag_name]
                    else:
                        level, block_type = 0, BlockType.BODY

                    block = DocumentBlock(
                        level=level,
                        type=block_type,
                        text=text,
                        source_ref=item.get_name(),
                    )
                    document.add_block(block)
                    blocks_found += 1

                items_found += 1

            except Exception as e:
                continue

        print(f"  [EPUB] Trích xuất {len(document.blocks)} blocks ({items_found} items đọc)")
        return document


# ─── Phase 3: Text Cleaner ───

class TextCleaner:
    """
    Làm sạch text và nối dòng (Line Unbreaking).
    Nhận đầu vào là list[DocumentBlock], trả về list[DocumentBlock] đã xử lý.
    """

    def __init__(self, max_merge_distance: int = 3):
        """
        Args:
            max_merge_distance: Số block liên tiếp không có dấu câu trước khi force break
        """
        self.max_merge_distance = max_merge_distance

        # Các abbr phổ biến tiếng Việt
        self.abbr_map = {
            r'\bđ/c\b': 'đồng chí',
            r'\bĐ/C\b': 'Đồng chí',
            r'\bTP\b': 'Thành phố',
            r'\bTT\b': 'Thị trấn',
            r'\bQĐ\b': 'Quyết định',
            r'\bTTCP\b': 'Thủ tướng Chính phủ',
            r'\bCP\b': 'Chính phủ',
            r'\bTNHH\b': 'Trách nhiệm hữu hạn',
            r'\bCổ phần\b': 'Cổ phần',
            r'\bv\.v\.\b': 'vân vân',
            r'\bv\.v\b': 'vân vân',
        }

    def _is_sentence_ending(self, text: str) -> bool:
        """Kiểm tra text có kết thúc bằng dấu câu không"""
        text = text.strip()
        if not text:
            return False
        return text[-1] in '.?!。"'

    def _merge_paragraph(self, sentences: list[str]) -> str:
        """Nối các câu lại thành đoạn văn"""
        merged = ' '.join(sentences)
        merged = re.sub(r'\s+', ' ', merged).strip()
        return merged

    def clean(self, blocks: list[DocumentBlock]) -> list[DocumentBlock]:
        """Làm sạch và xử lý blocks"""
        cleaned: list[DocumentBlock] = []
        i = 0

        while i < len(blocks):
            block = blocks[i]

            # Bỏ qua blocks mục lục (table_of_content)
            if block.type == BlockType.TABLE_OF_CONTENT:
                i += 1
                continue

            # Headings giữ nguyên
            if block.level > 0:
                block.text = self._expand_abbreviations(block.text)
                cleaned.append(block)
                i += 1
                continue

            # Body: gom nhóm và nối câu
            merged_text, next_i = self._merge_body_blocks(blocks, i)
            if merged_text:
                new_block = DocumentBlock(
                    level=0,
                    type=BlockType.BODY,
                    text=merged_text,
                    page=block.page,
                    source_ref=block.source_ref,
                )
                cleaned.append(new_block)
            i = next_i

        return cleaned

    def _merge_body_blocks(
        self,
        blocks: list[DocumentBlock],
        start_i: int,
    ) -> tuple[Optional[str], int]:
        """Gom nhóm các body blocks và nối câu"""
        sentences: list[str] = []
        i = start_i
        consecutive_non_ending = 0

        while i < len(blocks) and len(sentences) < 50:  # Giới hạn 50 câu/đoạn
            block = blocks[i]

            # Gặp heading mới -> kết thúc
            if block.level > 0:
                break

            text = block.text.strip()
            if not text:
                i += 1
                continue

            # Mở rộng từ viết tắt
            text = self._expand_abbreviations(text)

            # Kiểm tra xem có kết thúc câu không
            if self._is_sentence_ending(text):
                sentences.append(text)
                consecutive_non_ending = 0
            else:
                # Không kết thúc = có thể là dòng bị ngắt
                if sentences and not self._is_sentence_ending(sentences[-1]):
                    sentences[-1] += ' ' + text
                    consecutive_non_ending += 1
                else:
                    sentences.append(text)
                    consecutive_non_ending += 1

                # Force break nếu quá nhiều dòng không có dấu câu
                if consecutive_non_ending >= self.max_merge_distance:
                    break

            i += 1

        if not sentences:
            return None, start_i + 1

        merged = self._merge_paragraph(sentences)
        return merged, i

    def _expand_abbreviations(self, text: str) -> str:
        """Mở rộng từ viết tắt"""
        for pattern, replacement in self.abbr_map.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def remove_duplicate_headers(self, blocks: list[DocumentBlock]) -> list[DocumentBlock]:
        """Xóa header/footer trùng lặp ở nhiều trang"""
        header_counts: dict[str, int] = {}
        page_last_seen: dict[str, int] = {}

        result: list[DocumentBlock] = []
        for block in blocks:
            text_key = block.text[:50].lower()  # Normalize key

            # Đếm số lần xuất hiện
            header_counts[text_key] = header_counts.get(text_key, 0) + 1
            page_last_seen[text_key] = block.page or 0

            # Header xuất hiện ở >3 trang khác nhau = noise
            if header_counts[text_key] > 3:
                if block.page and page_last_seen[text_key] != block.page:
                    continue  # Bỏ qua

            result.append(block)

        return result


# ─── Phase 4: TTS Pre-processor & SSML Injector ───

class TTSFormatter:
    """
    Chuẩn hóa text cho TTS và tạo SSML.
    Đầu vào: ParsedDocument
    Đầu ra: SSML string
    """

    def __init__(self, lang: str = "vi"):
        self.lang = lang

        # Regex cho ngày tháng Việt Nam
        self.date_pattern = re.compile(
            r'(\d{1,2})/(\d{1,2})/(\d{4})|'  # DD/MM/YYYY
            r'(\d{1,2})-(\d{1,2})-(\d{4})|'   # DD-MM-YYYY
            r'(\d{4})-(\d{1,2})-(\d{1,2})'    # YYYY-MM-DD
        )

        # Regex cho số
        self.number_pattern = re.compile(r'\b\d+([.,]\d+)?\b')

    def normalize_text(self, text: str) -> str:
        """Chuẩn hóa text: ngày tháng, số, abbr"""
        text = self._normalize_dates(text)
        text = self._normalize_numbers(text)
        text = self._normalize_special_chars(text)
        return text

    def _normalize_dates(self, text: str) -> str:
        """Chuyển ngày tháng sang cách đọc tiếng Việt"""
        def date_replacer(m: re.Match) -> str:
            # DD/MM/YYYY
            if m.group(1):
                day = self._number_to_words(int(m.group(1)))
                month = self._number_to_words(int(m.group(2)))
                year = self._number_to_words(int(m.group(3)))
                return f"ngày {day} tháng {month} năm {year}"
            # DD-MM-YYYY
            elif m.group(4):
                day = self._number_to_words(int(m.group(4)))
                month = self._number_to_words(int(m.group(5)))
                year = self._number_to_words(int(m.group(6)))
                return f"ngày {day} tháng {month} năm {year}"
            # YYYY-MM-DD
            elif m.group(7):
                day = self._number_to_words(int(m.group(9)))
                month = self._number_to_words(int(m.group(8)))
                year = self._number_to_words(int(m.group(7)))
                return f"ngày {day} tháng {month} năm {year}"
            return m.group(0)

        return self.date_pattern.sub(date_replacer, text)

    def _number_to_words(self, num: int) -> str:
        """Chuyển số sang chữ (cơ bản)"""
        try:
            from num2words import num2words
            return num2words(num, lang='vi')
        except ImportError:
            return str(num)

    def _normalize_numbers(self, text: str) -> str:
        """Chuyển số thành chữ (tùy chọn)"""
        # Chỉ chuyển số điện thoại và số có 4+ chữ số
        def num_replacer(m: re.Match):
            num_str = m.group(0)
            num = float(num_str.replace(',', '.'))

            # Số điện thoại (10-11 số) -> giữ nguyên
            if 1000000000 <= num <= 99999999999:
                return num_str

            # Số lớn (4+ chữ số) -> chuyển sang chữ
            if num >= 1000:
                return self._number_to_words(int(num))

            return num_str

        return self.number_pattern.sub(num_replacer, text)

    def _normalize_special_chars(self, text: str) -> str:
        """Xử lý ký tự đặc biệt"""
        # Thay thế các ký tự đặc biệt
        replacements = {
            '&': 'và',
            '|': 'hoặc',
            '%': 'phần trăm',
            '§': 'điều',
            '€': 'êu rô',
            '$': 'đô la',
            '£': 'pound',
            '¥': 'yen',
            '×': 'nhân',
            '÷': 'chia',
            '≈': 'xấp xỉ',
            '≠': 'khác',
            '≤': 'nhỏ hơn hoặc bằng',
            '≥': 'lớn hơn hoặc bằng',
        }
        for char, word in replacements.items():
            text = text.replace(char, word)
        return text

    def to_ssml(self, blocks: list[DocumentBlock]) -> str:
        """Chuyển blocks thành SSML"""
        ssml_parts = ['<speak version="1.0" xmlns="http://www.w3.org/2006/10/ssml" xml:lang="vi">']

        for block in blocks:
            normalized = self.normalize_text(block.text)

            if block.level == 0:
                # Body: tách câu, bọc <s> mỗi câu
                ssml_parts.append(self._wrap_body(normalized))
            elif block.level == 1:
                # Heading 1: Chapter
                ssml_parts.append(f'<s>{normalized}</s><break time="2s"/>')
            elif block.level >= 2:
                # Heading 2+: Subtitle
                ssml_parts.append(f'<s>{normalized}</s><break time="1s"/>')

        ssml_parts.append('</speak>')
        return '\n'.join(ssml_parts)

    def _wrap_body(self, text: str) -> str:
        """Bọc body text trong thẻ SSML"""
        # Tách câu theo dấu . ? !
        sentences = re.split(r'(?<=[.?!])\s+', text)

        wrapped = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            # Bỏ dấu chấm cuối để đọc tự nhiên hơn
            if sent.endswith('.'):
                sent = sent[:-1]
            wrapped.append(f'<s>{sent}</s><break time="0.5s"/>')

        return '\n'.join(wrapped) if wrapped else f'<s>{text}</s>'


# ─── Phase 5: Document Pipeline (Orchestration) ───

class DocumentPipeline:
    """
    Pipeline chính: kết hợp tất cả các thành phần.
    Extract -> Clean -> Format -> Output
    """

    def __init__(
        self,
        pdf_extractor: Optional[PDFExtractor] = None,
        epub_extractor: Optional[EPUBExtractor] = None,
        text_cleaner: Optional[TextCleaner] = None,
        tts_formatter: Optional[TTSFormatter] = None,
        use_llm_fallback: bool = False,
        llm_api_key: Optional[str] = None,
    ):
        self.pdf_extractor = pdf_extractor or PDFExtractor()
        self.epub_extractor = epub_extractor or EPUBExtractor()
        self.text_cleaner = text_cleaner or TextCleaner()
        self.tts_formatter = tts_formatter or TTSFormatter()
        self.use_llm_fallback = use_llm_fallback
        self.llm_api_key = llm_api_key

    def _split_sentences_for_txt(self, text: str) -> list[str]:
        """Tách nội dung body thành từng câu để xuống dòng trong TXT"""
        text = text.strip()
        if not text:
            return []

        sentences = re.split(r'(?<=[.!?。！？])\s+', text)
        sentences = [sent.strip() for sent in sentences if sent.strip()]
        return sentences if sentences else [text]

    def to_plain_text(self, blocks: list[DocumentBlock]) -> str:
        """
        Xuất văn bản TXT theo cấu trúc:
        - Heading/Chapter nằm trên 1 dòng
        - Giữa các heading/chapter có 1 dòng trống
        - Body: mỗi câu 1 dòng
        """
        lines: list[str] = []

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            if block.level > 0:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(text)
                continue

            for sentence in self._split_sentences_for_txt(text):
                lines.append(sentence)

        # Tránh dòng trống thừa ở cuối file
        while lines and lines[-1] == "":
            lines.pop()

        return '\n'.join(lines)

    def process(self, file_path: str) -> dict:
        """
        Xử lý file PDF/EPUB.
        Trả về dict với keys:
          - document: ParsedDocument (dict format)
          - ssml: SSML string
          - txt: plain text theo cấu trúc heading/body
          - stats: thống kê
        """
        ext = os.path.splitext(file_path)[1].lower()

        # ── Extract ──
        if ext == '.pdf':
            raw_doc = self.pdf_extractor.extract(file_path)
        elif ext in ['.epub', '.pdfepub']:
            raw_doc = self.epub_extractor.extract(file_path)
        else:
            raise ValueError(f"Định dạng không được hỗ trợ: {ext}")

        # ── Clean ──
        cleaned_blocks = self.text_cleaner.clean(raw_doc.blocks)
        cleaned_blocks = self.text_cleaner.remove_duplicate_headers(cleaned_blocks)

        # Cập nhật document đã clean
        cleaned_doc = ParsedDocument(
            blocks=cleaned_blocks,
            metadata=raw_doc.metadata,
        )

        # ── Format to SSML ──
        ssml = self.tts_formatter.to_ssml(cleaned_blocks)
        txt = self.to_plain_text(cleaned_blocks)

        # ── Stats ──
        stats = {
            "total_blocks": len(cleaned_blocks),
            "headings": sum(1 for b in cleaned_blocks if b.level > 0),
            "body_blocks": sum(1 for b in cleaned_blocks if b.level == 0),
            "by_level": {
                f"level_{b.level}": sum(1 for x in cleaned_blocks if x.level == b.level)
                for b in cleaned_blocks
            },
        }

        return {
            "document": cleaned_doc.to_dict(),
            "ssml": ssml,
            "txt": txt,
            "stats": stats,
        }

    def process_to_json(self, file_path: str, output_path: str) -> None:
        """Xử lý và lưu kết quả ra JSON"""
        import json

        result = self.process(file_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  Đã lưu -> {output_path}")
        print(f"  Stats: {result['stats']}")


# ─── CLI Entry Point ───

def _resolve_output_path(input_path: str, output_arg: Optional[str], default_ext: str) -> Optional[str]:
    """Chuẩn hóa output path: hỗ trợ truyền file hoặc thư mục."""
    if not output_arg:
        return None

    output_arg = os.path.expanduser(output_arg)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    default_filename = f"{base_name}{default_ext}"

    # Nếu là thư mục, tự sinh file theo tên input.
    if os.path.isdir(output_arg):
        return os.path.join(output_arg, default_filename)

    # Hỗ trợ trường hợp path kết thúc bằng '/'.
    if output_arg.endswith(os.sep):
        os.makedirs(output_arg, exist_ok=True)
        return os.path.join(output_arg, default_filename)

    parent_dir = os.path.dirname(output_arg)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    return output_arg


def _build_chapter_text(document_dict: dict) -> str:
    """Ghép văn bản theo chương: mỗi câu một dòng, giữa 2 chương có 1 dòng trống."""
    blocks = document_dict.get("blocks", [])
    chapters: list[str] = []
    current_chapter_lines: list[str] = []

    web_link_pattern = re.compile(
        r'(?i)(?:https?://|www\.)\S+|(?:[a-z0-9-]+\.)+(?:com|org|net|vn|io|edu|gov)(?:/\S*)?'
    )

    def clean_web_tags(text: str) -> str:
        cleaned = web_link_pattern.sub(' ', text)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if not cleaned:
            return ''
        if re.fullmatch(r'[\W_]+', cleaned):
            return ''
        return cleaned

    def split_sentences(text: str) -> list[str]:
        normalized = re.sub(r'\s+', ' ', text).strip()
        if not normalized:
            return []
        sentences = re.split(r'(?<=[.!?…])\s+', normalized)
        cleaned_sentences: list[str] = []
        for sentence in sentences:
            cleaned_sentence = clean_web_tags(sentence)
            if cleaned_sentence:
                cleaned_sentences.append(cleaned_sentence)
        return cleaned_sentences

    def flush_chapter() -> None:
        if not current_chapter_lines:
            return
        chapter_text = '\n'.join(current_chapter_lines).strip()
        if chapter_text:
            chapters.append(chapter_text)

    for block in blocks:
        text = str(block.get("text", "")).strip()
        if not text:
            continue

        level = int(block.get("level", 0) or 0)
        lines = split_sentences(text)
        if not lines:
            continue

        if level == 1:
            flush_chapter()
            current_chapter_lines = lines[:]
        else:
            current_chapter_lines.extend(lines)

    flush_chapter()
    return '\n\n'.join(chapters)

def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Chuyển đổi PDF/EPUB thành JSON + SSML + TXT cho TTS Audiobook"
    )
    parser.add_argument('--input', '-i', required=True, help='Đường dẫn file đầu vào (PDF/EPUB)')
    parser.add_argument('--output', '-o', default=None, help='Đường dẫn file đầu ra (JSON)')
    parser.add_argument('--ssml', '-s', default=None, help='Đường dẫn file SSML đầu ra')
    parser.add_argument('--txt', '-t', default=None, help='Đường dẫn file TXT đầu ra')
    parser.add_argument('--lang', '-l', default='vi', help='Ngôn ngữ (mặc định: vi)')
    parser.add_argument('--no-clean', action='store_true', help='Bỏ qua bước clean text')
    parser.add_argument('--api-key', '-k', default=None, help='API key cho LLM fallback')

    args = parser.parse_args()

    # Tạo pipeline
    pipeline = DocumentPipeline(
        use_llm_fallback=bool(args.api_key),
        llm_api_key=args.api_key,
    )

    print(f"Xử lý: {args.input}")
    result = pipeline.process(args.input)

    # Lưu JSON
    output_json_path = _resolve_output_path(args.input, args.output, '.json')
    if output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  JSON -> {output_json_path}")

    # Lưu SSML riêng
    output_ssml_path = _resolve_output_path(args.input, args.ssml, '.ssml')
    if output_ssml_path:
        with open(output_ssml_path, 'w', encoding='utf-8') as f:
            f.write(result['ssml'])
        print(f"  SSML -> {args.ssml}")

    # Lưu TXT riêng
    if args.txt:
        with open(args.txt, 'w', encoding='utf-8') as f:
            f.write(result['txt'])
        print(f"  TXT -> {args.txt}")

    # In stats
    print(f"\nStats:")
    print(f"  Total blocks: {result['stats']['total_blocks']}")
    print(f"  Headings: {result['stats']['headings']}")
    print(f"  Body blocks: {result['stats']['body_blocks']}")


if __name__ == "__main__":
    main()
