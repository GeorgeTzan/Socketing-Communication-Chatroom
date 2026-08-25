# Architecture Design Document: UTP Support
## Detailed Technical Architecture for Issue #1

**Document Version:** 1.0  
**Classification:** Technical Design  
**Target Audience:** Development Team, Code Reviewers  
**Date:** 2026-08-25  

---

## 1. Core Interfaces & Abstractions

### 1.1 Transport Protocol Interface

```python
# transport_adapter.py

from abc import ABC, abstractmethod
from typing import Tuple, Optional, Any
from dataclasses import dataclass

@dataclass
class ConnectionInfo:
    """Metadata about a connection"""
    protocol: str  # 'tcp' or 'utp'
    local_addr: Tuple[str, int]
    remote_addr: Tuple[str, int]
    created_at: float
    last_activity: float

class Connection(ABC):
    """Abstract base class for transport connections"""
    
    @property
    @abstractmethod
    def info(self) -> ConnectionInfo:
        """Get connection metadata"""
        pass
    
    @abstractmethod
    async def send(self, data: bytes) -> int:
        """
        Send data over connection.
        
        Args:
            data: Bytes to send
            
        Returns:
            Number of bytes sent
            
        Raises:
            ConnectionError: If connection is closed
            TimeoutError: If send times out
        """
        pass
    
    @abstractmethod
    async def recv(self, bufsize: int) -> bytes:
        """
        Receive data from connection.
        
        Args:
            bufsize: Maximum bytes to receive
            
        Returns:
            Received bytes (empty if connection closed)
            
        Raises:
            ConnectionError: If connection is closed
            TimeoutError: If receive times out
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close connection gracefully"""
        pass
    
    @abstractmethod
    def is_open(self) -> bool:
        """Check if connection is still open"""
        pass


class TransportProtocol(ABC):
    """Abstract base class for transport protocols"""
    
    @abstractmethod
    async def listen(self, host: str, port: int) -> None:
        """
        Start listening for incoming connections.
        
        Args:
            host: Bind address (0.0.0.0 for all interfaces)
            port: Bind port
            
        Raises:
            OSError: If bind fails
        """
        pass
    
    @abstractmethod
    async def accept(self) -> Tuple[Connection, Tuple[str, int]]:
        """
        Accept incoming connection.
        
        Returns:
            Tuple of (Connection object, (remote_host, remote_port))
            
        Raises:
            RuntimeError: If not listening
        """
        pass
    
    @abstractmethod
    async def connect(self, host: str, port: int) -> Connection:
        """
        Establish outgoing connection.
        
        Args:
            host: Remote host
            port: Remote port
            
        Returns:
            Connection object
            
        Raises:
            ConnectionRefusedError: If connection refused
            TimeoutError: If connection times out
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close transport and all connections"""
        pass
    
    @abstractmethod
    async def get_metrics(self) -> dict:
        """Get protocol-specific metrics"""
        pass
```

### 1.2 Exception Hierarchy

```python
# transport_exceptions.py

class TransportError(Exception):
    """Base exception for transport layer"""
    pass

class ConnectionError(TransportError):
    """Connection operation failed"""
    pass

class ProtocolNegotiationError(TransportError):
    """Protocol selection/negotiation failed"""
    pass

class ProtocolUnavailableError(TransportError):
    """Requested protocol is not available"""
    pass

class ConnectionTimeoutError(TransportError):
    """Connection operation timed out"""
    pass
```

---

## 2. TCP Transport Implementation

### 2.1 Architecture

```
TCPTransport
├── Server Socket (listening)
├── Accept Loop
│   └── Create TCPConnection per client
├── TCPConnection Pool
│   ├── TCPConnection 1 (send/recv)
│   ├── TCPConnection 2
│   └── TCPConnection N
└── Metrics
    ├── connections_active
    ├── bytes_sent/recv
    └── errors
```

### 2.2 Implementation Details

