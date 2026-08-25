# Implementation Specification: UTP Support for Socketing Communication Chatroom

**Issue:** #1 - Add UTP support to the application  
**Date:** 2026-08-25  
**Status:** Specification Ready for Implementation  
**Architect:** Autonomous Principal Software Architect

---

## Executive Summary

This specification defines the implementation strategy for adding UDP-based Transfer Protocol (UTP) support to the existing TCP-based chatroom application. UTP provides benefits for low-latency communication scenarios while maintaining message reliability through custom protocol mechanisms.

**Key Objectives:**
- Support both TCP and UTP protocols concurrently
- Maintain backward compatibility with existing TCP clients
- Implement message ordering and delivery guarantees over UDP
- Preserve existing RSA encryption layer
- Minimize performance degradation

---

## 1. Current Architecture Analysis

### 1.1 Existing TCP Implementation
- **Server** (`server.py`): Multi-threaded TCP server using `socket.SOCK_STREAM`
- **Client** (`client.py`): Tkinter GUI client with TCP connection
- **Security**: RSA 1024-bit encryption for all messages
- **Message Model**: Encrypted byte streams with 1024-byte buffer

### 1.2 Current Limitations
- TCP adds header overhead (20+ bytes)
- Connection-oriented model creates latency in high-frequency messaging
- No support for unreliable but faster communication scenarios

---

## 2. UTP Protocol Design

### 2.1 Protocol Overview
**UTP** (UDP-based Transfer Protocol) will be implemented as a custom layer over UDP providing:
- Sequence numbering for message ordering
- Acknowledgment mechanism for reliability
- Connection state management
- Packet loss recovery

### 2.2 Message Format

```
UTP Frame Structure (Big-Endian):
┌─────────────┬──────────┬──────────┬──────────┬─────────────┬────────────────────┐
│ Protocol ID │ Version  │ Type     │ Flags    │ Sequence#   │ Data               │
│ (1 byte)    │ (1 byte) │ (1 byte) │ (1 byte) │ (2 bytes)   │ (Variable - 1024B) │
└─────────────┴──────────┴──────────┴──────────┴─────────────┴────────────────────┐

Protocol ID: 0x55 (constant, 'U' for UTP)
Version: 0x01
Type Values:
  0x01 = HANDSHAKE_INIT (client initiates)
  0x02 = HANDSHAKE_RESP (server responds)
  0x03 = DATA (message data)
  0x04 = ACK (acknowledgment)
  0x05 = CLOSE (connection close)

Flags:
  Bit 0: Requires ACK
  Bit 1: Is ACK
  Bit 2: Connection termination
```

### 2.3 Connection State Machine

```
CLIENT                              SERVER
  │                                    │
  ├──────── HANDSHAKE_INIT ───────────>│
  │                                 (bind address)
  │                                    │
  │<────── HANDSHAKE_RESP ─────────────┤
  │       (public key exchange)         │
  │                                    │
  │───── DATA (ACK_REQUIRED) ────────>│
  │                                    │
  │<────── ACK ─────────────────────────┤
  │                                    │
  │───── DATA (ACK_REQUIRED) ────────>│
  │       (name + RSA public key)       │
  │<────── ACK ─────────────────────────┤
  │                                    │
  │      CONNECTED STATE               │
  │      (bidirectional messaging)     │
  │                                    │
  │───── CLOSE ──────────────────────>│
  │<────── ACK ─────────────────────────┤
```

---

## 3. Implementation Architecture

### 3.1 Module Structure

```
├── server.py
│   ├── UTPServer (new class)
│   ├── TCPServer (existing, refactored)
│   └── main()
├── client.py
│   ├── CLIENT (existing, enhanced)
│   └── UTPConnectionManager (new class)
├── utp_protocol.py (new module)
│   ├── UTPFrame
│   ├── MessageType
│   ├── UTPState
│   └── Frame parsing/serialization
├── utp_connection.py (new module)
│   ├── UTPConnection (connection handler)
│   └── RetransmissionTimer
└── constants.py (new module)
    └── Protocol constants, timeouts, buffer sizes
```

