"""
Unit Tests for UTP Connection State Machine
File: test_utp_connection.py
Date: 2026-08-25

Comprehensive test suite for UTPConnection state management and retransmission.
"""

import pytest
import time
from utp_connection import UTPConnection, UTPState, PendingFrame
from utp_protocol import UTPFrame
from constants import MessageType, Flags, Timeouts, RetransmissionConfig


class TestUTPConnectionInitialization:
    """Test connection initialization and basic properties."""
    
    def test_init_default_state(self):
        """Test connection starts in DISCONNECTED state."""
        conn = UTPConnection(("127.0.0.1", 5000), is_server=False)
        assert conn.state == UTPState.DISCONNECTED
    
    def test_init_client_mode(self):
        """Test client-mode connection."""
        conn = UTPConnection(("192.168.1.1", 8000), is_server=False)
        assert conn.is_server is False
        assert conn.peer_addr == ("192.168.1.1", 8000)
    
    def test_init_server_mode(self):
        """Test server-mode connection."""
        conn = UTPConnection(("192.168.1.100", 8000), is_server=True)
        assert conn.is_server is True
    
    def test_init_sequence_numbers(self):
        """Test initial sequence numbers are zero."""
        conn = UTPConnection(("127.0.0.1", 5000))
        assert conn.send_seq == 0
        assert conn.recv_seq == 0
    
    def test_init_empty_pending_acks(self):
        """Test no pending ACKs initially."""
        conn = UTPConnection(("127.0.0.1", 5000))
        assert len(conn.pending_acks) == 0
    
    def test_init_activity_timestamp(self):
        """Test last activity is set to initialization time."""
        before = time.time()
        conn = UTPConnection(("127.0.0.1", 5000))
        after = time.time()
        assert before <= conn.last_activity <= after


class TestStateTransitions:
    """Test state machine transitions."""
    
    def test_handshake_transition_from_disconnected(self):
        """Test DISCONNECTED -> HANDSHAKING transition."""
        conn = UTPConnection(("127.0.0.1", 5000), is_server=False)
        conn.initiate_handshake()
        assert conn.state == UTPState.HANDSHAKING
    
    def test_cannot_initiate_handshake_when_connected(self):
        """Test cannot initiate handshake when already connected."""
        conn = UTPConnection(("127.0.0.1", 5000), is_server=False)
        conn.initiate_handshake()
        with pytest.raises(RuntimeError):
            conn.initiate_handshake()
    
    def test_accept_handshake_from_handshaking(self):
        """Test HANDSHAKING -> CONNECTED transition."""
        conn = UTPConnection(("127.0.0.1", 5000), is_server=True)
        conn._set_state(UTPState.HANDSHAKING)
        conn.accept_handshake()
        assert conn.state == UTPState.CONNECTED
    
    def test_cannot_accept_handshake_when_disconnected(self):
        """Test cannot accept handshake from DISCONNECTED."""
        conn = UTPConnection(("127.0.0.1", 5000), is_server=True)
        with pytest.raises(RuntimeError):
            conn.accept_handshake()
    
    def test_close_from_connected(self):
        """Test CONNECTED -> CLOSING transition."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        conn.close()
        assert conn.state == UTPState.CLOSING
    
    def test_close_from_handshaking(self):
        """Test can close from HANDSHAKING state."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.HANDSHAKING)
        conn.close()
        assert conn.state == UTPState.CLOSING
    
    def test_cannot_close_when_disconnected(self):
        """Test cannot close from DISCONNECTED."""
        conn = UTPConnection(("127.0.0.1", 5000))
        with pytest.raises(RuntimeError):
            conn.close()
    
    def test_cannot_close_when_already_closed(self):
        """Test cannot close from CLOSED state."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CLOSED)
        with pytest.raises(RuntimeError):
            conn.close()
    
    def test_mark_closed(self):
        """Test marking connection as closed."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CLOSING)
        conn.mark_closed()
        assert conn.state == UTPState.CLOSED


