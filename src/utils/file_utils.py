"""
File utilities for file operations.
"""

import os
import hashlib
from pathlib import Path
from typing import Optional


def ensure_dir(path: str) -> str:
    """
    Ensure directory exists, create if not.
    
    Returns the path.
    """
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def get_file_hash(file_path: str, algorithm: str = "md5") -> str:
    """
    Calculate hash of a file.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (md5, sha256, etc.)
        
    Returns:
        Hex digest of file hash
    """
    hash_func = hashlib.new(algorithm)
    
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    return os.path.getsize(file_path)


def get_file_extension(file_path: str) -> str:
    """Get file extension (lowercase, without dot)"""
    return Path(file_path).suffix.lower().lstrip(".")


def safe_filename(filename: str) -> str:
    """
    Make filename safe for filesystem.
    
    Removes/replaces problematic characters.
    """
    # Characters not allowed in filenames
    invalid_chars = '<>:"/\\|?*'
    
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip(". ")
    
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    
    return filename


def list_files(
    directory: str,
    extensions: Optional[list] = None,
    recursive: bool = False
) -> list:
    """
    List files in directory.
    
    Args:
        directory: Directory path
        extensions: List of extensions to filter (e.g., ['.mp3', '.wav'])
        recursive: Search subdirectories
        
    Returns:
        List of file paths
    """
    dir_path = Path(directory)
    
    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"
    
    files = []
    for file_path in dir_path.glob(pattern):
        if file_path.is_file():
            if extensions is None or file_path.suffix.lower() in extensions:
                files.append(str(file_path))
    
    return sorted(files)
