# UTP Implementation Architecture

## System Components

### 1. Core Protocol Layer (`utp_protocol.py`)
**Responsibility**: UTP frame serialization, frame type definitions, protocol constants

```
┌──────────────────────────────────────┐
│       UTP Protocol Module            │
├──────────────────────────────────────┤
│ • MessageType (Enum)                 │
│ • UTPFrame (Serialization)           │
│ • FrameFlags (Bit flags)             │
│ • ProtocolConstants                  │
└──────────────────────────────────────┘
         ↓                    ↓
   ┌─────────────┐    ┌──────────────┐
   │   Server    │    │   Client     │
   └─────────────┘    └──────────────┘
```

**Key Classes**:
- `MessageType` - Enum for frame types (HANDSHAKE_INIT, HANDSHAKE_RESP, DATA, ACK, CLOSE)
- `UTPFrame` - Represents a single frame with header and payload
  - `serialize()` → bytes
  - `deserialize(bytes)` → UTPFrame (static)
- `FrameFlags` - Bitfield utilities (ACK_REQUIRED, IS_ACK, CLOSE)

### 2. Connection State Machine (`utp_connection.py`)
**Responsibility**: Per-connection lifecycle management, acknowledgment tracking, retransmission

```
              ┌─────────────────────────┐
              │      DISCONNECTED       │
              └──────────┬──────────────┘
                         │ (initiate handshake)
                         ▼
              ┌─────────────────────────┐
        ┌────►│    HANDSHAKING          │◄─────┐
        │     └──────────┬──────────────┘       │
        │                │ (got RESP)           │ (timeout)
        │                ▼                      │ (retry < 3)
        │     ┌─────────────────────────┐       │
        │     │      CONNECTED          ├──────┘
        │     └──────────┬──────────────┘
        │                │ (send/recv DATA)
        │                │ (ACK/retransmit)
        │                │
        │                ▼
        │     ┌─────────────────────────┐
        └─────┤      CLOSING            │
              │ (sent/got CLOSE)        │
              └──────────┬──────────────┘
                         │ (ACK received)
                         ▼
              ┌─────────────────────────┐
              │      CLOSED             │
              └─────────────────────────┘
```

**Key Classes**:
- `UTPState` - Enum (DISCONNECTED, HANDSHAKING, CONNECTED, CLOSING, CLOSED)
- `UTPConnection`
  - Sequence number management (send_seq, recv_seq)
  - Pending acknowledgments tracking
  - Retransmission queue with timestamps
  - Connection timeouts
  - Encryption/decryption coordination

**Retransmission Algorithm**:
```python
def handle_timeout():
    for (seq, data, attempt, last_sent) in pending_acks:
        elapsed = now() - last_sent
        backoff = INITIAL_BACKOFF * (2 ** attempt)
        
        if elapsed > backoff and attempt < MAX_RETRIES:
            resend_frame(seq, data)
            attempt += 1
        elif attempt >= MAX_RETRIES:
            close_connection()  # Hard fail
```

### 3. Server (`server.py` - Enhanced)
**Responsibility**: UDP socket management, connection pooling, message routing

```
┌─────────────────────────────────────────┐
│          UTPServer                      │
├─────────────────────────────────────────┤
│ • UDP Socket (SOCK_DGRAM)              │
│ • Connection Pool (addr → UTPConnection)│
│ • Public Keys Store                    │
│ • Client Names Store                   │
│ • RSA Keys (Server)                    │
└─────────────────────────────────────────┘
         │                │               │
   ┌─────▼─┐        ┌────▼─────┐    ┌──▼───────┐
   │ Receive│        │ Broadcast│    │ Cleanup  │
   │ Loop   │        │ Logic    │    │ Timeout  │
   └────────┘        └──────────┘    └──────────┘
```

**State Transitions**:
```python
class UTPServer:
    def handle_incoming(self):
        while True:
            data, addr = socket.recvfrom()
            frame = UTPFrame.deserialize(data)
            
            if addr not in connections:
                # New connection
                if frame.type == HANDSHAKE_INIT:
                    conn = UTPConnection(addr)
                    connections[addr] = conn
                else:
                    # Ignore unsolicited DATA
                    continue
            
            conn = connections[addr]
            self._dispatch_frame(frame, conn, addr)
    
    def _dispatch_frame(self, frame, conn, addr):
        if frame.type == HANDSHAKE_INIT:
            self._handle_handshake_init(conn, addr)
        elif frame.type == DATA:
            self._handle_data(frame, conn, addr)
        elif frame.type == ACK:
            self._handle_ack(frame, conn)
        elif frame.type == CLOSE:
            self._handle_close(conn, addr)
```

### 4. Client Enhancement (`client.py` - Extended)
**Responsibility**: UI protocol selection, connection management, message I/O

