# UTP Protocol API Specification

**Version:** 1.0  
**Status:** Final Specification  
**Last Updated:** 2026-08-25

---

## Table of Contents

1. [Protocol Overview](#protocol-overview)
2. [Data Types](#data-types)
3. [Server API](#server-api)
4. [Client API](#client-api)
5. [Connection API](#connection-api)
6. [Frame Format](#frame-format)
7. [State Machines](#state-machines)
8. [Error Handling](#error-handling)
9. [Examples](#examples)

---

## Protocol Overview

**UTP** (UDP-based Transfer Protocol) is a custom protocol layer built on top of UDP that provides:
- **Ordered message delivery** via sequence numbering
- **Reliable delivery** via acknowledgment mechanism
- **Connection state management** (handshake, data, close)
- **Transparent encryption** (RSA integration)

### Key Characteristics

| Property | Value |
|----------|-------|
| Transport | UDP (SOCK_DGRAM) |
| Frame Size | 8-byte header + 0-1024 byte payload |
| Sequence Numbers | 16-bit (0-65535, wrapping) |
| Reliability | Selective-repeat ARQ with exponential backoff |
| Ordering | In-order delivery (buffering on receiver) |
| Encryption | RSA 1024-bit (external layer) |

---

## Data Types

### `MessageType` (Enum)

```python
class MessageType(IntEnum):
    HANDSHAKE_INIT = 0x01  # Initiator → Server (empty payload)
    HANDSHAKE_RESP = 0x02  # Server → Initiator (server pubkey)
    DATA = 0x03            # Bidirectional (encrypted payload)
    ACK = 0x04             # Bidirectional (ack sequence in payload)
    CLOSE = 0x05           # Bidirectional (connection close)
```

### `FrameFlags` (Bitfield)

```python
class FrameFlags:
    ACK_REQUIRED = 0x01    # Bit 0: recipient must send ACK
    IS_ACK = 0x02          # Bit 1: this frame is an ACK
    CLOSE = 0x04           # Bit 2: connection termination
    RESERVED = 0xF8        # Bits 3-7: reserved for future use
```

### `UTPState` (Enum)

```python
class UTPState(Enum):
    DISCONNECTED = 0    # Initial state, not connected
    HANDSHAKING = 1     # Handshake in progress
    CONNECTED = 2       # Ready for DATA frames
    CLOSING = 3         # Close initiated, awaiting ACK
    CLOSED = 4          # Connection closed, can be removed
```

### `UTPFrame` (Class)

Complete frame structure (total 8 + len(data) bytes):

```python
class UTPFrame:
    protocol_id: int        # 0x55 (constant)
    version: int            # 0x01 (constant)
    msg_type: MessageType   # Frame type
    flags: int              # FrameFlags bitfield
    sequence: int           # 16-bit sequence number
    data: bytes             # Payload (0-1024 bytes)
    
    def serialize(self) -> bytes:
        """
        Encode frame to bytes (big-endian).
        
        Returns:
            bytes: 8-byte header + payload
            
        Raises:
            ValueError: If data > 1024 bytes
            
        Example:
            >>> frame = UTPFrame(MessageType.DATA, 42, b"hello")
            >>> serialized = frame.serialize()
            >>> len(serialized)
            13  # 8 + 5
        """
    
    @staticmethod
    def deserialize(buffer: bytes) -> 'UTPFrame':
        """
        Decode frame from bytes.
        
        Args:
            buffer: Byte string of at least 8 bytes
            
        Returns:
            UTPFrame: Parsed frame
            
        Raises:
            ValueError: If buffer < 8 bytes or invalid header
            ValueError: If protocol_id != 0x55 or version != 0x01
            
        Example:
            >>> data = b'\x55\x01\x03\x00...'  # 8 + bytes
            >>> frame = UTPFrame.deserialize(data)
            >>> frame.msg_type == MessageType.DATA
            True
        """
```

**Wire Format (8-byte header, big-endian):**

```
Byte 0:     Protocol ID (0x55 = 'U')
Byte 1:     Version (0x01)
Byte 2:     Message Type (enum value)
Byte 3:     Flags (bitfield)
Bytes 4-5:  Sequence Number (uint16_be)
Bytes 6-7:  Payload Length (uint16_be)
[Bytes 8+]: Payload Data (0-1024 bytes)
```

---

## Server API

### `UTPServer` Class

```python
class UTPServer:
    """
    UDP-based chatroom server supporting multiple clients.
    
    Attributes:
        socket (socket.socket): UDP socket (SOCK_DGRAM)
        host (str): Bind address (e.g., '0.0.0.0')
        port (int): Bind port (e.g., 5001)
        connections (dict): {addr → UTPConnection}
        client_names (dict): {addr → str}
        public_keys (dict): {addr → RSA PublicKey}
        server_public_key (RSA PublicKey): Server's public key
        server_private_key (RSA PrivateKey): Server's private key
    """
    
    def __init__(self, host: str, port: int, key_size: int = 1024):
        """
        Initialize UTP server.
        
        Args:
            host: Bind address (e.g., '0.0.0.0' for all interfaces)
            port: Bind port (e.g., 5001)
            key_size: RSA key size in bits (default 1024)
            
        Raises:
            OSError: If bind fails (port already in use, permission denied, etc.)
            
        Example:
            >>> server = UTPServer('0.0.0.0', 5001)
            >>> server.start()
        """
    
    def start(self) -> None:
        """
        Start server receive loop (blocking).
        
        This method runs forever, accepting frames from clients.
        Exit with KeyboardInterrupt (Ctrl+C).
        
        The receive loop:
        1. socket.recvfrom() → (data, addr)
        2. UTPFrame.deserialize(data)
        3. Dispatch frame to handler (see _dispatch_frame)
        4. Continue
        
        Raises:
            KeyboardInterrupt: On Ctrl+C (graceful shutdown)
            
        Example:
            >>> server = UTPServer('0.0.0.0', 5001)
            >>> try:
            ...     server.start()
            ... except KeyboardInterrupt:
            ...     print("Shutting down...")
        """
    
    def stop(self) -> None:
        """
        Stop server and close all connections.
        
        Closes socket and removes all client connections.
        Safe to call from any thread.
        """
    
    def send_to_client(self, addr: tuple, frame: UTPFrame) -> None:
        """
        Send frame to specific client.
        
        Args:
            addr: (host, port) tuple
            frame: UTPFrame to send
            
        Raises:
            OSError: If sendto fails (e.g., network unreachable)
            
        Note:
            Frames are sent immediately; caller responsible for
            tracking acknowledgments if ACK_REQUIRED.
        """
    
    def broadcast(self, message: bytes, sender_addr: tuple) -> None:
        """
        Send message to all connected clients except sender.
        
        Args:
            message: Encrypted message bytes (post-RSA encryption)
            sender_addr: (host, port) of sender (excluded from broadcast)
            
        Note:
            - Message is re-encrypted with each recipient's public key
            - Frames are marked ACK_REQUIRED
            - Acknowledgments tracked per client
            
        Example:
            >>> decrypted = rsa.decrypt(frame.data, server_private_key)
            >>> server.broadcast(decrypted, sender_addr)
        """
    
    def close_connection(self, addr: tuple) -> None:
        """
        Close connection to specific client.
        
        Args:
            addr: (host, port) tuple
            
        Removes from connections dict, cleans up state.
        """
    
    # Private methods (not part of public API):
    
    def _dispatch_frame(self, frame: UTPFrame, addr: tuple) -> None:
        """Route frame to appropriate handler based on type."""
    
    def _handle_handshake_init(self, frame: UTPFrame, addr: tuple) -> None:
        """Handle HANDSHAKE_INIT: create connection, send pubkey."""
    
    def _handle_data(self, frame: UTPFrame, conn: UTPConnection, addr: tuple) -> None:
        """Handle DATA: decrypt, broadcast, send ACK."""
    
    def _handle_ack(self, frame: UTPFrame, conn: UTPConnection) -> None:
        """Handle ACK: mark frame as acknowledged."""
    
    def _handle_close(self, frame: UTPFrame, conn: UTPConnection, addr: tuple) -> None:
        """Handle CLOSE: transition to CLOSED state."""
    
    def _maintenance_loop(self) -> None:
        """Background thread: detect timeouts, process retransmissions."""
```

---

## Client API

### `UTPConnectionManager` Class

```python
class UTPConnectionManager:
    """
    Client-side connection manager for UTP chatroom.
    
    Handles handshake, encryption key exchange, and message I/O.
    
    Attributes:
        server_host (str): Server address
        server_port (int): Server port
        client_name (str): Client display name
        connection (UTPConnection): Underlying connection state
        public_key (RSA PublicKey): Client's public key
        private_key (RSA PrivateKey): Client's private key
        server_public_key (RSA PublicKey): Server's public key
        socket (socket.socket): UDP socket
    """
    
    def __init__(
        self,
        server_host: str,
        server_port: int,
        client_name: str,
        on_message_received=None,
        key_size: int = 1024
    ):
        """
        Initialize UTP connection manager.
        
        Args:
            server_host: Server hostname/IP
            server_port: Server port
            client_name: Display name for this client
            on_message_received: Optional callback fn(message: str)
            key_size: RSA key size in bits (default 1024)
            
        Example:
            >>> def on_msg(msg):
            ...     print(f"Received: {msg}")
            >>> manager = UTPConnectionManager(
            ...     '192.168.1.100', 5001,
            ...     'Alice',
            ...     on_message_received=on_msg
            ... )
        """
    
    def connect(self) -> None:
        """
        Initiate connection to server (blocking).
        
        Handshake sequence:
        1. Send HANDSHAKE_INIT
        2. Receive HANDSHAKE_RESP (server's public key)
        3. Send DATA (client name + public key, encrypted)
        4. Receive ACK
        5. Connection established
        
        Raises:
            ConnectionError: If handshake fails (timeout, invalid response)
            OSError: If socket error occurs
            
        Example:
            >>> manager = UTPConnectionManager('host', 5001, 'Alice')
            >>> manager.connect()
            >>> print("Connected!")
        """
    
    def send_message(self, message: str) -> None:
        """
        Send message to server (non-blocking).
        
        Args:
            message: Message text
            
        Message flow:
        1. Format: "client_name: message"
        2. Encrypt with server's public key
        3. Wrap in DATA frame (ACK_REQUIRED)
        4. Send via UDP
        5. Track in pending acknowledgments
        
        Raises:
            RuntimeError: If not connected
            OSError: If send fails
            
        Example:
            >>> manager.send_message("Hello, world!")
            >>> print("Sent!")
        """
    
    def receive_messages(self) -> None:
        """
        Receive messages from server (blocking).
        
        This method runs in a background thread.
        - Continuously listens for incoming frames
        - Decrypts messages
        - Invokes on_message_received() callback
        
        Exits when:
        - Connection closed
        - Exception occurs (logged, doesn't crash)
        
        Should be run in a threading.Thread:
        
        Example:
            >>> import threading
            >>> manager = UTPConnectionManager(...)
            >>> manager.connect()
            >>> thread = threading.Thread(target=manager.receive_messages)
            >>> thread.start()
        """
    
    def close(self) -> None:
        """
        Close connection gracefully.
        
        - Sends CLOSE frame to server
        - Closes UDP socket
        - Sets state to CLOSED
        
        Safe to call multiple times (idempotent).
        """
    
    def is_connected(self) -> bool:
        """
        Check if connection is established.
        
        Returns:
            bool: True if state is CONNECTED, False otherwise
        """
    
    # Private methods (not part of public API):
    
    def _handle_handshake_response(self, frame: UTPFrame) -> None:
        """Parse HANDSHAKE_RESP, extract server public key."""
    
    def _handle_data_frame(self, frame: UTPFrame) -> None:
        """Receive DATA frame, decrypt, invoke callback."""
    
    def _handle_ack_frame(self, frame: UTPFrame) -> None:
        """Receive ACK, mark frame as acknowledged."""
```

---

## Connection API

### `UTPConnection` Class

```python
class UTPConnection:
    """
    Per-connection state machine and acknowledgment tracker.
    
    Manages:
    - Connection lifecycle (DISCONNECTED → CONNECTED → CLOSED)
    - Sequence number tracking
    - Pending acknowledgments
    - Retransmission state
    - Idle timeouts
    
    Attributes:
        peer_addr (tuple): (host, port)
        state (UTPState): Current state
        send_seq (int): Next sequence number to send (0-65535)
        recv_seq (int): Expected sequence number to receive
        pending_acks (dict): {seq → (frame, timestamp, retry_count)}
        last_activity (float): Timestamp of last frame (for timeout)
    """
    
    def __init__(self, peer_addr: tuple, is_server: bool = False):
        """
        Initialize connection.
        
        Args:
            peer_addr: (host, port) tuple
            is_server: True if this is server-side connection
            
        Initializes state to DISCONNECTED.
        Sets send_seq to random value (0-65535).
        """
    
    def get_state(self) -> UTPState:
        """Get current connection state."""
        
    def is_connected(self) -> bool:
        """Return True if state is CONNECTED."""
        
    def is_idle(self) -> bool:
        """
        Check if connection has been idle too long.
        
        Returns:
            bool: True if (now() - last_activity) > IDLE_TIMEOUT
        """
    
    def update_activity(self) -> None:
        """Update last_activity timestamp (called on frame receipt)."""
    
    def queue_frame(self, frame: UTPFrame) -> None:
        """
        Add frame to pending acknowledgments.
        
        Args:
            frame: UTPFrame with sequence number
            
        Raises:
            RuntimeError: If frame not marked ACK_REQUIRED
            
        Stores (frame, timestamp, attempt=0) in pending_acks[seq].
        """
    
    def acknowledge(self, seq: int) -> bool:
        """
        Mark frame as acknowledged.
        
        Args:
            seq: Sequence number being acknowledged
            
        Returns:
            bool: True if frame was pending (now removed)
            
        If seq not in pending_acks, returns False (no-op).
        """
    
    def get_pending_retransmits(self) -> List[Tuple[int, UTPFrame, float]]:
        """
        Get list of frames ready for retransmission.
        
        Returns:
            List of (seq, frame, next_send_time) for frames
            that have exceeded their backoff timeout.
            
        Example:
            >>> for seq, frame, _ in conn.get_pending_retransmits():
            ...     socket.sendto(frame.serialize(), conn.peer_addr)
            ...     conn.mark_retry(seq)
        """
    
    def mark_retry(self, seq: int) -> None:
        """
        Increment retry count for frame.
        
        Args:
            seq: Sequence number being retried
            
        Raises:
            RuntimeError: If frame exceeds MAX_RETRIES
            
        Updates timestamp to now().
        Increments retry_count.
        If retry_count >= MAX_RETRIES, raises RuntimeError
        (caller should close connection).
        """
    
    def next_send_seq(self) -> int:
        """
        Get next sequence number to use, then increment.
        
        Returns:
            int: Current send_seq (0-65535)
            
        Increments send_seq (wraps at 65536).
        
        Example:
            >>> frame = UTPFrame(MessageType.DATA, conn.next_send_seq(), data)
        """
    
    def expect_recv_seq(self, seq: int) -> bool:
        """
        Check if received sequence is expected.
        
        Args:
            seq: Received sequence number
            
        Returns:
            bool: True if seq == recv_seq
            
        If True, increments recv_seq for next frame.
        If False, frame is out-of-order (should be buffered).
        """
    
    def get_recv_buffer(self) -> dict:
        """
        Get out-of-order receive buffer.
        
        Returns:
            dict: {seq → frame} for buffered frames
            
        Caller uses this to check if gap is now closed.
        """
```

---

## Frame Format

### Serialization Example

**Frame: HANDSHAKE_RESP with server public key**

```python
frame = UTPFrame(
    msg_type=MessageType.HANDSHAKE_RESP,
    sequence=1000,
    data=server_pubkey.save_pkcs1("PEM"),
    requires_ack=True
)

# Serialize
serialized = frame.serialize()

# Byte representation (hex):
# 55          = Protocol ID (0x55)
# 01          = Version (0x01)
# 02          = Message Type (HANDSHAKE_RESP)
# 01          = Flags (ACK_REQUIRED)
# 03E8        = Sequence 1000 (big-endian uint16)
# 01A0        = Payload length 416 (big-endian uint16)
# [416 bytes] = PEM-encoded public key

# Result: 8 + 416 = 424 bytes total
assert len(serialized) == 424
```

### Deserialization Example

```python
# Received 424 bytes
data = b'\x55\x01\x02\x01\x03\xe8\x01\xa0...[416 bytes]...'

frame = UTPFrame.deserialize(data)

assert frame.protocol_id == 0x55
assert frame.version == 0x01
assert frame.msg_type == MessageType.HANDSHAKE_RESP
assert frame.flags & FrameFlags.ACK_REQUIRED == FrameFlags.ACK_REQUIRED
assert frame.sequence == 1000
assert len(frame.data) == 416
```

---

## State Machines

### Client State Machine

```
START
  │
  ├─► DISCONNECTED
  │     │
  │     ├─► connect() called
  │     │     │
  │     │     └─► send HANDSHAKE_INIT
  │     │           │
  │     │           └─► HANDSHAKING
  │     │                 │
  │     │                 ├─► receive HANDSHAKE_RESP
  │     │                 │     │
  │     │                 │     └─► send DATA (name+pubkey)
  │     │                 │           │
  │     │                 │           └─► receive ACK
  │     │                 │                 │
  │     │                 │                 └─► CONNECTED
  │     │                 │                       │
  │     │                 │                       ├─► send DATA (messages)
  │     │                 │                       ├─► receive DATA (broadcasts)
  │     │                 │                       │
  │     │                 │                       └─► close() called
  │     │                 │                             │
  │     │                 │                             └─► send CLOSE
  │     │                 │                                   │
  │     │                 │                                   └─► CLOSING
  │     │                 │                                         │
  │     │                 │                                         └─► receive ACK
  │     │                 │                                               │
  │     │                 │                                               └─► CLOSED
  │     │                 │
  │     │                 ├─► timeout → MAX_RETRIES exceeded
  │     │                 │     │
  │     │                 │     └─► CLOSED (error)
  │     │                 │
  │     │                 └─► socket error
  │     │                       │
  │     │                       └─► CLOSED (error)
  │     │
  │     └─► socket error
  │           │
  │           └─► CLOSED (error)
  │
  └─► END (closed)
```

### Server State Machine (per connection)

```
START
  │
  ├─► DISCONNECTED
  │     │
  │     ├─► receive HANDSHAKE_INIT from new addr
  │     │     │
  │     │     └─► create connection
  │     │           │
  │     │           └─► send HANDSHAKE_RESP (pubkey)
  │     │                 │
  │     │                 └─► HANDSHAKING
  │     │                       │
  │     │                       ├─► receive DATA (name+pubkey)
  │     │                       │     │
  │     │                       │     └─► send ACK
  │     │                       │           │
  │     │                       │           └─► CONNECTED
  │     │                       │                 │
  │     │                       │                 ├─► receive DATA (messages)
  │     │                       │                 │     │
  │     │                       │                 │     └─► broadcast to others
  │     │                       │                 │           │
  │     │                       │                 │           └─► send ACK
  │     │                       │                 │
  │     │                       │                 ├─► receive CLOSE
  │     │                       │                 │     │
  │     │                       │                 │     └─► send ACK
  │     │                       │                 │           │
  │     │                       │                 │           └─► CLOSING
  │     │                       │                 │                 │
  │     │                       │                 │                 └─► remove after delay
  │     │                       │                 │                       │
  │     │                       │                 │                       └─► CLOSED
  │     │                       │                 │
  │     │                       │                 └─► idle timeout (30s)
  │     │                       │                       │
  │     │                       │                       └─► CLOSED (timeout)
  │     │                       │
  │     │                       └─► timeout waiting for DATA
  │     │                             │
  │     │                             └─► CLOSED (handshake timeout)
  │     │
  │     └─► malformed frame ignored
  │           │
  │           └─► (stay DISCONNECTED)
  │
  └─► END (closed/removed)
```

---

## Error Handling

### Exception Classes

```python
class UTPError(Exception):
    """Base exception for UTP protocol errors."""

class UTPConnectionError(UTPError):
    """Connection failed or closed unexpectedly."""
    
class UTPTimeoutError(UTPError):
    """Handshake or operation timed out."""
    
class UTPProtocolError(UTPError):
    """Invalid protocol state or frame format."""
```

### Error Handling Patterns

#### Server-Side

```python
def _dispatch_frame(self, frame: UTPFrame, addr: tuple) -> None:
    try:
        if frame.msg_type == MessageType.HANDSHAKE_INIT:
            self._handle_handshake_init(frame, addr)
        elif frame.msg_type == MessageType.DATA:
            # Ensure connection exists
            if addr not in self.connections:
                logger.warning(f"DATA from unknown addr: {addr}")
                return  # Silently drop
            conn = self.connections[addr]
            self._handle_data(frame, conn, addr)
        elif frame.msg_type == MessageType.ACK:
            if addr not in self.connections:
                return  # Silently drop
            self._handle_ack(frame, self.connections[addr])
        elif frame.msg_type == MessageType.CLOSE:
            if addr in self.connections:
                self._handle_close(frame, self.connections[addr], addr)
        else:
            logger.warning(f"Unknown message type: {frame.msg_type}")
    
    except Exception as e:
        logger.error(f"Error handling frame from {addr}: {e}")
        # Don't crash; continue processing
```

#### Client-Side

```python
def receive_messages(self) -> None:
    while self.is_connected():
        try:
            data, addr = self.socket.recvfrom(1024 + 8)
            frame = UTPFrame.deserialize(data)
            
            if frame.msg_type == MessageType.DATA:
                self._handle_data_frame(frame)
            elif frame.msg_type == MessageType.ACK:
                self._handle_ack_frame(frame)
            elif frame.msg_type == MessageType.CLOSE:
                self.close()
                break
        
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            # Continue trying to receive
            # Only exit if socket is closed
```

---

## Examples

### Example 1: Starting a Server

```python
import logging
from utp_protocol import UTPServer

logging.basicConfig(level=logging.DEBUG)

server = UTPServer('0.0.0.0', 5001)
print("Starting UTP server on port 5001...")

try:
    server.start()  # Blocking
except KeyboardInterrupt:
    print("\nShutting down...")
    server.stop()
```

### Example 2: Connecting a Client

```python
from utp_protocol import UTPConnectionManager
import threading

def on_message(msg):
    print(f"Received: {msg}")

manager = UTPConnectionManager(
    'localhost', 5001,
    'Alice',
    on_message_received=on_message
)

print("Connecting to server...")
manager.connect()
print("Connected!")

# Start receive thread
thread = threading.Thread(target=manager.receive_messages)
thread.daemon = True
thread.start()

# Send messages
manager.send_message("Hello, world!")
manager.send_message("This is a test")

# Clean up
import time
time.sleep(2)
manager.close()
```

### Example 3: Creating & Sending a Frame

```python
from utp_protocol import UTPFrame, MessageType

# Create a DATA frame
frame = UTPFrame(
    msg_type=MessageType.DATA,
    sequence=42,
    data=b"encrypted_message_here",
    requires_ack=True
)

# Serialize
serialized = frame.serialize()
print(f"Frame size: {len(serialized)} bytes")

# Send via UDP
socket.sendto(serialized, ('192.168.1.100', 5001))

# Track for retransmission
connection.queue_frame(frame)
```

### Example 4: Handling Acknowledgments

```python
from utp_protocol import UTPConnection

conn = UTPConnection(('192.168.1.50', 12345))

# Track a sent frame
frame = UTPFrame(MessageType.DATA, conn.next_send_seq(), data)
conn.queue_frame(frame)

# Later, receive ACK with sequence number
ack_frame = UTPFrame.deserialize(received_data)
if ack_frame.msg_type == MessageType.ACK:
    seq = int.from_bytes(ack_frame.data[:2], 'big')
    success = conn.acknowledge(seq)
    if success:
        print(f"Frame {seq} acknowledged!")
    else:
        print(f"Frame {seq} was not pending")
```

### Example 5: Handling Retransmissions

```python
from utp_protocol import UTPConnection
import time

conn = UTPConnection(('client', 12345))

# Send some frames
for i in range(5):
    frame = UTPFrame(MessageType.DATA, conn.next_send_seq(), data)
    conn.queue_frame(frame)
    socket.sendto(frame.serialize(), conn.peer_addr)

# Main loop: check for retransmissions
last_check = time.time()
while conn.is_connected():
    now = time.time()
    if now - last_check > 0.1:  # Check every 100ms
        for seq, frame, _ in conn.get_pending_retransmits():
            print(f"Retransmitting frame {seq}")
            socket.sendto(frame.serialize(), conn.peer_addr)
            conn.mark_retry(seq)  # Raises if MAX_RETRIES exceeded
        last_check = now
    
    # Process incoming frames...
```

---

**End of API Specification**

*This document serves as the authoritative reference for implementing UTP protocol support.*
