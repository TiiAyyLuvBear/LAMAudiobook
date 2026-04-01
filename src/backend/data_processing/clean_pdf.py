import re
import os
import unicodedata
import logging
import pdfplumber
from collections import Counter

logging.getLogger("pdfminer").setLevel(logging.ERROR)

class UltimatePDFCleaner:
    def __init__(self):
        self.garbage_phrases = ["Ồ Ằ", "Ổ Ầ", "Ồ Ầ", "Ể "]

        self.meta_keywords = [
            "Copyright", "Cataloging", "NXB", "NHÀ XUẤT BẢN",
            "Publishing House", "THƯ VIỆN"
        ]

        self.meta_connectors = ["-", "--", "–", "và", ":", ","]

    # =========================
    # 🔥 NEW: REMOVE FOOTER LINK
    # =========================
    def remove_footer_noise(self, text):
        if not text:
            return ""

        # Xoá URL (xử lý case dính khoảng trắng, vd https://thuviensach. vn)
        text = re.sub(r'(?i)(?:https?:\s*//|www\s*\.)[^\s]+\s*\.\s*[a-z]+', ' ', text)

        # Xoá domain dạng abc.com (xử lý khoảng trắng và dấu gạch ngang vd dtv-ebook . com)
        text = re.sub(r'(?i)\b(?:www\s*\.\s*)?[\w-]+\s*\.\s*(?:com|vn|net|org|info)\b', ' ', text)
        
        text = re.sub(r'(?i)\b(?:thuviensach|dtv-ebook|tve-4u|sachvui|isach|taisachhay|epub|www)\b', ' ', text)

        # Xoá dòng kiểu ebook watermark
        if re.search(r'(ebook|pdf|download|tải xuống)', text, re.IGNORECASE):
            return ""

        return text.strip()

    # =========================
    # 🔥 NEW: REMOVE TOC
    # =========================
    def is_table_of_content(self, text):
        if not text:
            return False

        text_low = text.lower()

        # "Mục lục"
        if "mục lục" in text_low:
            return True

        # "Chương 1-10"
        if re.match(r'chương\s*\d+[-–]\d+', text_low):
            return True

        # chỉ toàn số range
        if re.match(r'^\d+[-–]\d+$', text):
            return True

        return False

    # =========================
    # 🔥 FIX TEXT DÍNH
    # =========================
    def fix_sticky_words(self, text):
        viet_lower = "a-zàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
        viet_upper = "A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
        
        # chữ thường dính chữ hoa → tách
        text = re.sub(rf'([{viet_lower}])([{viet_upper}])', r'\1 \2', text)

        # chữ + số
        text = re.sub(rf'([{viet_lower}{viet_upper}])(\d)', r'\1 \2', text)
        text = re.sub(rf'(\d)([{viet_lower}{viet_upper}])', r'\1 \2', text)

        return text

    def clean_string(self, text):
        if not text:
            return ""

        text = unicodedata.normalize('NFKC', text)

        text = self.remove_footer_noise(text)

        if text in self.garbage_phrases:
            return ""

        # FIX WORD DÍNH
        text = self.fix_sticky_words(text)

        # fix dấu câu
        text = re.sub(r'\s+([,.:;!?])', r'\1', text)

        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def split_sentences(self, text):
        if not text:
            return []

        text = re.sub(r'\s+', ' ', text).strip()

        # 1. Bảo vệ các từ viết tắt phổ biến để không bị cắt xén
        abbreviations = ["Tp.", "TP.", "T.P.", "Th.S.", "PGS.", "TS.", "ThS.", "Ths.", "vs.", "v.v.", "St.", "GS.", "BS.", "GS.TS.", "PGS.TS.", "Mr.", "Mrs.", "Dr."]
        for abbr in abbreviations:
            text = text.replace(abbr, abbr.replace('.', '__DOT__'))

        # 2. Bảo vệ các tên viết tắt định dạng "A.", "B.", "J. C.", v.v.
        viet_upper = "A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
        text = re.sub(rf'\b([{viet_upper}])\.(?=\s)', r'\1__DOT__', text)

        # Split pattern handling Vietnamese upper case and NOT splitting continuous dots like `...`
        pattern = rf'(?<=[.?!])(?<!\.\.)\s+(?=[{viet_upper}\"\'])'

        return [s.strip().replace('__DOT__', '.') for s in re.split(pattern, text) if s.strip()]

    def get_lines_with_meta(self, page):
        words = page.extract_words(extra_attrs=['size'])
        # Cắt lề trên dưới để loại bỏ số trang và header cố định
        words = [w for w in words if 40 < w['top'] < 790]
        if not words:
            return []

        all_sizes = [w['size'] for w in words]
        page_body_size = Counter(all_sizes).most_common(1)[0][0]

        words.sort(key=lambda w: w['top'])

        lines_cluster = []
        current = [words[0]]

        for w in words[1:]:
            avg_top = sum(x['top'] for x in current) / len(current)
            if abs(w['top'] - avg_top) < 6:
                current.append(w)
            else:
                lines_cluster.append(current)
                current = [w]

        lines_cluster.append(current)

        processed_lines = []

        for cluster in lines_cluster:
            cluster.sort(key=lambda w: w['x0'])
            text = " ".join(w['text'] for w in cluster)

            text = self.clean_string(text)

            # ❌ bỏ TOC và các dòng quá ngắn đặc trưng của rác
            if self.is_table_of_content(text):
                continue
                
            if len(text) <= 5 and not re.search(r'[A-Za-zÀ-Ỹà-ỹ]', text):
                continue # Nếu là số trang hoặc ký tự lặt vặt (không có chữ cái) thì bỏ

            if text:
                processed_lines.append({
                    "text": text,
                    "size": round(max(w['size'] for w in cluster), 1)
                })

        return processed_lines

    def analyze_font_structure(self, all_lines):
        sizes = [l['size'] for l in all_lines]
        return Counter(sizes).most_common(1)[0][0]

    def process_hybrid_structure(self, all_lines, body_size):
        final = []
        buffer = []

        def ends_with_abbreviation(s):
            s = s.strip()
            words = s.split()
            if not words: return False
            last_word = words[-1]
            if last_word in ["Tp.", "TP.", "T.P.", "Th.S.", "PGS.", "TS.", "ThS.", "Ths.", "vs.", "v.v.", "St.", "GS.", "BS.", "GS.TS.", "PGS.TS.", "Mr.", "Mrs.", "Dr."]:
                return True
            if re.match(r'^[A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]\.$', last_word):
                return True
            return False

        def is_end_of_sentence(s):
            s = s.strip()
            if re.search(r'\.{3,}["\']?$', s): return False
            if ends_with_abbreviation(s): return False
            return bool(re.search(r'[.?!]["\']?$', s))

        def is_continue_punct(s):
            s = s.strip()
            if re.search(r'\.{3,}["\']?$', s): return True
            return bool(re.search(r'[,:;-]["\']?$', s))

        for line in all_lines:
            text = line['text'].strip()
            if not text: continue

            # ❌ bỏ dòng ALL CAPS dài (title rác)
            if text.isupper() and len(text) > 20:
                continue

            if buffer:
                prev = buffer[-1].strip()

                if not is_end_of_sentence(prev):
                    is_prev_title_or_meta = (len(prev) < 40 and not is_continue_punct(prev)) or prev.isupper()
                    if text[0].islower() or text[0].isdigit() or is_continue_punct(prev) or ends_with_abbreviation(prev) or not is_prev_title_or_meta:
                        buffer[-1] = prev + " " + text
                    else:
                        final.extend(self.split_sentences(" ".join(buffer)))
                        buffer = [text]
                else:
                    final.extend(self.split_sentences(" ".join(buffer)))
                    buffer = [text]
            else:
                buffer.append(text)

        if buffer:
            final.extend(self.split_sentences(" ".join(buffer)))

        # Ensure all content lines end with a period if missing (except short title/metadata)
        result = []
        for f in final:
            f = f.strip()
            if not f: continue
            if len(f) > 50 and not is_end_of_sentence(f):
                f += '.'
            result.append(f)

        return result

    def extract_and_clean(self, pdf_path, output_txt_path):
        print(f"Đang xử lý: {pdf_path}")
        all_lines = []

        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                print(f"Trang {i+1}/{len(pdf.pages)}", end='\r')
                all_lines.extend(self.get_lines_with_meta(page))

        print("\nĐang xử lý text...")

        body_size = self.analyze_font_structure(all_lines)
        final_lines = self.process_hybrid_structure(all_lines, body_size)

        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(final_lines))

        print("✅ Done:", output_txt_path)


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    INPUT_FOLDER = os.path.join(BASE_DIR, "books_pdf")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "clean_text")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    cleaner = UltimatePDFCleaner()

    pdf_files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith(".pdf")]

    if not pdf_files:
        print("❌ Không tìm thấy file PDF")
    else:
        for pdf_file in pdf_files:
            input_path = os.path.join(INPUT_FOLDER, pdf_file)
            output_path = os.path.join(
                OUTPUT_FOLDER,
                pdf_file.replace(".pdf", ".txt")
            )

            print(f"\n📘 Processing: {pdf_file}")
            cleaner.extract_and_clean(input_path, output_path)