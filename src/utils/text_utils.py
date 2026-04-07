"""
Text utilities for text processing.
"""

import re
from typing import List


def normalize_text(text: str) -> str:
    """
    Normalize text for TTS processing.
    
    - Remove extra whitespace
    - Normalize unicode
    - Fix common issues
    """
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Normalize quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    
    # Normalize dashes
    text = text.replace('–', '-').replace('—', '-')
    
    return text


def split_sentences(text: str, language: str = "vi") -> List[str]:
    """
    Split text into sentences.
    
    Args:
        text: Input text
        language: Language code
        
    Returns:
        List of sentences
    """
    # Simple sentence splitting
    # For Vietnamese, we need to be careful with abbreviations
    
    # Split on common sentence endings
    pattern = r'(?<=[.!?])\s+'
    sentences = re.split(pattern, text)
    
    # Clean up
    sentences = [s.strip() for s in sentences if s.strip()]
    
    return sentences


def chunk_text(text: str, max_chars: int = 500) -> List[str]:
    """
    Split text into chunks suitable for TTS.
    
    Tries to split at sentence boundaries.
    """
    sentences = split_sentences(text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += (" " + sentence) if current_chunk else sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def detect_dialogue(text: str) -> bool:
    """
    Detect if text contains dialogue.
    
    Looks for quoted text patterns.
    """
    # Vietnamese dialogue patterns
    patterns = [
        r'"[^"]+?"',  # Double quotes
        r"'[^']+?'",  # Single quotes
        r"-\s*[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ]",  # Dialogue dash
    ]
    
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    
    return False
