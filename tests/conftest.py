# [2026-08-25] Pytest configuration and shared fixtures

import pytest
import asyncio
import sys
import os


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment variables before each test."""
    # Store original values
    original_env = os.environ.copy()
    
    # Set safe defaults for testing
    os.environ["CHATROOM_PRIMARY_PROTOCOL"] = "tcp"
    os.environ["CHATROOM_ENABLE_TCP"] = "true"
    os.environ["CHATROOM_ENABLE_UTP"] = "true"
    os.environ["CHATROOM_FALLBACK_TIMEOUT"] = "5"
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
