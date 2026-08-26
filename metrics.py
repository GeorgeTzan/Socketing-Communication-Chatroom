# [2026-08-25] Metrics collection and logging for transport protocols
# Provides ProtocolMetrics class for tracking performance and a configured logger

import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConnectionMetrics:
    """Metrics for a single connection."""
    protocol: str
    remote_addr: str
    start_time: float = field(default_factory=time.time)
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    errors: int = 0
    
    @property
    def duration(self) -> float:
        """Get connection duration in seconds."""
        return time.time() - self.start_time
    
    @property
    def throughput_sent(self) -> float:
        """Get send throughput in bytes/sec."""
        duration = self.duration
        return self.bytes_sent / duration if duration > 0 else 0
    
    @property
    def throughput_received(self) -> float:
        """Get receive throughput in bytes/sec."""
        duration = self.duration
        return self.bytes_received / duration if duration > 0 else 0


class ProtocolMetrics:
    """Tracks metrics across all protocol usage."""
    
    def __init__(self):
        self.tcp_connections = 0
        self.utp_connections = 0
        self.bytes_sent_tcp = 0
        self.bytes_sent_utp = 0
        self.bytes_received_tcp = 0
        self.bytes_received_utp = 0
        self.fallback_events = 0
        self.connection_errors = 0
        self.active_connections: Dict[str, ConnectionMetrics] = {}
        self.start_time = time.time()
    
    def register_connection(self, conn_id: str, protocol: str, remote_addr: str) -> None:
        """Register a new connection."""
        self.active_connections[conn_id] = ConnectionMetrics(protocol, remote_addr)
        if protocol == "tcp":
            self.tcp_connections += 1
        elif protocol == "utp":
            self.utp_connections += 1
    
    def unregister_connection(self, conn_id: str) -> Optional[ConnectionMetrics]:
        """Unregister a connection and return its metrics."""
        return self.active_connections.pop(conn_id, None)
    
    def record_send(self, conn_id: str, bytes_count: int) -> None:
        """Record bytes sent on a connection."""
        if conn_id in self.active_connections:
            conn_metric = self.active_connections[conn_id]
            conn_metric.bytes_sent += bytes_count
            if conn_metric.protocol == "tcp":
                self.bytes_sent_tcp += bytes_count
            elif conn_metric.protocol == "utp":
                self.bytes_sent_utp += bytes_count
    
    def record_receive(self, conn_id: str, bytes_count: int) -> None:
        """Record bytes received on a connection."""
        if conn_id in self.active_connections:
            conn_metric = self.active_connections[conn_id]
            conn_metric.bytes_received += bytes_count
            if conn_metric.protocol == "tcp":
                self.bytes_received_tcp += bytes_count
            elif conn_metric.protocol == "utp":
                self.bytes_received_utp += bytes_count
    
    def record_message_sent(self, conn_id: str) -> None:
        """Record a message sent on a connection."""
        if conn_id in self.active_connections:
            self.active_connections[conn_id].messages_sent += 1
    
    def record_message_received(self, conn_id: str) -> None:
        """Record a message received on a connection."""
        if conn_id in self.active_connections:
            self.active_connections[conn_id].messages_received += 1
    
    def record_error(self, conn_id: str) -> None:
        """Record an error on a connection."""
        self.connection_errors += 1
        if conn_id in self.active_connections:
            self.active_connections[conn_id].errors += 1
    
    def record_fallback(self) -> None:
        """Record a protocol fallback event."""
        self.fallback_events += 1
    
    @property
    def total_bytes_sent(self) -> int:
        """Total bytes sent across all connections."""
        return self.bytes_sent_tcp + self.bytes_sent_utp
    
    @property
    def total_bytes_received(self) -> int:
        """Total bytes received across all connections."""
        return self.bytes_received_tcp + self.bytes_received_utp
    
    @property
    def uptime(self) -> float:
        """Total uptime in seconds."""
        return time.time() - self.start_time
    
    def get_summary(self) -> Dict:
        """Get a summary of all metrics."""
        return {
            "uptime_seconds": self.uptime,
            "tcp_connections_total": self.tcp_connections,
            "utp_connections_total": self.utp_connections,
            "active_connections": len(self.active_connections),
            "bytes_sent_tcp": self.bytes_sent_tcp,
            "bytes_sent_utp": self.bytes_sent_utp,
            "bytes_received_tcp": self.bytes_received_tcp,
            "bytes_received_utp": self.bytes_received_utp,
            "total_bytes_sent": self.total_bytes_sent,
            "total_bytes_received": self.total_bytes_received,
            "fallback_events": self.fallback_events,
            "connection_errors": self.connection_errors,
            "timestamp": datetime.now().isoformat()
        }


# Global metrics instance
_global_metrics = ProtocolMetrics()


def get_metrics() -> ProtocolMetrics:
    """Get the global metrics instance."""
    return _global_metrics


# Configure logging
def setup_logging(level: str = "INFO", filename: Optional[str] = None) -> logging.Logger:
    """Set up logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        filename: Optional log file path
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("chatroom")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if filename:
        try:
            file_handler = logging.FileHandler(filename)
            file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.error(f"Failed to set up file logging: {e}")
    
    return logger


# Create default logger
logger = setup_logging("INFO")
