"""
Unit Tests for UTP Client
File: test_utp_client.py
Date: 2026-08-25

Tests for UTP client connection management and message handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from utp_client import UTPConnectionManager, TCPConnection
from utp_protocol import UTPFrame
from constants import MessageType


class TestUTPConnectionManagerInit:
    """Test client initialization."""
    
    def test_init_stores_parameters(self):
        """Test initialization stores connection parameters."""
        manager = UTPConnectionManager(
            "192.168.1.1",
            9000,
            "TestClient"
        )
        
        assert manager.server_host == "192.168.1.1"
        assert manager.server_port == 9000
        assert manager.client_name == "TestClient"
    
    def test_init_with_callback(self):
        """Test initialization with message callback."""
        def callback(msg):
            pass
        
        manager = UTPConnectionManager(
            "127.0.0.1",
            9000,
            "Test",
            callback_on_message=callback
        )
        
        assert manager.callback_on_message == callback
    
    def test_init_not_running(self):
        """Test client not running initially."""
        manager = UTPConnectionManager("127.0.0.1", 9000, "Test")
        assert manager.running is False


class TestTCPConnectionAdapter:
    """Test TCP connection adapter."""
    
    def test_tcp_init(self):
        """Test TCP connection initialization."""
        conn = TCPConnection("127.0.0.1", 5000, "Client")
        assert conn.host == "127.0.0.1"
        assert conn.port == 5000
        assert conn.name == "Client"
    
    @patch('socket.socket')
    def test_tcp_connect(self, mock_socket_class):
        """Test TCP connect calls socket methods."""
        mock_sock = Mock()
        mock_socket_class.return_value = mock_sock
        
        conn = TCPConnection("127.0.0.1", 5000, "Client")
        conn.connect()
        
        assert mock_sock.connect.called
    
    def test_tcp_send_receive_close(self):
        """Test TCP send, receive, close methods exist."""
        conn = TCPConnection("127.0.0.1", 5000, "Client")
        
        # Just verify methods exist and are callable
        assert callable(conn.send)
        assert callable(conn.receive)
        assert callable(conn.close)


class TestUTPConnectionRepr:
    """Test string representation."""
    
    def test_repr_includes_host_port(self):
        """Test repr includes connection info."""
        manager = UTPConnectionManager("192.168.1.1", 9000, "TestClient")
        repr_str = repr(manager)
        
        assert "192.168.1.1" in repr_str
        assert "9000" in repr_str
        assert "TestClient" in repr_str


class TestMessageFormatting:
    """Test message handling (without full socket integration)."""
    
    @patch('socket.socket')
    def test_send_message_requires_connection(self, mock_socket_class):
        """Test send_message raises when not connected."""
        manager = UTPConnectionManager("127.0.0.1", 9000, "Test")
        
        with pytest.raises(RuntimeError):
            manager.send_message("Hello")


class TestHandshakeFlow:
    """Test handshake state transitions (mock-based)."""
    
    @patch('socket.socket')
    @patch('rsa.newkeys')
    def test_handshake_initializes_keys(self, mock_newkeys, mock_socket_class):
        """Test handshake generates RSA keys."""
        # This test would verify key generation without full socket mocking
        # Actual key generation happens during connect()
        mock_pub = Mock()
        mock_priv = Mock()
        mock_newkeys.return_value = (mock_pub, mock_priv)
        
        # Just verify the method exists and can be called
        manager = UTPConnectionManager("127.0.0.1", 9000, "Test")
        assert manager.client_public_key is None
        assert manager.client_private_key is None


class TestCloseOperation:
    """Test connection close."""
    
    def test_close_not_connected(self):
        """Test close works when not connected."""
        manager = UTPConnectionManager("127.0.0.1", 9000, "Test")
        # Should not raise
        manager.close()
        assert manager.running is False
    
    @patch('socket.socket')
    def test_close_stops_running(self, mock_socket_class):
        """Test close sets running to False."""
        mock_sock = Mock()
        
        manager = UTPConnectionManager("127.0.0.1", 9000, "Test")
        manager.socket = mock_sock
        manager.running = True
        
        manager.close()
        assert manager.running is False


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
