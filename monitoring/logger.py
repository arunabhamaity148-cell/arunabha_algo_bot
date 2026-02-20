"""
ARUNABHA ALGO BOT - Logger
Custom logging with file rotation and formatting
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional

import config


class BotLogger:
    """
    Custom logger with file rotation and multiple outputs
    """
    
    def __init__(self, name: str = "arunabha"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
        
        # Create logs directory
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Remove existing handlers
        self.logger.handlers.clear()
        
        # Setup handlers
        self._setup_console_handler()
        self._setup_file_handler()
        self._setup_error_handler()
        
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    def _setup_console_handler(self):
        """Setup console handler with color formatting"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, config.LOG_LEVEL))
        
        # Color formatter for console
        class ColorFormatter(logging.Formatter):
            """Add colors to console output"""
            
            COLORS = {
                'DEBUG': '\033[36m',      # Cyan
                'INFO': '\033[32m',       # Green
                'WARNING': '\033[33m',    # Yellow
                'ERROR': '\033[31m',      # Red
                'CRITICAL': '\033[35m',   # Magenta
                'RESET': '\033[0m'         # Reset
            }
            
            def format(self, record):
                log_message = super().format(record)
                color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
                return f"{color}{log_message}{self.COLORS['RESET']}"
        
        console_formatter = ColorFormatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def _setup_file_handler(self):
        """Setup rotating file handler"""
        log_file = self.log_dir / f"{self.name}_{datetime.now().strftime('%Y%m')}.log"
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=config.LOG_MAX_SIZE,
            backupCount=config.LOG_BACKUP_COUNT
        )
        file_handler.setLevel(logging.DEBUG)
        
        file_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
    
    def _setup_error_handler(self):
        """Setup separate error log file"""
        error_file = self.log_dir / f"{self.name}_errors_{datetime.now().strftime('%Y%m')}.log"
        
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=config.LOG_MAX_SIZE,
            backupCount=config.LOG_BACKUP_COUNT
        )
        error_handler.setLevel(logging.ERROR)
        
        error_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        error_handler.setFormatter(error_formatter)
        self.logger.addHandler(error_handler)
    
    def get_logger(self) -> logging.Logger:
        """Get configured logger"""
        return self.logger
    
    @staticmethod
    def log_exception(logger: logging.Logger, exc: Exception, context: str = ""):
        """Log exception with traceback"""
        import traceback
        tb = traceback.format_exc()
        
        if context:
            logger.error(f"Exception in {context}: {exc}")
        else:
            logger.error(f"Exception: {exc}")
        
        logger.debug(f"Traceback:\n{tb}")


# Global logger instance
bot_logger = BotLogger().get_logger()