### 3.2 UTPFrame Class
**File:** `utp_protocol.py`

```python
class MessageType(IntEnum):
    HANDSHAKE_INIT = 0x01
    HANDSHAKE_RESP = 0x02
    DATA = 0x03
    ACK = 0x04
    CLOSE = 0x05

class UTPFrame:
    def __init__(self, msg_type, sequence, data=b'', requires_ack=False):
        self.protocol_id = 0x55
        self.version = 0x01
        self.msg_type = msg_type
        self.flags = 0x01 if requires_ack else 0x00
        self.sequence = sequence
        self.data = data

    def serialize(self) -> bytes:
        # Return 8-byte header + data

    @staticmethod
    def deserialize(buffer: bytes) -> 'UTPFrame':
        # Parse buffer and return UTPFrame instance
```

### 3.3 UTPConnection Class
**File:** `utp_connection.py`

Manages per-connection state:
- Sequence number tracking
- Pending acknowledgments
- Retransmission queue with exponential backoff
- Connection timeouts (30 seconds idle)
- Encryption/decryption coordination with RSA keys

```python
class UTPConnection:
    def __init__(self, peer_addr, use_ack_mode=True):
        self.peer_addr = peer_addr
        self.state = UTPState.HANDSHAKING
        self.send_seq = random.randint(1, 65535)
        self.recv_seq = None
        self.pending_acks = {}  # seq -> (data, timestamp)
        self.last_activity = time.time()
        self.timeout = 30.0
```

### 3.4 UTPServer Class
**File:** `server.py` (new class)

```python
class UTPServer:
    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.connections = {}  # addr -> UTPConnection
        self.client_names = {}
        self.public_keys = {}
        self.server_keys = rsa.newkeys(1024)

    def handle_incoming(self):
        # Main receive loop
        while True:
            data, addr = self.socket.recvfrom(1024 + 8)
            frame = UTPFrame.deserialize(data)
            self._process_frame(frame, addr)

    def _process_frame(self, frame, addr):
        # Dispatch based on frame type
        # Handle HANDSHAKE_INIT, DATA, ACK, CLOSE

    def broadcast(self, message, sender_addr):
        # Send to all connected clients except sender
```

### 3.5 Client Enhancement
**File:** `client.py` (modified)

```python
class CLIENT:
    def __init__(self):
        # ... existing init ...
        self.protocol_mode = ProtocolMode.TCP  # default
        self.utp_manager = None

    def connect_to_server(self):
        protocol = self.protocol_var.get()  # radio button selection
        if protocol == "TCP":
            self._connect_tcp()
        else:
            self._connect_utp()

    def _connect_utp(self):
        self.utp_manager = UTPConnectionManager(
            host=self.ip_var.get(),
            port=int(self.port_var.get()),
            name=self.name_var.get()
        )
        self.utp_manager.connect()
```

---

## 4. Implementation Phases

### Phase 1: Core Protocol (Days 1-2)
- [ ] Create `utp_protocol.py` with UTPFrame serialization/deserialization
- [ ] Create `constants.py` for protocol constants
- [ ] Unit tests for frame encoding/decoding

### Phase 2: Connection Management (Days 2-3)
- [ ] Implement `UTPConnection` state machine
- [ ] Retransmission logic with exponential backoff
- [ ] Timeout handling
- [ ] Unit tests for connection lifecycle

### Phase 3: Server Integration (Days 3-4)
- [ ] Implement `UTPServer` class
- [ ] Handle handshake protocol
- [ ] RSA key exchange over UDP
- [ ] Message routing and broadcast
- [ ] Integration tests with existing encryption

### Phase 4: Client Integration (Days 4-5)
- [ ] Add protocol selection UI (radio buttons: TCP/UTP)
- [ ] Implement `UTPConnectionManager`
- [ ] Handle client-side handshake
- [ ] Integrate with existing message send/receive
- [ ] End-to-end tests