```
┌─────────────────────────────────────────┐
│         CLIENT GUI                      │
├─────────────────────────────────────────┤
│ • Protocol Selection (TCP/UTP)         │
│ • Connection Manager                   │
│ • Send/Receive Threads                 │
│ • Message Display                      │
└─────────────────────────────────────────┘
         │
    ┌────▼─────────────┐
    │ Connection Mode  │
    ├────┬────────────┐
    │    │            │
TCP │ UDP│  (Unified  │
    │    │  Handler)  │
    └────┴────────────┘
```

**Message Flow**:
```
User Input
    │
    ▼
┌─────────────────────┐
│  send_message()     │
└──────┬──────────────┘
       │
       ├─► Format: "name: text"
       │
       ├─► Encrypt with server pubkey
       │
       ├─► Wrap in UTP Frame (if UTP)
       │
       ▼
Transmit to Server
```

---

## Data Flow Diagrams

### Handshake Sequence
```
CLIENT                                  SERVER

┌──────────────┐
│   Init UTP   │
└──────┬───────┘
       │
       │ Frame: HANDSHAKE_INIT
       │ Seq: 1000
       │ Data: empty
       │
       ├────────────────────────────────>
       │                              ┌──────────────┐
       │                              │ Create Conn  │
       │                              │ Seq: 1001    │
       │                              └──────┬───────┘
       │                                     │
       │                    Frame: HANDSHAKE_RESP
       │                    Seq: 1001
       │                    Data: server_pubkey
       │                    Flags: ACK_REQUIRED
       │
       │<────────────────────────────────┤
       │                                 │
   ┌───▼────────────┐             ┌─────▼──┐
   │Store Srv Pubkey│             │ Waiting│
   │Send Name+Pubkey│             │for Ack │
   └───┬────────────┘             └─────┬──┘
       │                                │
       │ Frame: DATA                    │
       │ Seq: 1001                      │
       │ Data: encrypt(name+pubkey)     │
       │ Flags: ACK_REQUIRED            │
       │                                │
       ├────────────────────────────────>
       │                          ┌─────▼──────────┐
       │                          │ Store Name     │
       │                          │ Store Client PK│
       │                          │ Send ACK       │
       │                          └─────┬──────────┘
       │                                │
       │ Frame: ACK                     │
       │ Seq: 1001                      │
       │ (Connection Established)       │
       │                                │
       │<────────────────────────────────┤
       │
   ┌───▼────────────────┐
   │ CONNECTED STATE    │
   │ Ready for messaging│
   └────────────────────┘
```

### Message Broadcast
```
CLIENT1             SERVER             CLIENT2, CLIENT3

Frame: DATA
Seq: 1002
Data: encrypt(msg)
Flags: ACK_REQUIRED
│
├──────────────────────>
                   ┌─────────────────┐
                   │ Decrypt (RSA)   │
                   │ (needs Client1  │
                   │  private key)   │
                   └──────┬──────────┘
                          │
                    ┌─────▼──────────┐
                    │ Broadcast to   │
                    │ other clients  │
                    └──────┬─────────┘
                           │
         Frame: DATA    ───┼─── Frame: DATA
         Seq: 2000         │         Seq: 2001
         Data: msg         │         Data: msg
         (re-encrypted)    │
                           │
                ┌──────────┼──────────┐
                │          │          │
                ▼          ▼          ▼
             CLIENT1   CLIENT2    CLIENT3
            (ignore)  (receive)  (receive)
```

---

## Module Dependencies

```
┌─────────────────────────────────────────────────────┐
│                   server.py                         │
└────────────┬────────────────────────────────────────┘
             │
             ├─► utp_protocol.py (UTPFrame)
             ├─► utp_connection.py (UTPConnection)
             ├─► constants.py (timeouts, limits)
             └─► rsa (encryption)

┌─────────────────────────────────────────────────────┐
│                   client.py                         │
└────────────┬────────────────────────────────────────┘
             │
             ├─► utp_protocol.py (UTPFrame)
             ├─► utp_connection.py (UTPConnection)
             ├─► constants.py (timeouts, limits)
             ├─► tkinter (UI)
             ├─► socket (TCP mode)
             └─► rsa (encryption)

┌─────────────────────────────────────────────────────┐
│              utp_connection.py                      │
└────────────┬────────────────────────────────────────┘
             │
             ├─► utp_protocol.py (UTPFrame)
             ├─► constants.py (timeouts, backoff)
             └─► time (retransmission timing)

┌─────────────────────────────────────────────────────┐
│              utp_protocol.py                        │
└────────────┬────────────────────────────────────────┘
             │
             └─► constants.py (protocol ID, version)
```

---