```python
# tcp_handler.py

import asyncio
import socket
from typing import Optional, Tuple
from transport_adapter import Connection, TransportProtocol, ConnectionInfo
import time

class TCPConnection(Connection):
    """TCP-based connection"""
    
    def __init__(self, sock: socket.socket, remote_addr: Tuple[str, int]):
        self._sock = sock
        self._remote_addr = remote_addr
        self._loop = asyncio.get_event_loop()
        self._created_at = time.time()
        self._last_activity = self._created_at
    
    @property
    def info(self) -> ConnectionInfo:
        local_addr = self._sock.getsockname()
        return ConnectionInfo(
            protocol='tcp',
            local_addr=local_addr,
            remote_addr=self._remote_addr,
            created_at=self._created_at,
            last_activity=self._last_activity
        )
    
    async def send(self, data: bytes) -> int:
        """Send data with proper error handling"""
        if not self.is_open():
            raise ConnectionError("Connection closed")
        
        try:
            sent = await self._loop.sock_sendall(self._sock, data)
            self._last_activity = time.time()
            return len(data)
        except (OSError, BrokenPipeError) as e:
            await self.close()
            raise ConnectionError(f"Send failed: {e}")
    
    async def recv(self, bufsize: int) -> bytes:
        """Receive data with timeout handling"""
        if not self.is_open():
            return b''
        
        try:
            data = await self._loop.sock_recv(self._sock, bufsize)
            if not data:
                await self.close()
            self._last_activity = time.time()
            return data
        except OSError as e:
            await self.close()
            raise ConnectionError(f"Recv failed: {e}")
    
    async def close(self) -> None:
        """Close connection cleanly"""
        try:
            self._sock.close()
        except:
            pass
    
    def is_open(self) -> bool:
        """Check if socket is still open"""
        try:
            # Check with non-blocking peek
            self._sock.setblocking(False)
            try:
                self._sock.recv(0)  # Poll the socket
                return True
            except BlockingIOError:
                return True
            finally:
                self._sock.setblocking(True)
        except:
            return False


class TCPTransport(TransportProtocol):
    """TCP transport implementation"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5000, 
                 backlog: int = 5):
        self.host = host
        self.port = port
        self.backlog = backlog
        self._server_sock: Optional[socket.socket] = None
        self._loop = asyncio.get_event_loop()
        self._metrics = {
            'connections_accepted': 0,
            'bytes_sent': 0,
            'bytes_recv': 0,
            'connection_errors': 0,
        }
    
    async def listen(self, host: str, port: int) -> None:
        """Start TCP server"""
        self.host = host
        self.port = port
        
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(self.backlog)
            print(f"TCP transport listening on {self.host}:{self.port}")
        except OSError as e:
            self._server_sock.close()
            raise OSError(f"Failed to bind TCP socket: {e}")
    
    async def accept(self) -> Tuple[Connection, Tuple[str, int]]:
        """Accept TCP connection"""
        if not self._server_sock:
            raise RuntimeError("Transport not listening")
        
        try:
            conn, addr = await self._loop.sock_accept(self._server_sock)
            self._metrics['connections_accepted'] += 1
            return TCPConnection(conn, addr), addr
        except Exception as e:
            self._metrics['connection_errors'] += 1
            raise ConnectionError(f"Accept failed: {e}")
    
    async def connect(self, host: str, port: int) -> Connection:
        """Establish TCP connection"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            await self._loop.sock_connect(sock, (host, port))
            return TCPConnection(sock, (host, port))
        except Exception as e:
            sock.close()
            raise ConnectionError(f"Connect failed to {host}:{port}: {e}")
    
    async def close(self) -> None:
        """Close TCP transport"""
        if self._server_sock:
            self._server_sock.close()
    
    async def get_metrics(self) -> dict:
        """Return TCP-specific metrics"""
        return self._metrics.copy()
```

---

## 3. UTP Transport Implementation

### 3.1 Architecture

```
UTPTransport
├── UDP Socket (raw)
├── UTP Connection Manager
│   ├── Connection State Machine
│   └── Retransmission Handler
├── Packet Multiplexer
│   ├── Incoming Packet Router
│   └── Outgoing Packet Queue
├── UTPConnection Pool
│   ├── UTPConnection 1 (conn_id: 1)
│   ├── UTPConnection 2 (conn_id: 2)
│   └── UTPConnection N
└── Metrics
    ├── connections_active
    ├── packets_sent/recv
    ├── bytes_sent/recv
    └── retransmissions
```

### 3.2 Library Selection Strategy

```python
# utp_transport_selector.py

def get_utp_library():
    """Try to import UTP library with fallback strategy"""
    libraries_to_try = [
        ('libutp', try_import_libutp),      # C extension, fastest
        ('async_utp', try_import_async_utp), # Pure Python, async
        ('utp', try_import_utp),            # Pure Python, legacy
    ]
    
    for name, importer in libraries_to_try:
        try:
            return importer()
        except ImportError:
            continue
    
    raise ImportError("No UTP library available")


class UTPTransport(TransportProtocol):
    """UTP transport using available UTP library"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        self.host = host
        self.port = port
        self.utp_lib = get_utp_library()
        self._socket: Optional[socket.socket] = None
        self._connections: Dict[int, 'UTPConnection'] = {}
        self._connection_counter = 0
        self._metrics = {
            'connections_accepted': 0,
            'packets_sent': 0,
            'packets_recv': 0,
            'retransmissions': 0,
            'connection_errors': 0,
        }
```