### Phase 5: Testing & Optimization (Days 5-6)
- [ ] Packet loss simulation tests
- [ ] Performance benchmarks (TCP vs UTP)
- [ ] Connection stress tests
- [ ] Documentation

---

## 5. Technical Specifications

### 5.1 Sequence Numbering
- 16-bit sequence numbers (0-65535)
- Wraps around; receiver tracks expected sequence
- Out-of-order delivery: buffer until sequence gap closes

### 5.2 Acknowledgment Strategy
- Selective acknowledgment: ACK includes received sequence
- ACK timeout: 200ms default
- Max retransmissions: 5 (before connection reset)
- Exponential backoff: 200ms → 400ms → 800ms → 1.6s → 3.2s

### 5.3 Buffer Management
- Send buffer: 64KB (multiple frames queued)
- Receive buffer: 32KB (reassembly)
- Frame size: ≤1024 bytes (same as TCP buffer)

### 5.4 Encryption Integration
- RSA encryption applied **after** UTP framing
- Public key exchange during handshake (before DATA frames)
- All data payloads encrypted end-to-end

### 5.5 Timeout Behavior
- Idle timeout: 30 seconds (no activity)
- Handshake timeout: 5 seconds
- ACK timeout: 200ms (configurable)

---

## 6. Error Handling

### 6.1 Failure Scenarios
| Scenario | Behavior |
|----------|----------|
| Packet loss | Retransmit with backoff; connection reset after 5 retries |
| Out-of-order frames | Buffer until gap closes; request retransmit if timeout |
| Duplicate frame | Discard (track received sequences) |
| Invalid checksum | Discard frame (not implemented in v1, add in v2) |
| Handshake timeout | Retry up to 3 times, then fail |
| Idle timeout | Close connection, notify user |

### 6.2 Logging Strategy
```python
# DEBUG: Connection lifecycle events
logger.debug(f"UTP handshake initiated with {addr}")
logger.debug(f"Frame {seq} retransmitted (attempt 2/5)")

# WARNING: Recoverable errors
logger.warning(f"Packet loss detected: {seq} missing")
logger.warning(f"Connection timeout for {addr}")

# ERROR: Unrecoverable
logger.error(f"Handshake failed with {addr}: max retries")
```

---

## 7. Testing Strategy

### 7.1 Unit Tests (`test_utp_protocol.py`)
```python
def test_frame_serialization():
    frame = UTPFrame(MessageType.DATA, 42, b"hello")
    serialized = frame.serialize()
    deserialized = UTPFrame.deserialize(serialized)
    assert deserialized.sequence == 42

def test_sequence_wraparound():
    # Test 65535 + 1 = 0 wrapping

def test_invalid_frame_rejected():
    # Corrupt header, verify rejection
```

### 7.2 Integration Tests (`test_utp_integration.py`)
```python
def test_handshake_succeeds():
    # Client handshake with server

def test_message_delivery():
    # Send message, verify receipt

def test_broadcast_multiple_clients():
    # Connect 3 clients, broadcast from 1, verify others receive

def test_packet_loss_recovery():
    # Simulate 10% packet loss, verify retransmission
```

### 7.3 Performance Tests
```python
def benchmark_throughput():
    # Measure TCP vs UTP message throughput
    # Expected: UTP 5-10% faster (lower overhead)

def benchmark_latency():
    # Measure round-trip time
    # Expected: UTP 10-20% lower latency
```

---

## 8. Backward Compatibility

### 8.1 Server Configuration
```python
# server.py startup
parser = argparse.ArgumentParser()
parser.add_argument('--tcp-port', type=int, default=5000)
parser.add_argument('--utp-port', type=int, default=5001)
parser.add_argument('--protocol', choices=['tcp', 'utp', 'both'], default='both')

# Run both servers if 'both' selected
```

