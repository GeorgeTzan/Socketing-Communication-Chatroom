"""
Unit Tests for UTP Protocol Implementation
File: test_utp_protocol.py
Date: 2026-08-25

Comprehensive test suite for UTPFrame serialization and deserialization.
"""

import pytest
from utp_protocol import UTPFrame
from constants import (
    UTPConstants,
    MessageType,
    Flags,
    BufferLimits,
    SequenceNumbers
)


class TestUTPFrameCreation:
    """Test frame creation and validation."""
    
    def test_create_frame_with_data(self):
        """Test creating a DATA frame."""
        data = b"Hello, World!"
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=1,
            data=data
        )
        assert frame.message_type == MessageType.DATA
        assert frame.sequence == 1
        assert frame.data == data
        assert frame.flags == 0
    
    def test_create_frame_empty_payload(self):
        """Test creating frame with empty payload."""
        frame = UTPFrame(
            message_type=MessageType.ACK,
            sequence=5
        )
        assert frame.data == b''
    
    def test_create_handshake_init(self):
        """Test creating HANDSHAKE_INIT frame."""
        frame = UTPFrame(
            message_type=MessageType.HANDSHAKE_INIT,
            sequence=0
        )
        assert frame.message_type == MessageType.HANDSHAKE_INIT
    
    def test_create_handshake_resp(self):
        """Test creating HANDSHAKE_RESP frame."""
        frame = UTPFrame(
            message_type=MessageType.HANDSHAKE_RESP,
            sequence=1
        )
        assert frame.message_type == MessageType.HANDSHAKE_RESP
    
    def test_create_close_frame(self):
        """Test creating CLOSE frame."""
        frame = UTPFrame(
            message_type=MessageType.CLOSE,
            sequence=100
        )
        assert frame.message_type == MessageType.CLOSE
    
    def test_invalid_message_type(self):
        """Test that invalid message type raises ValueError."""
        with pytest.raises(ValueError):
            UTPFrame(message_type=0xFF, sequence=0)
    
    def test_sequence_out_of_range_negative(self):
        """Test that negative sequence raises ValueError."""
        with pytest.raises(ValueError):
            UTPFrame(message_type=MessageType.DATA, sequence=-1)
    
    def test_sequence_out_of_range_too_large(self):
        """Test that sequence > 65535 raises ValueError."""
        with pytest.raises(ValueError):
            UTPFrame(message_type=MessageType.DATA, sequence=65536)
    
    def test_sequence_max_valid(self):
        """Test that max sequence (65535) is valid."""
        frame = UTPFrame(message_type=MessageType.DATA, sequence=65535)
        assert frame.sequence == 65535
    
    def test_payload_too_large(self):
        """Test that payload > 1024 bytes raises ValueError."""
        with pytest.raises(ValueError):
            UTPFrame(
                message_type=MessageType.DATA,
                sequence=0,
                data=b'x' * (BufferLimits.MAX_FRAME_SIZE + 1)
            )
    
    def test_max_payload_valid(self):
        """Test that max payload (1024 bytes) is valid."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=b'x' * BufferLimits.MAX_FRAME_SIZE
        )
        assert len(frame.data) == BufferLimits.MAX_FRAME_SIZE


class TestSerialization:
    """Test frame serialization."""
    
    def test_serialize_data_frame(self):
        """Test serializing DATA frame."""
        data = b"Hello"
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=42,
            data=data
        )
        serialized = frame.serialize()
        
        # Should be 8-byte header + 5-byte payload
        assert len(serialized) == 8 + 5
        assert serialized[-5:] == data
    
    def test_serialize_frame_size(self):
        """Test that serialized frame is header + payload."""
        for size in [0, 1, 100, 512, 1024]:
            frame = UTPFrame(
                message_type=MessageType.DATA,
                sequence=0,
                data=b'x' * size
            )
            serialized = frame.serialize()
            assert len(serialized) == BufferLimits.HEADER_SIZE + size
    
    def test_serialize_protocol_id(self):
        """Test that protocol ID is correct in serialized frame."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=b"test"
        )
        serialized = frame.serialize()
        assert serialized[0] == UTPConstants.PROTOCOL_ID
    
    def test_serialize_version(self):
        """Test that version is correct in serialized frame."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=b"test"
        )
        serialized = frame.serialize()
        assert serialized[1] == UTPConstants.VERSION
    
    def test_serialize_message_type(self):
        """Test that message type is correct in serialized frame."""
        for msg_type in [
            MessageType.HANDSHAKE_INIT,
            MessageType.HANDSHAKE_RESP,
            MessageType.DATA,
            MessageType.ACK,
            MessageType.CLOSE
        ]:
            frame = UTPFrame(message_type=msg_type, sequence=0)
            serialized = frame.serialize()
            assert serialized[2] == msg_type
    
    def test_serialize_sequence_number(self):
        """Test that sequence number is encoded correctly."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=256,  # 0x0100 in big-endian
            data=b"test"
        )
        serialized = frame.serialize()
        # Sequence is at bytes 4-5 (big-endian)
        seq_bytes = serialized[4:6]
        assert seq_bytes == b'\x01\x00'
    
    def test_serialize_flags(self):
        """Test that flags are encoded correctly."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=b"test",
            flags=Flags.ACK_REQUIRED | Flags.IS_ACK
        )
        serialized = frame.serialize()
        assert serialized[3] == (Flags.ACK_REQUIRED | Flags.IS_ACK)
    
    def test_serialize_empty_payload(self):
        """Test serializing frame with no payload."""
        frame = UTPFrame(
            message_type=MessageType.ACK,
            sequence=10
        )
        serialized = frame.serialize()
        assert len(serialized) == BufferLimits.HEADER_SIZE


class TestDeserialization:
    """Test frame deserialization."""
    
    def test_deserialize_valid_frame(self):
        """Test deserializing a valid frame."""
        original = UTPFrame(
            message_type=MessageType.DATA,
            sequence=42,
            data=b"Hello"
        )
        serialized = original.serialize()
        deserialized = UTPFrame.deserialize(serialized)
        
        assert deserialized is not None
        assert deserialized.message_type == MessageType.DATA
        assert deserialized.sequence == 42
        assert deserialized.data == b"Hello"
    
    def test_deserialize_all_message_types(self):
        """Test deserializing all message types."""
        for msg_type in [
            MessageType.HANDSHAKE_INIT,
            MessageType.HANDSHAKE_RESP,
            MessageType.DATA,
            MessageType.ACK,
            MessageType.CLOSE
        ]:
            original = UTPFrame(message_type=msg_type, sequence=1)
            serialized = original.serialize()
            deserialized = UTPFrame.deserialize(serialized)
            
            assert deserialized is not None
            assert deserialized.message_type == msg_type
    
    def test_deserialize_max_payload(self):
        """Test deserializing frame with maximum payload."""
        data = b'x' * BufferLimits.MAX_FRAME_SIZE
        original = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=data
        )
        serialized = original.serialize()
        deserialized = UTPFrame.deserialize(serialized)
        
        assert deserialized is not None
        assert deserialized.data == data
    
    def test_deserialize_sequence_wraparound(self):
        """Test that sequence wraparound (65535) deserializes correctly."""
        original = UTPFrame(
            message_type=MessageType.DATA,
            sequence=SequenceNumbers.MAX_SEQUENCE
        )
        serialized = original.serialize()
        deserialized = UTPFrame.deserialize(serialized)
        
        assert deserialized is not None
        assert deserialized.sequence == SequenceNumbers.MAX_SEQUENCE
    
    def test_deserialize_flags(self):
        """Test that flags are preserved through serialization."""
        flags = Flags.ACK_REQUIRED | Flags.CLOSE
        original = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            flags=flags
        )
        serialized = original.serialize()
        deserialized = UTPFrame.deserialize(serialized)
        
        assert deserialized is not None
        assert deserialized.flags == flags
    
    def test_deserialize_invalid_protocol_id(self):
        """Test that invalid protocol ID returns None."""
        data = b'\xAA\x01\x03\x00\x00\x00\x00\x00test'  # Wrong protocol ID with proper 8-byte header
        result = UTPFrame.deserialize(data)
        assert result is None
    
    def test_deserialize_invalid_version(self):
        """Test that invalid version returns None."""
        data = b'\x55\xFF\x03\x00\x00\x00\x00\x00test'  # Wrong version with proper 8-byte header
        result = UTPFrame.deserialize(data)
        assert result is None
    
    def test_deserialize_truncated_header(self):
        """Test that truncated header returns None."""
        data = b'\x55\x01\x03'  # Only 3 bytes (need 8)
        result = UTPFrame.deserialize(data)
        assert result is None
    
    def test_deserialize_empty_data(self):
        """Test that empty data returns None."""
        result = UTPFrame.deserialize(b'')
        assert result is None
    
    def test_deserialize_oversized_payload(self):
        """Test that payload > 1024 bytes returns None."""
        header = b'\x55\x01\x03\x00\x00\x00\x00\x00'  # 8-byte header
        payload = b'x' * (BufferLimits.MAX_FRAME_SIZE + 1)
        data = header + payload
        result = UTPFrame.deserialize(data)
        assert result is None


class TestIdempotency:
    """Test that serialization is idempotent."""
    
    def test_round_trip_data_frame(self):
        """Test serialize -> deserialize -> serialize produces same result."""
        original = UTPFrame(
            message_type=MessageType.DATA,
            sequence=42,
            data=b"Hello, World!",
            flags=Flags.ACK_REQUIRED
        )
        
        serialized1 = original.serialize()
        deserialized = UTPFrame.deserialize(serialized1)
        serialized2 = deserialized.serialize()
        
        assert serialized1 == serialized2
    
    def test_round_trip_all_types(self):
        """Test round-trip for all message types."""
        for msg_type in [
            MessageType.HANDSHAKE_INIT,
            MessageType.HANDSHAKE_RESP,
            MessageType.DATA,
            MessageType.ACK,
            MessageType.CLOSE
        ]:
            original = UTPFrame(
                message_type=msg_type,
                sequence=100,
                data=b"test"
            )
            
            serialized1 = original.serialize()
            deserialized = UTPFrame.deserialize(serialized1)
            serialized2 = deserialized.serialize()
            
            assert serialized1 == serialized2


class TestFlagOperations:
    """Test flag management methods."""
    
    def test_has_flag_true(self):
        """Test has_flag returns True when flag is set."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            flags=Flags.ACK_REQUIRED
        )
        assert frame.has_flag(Flags.ACK_REQUIRED)
    
    def test_has_flag_false(self):
        """Test has_flag returns False when flag is not set."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            flags=0
        )
        assert not frame.has_flag(Flags.ACK_REQUIRED)
    
    def test_set_flag(self):
        """Test set_flag sets a flag."""
        frame = UTPFrame(message_type=MessageType.DATA, sequence=0)
        frame.set_flag(Flags.ACK_REQUIRED)
        assert frame.has_flag(Flags.ACK_REQUIRED)
    
    def test_clear_flag(self):
        """Test clear_flag removes a flag."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            flags=Flags.ACK_REQUIRED
        )
        frame.clear_flag(Flags.ACK_REQUIRED)
        assert not frame.has_flag(Flags.ACK_REQUIRED)
    
    def test_multiple_flags(self):
        """Test multiple flags can be set and cleared independently."""
        frame = UTPFrame(message_type=MessageType.DATA, sequence=0)
        frame.set_flag(Flags.ACK_REQUIRED)
        frame.set_flag(Flags.IS_ACK)
        
        assert frame.has_flag(Flags.ACK_REQUIRED)
        assert frame.has_flag(Flags.IS_ACK)
        
        frame.clear_flag(Flags.ACK_REQUIRED)
        assert not frame.has_flag(Flags.ACK_REQUIRED)
        assert frame.has_flag(Flags.IS_ACK)


