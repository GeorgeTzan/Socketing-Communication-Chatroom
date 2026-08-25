"""
UTP Protocol Frame Implementation
File: utp_protocol.py
Date: 2026-08-25

This module implements the UTPFrame class for serializing and deserializing
UTP protocol frames with 8-byte header and variable-length payload.
"""

import struct
from typing import Optional, Tuple
from constants import (
    UTPConstants,
    MessageType,
    Flags,
    BufferLimits,
    SequenceNumbers
)


class UTPFrame:
    """
    Represents a single UTP protocol frame with header and payload.
    
    Frame Structure (Big-Endian):
    ┌─────────────┬──────────┬──────────┬──────────┬─────────────┬──────────┬────────────────────┐
    │ Protocol ID │ Version  │ Type     │ Flags    │ Sequence#   │ Reserved │ Data               │
    │ (1 byte)    │ (1 byte) │ (1 byte) │ (1 byte) │ (2 bytes)   │ (2 bytes)│ (Variable - 1024B) │
    └─────────────┴──────────┴──────────┴──────────┴─────────────┴──────────┴────────────────────┘
    """
    
    def __init__(
        self,
        message_type: int,
        sequence: int,
        data: bytes = b'',
        flags: int = 0
    ):
        """
        Initialize a UTP frame.
        
        Args:
            message_type: Type of message (from MessageType class)
            sequence: Sequence number (0-65535)
            data: Payload data (max 1024 bytes)
            flags: Frame flags (from Flags class)
            
        Raises:
            ValueError: If parameters are invalid
        """
        if message_type not in (
            MessageType.HANDSHAKE_INIT,
            MessageType.HANDSHAKE_RESP,
            MessageType.DATA,
            MessageType.ACK,
            MessageType.CLOSE
        ):
            raise ValueError(f"Invalid message type: {message_type}")
        
        if not (0 <= sequence <= SequenceNumbers.MAX_SEQUENCE):
            raise ValueError(f"Sequence must be 0-65535, got {sequence}")
        
        if len(data) > BufferLimits.MAX_FRAME_SIZE:
            raise ValueError(
                f"Data exceeds max frame size {BufferLimits.MAX_FRAME_SIZE}: {len(data)}"
            )
        
        self.message_type = message_type
        self.sequence = sequence
        self.data = data
        self.flags = flags
    
    def serialize(self) -> bytes:
        """
        Serialize the frame to bytes (header + payload).
        
        Returns:
            bytes: Serialized frame (8-byte header + payload)
        """
        # Pack header: protocol_id, version, type, flags, sequence, reserved (big-endian)
        header = struct.pack(
            '>BBBBHH',  # Big-endian: 4 unsigned bytes + 2 unsigned shorts
            UTPConstants.PROTOCOL_ID,
            UTPConstants.VERSION,
            self.message_type,
            self.flags,
            self.sequence,
            0  # Reserved bytes
        )
        return header + self.data
    
    @staticmethod
    def deserialize(data: bytes) -> Optional['UTPFrame']:
        """
        Deserialize bytes to a UTP frame.
        
        Args:
            data: Raw bytes containing frame (min 8 bytes for header)
            
        Returns:
            UTPFrame: Deserialized frame, or None if invalid
        """
        if len(data) < BufferLimits.HEADER_SIZE:
            return None
        
        try:
            # Unpack header (8 bytes total)
            protocol_id, version, msg_type, flags, sequence, _reserved = struct.unpack(
                '>BBBBHH',
                data[:BufferLimits.HEADER_SIZE]
            )
            
            # Validate protocol ID and version
            if protocol_id != UTPConstants.PROTOCOL_ID:
                return None
            
            if version != UTPConstants.VERSION:
                return None
            
            # Extract payload
            payload = data[BufferLimits.HEADER_SIZE:]
            
            # Validate payload size
            if len(payload) > BufferLimits.MAX_FRAME_SIZE:
                return None
            
            # Create and return frame
            return UTPFrame(
                message_type=msg_type,
                sequence=sequence,
                data=payload,
                flags=flags
            )
        
        except (struct.error, ValueError):
            return None
    
    def has_flag(self, flag: int) -> bool:
        """
        Check if a specific flag is set.
        
        Args:
            flag: Flag constant from Flags class
            
        Returns:
            bool: True if flag is set
        """
        return bool(self.flags & flag)
    
    def set_flag(self, flag: int) -> None:
        """
        Set a specific flag.
        
        Args:
            flag: Flag constant from Flags class
        """
        self.flags |= flag
    
    def clear_flag(self, flag: int) -> None:
        """
        Clear a specific flag.
        
        Args:
            flag: Flag constant from Flags class
        """
        self.flags &= ~flag
    
    def __repr__(self) -> str:
        """Return string representation of frame."""
        type_names = {
            MessageType.HANDSHAKE_INIT: 'HANDSHAKE_INIT',
            MessageType.HANDSHAKE_RESP: 'HANDSHAKE_RESP',
            MessageType.DATA: 'DATA',
            MessageType.ACK: 'ACK',
            MessageType.CLOSE: 'CLOSE',
        }
        type_name = type_names.get(self.message_type, 'UNKNOWN')
        return (
            f"UTPFrame(type={type_name}, seq={self.sequence}, "
            f"flags={self.flags}, data_len={len(self.data)})"
        )
    
    def __eq__(self, other: object) -> bool:
        """Compare two frames for equality."""
        if not isinstance(other, UTPFrame):
            return False
        return (
            self.message_type == other.message_type
            and self.sequence == other.sequence
            and self.data == other.data
            and self.flags == other.flags
        )
