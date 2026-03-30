import os
import re
import glob
import logging
import pdfplumber
import unicodedata
from collections import Counter

# Tắt cảnh báo và log rác từ pdfminer để console sạch sẽ
logging.getLogger("pdfminer").setLevel(logging.ERROR)

class PDFToTextProcessor:
    """
    A robust, OOP-based processor for extracting and cleaning text from PDF files,
    specifically tailored for generating high-quality text for TTS (e.g., XTTSv2) 
    training in Vietnamese.
    """
    
    def __init__(self, input_dir, output_dir):
        """
        Initialize the processor with input and output directories.
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        
        # Create the output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Character set rules for Vietnamese
        viet_lower = "a-zàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
        viet_upper = "A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
        self.viet_chars = viet_lower + viet_upper

    def process_folder(self):
        """
        Processes ALL PDF files in the specified input directory and saves 
        the cleaned text into the output directory.
        """
        pdf_files = glob.glob(os.path.join(self.input_dir, "*.pdf"))
        
        if not pdf_files:
            print(f"❌ No PDF files found in: {self.input_dir}")
            return
            
        print(f"📂 Found {len(pdf_files)} PDF file(s). Starting extraction...\n")
        
        for idx, pdf_path in enumerate(pdf_files, 1):
            file_name = os.path.basename(pdf_path)
            output_name = file_name.replace(".pdf", ".txt")
            output_path = os.path.join(self.output_dir, output_name)
            
            print(f"[{idx}/{len(pdf_files)}] Processing: {file_name}")
            
            # Step 1: Extract and merge lines using layout context
            raw_text = self.extract_lines(pdf_path)
            
            # Step 2: Split text into proper sentences
            sentences = self.split_sentences(raw_text)
            
            # Step 3: Filter invalid/too long/too short sentences
            valid_sentences = [s for s in sentences if self.is_valid_sentence_for_tts(s)]
            
            # Step 4: Save to file
            if valid_sentences:
                self.save_to_file(valid_sentences, output_path)
                print(f"   => ✅ Saved {len(valid_sentences)} valid sentences to: {output_name}\n")
            else:
                print(f"   => ⚠️ Warning: No valid sentences found in {file_name}\n")

        print("🎉 All files processed successfully!")

    def extract_lines(self, pdf_path):
        """
        Extracts words from PDF and groups them into lines based on Y-axis (top coordinate).
        Also merges broken physical lines into a continuous block of text.
        """
        all_clean_lines = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages, 1):
                    # Print progress on the same line
                    print(f"   - Scanning Page {page_num}/{total_pages}", end='\r')
                    
                    # Extract words with bounding box properties
                    words = page.extract_words(extra_attrs=['size'])
                    # Filter out header/footer words (heuristically, top < 40 or top > 790 for A4 size)
                    words = [w for w in words if 40 < w['top'] < 790]
                    if not words:
                        continue
                    
                    # Cluster words into lines:
                    # We group by Y-axis (rounded to nearest 3 points) to tolerate minor baseline shifts.
                    # Then we sort by X-axis (left-to-right)
                    words.sort(key=lambda w: (round(w['top'] / 3) * 3, w['x0']))
                    
                    current_line_words = []
                    current_y = round(words[0]['top'] / 3) * 3
                    
                    lines_in_page = []
                    
                    for w in words:
                        w_y = round(w['top'] / 3) * 3
                        if abs(w_y - current_y) <= 3:
                            current_line_words.append(w['text'])
                        else:
                            # New line detected
                            lines_in_page.append(" ".join(current_line_words))
                            current_line_words = [w['text']]
                            current_y = w_y
                    
                    # Append the last line
                    if current_line_words:
                        lines_in_page.append(" ".join(current_line_words))
                        
                    # Process lines in the current page
                    for raw_line in lines_in_page:
                        # Clean the line to remove space issues and noise
                        clean_line = self.clean_text(raw_line)
                        if self.is_valid_content(clean_line):
                            all_clean_lines.append(clean_line)
                            
        except Exception as e:
            print(f"\n   ❌ Error extracting {pdf_path}: {e}")
            
        print() # Add new line to break the \r progress indicator
        
        # Merge all lines across pages into one giant text block. 
        # (This helps sentences split across multiple lines or pages to be unified).
        full_text = " ".join(all_clean_lines)
        return full_text

    def clean_text(self, text):
        """
        Cleans the extracted text by fixing broken characters, removing noise, 
        fixing spaces, and applying Unicode normalization.
        """
        # Normalize Unicode safely
        text = unicodedata.normalize("NFC", text.strip())
        
        # 1. Remove systemic PDF noise
        noise_patterns = [
            r"Trang\s+\d+",       # e.g., "Trang 1", "Trang 12"
            r"cid:\d+",          # e.g., "cid:123"
            r"cid\d+",           # e.g., "cid123"
            r"^\d+$",            # Standalone page numbers on a line
        ]
        for pattern in noise_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            
        # Clean Table of Content dot leaders: "Chương 1 ......... 12" -> "Chương 1 12"
        text = re.sub(r'(?:\.\s*){3,}', ' ', text)
            
        # 2. Fix broken Vietnamese words (e.g., "c ơ ch ế" -> "cơ chế")
        text = self.fix_broken_vietnamese(text)
        
        # 3. Clean weird symbols but retain letters, standard punctuations, numbers, and basic math symbols
        text = re.sub(rf"[^{self.viet_chars}0-9\s.,!?:;'\"()<>\-\/%]", " ", text)
        
        # 4. Fix spacing issues
        text = re.sub(r'\s+', ' ', text) # Compress duplicate spaces
        text = re.sub(r'\s+([.,!?:;])', r'\1', text) # Remove space before punctuation
        text = re.sub(r'([.,!?:;])([A-Za-z])', r'\1 \2', text) # Add space after punctuation if missing
        
        # 5. Normalize quotation marks to straight quotes
        text = re.sub(r'[“”]', '"', text)
        text = re.sub(r"[‘’]", "'", text)
        text = re.sub(r'"\s+', '"', text)
        text = re.sub(r'\s+"', '"', text)
        
        return text.strip()

    def fix_broken_vietnamese(self, text):
        """
        Fix broken Vietnamese characters caused by PDF character placement.
        Specifically handles torn words like: "c ơ ch ế" -> "cơ chế", "nh ững" -> "những".
        """
        # Vietnamese isolated consonants & vowels definitions
        consonants = "b|c|ch|d|đ|g|gh|gi|h|k|kh|l|m|n|ng|ngh|nh|p|ph|q|qu|r|s|t|th|tr|v|x"
        vowels = "[a-eioquyàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ]+"
        
        # Rule: A standalone consonant followed by a space, then immediate vowels.
        # Ensure we stay within word bounds using negative lookarounds.
        pattern_cv = re.compile(
            rf'(?<![{self.viet_chars}])({consonants})\s+({vowels})(?![{self.viet_chars}])', 
            re.IGNORECASE
        )
        
        # Execute twice to handle adjacent sequences, e.g., "c ơ ch ế"
        text = pattern_cv.sub(r'\1\2', text)
        text = pattern_cv.sub(r'\1\2', text)
        
        return text

    def split_sentences(self, text):
        """
        Splits merged text blocks into distinct sentences, respecting Vietnamese layout 
        and avoiding splitting at known abbreviations.
        """
        # 1. Protect abbreviations (replace with placeholders to avoid bad splitting)
        abbreviations = ["Tp.", "T.P.", "Th.S.", "PGS.", "TS.", "ThS.", "Ths.", "vs.", "v.v.", "St."]
        for i, abbr in enumerate(abbreviations):
            text = text.replace(abbr, f"__ABBR_{i}__")
            
        # 2. Advanced Regex split: Split by '.', '!', '?' followed by a space and an uppercase letter (or quote)
        viet_upper_chars = "A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
        split_pattern = rf'(?<=[.!?])\s+(?=[{viet_upper_chars}"\'])'
        
        raw_sentences = re.split(split_pattern, text)
        
        # 3. Clean up and restore abbreviations
        final_sentences = []
        for sentence in raw_sentences:
            sentence = sentence.strip()
            # Restore abbreviation strings
            for i, abbr in enumerate(abbreviations):
                sentence = sentence.replace(f"__ABBR_{i}__", abbr)
            
            if sentence:
                final_sentences.append(sentence)
                
        return final_sentences

    def is_valid_content(self, text):
        """
        Filters out low-quality lines before cross-page text merging.
        Ideal for pruning raw numerical lines (e.g. metadata tables, indices).
        """
        # Exclude very short isolated artifacts or pure numbers
        if not text or len(text) < 2: return False
        if text.isdigit(): return False
        
        # Exclude lines that are mostly symbols/numbers and not actual written text
        letters = re.findall(rf'[{self.viet_chars}]', text)
        if len(letters) < (len(text) * 0.4): # Require at least 40% real letters
            return False
            
        return True
        
    def is_valid_sentence_for_tts(self, sentence):
        """
        Determines if a sentence length and content quality is suitable for TTS.
        """
        # Filter based on sentence length specs
        if len(sentence) < 10:
            return False
        if len(sentence) > 300:
            return False
            
        # Must contain at least one Vietnamese letter
        if not re.search(rf'[{self.viet_chars}]', sentence):
            return False
            
        return True

    def save_to_file(self, sentences, output_path):
        """
        Saves a list of processed sentences to a .txt file. 
        Ensures sentences are unique while preserving file order. Each sentence gets ONE line.
        """
        unique_sentences = list(dict.fromkeys(sentences))
        with open(output_path, 'w', encoding='utf-8') as f:
            for s in unique_sentences:
                f.write(s + "\n")


if __name__ == "__main__":
    # Configure absolute paths to guarantee it runs flawlessly from any working directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INPUT_FOLDER = os.path.join(BASE_DIR, "books_pdf")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "clean_text")
    
    # Initialize processor
    processor = PDFToTextProcessor(input_dir=INPUT_FOLDER, output_dir=OUTPUT_FOLDER)
    
    # Run directory processing
    processor.process_folder()