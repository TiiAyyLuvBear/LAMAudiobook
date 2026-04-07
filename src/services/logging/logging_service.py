"""
Logging Service - Centralized logging for the application.
"""

import logging
import sys
from typing import Optional
from datetime import datetime
from pathlib import Path


class LoggingService:
    """
    Centralized logging service.
    
    Features:
    - Console and file logging
    - Structured log format
    - Log level configuration
    - Job-specific logging
    """
    
    _instance: Optional["LoggingService"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        log_dir: str = "./logs",
        log_level: int = logging.INFO,
        console_output: bool = True
    ):
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure root logger
        self.logger = logging.getLogger("audiobook")
        self.logger.setLevel(log_level)
        
        # Console handler
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(self._get_formatter())
            self.logger.addHandler(console_handler)
        
        # File handler
        log_file = self.log_dir / f"audiobook_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(self._get_formatter())
        self.logger.addHandler(file_handler)
    
    def _get_formatter(self) -> logging.Formatter:
        """Get log formatter"""
        return logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a named logger"""
        return self.logger.getChild(name)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self.logger.info(self._format_message(message, kwargs))
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self.logger.debug(self._format_message(message, kwargs))
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self.logger.warning(self._format_message(message, kwargs))
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        self.logger.error(self._format_message(message, kwargs))
    
    def _format_message(self, message: str, context: dict) -> str:
        """Format message with context"""
        if context:
            context_str = " | ".join(f"{k}={v}" for k, v in context.items())
            return f"{message} | {context_str}"
        return message


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    service = LoggingService()
    return service.get_logger(name)
