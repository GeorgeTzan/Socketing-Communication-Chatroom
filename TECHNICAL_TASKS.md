# Technical Implementation Tasks for UTP Support

**Epic:** UTP Support (Issue #1)  
**Priority:** High  
**Complexity:** High (6-8 engineering days)

---

## Task Breakdown

### PHASE 1: Protocol Definition & Testing Foundation

#### Task 1.1: Create `constants.py`
**Objective**: Define all protocol constants and configuration parameters

**Acceptance Criteria**:
- [ ] Protocol identifiers defined (UTP_PROTOCOL_ID = 0x55, VERSION = 0x01)
- [ ] Message type constants defined (HANDSHAKE_INIT, HANDSHAKE_RESP, DATA, ACK, CLOSE)
- [ ] Timeout constants (ACK_TIMEOUT=200ms, HANDSHAKE_TIMEOUT=5s, IDLE_TIMEOUT=30s)
- [ ] Buffer limits (MAX_FRAME_SIZE=1024, MAX_BUFFER_SIZE=65KB, SEND_BUFFER_SIZE=64KB)
- [ ] Retransmission parameters (MAX_RETRIES=5, INITIAL_BACKOFF=200ms, MAX_BACKOFF=3.2s)
- [ ] Can be imported without errors
- [ ] All values documented with rationale

**Estimated Effort**: 2 hours

**Dependencies**: None

**Code Structure**:
```python
# constants.py
class UTPConstants:
    PROTOCOL_ID = 0x55
    VERSION = 0x01
    
class MessageType:
    HANDSHAKE_INIT = 0x01
    HANDSHAKE_RESP = 0x02
    DATA = 0x03
    ACK = 0x04
    CLOSE = 0x05
    
class Timeouts:
    ACK_MS = 200
    HANDSHAKE_MS = 5000
    IDLE_MS = 30000
```

---

#### Task 1.2: Create `utp_protocol.py` - Frame Serialization
**Objective**: Implement UTPFrame class with serialize/deserialize functionality

**Acceptance Criteria**:
- [ ] `UTPFrame` class with __init__, serialize(), deserialize() methods
- [ ] Header format: 8 bytes (ID, version, type, flags, sequence)
- [ ] Payload support up to 1024 bytes
- [ ] Serialize produces exactly (8 + len(data)) bytes
- [ ] Deserialize correctly parses valid frames
- [ ] Handles flags (ACK_REQUIRED, IS_ACK, CLOSE)
- [ ] Sequence number stored as 16-bit unsigned (0-65535)
- [ ] Unit tests: ≥10 test cases

**Estimated Effort**: 4 hours

**Dependencies**: Task 1.1 (constants.py)

**Test Cases to Implement**:
1. Create frame with DATA type → serialize → deserialize → verify all fields match
2. Frame with maximum payload (1024 bytes)
3. Frame with empty payload
4. Sequence wraparound (65535 + 1 = 0)
5. Invalid frame rejected (bad protocol ID)
6. Invalid frame rejected (bad version)
7. Flags correctly set/unset
8. Large payload handled correctly
9. Frame size validation (reject >1024 payload)
10. Bidirectional serialization (serialize then deserialize must be idempotent)

---

#### Task 1.3: Create Unit Test Suite
**Objective**: Establish testing infrastructure

**Acceptance Criteria**:
- [ ] `test_utp_protocol.py` created with pytest framework
- [ ] Mock server/client components available
- [ ] Fixture for generating test frames
- [ ] Fixture for random payloads
- [ ] All tests from Task 1.2 pass
- [ ] Test discovery works (`pytest test_utp_protocol.py`)

**Estimated Effort**: 3 hours

**Dependencies**: Task 1.2

---

### PHASE 2: Connection State Management

#### Task 2.1: Create `utp_connection.py` - Connection State Machine
**Objective**: Implement per-connection lifecycle management

**Acceptance Criteria**:
- [ ] `UTPState` enum: DISCONNECTED, HANDSHAKING, CONNECTED, CLOSING, CLOSED
- [ ] `UTPConnection` class with:
  - `__init__(peer_addr, is_server=False)`
  - `state` property
  - `send_seq` / `recv_seq` tracking (16-bit)
  - `pending_acks` dict with (seq → (frame, timestamp, attempt))
  - `last_activity` timestamp for timeout detection
- [ ] State transition methods:
  - `initiate_handshake()` → HANDSHAKING
  - `accept_handshake()` → CONNECTED
  - `queue_frame(frame)` → updates pending_acks
  - `acknowledge(seq)` → removes from pending_acks
  - `close()` → CLOSING
- [ ] Timeout detection: `is_idle()` → bool (checks last_activity > IDLE_TIMEOUT)
- [ ] Unit tests: ≥15 test cases

**Estimated Effort**: 5 hours

**Dependencies**: Task 1.2 (utp_protocol.py)

**Test Cases**:
1. Initialize in DISCONNECTED state
2. Handshake sequence: DISCONNECTED → HANDSHAKING → CONNECTED
3. Sequence increment (send_seq wraps at 65536)
4. Queue frame to pending_acks
5. Acknowledge removes from pending
6. Unacknowledged frame remains pending
7. Timeout detection (idle > 30s)
8. Close transitions to CLOSING then CLOSED
9. Cannot send in DISCONNECTED state (raises exception)
10. Cannot close from DISCONNECTED state
11. Multiple frames can be pending simultaneously
12. Out-of-order acknowledgment (ACK seq=100 when seq=50 pending)
13. Duplicate acknowledgment handled gracefully
14. Last activity updates on frame receive
15. Idle timer only triggers after IDLE_TIMEOUT

---

#### Task 2.2: Implement Retransmission Logic
**Objective**: Add exponential backoff retransmission mechanism

**Acceptance Criteria**:
- [ ] `UTPConnection.get_pending_retransmits()` → list of (seq, frame, next_send_time)
- [ ] Exponential backoff: 200ms → 400ms → 800ms → 1.6s → 3.2s
- [ ] After MAX_RETRIES (5), mark connection dead
- [ ] `mark_retry(seq)` increments attempt counter
- [ ] Backoff calculation: `backoff = INITIAL * (2 ** attempt)`, capped at MAX
- [ ] Unit tests: ≥8 test cases

**Estimated Effort**: 3 hours

**Dependencies**: Task 2.1

**Test Cases**:
1. First timeout at 200ms
2. Second timeout at 400ms
3. Backoff caps at 3.2s
4. After 5 retries, connection closes
5. Successful ACK resets attempt counter
6. Multiple frames maintain independent retry counters
7. Timeout calculation considers last_sent timestamp
8. Next retry time = last_sent + backoff_duration

---

### PHASE 3: Server Implementation

#### Task 3.1: Refactor Server to UTP
**Objective**: Implement `UTPServer` class with socket management

**Acceptance Criteria**:
- [ ] `UTPServer` class with:
  - `__init__(host, port)` creates UDP socket (SOCK_DGRAM)
  - `start()` method runs receive loop
  - `connections` dict (addr → UTPConnection)
  - `client_names` dict (addr → name)
  - `public_keys` dict (addr → public_key)
  - `server_public_key` and `server_private_key` (RSA)
- [ ] `receive_loop()` method:
  - `socket.recvfrom()` accepts data from any client
  - Parses UTPFrame
  - Dispatches to appropriate handler
  - Continues after each frame (non-blocking)
- [ ] Error handling: malformed frames silently dropped
- [ ] Graceful shutdown on KeyboardInterrupt
- [ ] Unit tests: ≥5 test cases

**Estimated Effort**: 4 hours

**Dependencies**: Task 2.1, Task 1.2

**Test Cases**:
1. Socket created on correct port
2. Receives frame from client
3. Malformed frame dropped (no crash)
4. Connection created on first frame
5. Same client address reuses connection

---

#### Task 3.2: Implement Handshake Handler
**Objective**: Handle HANDSHAKE_INIT/HANDSHAKE_RESP protocol

**Acceptance Criteria**:
- [ ] `_handle_handshake_init(frame, addr)`:
  - Creates UTPConnection if new
  - Generates HANDSHAKE_RESP frame with server public key
  - Sends response
  - Connection state → HANDSHAKING
- [ ] `_handle_handshake_resp(frame, conn)`:
  - Updates connection state
  - Stores client public key
  - Awaits DATA frame with client name
- [ ] Timeout: if no DATA within HANDSHAKE_TIMEOUT, close connection
- [ ] Unit tests: ≥4 test cases

**Estimated Effort**: 3 hours

**Dependencies**: Task 3.1

---

#### Task 3.3: Implement Data Handler
**Objective**: Handle DATA frames, decryption, broadcast

**Acceptance Criteria**:
- [ ] `_handle_data(frame, conn, addr)`:
  - Verify sequence number (reject out-of-sequence without buffer)
  - Send ACK if ACK_REQUIRED flag set
  - Decrypt payload using connection's RSA private key
  - On first data (name+pubkey): store client name, store client pubkey
  - On subsequent data: broadcast to other clients
- [ ] `broadcast(message, sender_addr)`:
  - Send to all connections except sender
  - Re-encrypt with each recipient's public key
  - Set ACK_REQUIRED flag
  - Track in pending_acks
- [ ] Logging: DEBUG level for each step
- [ ] Unit tests: ≥6 test cases

**Estimated Effort**: 4 hours

**Dependencies**: Task 3.2

---

#### Task 3.4: Implement ACK Handler
**Objective**: Handle acknowledgment frames

**Acceptance Criteria**:
- [ ] `_handle_ack(frame, conn)`:
  - Extract acknowledged sequence number from frame
  - Call `conn.acknowledge(seq)`
  - Remove from pending_acks
  - Log success
- [ ] Multiple ACKs in flight handled correctly
- [ ] ACK for non-existent seq ignored (no crash)
- [ ] Unit tests: ≥3 test cases

**Estimated Effort**: 2 hours

**Dependencies**: Task 3.1

---

#### Task 3.5: Implement Close Handler
**Objective**: Handle graceful connection closure

**Acceptance Criteria**:
- [ ] `_handle_close(frame, conn, addr)`:
  - Transition connection state to CLOSING
  - Send ACK
  - Remove from connections dict after short delay (100ms)
- [ ] Client cleanup on close:
  - Remove from client_names
  - Remove from public_keys
  - Log disconnect
- [ ] Broadcast "user left" message to others (optional v1)
- [ ] Unit tests: ≥2 test cases

**Estimated Effort**: 2 hours

**Dependencies**: Task 3.1

---

#### Task 3.6: Server Maintenance & Timeouts
**Objective**: Implement periodic cleanup

**Acceptance Criteria**:
- [ ] Background thread runs every 5 seconds:
  - Check all connections for idle timeout
  - Call `conn.is_idle()` 
  - Close idle connections
  - Log timeouts
- [ ] Retransmission processor:
  - Every 100ms, check `conn.get_pending_retransmits()`
  - Send queued retransmits
  - Update attempt counters
- [ ] Thread-safe operations (use threading.Lock on connections dict)
- [ ] Graceful daemon thread shutdown
- [ ] Unit tests: ≥3 test cases

**Estimated Effort**: 3 hours

**Dependencies**: Task 3.1, Task 2.2

---

### PHASE 4: Client Implementation

#### Task 4.1: Extend Client UI for Protocol Selection
**Objective**: Add protocol selection radio buttons

**Acceptance Criteria**:
- [ ] New frame "Connection Protocol" in setup_boxes()
- [ ] Radio button options: "TCP (Original)" and "UTP (Low-latency)"
- [ ] Default selection: TCP
- [ ] `protocol_var` StringVar tracks selection
- [ ] Help text added: "TCP is stable, UTP may be faster on good networks"
- [ ] Visual layout maintained (no overlapping widgets)
- [ ] UI tests: screenshot verification

**Estimated Effort**: 2 hours

**Dependencies**: Existing client.py

---

#### Task 4.2: Create `UTPConnectionManager`
**Objective**: Implement UTP client connection handler

**Acceptance Criteria**:
- [ ] `UTPConnectionManager` class:
  - `__init__(server_host, server_port, client_name, callback_on_message)`
  - `connect()` → initiates handshake
  - `send_message(msg)` → encapsulates in UTP frame
  - `close()` → sends CLOSE frame
  - `receive_loop()` → background thread receiving frames
- [ ] Handshake flow:
  - Generate RSA keys (1024-bit)
  - Send HANDSHAKE_INIT (empty)
  - Receive HANDSHAKE_RESP (parse server pubkey)
  - Send DATA (client name + pubkey, encrypted)
  - Await ACK
  - Transition to CONNECTED
- [ ] Message flow:
  - Format: "name: message"
  - Encrypt with server pubkey
  - Wrap in DATA frame
  - Set ACK_REQUIRED
  - Queue for transmission
  - Track pending ACKs
- [ ] Error handling:
  - Handshake timeout → raise exception
  - Send fails → log, continue (UDP is unreliable)
  - Receive loop catches all exceptions
- [ ] Unit tests: ≥5 test cases

**Estimated Effort**: 5 hours

**Dependencies**: Task 1.2, Task 2.1

---

#### Task 4.3: Integrate UTP into Client Connect Flow
**Objective**: Modify connect_to_server() to support both protocols

**Acceptance Criteria**:
- [ ] `connect_to_server()` checks `protocol_var`:
  - If "TCP": call `_connect_tcp()` (existing)
  - If "UTP": call `_connect_utp()` (new)
- [ ] `_connect_tcp()`: existing code moved to method
- [ ] `_connect_utp()`:
  - Create UTPConnectionManager
  - Call connect()
  - Catch exceptions, show "Connection failed" message
  - Start receive_messages() thread
- [ ] Error messages distinguish TCP vs UTP failures
- [ ] Both modes update UI state (disable connect button, etc.)
- [ ] Unit tests: ≥3 test cases

**Estimated Effort**: 3 hours

**Dependencies**: Task 4.1, Task 4.2

---

#### Task 4.4: Unified Send/Receive Interface
**Objective**: Handle both TCP and UTP transparently

**Acceptance Criteria**:
- [ ] `send_message(event)`: works for both protocols
  - Format message
  - Call `self.conn.send()` (generic interface)
  - Display in text area
- [ ] `receive_messages()`: protocol-agnostic
  - Uses `self.conn.receive()` (generic interface)
  - Decrypts response
  - Updates text area
- [ ] `self.conn` interface (abstract):
  - `connect()` → raises if fails
  - `send(msg: bytes)` → sends, no return
  - `receive() → bytes` → blocks until data
  - `close()` → closes connection
- [ ] Both TCPConnection and UTPConnection implement this interface
- [ ] Unit tests: ≥4 test cases

**Estimated Effort**: 3 hours

**Dependencies**: Task 4.2

---

### PHASE 5: Integration & Testing

#### Task 5.1: End-to-End Integration Test
**Objective**: Test full chatroom flow with both protocols

**Acceptance Criteria**:
- [ ] `test_e2e_tcp.py`: Existing TCP flow still works
  - Start server
  - Connect 2 clients
  - Send message from client 1
  - Client 2 receives
  - Both log activity
  - Disconnect gracefully
- [ ] `test_e2e_utp.py`: New UTP flow
  - Start server on UTP port
  - Connect 2 clients (UTP mode)
  - Send message from client 1
  - Client 2 receives
  - Both log activity
  - Disconnect gracefully
- [ ] `test_e2e_multiprotocol.py`: Both simultaneously
  - Start server with both TCP and UTP
  - Connect TCP + UTP client
  - Cross-protocol messaging (TCP client messages UTP client, etc.)
  - All messages delivered
- [ ] All tests pass without manual intervention
- [ ] Test execution time < 10 seconds

**Estimated Effort**: 4 hours

**Dependencies**: Task 3.6, Task 4.4

---

#### Task 5.2: Packet Loss Simulation
**Objective**: Test reliability under adverse conditions

**Acceptance Criteria**:
- [ ] Mock UDP socket with configurable packet loss rate
- [ ] Test scenarios:
  - 5% packet loss: all messages delivered (retransmit works)
  - 25% packet loss: all messages delivered (slower)
  - 50% packet loss: messages delivered or timeout
  - Lost ACK: frame retransmitted
  - Lost DATA: no receipt, timeout after 5 retries
- [ ] Metrics:
  - Total messages sent: N
  - Total messages delivered: N (100%)
  - Average latency increase with loss
- [ ] Test time limit: 30 seconds per scenario
- [ ] Document results in `BENCHMARKS.md`

**Estimated Effort**: 4 hours

**Dependencies**: Task 5.1

---

#### Task 5.3: Performance Benchmarks
**Objective**: Measure TCP vs UTP performance

**Acceptance Criteria**:
- [ ] Benchmark script `benchmark.py`:
  - Measure handshake time (both protocols)
  - Measure message latency (both protocols)
  - Measure throughput (messages/sec)
  - Measure CPU usage (both protocols)
  - Measure memory usage (per connection)
- [ ] Report format:
  ```
  Protocol | Handshake (ms) | Latency (ms) | Throughput | CPU | Memory
  ---------|----------------|--------------|-----------|-----|--------
  TCP      | 10             | 2.0          | 1000 msg/s| 0.1%| 16 KB
  UTP      | 12             | 1.2          | 1050 msg/s| 0.1%| 24 KB
  ```
- [ ] Publish to BENCHMARKS.md
- [ ] All measurements within expected deltas
- [ ] Test runs on multiple hardware (if feasible)

**Estimated Effort**: 3 hours

**Dependencies**: Task 5.1

---

#### Task 5.4: Documentation & Deployment
**Objective**: Complete documentation and prepare deployment

**Acceptance Criteria**:
- [ ] Update README.md:
  - Add "Running" section with both protocols
  - Example: `python server.py --protocol both`
  - Example: UI screenshot showing protocol selection
- [ ] Add USAGE.md:
  - TCP vs UTP comparison table
  - When to use each protocol
  - Troubleshooting common issues
- [ ] Add API.md:
  - UTPFrame class documentation
  - UTPConnection state machine
  - UTPServer class reference
  - UTPConnectionManager class reference
- [ ] Code comments:
  - All public methods documented (docstrings)
  - Complex algorithms commented (retransmission logic, etc.)
- [ ] CHANGELOG:
  - Record new features, breaking changes, bug fixes
- [ ] Release notes (v2.0-utp):
  - High-level summary of changes
  - Installation instructions
  - Known limitations

**Estimated Effort**: 3 hours

**Dependencies**: All tasks

---

### PHASE 6: Code Review & Hardening

#### Task 6.1: Code Quality Review
**Objective**: Ensure code meets standards

**Acceptance Criteria**:
- [ ] pylint/flake8 pass (style)
- [ ] Type hints added to new modules (mypy)
- [ ] No unused imports
- [ ] No deprecated function calls
- [ ] Docstrings for all public methods
- [ ] Comments for complex logic
- [ ] Test coverage > 90% (new code)
- [ ] README lists any new dependencies

**Estimated Effort**: 2 hours

**Dependencies**: All implementation tasks

---

#### Task 6.2: Security Audit
**Objective**: Validate security assumptions

**Acceptance Criteria**:
- [ ] RSA keys are 1024-bit (document limitation)
- [ ] No hardcoded secrets
- [ ] No raw socket data printed to logs
- [ ] Encryption applied before transmission (verified)
- [ ] No authenticated encryption (HMAC) - documented limitation
- [ ] Connection spoofing possible - document requirement for v2
- [ ] Write security.md with findings and recommendations

**Estimated Effort**: 2 hours

**Dependencies**: All implementation tasks

---

#### Task 6.3: Final Integration & Merge
**Objective**: Prepare for production release

**Acceptance Criteria**:
- [ ] All tasks completed and merged to feature branch
- [ ] CI/CD pipeline passes (if configured)
- [ ] Manual testing on target platforms (Windows, Linux, macOS)
- [ ] No regressions in TCP mode
- [ ] UTP mode fully functional
- [ ] Create PR with all changes
- [ ] Code review approved
- [ ] Merge to main branch
- [ ] Tag release v2.0-utp

**Estimated Effort**: 2 hours

**Dependencies**: Task 6.1, Task 6.2

---

## Task Dependencies Graph

```
1.1 (constants.py)
  ├─→ 1.2 (utp_protocol.py)
  │     ├─→ 1.3 (unit tests)
  │     ├─→ 2.1 (connection state)
  │     │     ├─→ 2.2 (retransmission)
  │     │     ├─→ 3.1 (server impl)
  │     │     │     ├─→ 3.2 (handshake)
  │     │     │     ├─→ 3.3 (data handler)
  │     │     │     ├─→ 3.4 (ack handler)
  │     │     │     ├─→ 3.5 (close handler)
  │     │     │     ├─→ 3.6 (maintenance)
  │     │     │     ├─→ 5.1 (e2e test)
  │     │     │     │     ├─→ 5.2 (packet loss)
  │     │     │     │     ├─→ 5.3 (benchmarks)
  │     │     │     │     └─→ 5.4 (docs)
  │     │     └─→ 4.2 (UTPConnectionManager)
  │     │           ├─→ 4.1 (UI protocol selection)
  │     │           └─→ 4.3 (connect flow)
  │     │                 └─→ 4.4 (unified interface)
  │     │                       └─→ 5.1 (e2e test)
  └─────────────────────────────→ 6.1 (code review)
                                   ├─→ 6.2 (security audit)
                                   └─→ 6.3 (merge & release)
```

---

## Timeline Estimate

| Phase | Tasks | Duration | Start | End |
|-------|-------|----------|-------|-----|
| 1 | 1.1-1.3 | 9 hours | Day 1 | Day 1 PM |
| 2 | 2.1-2.2 | 8 hours | Day 1 PM | Day 2 |
| 3 | 3.1-3.6 | 18 hours | Day 2 | Day 3 PM |
| 4 | 4.1-4.4 | 13 hours | Day 3 PM | Day 4 PM |
| 5 | 5.1-5.4 | 14 hours | Day 4 PM | Day 5 PM |
| 6 | 6.1-6.3 | 6 hours | Day 5 PM | Day 6 |
| **Total** | **26 tasks** | **~68 hours** | **Day 1** | **Day 6** |

**Optimized Schedule** (parallel execution):
- **Day 1**: Tasks 1.1-1.3 (sequential, foundation)
- **Day 2**: Tasks 2.1-2.2 + 4.1 (parallel)
- **Day 3**: Tasks 3.1-3.6 (mostly sequential due to dependencies)
- **Day 4**: Tasks 4.2-4.4 + 5.1 (parallel)
- **Day 5**: Tasks 5.2-5.3 + 6.1 (parallel)
- **Day 6**: Tasks 5.4 + 6.2-6.3 (finish)

---

## Success Metrics

| Metric | Target |
|--------|--------|
| All 26 tasks completed | 100% |
| Unit test coverage (new code) | >90% |
| All integration tests passing | 100% |
| Code review approved | Yes |
| No security vulnerabilities | Confirmed |
| TCP mode unaffected | Verified |
| UTP mode functional | Verified |
| Performance benchmarks acceptable | Confirmed |
| Documentation complete | Yes |
| Ready for production release | Yes |

---

**End of Technical Tasks**