class TestEquality:
    """Test frame equality comparison."""
    
    def test_equal_frames(self):
        """Test that identical frames are equal."""
        frame1 = UTPFrame(
            message_type=MessageType.DATA,
            sequence=42,
            data=b"test",
            flags=Flags.ACK_REQUIRED
        )
        frame2 = UTPFrame(
            message_type=MessageType.DATA,
            sequence=42,
            data=b"test",
            flags=Flags.ACK_REQUIRED
        )
        assert frame1 == frame2
    
    def test_different_type(self):
        """Test that frames with different types are not equal."""
        frame1 = UTPFrame(message_type=MessageType.DATA, sequence=0)
        frame2 = UTPFrame(message_type=MessageType.ACK, sequence=0)
        assert frame1 != frame2
    
    def test_different_sequence(self):
        """Test that frames with different sequences are not equal."""
        frame1 = UTPFrame(message_type=MessageType.DATA, sequence=0)
        frame2 = UTPFrame(message_type=MessageType.DATA, sequence=1)
        assert frame1 != frame2
    
    def test_different_data(self):
        """Test that frames with different data are not equal."""
        frame1 = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=b"a"
        )
        frame2 = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            data=b"b"
        )
        assert frame1 != frame2
    
    def test_different_flags(self):
        """Test that frames with different flags are not equal."""
        frame1 = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            flags=Flags.ACK_REQUIRED
        )
        frame2 = UTPFrame(
            message_type=MessageType.DATA,
            sequence=0,
            flags=0
        )
        assert frame1 != frame2
    
    def test_not_equal_to_other_type(self):
        """Test that frame is not equal to non-frame objects."""
        frame = UTPFrame(message_type=MessageType.DATA, sequence=0)
        assert frame != "not a frame"
        assert frame != 42
        assert frame != None


class TestRepr:
    """Test string representation."""
    
    def test_repr_data_frame(self):
        """Test repr for DATA frame."""
        frame = UTPFrame(
            message_type=MessageType.DATA,
            sequence=42,
            data=b"hello"
        )
        repr_str = repr(frame)
        assert "DATA" in repr_str
        assert "seq=42" in repr_str
        assert "data_len=5" in repr_str
    
    def test_repr_includes_type(self):
        """Test repr includes message type."""
        for msg_type, type_name in [
            (MessageType.HANDSHAKE_INIT, "HANDSHAKE_INIT"),
            (MessageType.ACK, "ACK"),
            (MessageType.CLOSE, "CLOSE"),
        ]:
            frame = UTPFrame(message_type=msg_type, sequence=0)
            assert type_name in repr(frame)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
