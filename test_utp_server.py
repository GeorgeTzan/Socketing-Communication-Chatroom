"""
Unit Tests for UTP Server Implementation
File: test_utp_server.py
Date: 2026-08-25

Tests for UTP server socket handling, connection management, and message routing.
"""

import pytest
import socket
import threading
import time
import rsa
from unittest.mock import Mock, patch, MagicMock
from utp_server import UTPServer
from utp_protocol import UTPFrame
from utp_connection import UTPConnection, UTPState
from constants import MessageType, Flags


class TestUTPServerInitialization:
    """Test server initialization."""
    
    def test_init_creates_server(self):
        """Test server initialization."""
        server = UTPServer("127.0.0.1", 9000)
        assert server.host == "127.0.0.1"
        assert server.port == 9000
        assert server.running is False
        assert len(server.connections) == 0
    
    def test_init_generates_rsa_keys(self):
        """Test server generates RSA key pair."""
        server = UTPServer("127.0.0.1", 9000)
        assert server.server_public_key is not None
        assert server.server_private_key is not None
    
    def test_init_thread_lock(self):
        """Test server has thread lock."""
        server = UTPServer("127.0.0.1", 9000)
        assert server.lock is not None


class TestHandshakeHandling:
    """Test handshake processing."""
    
    def test_handle_handshake_init_creates_connection(self):
        """Test HANDSHAKE_INIT creates new connection."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()  # Mock socket first
        
        frame = UTPFrame(MessageType.HANDSHAKE_INIT, 0)
        addr = ("192.168.1.1", 5000)
        
        server._handle_frame(frame, addr)
        
        assert addr in server.connections
        assert server.connections[addr].state == UTPState.HANDSHAKING
    
    def test_handle_handshake_init_sends_response(self):
        """Test HANDSHAKE_INIT sends HANDSHAKE_RESP."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        frame = UTPFrame(MessageType.HANDSHAKE_INIT, 0)
        addr = ("192.168.1.1", 5000)
        
        server._handle_frame(frame, addr)
        
        # Verify sendto was called
        assert server.socket.sendto.called
        
        # Verify response contains server's public key
        call_args = server.socket.sendto.call_args
        sent_data = call_args[0][0]
        response = UTPFrame.deserialize(sent_data)
        
        assert response is not None
        assert response.message_type == MessageType.HANDSHAKE_RESP
        assert len(response.data) > 0  # Contains public key


class TestDataHandling:
    """Test data frame processing."""
    
    def test_handle_data_requires_connected_state(self):
        """Test DATA frames rejected if not connected."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        server.connections[addr] = conn
        
        # Connection in DISCONNECTED state
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        
        server._handle_frame(frame, addr)
        
        # Should not process (would need to be CONNECTED)
        # Socket should not be called for DATA from disconnected client
        assert not server.socket.sendto.called or len(server.socket.sendto.call_args_list) == 0
    
    def test_handle_data_with_connected_connection(self):
        """Test DATA processing with connected client."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        conn._set_state(UTPState.CONNECTED)
        server.connections[addr] = conn
        
        # Add public key for encryption
        client_pub, _ = rsa.newkeys(512)  # Small key for testing
        server.public_keys[addr] = client_pub
        
        # Create encrypted data frame
        message = b"Hello Server"
        encrypted = rsa.encrypt(message, server.server_public_key)
        frame = UTPFrame(MessageType.DATA, 0, encrypted)
        frame.set_flag(Flags.ACK_REQUIRED)
        
        server._handle_frame(frame, addr)
        
        # Should send ACK
        assert server.socket.sendto.called


class TestAckHandling:
    """Test ACK frame processing."""
    
    def test_handle_ack_removes_pending(self):
        """Test ACK removes frame from pending."""
        server = UTPServer("127.0.0.1", 9000)
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        conn._set_state(UTPState.CONNECTED)
        server.connections[addr] = conn
        
        # Queue a frame
        frame_to_send = UTPFrame(MessageType.DATA, 5, b"test")
        frame_to_send.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame_to_send)
        
        # Verify it's pending
        assert 5 in conn.pending_acks
        
        # Handle ACK
        ack_frame = UTPFrame(MessageType.ACK, 5)
        ack_frame.set_flag(Flags.IS_ACK)
        
        server._handle_frame(ack_frame, addr)
        
        # Should be removed
        assert 5 not in conn.pending_acks