class TestSequenceNumbers:
    """Test sequence number management."""
    
    def test_increment_send_seq(self):
        """Test send sequence increments."""
        conn = UTPConnection(("127.0.0.1", 5000))
        assert conn.increment_send_seq() == 1
        assert conn.increment_send_seq() == 2
        assert conn.send_seq == 2
    
    def test_increment_recv_seq(self):
        """Test receive sequence increments."""
        conn = UTPConnection(("127.0.0.1", 5000))
        assert conn.increment_recv_seq() == 1
        assert conn.recv_seq == 1
    
    def test_sequence_wraparound_at_65536(self):
        """Test sequence wraps at 65536."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn.send_seq = 65535
        assert conn.increment_send_seq() == 0
        assert conn.send_seq == 0
    
    def test_sequence_wraparound_recv(self):
        """Test receive sequence wraps at 65536."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn.recv_seq = 65535
        assert conn.increment_recv_seq() == 0
        assert conn.recv_seq == 0


class TestFrameQueuing:
    """Test frame queuing and acknowledgment."""
    
    def test_queue_frame_in_connected_state(self):
        """Test queuing frame in CONNECTED state."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        
        conn.queue_frame(frame)
        assert 0 in conn.pending_acks
    
    def test_queue_frame_in_closing_state(self):
        """Test can queue frame in CLOSING state."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CLOSING)
        
        frame = UTPFrame(MessageType.CLOSE, 0)
        frame.set_flag(Flags.ACK_REQUIRED)
        
        conn.queue_frame(frame)
        assert 0 in conn.pending_acks
    
    def test_cannot_queue_frame_when_disconnected(self):
        """Test cannot queue frame when disconnected."""
        conn = UTPConnection(("127.0.0.1", 5000))
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        
        with pytest.raises(RuntimeError):
            conn.queue_frame(frame)
    
    def test_queue_frame_without_ack_required(self):
        """Test frame without ACK flag is not tracked."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        # No ACK_REQUIRED flag
        
        conn.queue_frame(frame)
        assert 0 not in conn.pending_acks
    
    def test_acknowledge_removes_from_pending(self):
        """Test acknowledgment removes frame from pending."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 5, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        
        conn.queue_frame(frame)
        assert 5 in conn.pending_acks
        
        result = conn.acknowledge(5)
        assert result is True
        assert 5 not in conn.pending_acks
    
    def test_acknowledge_nonexistent_sequence(self):
        """Test acknowledging non-existent sequence returns False."""
        conn = UTPConnection(("127.0.0.1", 5000))
        result = conn.acknowledge(999)
        assert result is False
    
    def test_multiple_pending_frames(self):
        """Test multiple frames can be pending simultaneously."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        for i in range(5):
            frame = UTPFrame(MessageType.DATA, i, b"test")
            frame.set_flag(Flags.ACK_REQUIRED)
            conn.queue_frame(frame)
        
        assert len(conn.pending_acks) == 5
        
        # Acknowledge one
        conn.acknowledge(2)
        assert len(conn.pending_acks) == 4
        assert 2 not in conn.pending_acks
    
    def test_out_of_order_acknowledgment(self):
        """Test acknowledging out-of-order sequences."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        # Queue frames 10, 20, 30
        for seq in [10, 20, 30]:
            frame = UTPFrame(MessageType.DATA, seq, b"test")
            frame.set_flag(Flags.ACK_REQUIRED)
            conn.queue_frame(frame)
        
        # Acknowledge out of order
        conn.acknowledge(30)
        conn.acknowledge(10)
        
        assert 10 not in conn.pending_acks
        assert 20 in conn.pending_acks
        assert 30 not in conn.pending_acks


class TestIdleDetection:
    """Test idle timeout detection."""
    
    def test_not_idle_immediately_after_init(self):
        """Test connection is not idle immediately."""
        conn = UTPConnection(("127.0.0.1", 5000))
        assert not conn.is_idle()
    
    def test_idle_after_timeout(self):
        """Test connection marked idle after IDLE_TIMEOUT."""
        conn = UTPConnection(("127.0.0.1", 5000))
        # Manually set activity to past
        conn.last_activity = time.time() - (Timeouts.IDLE_MS + 1000) / 1000.0
        assert conn.is_idle()
    
    def test_activity_update_resets_idle(self):
        """Test updating activity resets idle timer."""
        conn = UTPConnection(("127.0.0.1", 5000))
        # Set to idle
        conn.last_activity = time.time() - (Timeouts.IDLE_MS + 1000) / 1000.0
        assert conn.is_idle()
        
        # Update activity
        conn.update_activity()
        assert not conn.is_idle()