### 3.3 Connection Management

```python
# utp_connection.py

from enum import Enum

class UTPConnectionState(Enum):
    """UTP connection states"""
    IDLE = 'idle'
    SYN_SENT = 'syn_sent'
    CONNECTED = 'connected'
    FIN_SENT = 'fin_sent'
    FIN_RECV = 'fin_recv'
    DESTROYED = 'destroyed'


class UTPConnection(Connection):
    """UTP-based connection"""
    
    def __init__(self, utp_socket, conn_id: int, remote_addr: Tuple[str, int]):
        self.utp_socket = utp_socket
        self.conn_id = conn_id
        self._remote_addr = remote_addr
        self._state = UTPConnectionState.CONNECTED
        self._created_at = time.time()
        self._last_activity = self._created_at
        self._recv_buffer = asyncio.Queue()
        self._send_queue = asyncio.Queue()
    
    @property
    def info(self) -> ConnectionInfo:
        return ConnectionInfo(
            protocol='utp',
            local_addr=self.utp_socket.getsockname(),
            remote_addr=self._remote_addr,
            created_at=self._created_at,
            last_activity=self._last_activity
        )
    
    async def send(self, data: bytes) -> int:
        """Queue data for sending"""
        if self._state == UTPConnectionState.DESTROYED:
            raise ConnectionError("Connection destroyed")
        
        await self._send_queue.put(data)
        # Send is handled by background task
        return len(data)
    
    async def recv(self, bufsize: int) -> bytes:
        """Receive data from buffer"""
        if self._state == UTPConnectionState.DESTROYED:
            return b''
        
        try:
            # Try to get data with timeout
            return await asyncio.wait_for(
                self._recv_buffer.get(), 
                timeout=30.0
            )
        except asyncio.TimeoutError:
            raise TimeoutError("Receive timeout")
    
    async def close(self) -> None:
        """Close connection"""
        self._state = UTPConnectionState.FIN_SENT
        await self._send_queue.put(b'__FIN__')  # Signal close
        self._state = UTPConnectionState.DESTROYED
```

---

## 4. Protocol Negotiation

### 4.1 Client-Side Negotiation

```python
# client_protocol_negotiator.py

class ClientProtocolNegotiator:
    """Handles protocol selection on client side"""
    
    async def connect_with_fallback(self, host: str, port: int,
                                    preferred: str = 'auto') -> Connection:
        """
        Connect with protocol fallback chain.
        
        Priority Order:
        1. Preferred protocol if specified
        2. UTP (if enabled and available)
        3. TCP (fallback)
        """
        
        protocols_to_try = self._get_priority_list(preferred)
        last_error = None
        
        for protocol in protocols_to_try:
            try:
                return await self._connect_with_protocol(
                    host, port, protocol
                )
            except Exception as e:
                last_error = e
                continue
        
        raise ProtocolNegotiationError(
            f"Failed to connect with any protocol: {last_error}"
        )
    
    def _get_priority_list(self, preferred: str) -> list:
        """Determine protocol priority order"""
        if preferred == 'tcp':
            return ['tcp']
        elif preferred == 'utp':
            return ['utp', 'tcp']  # UTP with TCP fallback
        else:  # 'auto' (default)
            return ['utp', 'tcp']  # Try UTP first
    
    async def _connect_with_protocol(self, host: str, port: int,
                                      protocol: str) -> Connection:
        """Attempt connection with specific protocol"""
        
        if protocol == 'tcp':
            transport = TCPTransport(host, port)
        elif protocol == 'utp':
            transport = UTPTransport(host, port)
        else:
            raise ProtocolUnavailableError(f"Unknown protocol: {protocol}")
        
        conn = await transport.connect(host, port)
        
        # Send protocol identifier for server logging
        await conn.send(f"__PROTO:{protocol}__".encode())
        
        return conn
```

### 4.2 Server-Side Negotiation

