"""
UTP Protocol Constants and Configuration
File: constants.py
Date: 2026-08-25

This module defines all protocol constants, message types, timeouts, and buffer
limits used by the UTP (UDP-based Transfer Protocol) implementation.
"""


class UTPConstants:
    """Core protocol identifiers and version information."""
    
    PROTOCOL_ID = 0x55  # 'U' for UTP - identifies UTP frames
    VERSION = 0x01      # Protocol version 1


class MessageType:
    """Message type constants for different UTP frame types."""
    
    HANDSHAKE_INIT = 0x01   # Client initiates connection
    HANDSHAKE_RESP = 0x02   # Server responds to handshake
    DATA = 0x03             # Message data frame
    ACK = 0x04              # Acknowledgment frame
    CLOSE = 0x05            # Connection close frame


class Flags:
    """Frame flag bits for control information."""
    
    ACK_REQUIRED = 0x01     # Bit 0: Sender requires acknowledgment
    IS_ACK = 0x02           # Bit 1: This frame is an acknowledgment
    CLOSE = 0x04            # Bit 2: Connection termination indicator


class Timeouts:
    """Timeout values in milliseconds for various protocol operations."""
    
    ACK_MS = 200            # Wait 200ms for ACK before retransmitting
    HANDSHAKE_MS = 5000     # Wait 5s for handshake response
    IDLE_MS = 30000         # Close connection after 30s idle


class BufferLimits:
    """Size limits for frames and buffers."""
    
    MAX_FRAME_SIZE = 1024       # Maximum data payload per frame
    MAX_BUFFER_SIZE = 65536     # Maximum receive buffer (64KB)
    SEND_BUFFER_SIZE = 65536    # Maximum send buffer (64KB)
    HEADER_SIZE = 8             # UTP frame header size in bytes


class RetransmissionConfig:
    """Configuration for retransmission and backoff strategy."""
    
    MAX_RETRIES = 5             # Maximum number of retransmission attempts
    INITIAL_BACKOFF = 200       # Initial backoff in milliseconds
    MAX_BACKOFF = 3200          # Maximum backoff in milliseconds (3.2s)
    BACKOFF_MULTIPLIER = 2      # Exponential backoff multiplier


class SequenceNumbers:
    """Sequence number configuration."""
    
    MAX_SEQUENCE = 65535        # 16-bit unsigned maximum (0-65535)
    WRAP_AROUND = 65536         # Wraparound value for sequence numbers