class TestCloseHandling:
    """Test connection close handling."""
    
    def test_handle_close_transitions_state(self):
        """Test CLOSE frame transitions connection to CLOSED."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        conn._set_state(UTPState.CONNECTED)
        server.connections[addr] = conn
        
        close_frame = UTPFrame(MessageType.CLOSE, 0)
        
        server._handle_frame(close_frame, addr)
        
        # Should transition to CLOSED
        assert server.connections[addr].state == UTPState.CLOSED
    
    def test_handle_close_sends_ack(self):
        """Test CLOSE sends acknowledgment."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        conn._set_state(UTPState.CONNECTED)
        server.connections[addr] = conn
        
        close_frame = UTPFrame(MessageType.CLOSE, 0)
        
        server._handle_frame(close_frame, addr)
        
        # Verify ACK was sent
        assert server.socket.sendto.called


class TestBroadcast:
    """Test message broadcasting."""
    
    def test_broadcast_sends_to_all_except_sender(self):
        """Test broadcast sends to all connected clients except sender."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        # Create three connections
        addrs = [("192.168.1.1", 5001), ("192.168.1.2", 5002), ("192.168.1.3", 5003)]
        
        for addr in addrs:
            conn = UTPConnection(addr, is_server=True)
            conn._set_state(UTPState.CONNECTED)
            server.connections[addr] = conn
            server.client_names[addr] = f"Client_{addr[0]}"
            
            # Add public keys
            pub, _ = rsa.newkeys(512)
            server.public_keys[addr] = pub
        
        # Broadcast from first address
        server._broadcast(b"Hello", addrs[0])
        
        # Should send to 2 clients (not the sender)
        call_count = server.socket.sendto.call_count
        assert call_count == 2
    
    def test_broadcast_skips_disconnected(self):
        """Test broadcast skips disconnected clients."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        # Create two connections, one disconnected
        addr1 = ("192.168.1.1", 5001)
        addr2 = ("192.168.1.2", 5002)
        
        conn1 = UTPConnection(addr1, is_server=True)
        conn1._set_state(UTPState.CONNECTED)
        server.connections[addr1] = conn1
        server.client_names[addr1] = "Client1"
        pub, _ = rsa.newkeys(512)
        server.public_keys[addr1] = pub
        
        conn2 = UTPConnection(addr2, is_server=True)
        conn2._set_state(UTPState.DISCONNECTED)  # Not connected
        server.connections[addr2] = conn2
        
        # Broadcast
        sender = ("192.168.1.3", 5003)
        server._broadcast(b"Hello", sender)
        
        # Should only send to addr1 (addr2 is disconnected)
        assert server.socket.sendto.call_count <= 1


class TestConnectionCleanup:
    """Test connection cleanup."""
    
    def test_cleanup_removes_idle_connections(self):
        """Test cleanup removes connections exceeding idle timeout."""
        server = UTPServer("127.0.0.1", 9000)
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        conn._set_state(UTPState.CONNECTED)
        
        # Make connection idle
        conn.last_activity = time.time() - 31  # 31 seconds old
        
        server.connections[addr] = conn
        server.client_names[addr] = "Test"
        
        server._cleanup_connections()
        
        # Should be removed
        assert addr not in server.connections
    
    def test_cleanup_removes_dead_connections(self):
        """Test cleanup removes connections with max retries exceeded."""
        server = UTPServer("127.0.0.1", 9000)
        
        addr = ("192.168.1.1", 5000)
        conn = UTPConnection(addr, is_server=True)
        conn._set_state(UTPState.CONNECTED)
        
        # Queue frame and mark for retry until dead
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        # Mark as dead
        for _ in range(6):
            conn.mark_retry(0)
        
        server.connections[addr] = conn
        server.client_names[addr] = "Test"
        
        server._cleanup_connections()
        
        # Should be removed
        assert addr not in server.connections


class TestShutdown:
    """Test server shutdown."""
    
    def test_shutdown_sets_running_false(self):
        """Test shutdown sets running flag to False."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        server.running = True
        
        server.shutdown()
        
        assert server.running is False
    
    def test_shutdown_closes_socket(self):
        """Test shutdown closes socket."""
        server = UTPServer("127.0.0.1", 9000)
        server.socket = Mock()
        
        server.shutdown()
        
        assert server.socket.close.called


class TestRepr:
    """Test string representation."""
    
    def test_repr_includes_host_port_connections(self):
        """Test repr includes server info."""
        server = UTPServer("192.168.1.1", 8888)
        repr_str = repr(server)
        
        assert "192.168.1.1" in repr_str
        assert "8888" in repr_str
        assert "connections" in repr_str


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