## Concurrency Model

### Server Threading
```
Main Thread:
  └─► UDP receive loop
      ├─► Accept frames from any client
      ├─► Dispatch to handler (non-blocking)
      └─► Loop continues
  
No per-connection threads needed (UDP is connectionless)
- Polling-based with dictionary lookup
- Lock-free if Python GIL ensures atomic dict ops
- Consider threading.Lock for connections dict if needed
```

### Client Threading
```
Main Thread (Tkinter event loop):
  └─► GUI event handling
      ├─► Connect button → start background thread
      ├─► Send message → directly send (non-blocking UDP)
      └─► UI updates only in main thread

Background Thread:
  └─► Receive loop (TCP or UDP)
      ├─► socket.recvfrom() / socket.recv()
      ├─► Frame parsing
      ├─► Tkinter.after() → update text area in main thread
      └─► Continues listening
```

---

## Error Handling Strategy

### Connection-Level Errors
```python
def handle_frame_error(error_type, conn):
    if error_type == "INVALID_HEADER":
        logger.warning(f"Invalid header from {conn.addr}")
        # Silently drop, wait for retransmit
        
    elif error_type == "SEQUENCE_GAP":
        logger.warning(f"Sequence gap: expected {conn.recv_seq}, got {frame.seq}")
        # Request retransmit via ACK with expected seq
        
    elif error_type == "ACK_TIMEOUT":
        logger.warning(f"ACK timeout for seq {frame.seq}, retransmitting")
        conn.retransmit(frame.seq)
        
    elif error_type == "MAX_RETRIES_EXCEEDED":
        logger.error(f"Max retries exceeded for {conn.addr}, closing")
        conn.close()
```

### Application-Level Errors
```python
def handle_app_error(error_type, client):
    if error_type == "HANDSHAKE_FAILED":
        print("Connection failed: Server unreachable")
        # GUI shows "Server not found" message
        
    elif error_type == "IDLE_TIMEOUT":
        print("Connection lost: Server idle timeout")
        # GUI shows "Connection lost" message
        
    elif error_type == "RSA_DECRYPT_FAILED":
        logger.error("Decryption failed - corrupted message?")
        # Silently drop, GUI unaffected
```

---

## Performance Characteristics

### Expected Benchmarks
| Metric | TCP | UTP | Delta |
|--------|-----|-----|-------|
| Handshake time | 10ms | 12ms | +20% (dual exchange) |
| Message latency (1KB) | 2ms | 1.2ms | -40% (less overhead) |
| Throughput (100 msg/sec) | 2.0Mbps | 2.1Mbps | +5% |
| CPU usage (idle) | 0.1% | 0.1% | =0% |
| Memory (per connection) | 16KB | 24KB | +50% (retransmit queue) |

### Bottlenecks
1. **RSA encryption** - Primary bottleneck (not protocol-specific)
   - Mitigation: Session keys in v2
2. **Frame serialization** - ~0.1ms per frame
   - Optimization: Struct module instead of manual packing
3. **Retransmission overhead** - Only under packet loss
   - Optimization: Selective repeat (v2)

---

## Security Architecture

### Encryption Layers
```
Application Data (Message)
    │
    ▼
┌──────────────────────────────────────────┐
│ Layer 1: RSA Encryption (1024-bit)      │
│ - Client encrypts with server public key│
│ - Server decrypts with private key      │
│ - Broadcast: re-encrypt per client      │
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│ Layer 2: UTP Framing (No integrity)     │
│ - Header not authenticated               │
│ - Frame type, seq, flags visible        │
└──────────────────────────────────────────┘
    │
    ▼
UDP Transport (Plaintext header, encrypted payload)
```

### Key Exchange
```
CLIENT                  SERVER
        
Private Key (client)    Private Key (server)
Public Key (client)     Public Key (server)
    │                        │
    ├─ HANDSHAKE_INIT ─────>
    │                   (no keys yet)
    │
    │ HANDSHAKE_RESP <─────┤
    │ (server public key)   │
    │
    ├─ DATA ──────────────>
    │ (client pubkey + name,
    │  encrypted with server pubkey)
    │
    [Connection established]
    ├─ DATA (encrypted) ──>
    │<─ DATA (encrypted) ──
    │ (each encrypted with respective public keys)
```

### Attack Vectors (Addressed/Unaddressed)
| Vector | Status | Notes |
|--------|--------|-------|
| Man-in-Middle | Unaddressed | No authentication; same as TCP mode |
| Replay attack | Addressed | Sequence numbers prevent replay |
| Spoofing | Partial | Source address binding in v2 |
| Amplification | N/A | Single endpoint, not multi-target |
| Eavesdropping | Addressed | RSA encryption |

---

**End of Architecture Document**