```python
# server_protocol_negotiator.py

class ServerProtocolNegotiator:
    """Handles dual-stack listening and protocol selection"""
    
    async def start_dual_stack(self, host: str, port: int):
        """
        Start listening on both TCP and UTP.
        Accept connections from either protocol.
        """
        
        self.tcp_transport = TCPTransport(host, port)
        self.utp_transport = UTPTransport(host, port)
        
        # Start both listeners
        await asyncio.gather(
            self.tcp_transport.listen(host, port),
            self.utp_transport.listen(host, port)
        )
        
        print(f"Dual-stack transport listening on {host}:{port}")
    
    async def accept_any_protocol(self) -> Tuple[Connection, Tuple[str, int]]:
        """Accept connection from TCP or UTP"""
        
        # Race both listeners
        tcp_task = asyncio.create_task(self.tcp_transport.accept())
        utp_task = asyncio.create_task(self.utp_transport.accept())
        
        done, pending = await asyncio.wait(
            [tcp_task, utp_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
        
        # Return connection from whichever completed first
        connection, addr = done.pop().result()
        return connection, addr
```

---

## 5. Integration Points

### 5.1 Server Refactoring

```python
# server.py (refactored)

import asyncio
import os
from protocol_factory import create_transport
from encryption import handle_encryption
from threading import Thread

class ChatServer:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or os.getenv('CHAT_HOST', '0.0.0.0')
        self.port = port or int(os.getenv('CHAT_PORT', '5000'))
        self.protocol = os.getenv('CHATROOM_PRIMARY_PROTOCOL', 'auto')
        
        self.clients = []
        self.client_names = {}
        self.public_keys = {}
        
        # RSA keys (unchanged)
        from rsa import newkeys
        self.public_key, self.private_key = newkeys(1024)
    
    async def run(self):
        """Main server loop"""
        transport = create_transport(self.protocol, self.host, self.port)
        await transport.listen(self.host, self.port)
        
        try:
            while True:
                conn, addr = await transport.accept()
                
                # Handle connection in thread pool
                loop = asyncio.get_event_loop()
                loop.run_in_executor(
                    None, 
                    self._handle_client_sync, 
                    conn, 
                    addr
                )
                
        except KeyboardInterrupt:
            print("Shutting down...")
            await transport.close()
    
    def _handle_client_sync(self, conn, addr):
        """Handle client (original logic, adapted)"""
        print(f"Connected by {addr}")
        try:
            client_name = handle_encryption.decrypt(
                conn.recv(1024), 
                self.private_key
            ).decode("utf-8")
            
            self.client_names[conn] = client_name
            
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                message = handle_encryption.decrypt(data, self.private_key).decode("utf-8")
                self.broadcast(message.encode(), conn)
                
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            self.cleanup_client(conn)


async def main():
    server = ChatServer()
    await server.run()

if __name__ == '__main__':
    asyncio.run(main())
```

### 5.2 Client Refactoring

```python
# client.py (refactored, key parts)

import asyncio
from protocol_factory import create_transport

class CLIENT:
    def __init__(self):
        self.root = tk.Tk()
        # ... existing GUI setup ...
        self.protocol_var = tk.StringVar(value='auto')
        self.protocol_label = tk.Label(self.root, text='Protocol:')
        self.protocol_combo = ttk.Combobox(
            self.root, 
            textvariable=self.protocol_var,
            values=['auto', 'tcp', 'utp']
        )
    
    def connect_to_server(self):
        """Establish connection with selected protocol"""
        self.name = self.name_var.get()
        protocol = self.protocol_var.get()
        
        # Run async connection in thread
        thread = Thread(
            target=self._async_connect,
            args=(protocol,),
            daemon=True
        )
        thread.start()
    
    def _async_connect(self, protocol: str):
        """Async connection logic"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            self.server_socket = loop.run_until_complete(
                self._connect_async(protocol)
            )
            # Start receive loop
            Thread(target=self.receive_messages, daemon=True).start()
        except Exception as e:
            print(f"Connection failed: {e}")
    
    async def _connect_async(self, protocol: str):
        """Async connection with fallback"""
        transport = create_transport(
            protocol=protocol,
            host=self.ipEntry.get(),
            port=int(self.portEntry.get())
        )
        
        conn = await transport.connect(
            self.ipEntry.get(),
            int(self.portEntry.get())
        )
        
        # Rest of connection logic
        return conn
```

---

## 6. Error Handling Flow

```
Connection Attempt
    │
    ├─→ Try Preferred Protocol
    │   │
    │   ├─→ Success → Return Connection
    │   │
    │   └─→ Timeout/Error
    │       │
    │       └─→ Try Fallback Protocol (if different)
    │           │
    │           ├─→ Success → Log Fallback, Return Connection
    │           │
    │           └─→ All Failed
    │               │
    │               └─→ Raise ProtocolNegotiationError
    │                   (with fallback details logged)
    │
    └─→ User Prompted with Error & Retry Option
```

