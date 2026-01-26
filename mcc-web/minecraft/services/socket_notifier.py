# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    socket_notifier.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unix Socket-based notification system for Minecraft Worker.

This module provides a simple notification mechanism using Unix domain sockets
to notify the Minecraft Worker when new events are available, eliminating the
need for constant polling.
"""

import os
import socket
import struct
from pathlib import Path
from django.conf import settings
from config.logger_utils import get_logger

logger = get_logger("minecraft")


def get_socket_path() -> Path:
    """Get the path to the Unix socket file."""
    # Use DATA_DIR for production, BASE_DIR for development
    if hasattr(settings, 'DATA_DIR'):
        socket_dir = settings.DATA_DIR / 'tmp'
    else:
        socket_dir = Path(settings.BASE_DIR) / 'tmp'
    
    socket_dir.mkdir(parents=True, exist_ok=True)
    return socket_dir / 'minecraft_worker.sock'


def notify_worker(event_id: int = None):
    """
    Send a notification to the worker via Unix socket.
    
    Args:
        event_id: Optional event ID to send (currently not used, but reserved for future use)
    
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    socket_path = get_socket_path()
    
    try:
        # Create Unix domain socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        
        # Set socket to non-blocking to avoid hanging if worker is not listening
        sock.settimeout(0.1)
        
        # Send a simple notification (just a byte to wake up the worker)
        # In the future, we could send event_id here
        try:
            sock.sendto(b'\x01', str(socket_path))
            logger.debug(f"[socket_notifier] Sent notification to worker (socket: {socket_path})")
            return True
        except FileNotFoundError:
            # Worker is not listening - this is OK, fallback polling will handle it
            logger.debug(f"[socket_notifier] Worker not listening (socket: {socket_path})")
            return False
        except OSError as e:
            # Socket error - log but don't fail
            logger.debug(f"[socket_notifier] Socket error: {e}")
            return False
        finally:
            sock.close()
    except Exception as e:
        # Any other error - log but don't fail
        logger.warning(f"[socket_notifier] Failed to send notification: {e}")
        return False


def wait_for_notification(timeout: float = None) -> bool:
    """
    Wait for a notification from Django via Unix socket.
    
    Args:
        timeout: Maximum time to wait in seconds (None = blocking wait)
    
    Returns:
        bool: True if notification was received, False if timeout
    """
    socket_path = get_socket_path()
    
    # Remove old socket if it exists
    if socket_path.exists():
        try:
            socket_path.unlink()
        except OSError:
            pass
    
    try:
        # Create Unix domain socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        
        # Bind to socket path
        sock.bind(str(socket_path))
        
        # Set permissions so Django can write to it
        os.chmod(socket_path, 0o666)
        
        # Set timeout if specified
        if timeout is not None:
            sock.settimeout(timeout)
        
        try:
            # Wait for notification
            data, _ = sock.recvfrom(1)
            logger.debug(f"[socket_notifier] Received notification from Django")
            return True
        except socket.timeout:
            # Timeout - this is expected when no events arrive
            return False
        finally:
            sock.close()
            # Clean up socket file
            if socket_path.exists():
                try:
                    socket_path.unlink()
                except OSError:
                    pass
    except Exception as e:
        logger.error(f"[socket_notifier] Error waiting for notification: {e}")
        return False