### 8.2 Client UI Changes
- New radio button: "Connection Protocol"
  - Option 1: "TCP (Original)"
  - Option 2: "UTP (Low-latency)"
- Help text: "UTP may be faster on stable networks"

### 8.3 No Breaking Changes
- Existing TCP clients connect unchanged
- UTP is opt-in via UI
- Message format unchanged (post-encryption)

---

## 9. Security Considerations

### 9.1 UDP-Specific Risks
- **Spoofing**: Mitigate with source address binding (not in v1)
- **Amplification**: Not applicable (single endpoint)
- **Replay**: Sequence numbers prevent old message replay

### 9.2 Encryption Remains Unchanged
- RSA 1024-bit encryption unchanged
- All data encrypted before transmission over UDP
- Public key exchange same protocol as TCP

### 9.3 Recommendations for Production
- Upgrade RSA to 2048-bit minimum
- Add HMAC for integrity (not just encryption)
- Implement connection tokens to prevent spoofing
- Rate limiting on handshake (DoS protection)

---

## 10. Configuration & Constants

**File:** `constants.py`

```python
# Protocol
UTP_PROTOCOL_ID = 0x55
UTP_VERSION = 0x01

# Timeouts (milliseconds)
ACK_TIMEOUT = 200
HANDSHAKE_TIMEOUT = 5000
IDLE_TIMEOUT = 30000

# Limits
MAX_RETRIES = 5
MAX_BUFFER_SIZE = 65536
MAX_FRAME_SIZE = 1024

# Backoff (ms)
INITIAL_BACKOFF = 200
MAX_BACKOFF = 3200
```

---

## 11. Deployment Checklist

- [ ] All unit tests pass (>95% coverage)
- [ ] Integration tests pass (3+ clients)
- [ ] Performance benchmarks validated (latency vs TCP)
- [ ] Documentation complete
- [ ] Code review passed
- [ ] Backward compatibility verified (TCP clients still work)
- [ ] Docker container updated (exposes both ports)
- [ ] User documentation (README, UI help)

---

## 12. Success Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Protocol Correctness | 100% | All test cases pass |
| Message Delivery | 99.9% | With 10% packet loss, >99% delivered |
| Latency Improvement | 10-20% | Benchmark vs TCP |
| Throughput | ±5% of TCP | Message/sec metric |
| Backward Compatibility | 100% | TCP clients work unchanged |
| Code Coverage | >90% | New modules only |

---

## 13. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| UDP packet loss in unstable networks | Medium | High | Implement robust retransmission with exponential backoff |
| Performance regression in TCP mode | Low | High | Performance testing before merge |
| Connection state sync issues | Low | Medium | Comprehensive state machine tests |
| RSA encryption overhead not amortized | Medium | Low | Benchmark; consider switching to session keys in v2 |

---

## 14. Future Enhancements (v2+)

- **Session-based encryption**: Use RSA to exchange AES keys, reduce overhead
- **Connection pooling**: Multiple UDP flows per client
- **Congestion control**: AIMD algorithm for fairness
- **IPv6 support**: Dual-stack
- **DTLS integration**: Replace custom UTP with standard protocol
- **Metrics collection**: Real-time performance telemetry

---

## Appendix A: Reference Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Chatroom Application                     │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
        ┌───────▼────────┐    │    ┌───────▼────────┐
        │  TCP Server    │    │    │  UTP Server    │
        │  (Port 5000)   │    │    │  (Port 5001)   │
        └───────┬────────┘    │    └───────┬────────┘
                │             │             │
        ┌───────▼──────┐  Clients   ┌───────▼──────┐
        │ TCP Client   │            │ UTP Client   │
        │ (Socket)     │            │ (Datagram)   │
        └──────────────┘            └──────────────┘
                │                         │
                └────────────┬────────────┘
                             │
                    ┌────────▼────────┐
                    │ RSA Encryption  │
                    │ (Both modes)    │
                    └─────────────────┘
```

---

**Document End**  
*This specification is ready for engineering team implementation review.*