class TestDeadConnection:
    """Test dead connection detection."""
    
    def test_not_dead_initially(self):
        """Test connection is not dead initially."""
        conn = UTPConnection(("127.0.0.1", 5000))
        assert not conn.is_dead()
    
    def test_dead_after_max_retries(self):
        """Test connection marked dead after max retries."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        # Simulate max retries
        for _ in range(RetransmissionConfig.MAX_RETRIES):
            conn.mark_retry(0)
        
        assert conn.is_dead()
    
    def test_not_dead_below_max_retries(self):
        """Test connection not dead below max retries."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        # One retry
        conn.mark_retry(0)
        
        assert not conn.is_dead()


class TestRetransmission:
    """Test retransmission logic."""
    
    def test_get_pending_retransmits_empty(self):
        """Test no retransmits when no pending frames."""
        conn = UTPConnection(("127.0.0.1", 5000))
        retransmits = conn.get_pending_retransmits()
        assert len(retransmits) == 0
    
    def test_get_pending_retransmits_not_ready(self):
        """Test retransmits not returned if timeout not exceeded."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        # Immediately check - should not be ready
        retransmits = conn.get_pending_retransmits()
        assert len(retransmits) == 0
    
    def test_get_pending_retransmits_after_timeout(self):
        """Test retransmits returned after initial timeout."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        # Manually set timestamp to past
        pending = conn.pending_acks[0]
        pending.timestamp = time.time() - (RetransmissionConfig.INITIAL_BACKOFF + 100) / 1000.0
        
        retransmits = conn.get_pending_retransmits()
        assert len(retransmits) == 1
        seq, retx_frame, _ = retransmits[0]
        assert seq == 0
        assert retx_frame == frame
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff increases with attempts."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        pending = conn.pending_acks[0]
        backoff_values = []
        
        # Simulate attempts and get backoff values
        for attempt in range(5):
            pending.attempt = attempt
            pending.timestamp = time.time() - 10  # Make it overdue
            
            retransmits = conn.get_pending_retransmits()
            if retransmits:
                _, _, next_send_time = retransmits[0]
                backoff_ms = (next_send_time - pending.timestamp) * 1000
                backoff_values.append(backoff_ms)
        
        # Should have exponential backoff: 200, 400, 800, 1600, 3200
        assert len(backoff_values) >= 3
        assert backoff_values[0] < backoff_values[1]  # First < Second
        if len(backoff_values) > 2:
            assert backoff_values[1] < backoff_values[2]  # Second < Third
    
    def test_mark_retry_increments_attempt(self):
        """Test mark_retry increments attempt counter."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        assert conn.pending_acks[0].attempt == 0
        
        result = conn.mark_retry(0)
        assert result is True
        assert conn.pending_acks[0].attempt == 1
    
    def test_mark_retry_stops_at_max(self):
        """Test mark_retry returns False after max retries."""
        conn = UTPConnection(("127.0.0.1", 5000))
        conn._set_state(UTPState.CONNECTED)
        
        frame = UTPFrame(MessageType.DATA, 0, b"test")
        frame.set_flag(Flags.ACK_REQUIRED)
        conn.queue_frame(frame)
        
        # Retry MAX_RETRIES-1 times (should return True)
        for i in range(RetransmissionConfig.MAX_RETRIES - 1):
            result = conn.mark_retry(0)
            assert result is True
        
        # Next retry should fail (MAX_RETRIES reached)
        result = conn.mark_retry(0)
        assert result is False
    
    def test_mark_retry_nonexistent_sequence(self):
        """Test mark_retry on nonexistent sequence."""
        conn = UTPConnection(("127.0.0.1", 5000))
        result = conn.mark_retry(999)
        assert result is False


class TestActivityTracking:
    """Test activity timestamp updates."""
    
    def test_update_activity(self):
        """Test manual activity update."""
        conn = UTPConnection(("127.0.0.1", 5000))
        original_time = conn.last_activity
        
        time.sleep(0.01)  # Small delay
        conn.update_activity()
        
        assert conn.last_activity > original_time
    
    def test_get_state_time(self):
        """Test getting time in current state."""
        conn = UTPConnection(("127.0.0.1", 5000))
        
        time.sleep(0.01)
        state_time = conn.get_state_time()
        
        assert state_time > 0
        assert state_time < 0.5  # Should be small


class TestRepr:
    """Test string representation."""
    
    def test_repr_includes_state(self):
        """Test repr includes current state."""
        conn = UTPConnection(("127.0.0.1", 5000), is_server=False)
        repr_str = repr(conn)
        
        assert "DISCONNECTED" in repr_str
        assert "127.0.0.1" in repr_str
        assert "5000" in repr_str


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
