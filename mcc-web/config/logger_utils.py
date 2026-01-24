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
    
    # Set logger level based on LoggingConfig (efficient filtering at logger level)
    # This prevents unnecessary log message creation and formatting
    # This will be called again by mgmt.apps.MgmtConfig when database is ready
    _sync_logger_level(logger, name)
    
    # Log initialization only once per logger (avoid spam)
    if not hasattr(logger, '_mcc_initialized'):
        logger._mcc_initialized = True
        
        # Log initialization using the logger itself (not root logger)
        # This ensures the log goes to the correct handler (api_file, mgmt_file, etc.)
        # Use INFO level so it's visible when LoggingConfig allows INFO logs
        # But only log if the logger level allows it (to avoid spam when level is WARNING)
        if logger.isEnabledFor(logging.INFO):
            log_record = logger.makeRecord(
                logger.name,
                logging.INFO,
                __file__,
                0,
                f"[Logger Init] Logger '{name}' initialized "
                f"(level={logging.getLevelName(logger.level)}, "
                f"effective_level={logging.getLevelName(logger.getEffectiveLevel())}, "
                f"handlers={len(logger.handlers)}, "
                f"propagate={logger.propagate})",
                (),
                None
            )
            logger.handle(log_record)
    
    return logger


def _sync_logger_level(logger, logger_name):
    """
    Synchronize logger level with LoggingConfig from database.
    
    This function reads the LoggingConfig and sets the logger level accordingly.
    This ensures efficient filtering at the logger level, preventing unnecessary
    log message creation and formatting.
    
    Args:
        logger: The logger instance to update
        logger_name: The name of the logger (e.g., 'api', 'api.views')
    """
    # Map logger name to app name (e.g., 'api.views' -> 'api')
    app_name = logger_name.split('.')[0]
    
    # Only update application loggers (api, mgmt, iot, kiosk, game, map, leaderboard, minecraft)
    if app_name not in ['api', 'mgmt', 'iot', 'kiosk', 'game', 'map', 'leaderboard', 'minecraft']:
        return
    
    try:
        # Try to get configuration from database
        from mgmt.models import LoggingConfig
        
        config = LoggingConfig.get_config()
        min_log_level = config.min_log_level
        
        # Map string level to logging constant
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        
        target_level = level_map.get(min_log_level, logging.WARNING)
        logger.setLevel(target_level)
        
    except Exception:
        # If database access fails (e.g., during migrations), use WARNING as default
        # This ensures that INFO logs are not written if database is not ready
        # The level will be updated by mgmt.apps.MgmtConfig when database is ready
        logger.setLevel(logging.WARNING)
