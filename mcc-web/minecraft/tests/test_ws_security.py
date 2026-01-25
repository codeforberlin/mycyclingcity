# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_ws_security.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Minecraft WebSocket security.

Tests cover:
- sign_payload
- verify_signature
"""

import pytest
from unittest.mock import patch
from django.conf import settings

from minecraft.services.ws_security import sign_payload, verify_signature


@pytest.mark.unit
class TestWebSocketSecurity:
    """Tests for WebSocket security functions."""
    
    def test_sign_payload(self):
        """Test signing a payload."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        
        signature = sign_payload(payload)
        
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest length
    
    def test_sign_payload_deterministic(self):
        """Test that signing the same payload produces the same signature."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        
        signature1 = sign_payload(payload)
        signature2 = sign_payload(payload)
        
        assert signature1 == signature2
    
    def test_sign_payload_order_independent(self):
        """Test that payload key order doesn't affect signature (due to sort_keys)."""
        payload1 = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        payload2 = {"player": "testplayer", "amount": 100, "type": "SPEND_COINS"}
        
        signature1 = sign_payload(payload1)
        signature2 = sign_payload(payload2)
        
        assert signature1 == signature2
    
    def test_verify_signature_valid(self):
        """Test verifying a valid signature."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        signature = sign_payload(payload)
        
        assert verify_signature(payload, signature) is True
    
    def test_verify_signature_invalid(self):
        """Test verifying an invalid signature."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        invalid_signature = "invalid_signature"
        
        assert verify_signature(payload, invalid_signature) is False
    
    def test_verify_signature_empty(self):
        """Test verifying with empty signature."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        
        assert verify_signature(payload, "") is False
    
    def test_verify_signature_none(self):
        """Test verifying with None signature."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        
        assert verify_signature(payload, None) is False
    
    def test_verify_signature_tampered_payload(self):
        """Test that tampering with payload invalidates signature."""
        payload = {"type": "SPEND_COINS", "player": "testplayer", "amount": 100}
        signature = sign_payload(payload)
        
        # Tamper with payload
        payload["amount"] = 200
        
        assert verify_signature(payload, signature) is False
    
    @patch('minecraft.services.ws_security.settings')
    def test_sign_payload_uses_secret(self, mock_settings):
        """Test that sign_payload uses the configured secret."""
        mock_settings.MCC_MINECRAFT_WS_SHARED_SECRET = "test_secret"
        
        payload = {"type": "SPEND_COINS", "player": "testplayer"}
        
        with patch('minecraft.services.ws_security.settings', mock_settings):
            signature = sign_payload(payload)
        
        # Signature should be different with different secret
        mock_settings.MCC_MINECRAFT_WS_SHARED_SECRET = "different_secret"
        with patch('minecraft.services.ws_security.settings', mock_settings):
            signature2 = sign_payload(payload)
        
        assert signature != signature2
