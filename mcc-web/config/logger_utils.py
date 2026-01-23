# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    logger_utils.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Utility functions for logger initialization and configuration.

This module provides a helper function to initialize loggers with automatic
logging of the initialization event.
"""
import logging
import sys


def get_logger(name):
    """
    Get or create a logger with the given name and log its initialization.
    
    This function should be used instead of logging.getLogger() directly
    to ensure that logger initialization is logged for debugging purposes.
    Also ensures that logger levels are synchronized with LoggingConfig.
    
    Args:
        name: Logger name (typically __name__ from the calling module)
    
    Returns:
        logging.Logger: The logger instance
    
    Example:
        from config.logger_utils import get_logger
        logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    
    # Ensure logger level is synchronized with LoggingConfig
    # This is done lazily to avoid database access during module import
    try:
        from mgmt.models import LoggingConfig
        config = LoggingConfig.get_config()
        
        # Map LoggingConfig levels to logging module levels
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        target_level = level_map.get(config.min_log_level, logging.INFO)
        
        # Set logger level to match LoggingConfig
        # This ensures DEBUG messages are generated when config is DEBUG
        logger.setLevel(target_level)
    except Exception:
        # If database access fails, use default level from settings
        pass
    
    # Log initialization only once per logger (avoid spam)
    if not hasattr(logger, '_mcc_initialized'):
        logger._mcc_initialized = True
        
        # Get root logger to log initialization
        root_logger = logging.getLogger()
        
        # Log initialization with INFO level
        # Use root logger to avoid recursion and ensure it's always logged
        root_logger.info(
            f"[Logger Init] Logger '{name}' initialized "
            f"(level={logging.getLevelName(logger.level)}, "
            f"effective_level={logging.getLevelName(logger.getEffectiveLevel())}, "
            f"handlers={len(logger.handlers)}, "
            f"propagate={logger.propagate})"
        )
    
    return logger
