"""
UTP Connection State Machine and Retransmission Logic
File: utp_connection.py
Date: 2026-08-25

Implements per-connection lifecycle management including state transitions,
frame queuing, acknowledgments, and exponential backoff retransmission.
"""

import time
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from utp_protocol import UTPFrame
from constants import (
    Timeouts,
    RetransmissionConfig,
    SequenceNumbers
)


class UTPState(Enum):
    """Connection state machine states."""
    DISCONNECTED = 0   # Initial state
    HANDSHAKING = 1    # Handshake in progress
    CONNECTED = 2      # Ready to send/receive data
    CLOSING = 3        # Close initiated
    CLOSED = 4         # Connection terminated


@dataclass
class PendingFrame:
    """Represents a frame waiting for acknowledgment."""
    frame: UTPFrame
    timestamp: float    # When frame was sent
    attempt: int        # Number of retransmission attempts


class UTPConnection:
    """
    Manages a single UDP connection between client and server.
    
    Handles state transitions, sequence numbering, pending frames,
    and retransmission with exponential backoff.
    """
    
    def __init__(self, peer_addr: Tuple[str, int], is_server: bool = False):
        """
        Initialize a UTP connection.
        
        Args:
            peer_addr: Tuple of (host, port) for the peer
            is_server: True if this is server-side connection
        """
        self.peer_addr = peer_addr
        self.is_server = is_server
        
        # State management
        self._state = UTPState.DISCONNECTED
        self._state_changed_at = time.time()
        
        # Sequence tracking (16-bit, wraps at 65536)
        self.send_seq = 0
        self.recv_seq = 0
        
        # Pending frames waiting for ACK
        self.pending_acks: Dict[int, PendingFrame] = {}
        
        # Activity tracking
        self.last_activity = time.time()
        
        # Connection metadata
        self.client_name: Optional[str] = None
        self.public_key_other: Optional[bytes] = None
    
    @property
    def state(self) -> UTPState:
        """Get current connection state."""
        return self._state
    
    def _set_state(self, new_state: UTPState) -> None:
        """
        Set connection state and update timestamp.
        
        Args:
            new_state: New state to transition to
        """
        self._state = new_state
        self._state_changed_at = time.time()
    
    def initiate_handshake(self) -> None:
        """
        Initiate handshake from client side.
        
        Raises:
            RuntimeError: If not in DISCONNECTED state
        """
        if self._state != UTPState.DISCONNECTED:
            raise RuntimeError(
                f"Cannot initiate handshake from {self._state.name} state"
            )
        self._set_state(UTPState.HANDSHAKING)
        self.last_activity = time.time()
    
    def accept_handshake(self) -> None:
        """
        Accept handshake from server side.
        
        Raises:
            RuntimeError: If not in HANDSHAKING state
        """
        if self._state != UTPState.HANDSHAKING:
            raise RuntimeError(
                f"Cannot accept handshake from {self._state.name} state"
            )
        self._set_state(UTPState.CONNECTED)
        self.last_activity = time.time()
    
    def queue_frame(self, frame: UTPFrame) -> None:
        """
        Queue a frame for transmission and track for ACK.
        
        Args:
            frame: Frame to queue
            
        Raises:
            RuntimeError: If not in CONNECTED state or invalid sequence
        """
        if self._state not in (UTPState.CONNECTED, UTPState.CLOSING):
            raise RuntimeError(
                f"Cannot send frame in {self._state.name} state"
            )
        
        # Add to pending if ACK required
        if frame.has_flag(1):  # ACK_REQUIRED flag
            self.pending_acks[frame.sequence] = PendingFrame(
                frame=frame,
                timestamp=time.time(),
                attempt=0
            )
        
        self.last_activity = time.time()
    
    def acknowledge(self, seq: int) -> bool:
        """
        Acknowledge receipt of a frame by sequence number.
        
        Args:
            seq: Sequence number to acknowledge
            
        Returns:
            bool: True if frame was pending and removed
        """
        if seq in self.pending_acks:
            del self.pending_acks[seq]
            self.last_activity = time.time()
            return True
        return False
    
    def close(self) -> None:
        """
        Initiate graceful connection close.
        
        Raises:
            RuntimeError: If already closed or disconnected
        """
        if self._state in (UTPState.DISCONNECTED, UTPState.CLOSED):
            raise RuntimeError(
                f"Cannot close connection in {self._state.name} state"
            )
        self._set_state(UTPState.CLOSING)
        self.last_activity = time.time()
    
    def mark_closed(self) -> None:
        """Mark connection as fully closed."""
        self._set_state(UTPState.CLOSED)
        self.last_activity = time.time()
    
    def is_idle(self) -> bool:
        """
        Check if connection has exceeded idle timeout.
        
        Returns:
            bool: True if idle time > IDLE_TIMEOUT
        """
        idle_time = (time.time() - self.last_activity) * 1000  # Convert to ms
        return idle_time > Timeouts.IDLE_MS
    
    def is_dead(self) -> bool:
        """
        Check if connection should be terminated due to failed retries.
        
        Returns:
            bool: True if any frame exceeded max retries
        """
        for pending in self.pending_acks.values():
            if pending.attempt >= RetransmissionConfig.MAX_RETRIES:
                return True
        return False
    
    def get_pending_retransmits(self) -> List[Tuple[int, UTPFrame, float]]:
        """
        Get list of frames that need retransmission.
        
        Returns:
            List of (seq, frame, next_send_time) for frames ready to retry
        """
        now = time.time()
        retransmits = []
        
        for seq, pending in self.pending_acks.items():
            # Calculate backoff duration
            backoff_ms = min(
                RetransmissionConfig.INITIAL_BACKOFF * (
                    RetransmissionConfig.BACKOFF_MULTIPLIER ** pending.attempt
                ),
                RetransmissionConfig.MAX_BACKOFF
            )
            backoff_seconds = backoff_ms / 1000.0
            
            # Check if ready to retry
            next_send_time = pending.timestamp + backoff_seconds
            if now >= next_send_time:
                retransmits.append((seq, pending.frame, next_send_time))
        
        return retransmits
    
    def mark_retry(self, seq: int) -> bool:
        """
        Mark a frame for retry and increment attempt counter.
        
        Args:
            seq: Sequence number to retry
            
        Returns:
            bool: True if retry scheduled, False if exceeded max retries
        """
        if seq not in self.pending_acks:
            return False
        
        pending = self.pending_acks[seq]
        pending.attempt += 1
        pending.timestamp = time.time()  # Reset timestamp for backoff calculation
        
        return pending.attempt < RetransmissionConfig.MAX_RETRIES
    
    def increment_send_seq(self) -> int:
        """
        Increment send sequence number with wraparound.
        
        Returns:
            int: New sequence number
        """
        self.send_seq = (self.send_seq + 1) % SequenceNumbers.WRAP_AROUND
        return self.send_seq
    
    def increment_recv_seq(self) -> int:
        """
        Increment receive sequence number with wraparound.
        
        Returns:
            int: New sequence number
        """
        self.recv_seq = (self.recv_seq + 1) % SequenceNumbers.WRAP_AROUND
        return self.recv_seq
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()
    
    def get_state_time(self) -> float:
        """
        Get time spent in current state.
        
        Returns:
            float: Seconds since last state transition
        """
        return time.time() - self._state_changed_at
    
    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"UTPConnection(addr={self.peer_addr}, state={self._state.name}, "
            f"send_seq={self.send_seq}, recv_seq={self.recv_seq}, "
            f"pending={len(self.pending_acks)})"
        )