---

## 7. Metrics & Monitoring

```python
# transport_metrics.py

class TransportMetrics:
    """Unified metrics collection across protocols"""
    
    def __init__(self):
        self.connections = {
            'tcp': 0,
            'utp': 0,
            'total': 0
        }
        self.bytes = {
            'tcp_sent': 0,
            'tcp_recv': 0,
            'utp_sent': 0,
            'utp_recv': 0,
        }
        self.errors = {
            'connection_failures': 0,
            'timeouts': 0,
            'fallbacks': 0,
        }
    
    async def get_health_status(self) -> dict:
        """Get overall transport health"""
        return {
            'tcp_available': await self._check_tcp_available(),
            'utp_available': await self._check_utp_available(),
            'active_connections': self.connections['total'],
            'recent_errors': self.errors,
        }
```

---

## 8. Testing Architecture

### 8.1 Unit Test Structure

```
tests/
├── unit/
│   ├── test_tcp_transport.py
│   ├── test_utp_transport.py
│   ├── test_protocol_negotiation.py
│   └── test_exceptions.py
├── integration/
│   ├── test_tcp_to_tcp.py
│   ├── test_utp_to_utp.py
│   ├── test_tcp_to_utp.py  # Cross-protocol
│   ├── test_fallback.py
│   └── test_concurrent_connections.py
└── performance/
    ├── benchmark_tcp.py
    ├── benchmark_utp.py
    └── latency_comparison.py
```

### 8.2 Mock Objects

```python
# tests/mocks.py

class MockConnection(Connection):
    """Mock connection for testing"""
    
    def __init__(self, protocol='mock'):
        self.protocol = protocol
        self.sent_data = []
        self.recv_queue = asyncio.Queue()
    
    async def send(self, data: bytes) -> int:
        self.sent_data.append(data)
        return len(data)
    
    async def recv(self, bufsize: int) -> bytes:
        return await self.recv_queue.get()


class MockTransport(TransportProtocol):
    """Mock transport for testing"""
    
    def __init__(self, should_fail=False):
        self.connections = []
        self.should_fail = should_fail
    
    async def connect(self, host: str, port: int) -> Connection:
        if self.should_fail:
            raise ConnectionError("Mock failure")
        conn = MockConnection()
        self.connections.append(conn)
        return conn
```

---

## 9. Deployment Configuration

### 9.1 Docker Consideration

```dockerfile
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libutp0 \
    libutp-dev

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV CHATROOM_PRIMARY_PROTOCOL=auto
ENV CHATROOM_ENABLE_UTP=true
ENV CHATROOM_ENABLE_TCP=true

CMD ["python", "server.py"]
```

### 9.2 Environment Configuration

```bash
# .env.production
CHAT_HOST=0.0.0.0
CHAT_PORT=5000
CHATROOM_PRIMARY_PROTOCOL=auto
CHATROOM_ENABLE_UTP=true
CHATROOM_ENABLE_TCP=true
CHATROOM_FALLBACK_TIMEOUT=5
CHATROOM_LOG_LEVEL=INFO
```

---

## 10. Performance Considerations

### 10.1 UTP Optimization Points

1. **Connection Multiplexing:** Multiple streams over single UDP socket
2. **Buffer Management:** Optimal window size for throughput
3. **Packet Batching:** Reduce packet count while maintaining latency
4. **Congestion Awareness:** Back off when network saturated

### 10.2 Memory Profile

```
TCP Connection (typical):
├── Socket object: ~200 bytes
├── Buffers (send/recv): ~8KB
└── Metadata: ~100 bytes
Total: ~8.3 KB per connection

UTP Connection (typical):
├── UTP socket: ~500 bytes
├── Retransmission buffer: ~16KB
├── Packet queue: ~4KB
└── Metadata: ~200 bytes
Total: ~20.7 KB per connection
```

---

## 11. Security Checklist

- [ ] RSA encryption layer remains unchanged
- [ ] No plaintext sensitive data transmitted
- [ ] UDP spoofing protection (UTP connection ID)
- [ ] Rate limiting on connection attempts
- [ ] All protocol negotiation logged for audit
- [ ] Timeout on hanging connections
- [ ] Graceful handling of malformed packets

---

**End of Architecture Design Document**

**Next Review Point:** After implementation of transport abstraction layer (Phase 1)
