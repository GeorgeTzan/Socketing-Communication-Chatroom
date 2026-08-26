# [2026-08-26] Slash command parser and message envelope formatter
# Handles chatroom slash commands (/whisper, /nick, /help, /list, /quit)
# and structured message formatting for system and direct messages

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class CommandType(Enum):
    """Enumeration of supported command types in the chatroom."""
    MESSAGE = "message"      # Regular chat message (no slash)
    NICK = "nick"            # /nick <new_username>
    WHISPER = "whisper"      # /whisper <target_user> <message>
    HELP = "help"            # /help
    LIST = "list"            # /list or /users
    QUIT = "quit"            # /quit or /exit
    UNKNOWN = "unknown"      # Invalid slash command


@dataclass
class ParsedCommand:
    """Represents a parsed command from user input.
    
    Attributes:
        command_type: Type of command (CommandType enum)
        target: Target user for whisper commands (optional)
        payload: Message content or parameter (optional)
    """
    command_type: CommandType
    target: Optional[str] = None
    payload: Optional[str] = None


def parse_user_input(raw_text: str) -> ParsedCommand:
    """Parse user input and extract command information.
    
    Handles slash commands and regular messages. Strips leading/trailing whitespace.
    
    Args:
        raw_text: Raw user input string
        
    Returns:
        ParsedCommand object with command type, target (if applicable), and payload
        
    Examples:
        >>> parse_user_input("hello world")
        ParsedCommand(command_type=CommandType.MESSAGE, payload="hello world")
        
        >>> parse_user_input("/whisper alice hello there")
        ParsedCommand(command_type=CommandType.WHISPER, target="alice", payload="hello there")
        
        >>> parse_user_input("/nick JohnDoe")
        ParsedCommand(command_type=CommandType.NICK, payload="JohnDoe")
    """
    # Strip leading and trailing whitespace
    text = raw_text.strip()
    
    # Handle empty or whitespace-only input
    if not text:
        return ParsedCommand(CommandType.MESSAGE, payload="")
    
    # Check if this is a slash command
    if not text.startswith("/"):
        # Regular message
        return ParsedCommand(CommandType.MESSAGE, payload=text)
    
    # Parse slash command
    parts = text.split(maxsplit=1)
    command = parts[0][1:].lower()  # Remove '/' and convert to lowercase
    rest = parts[1] if len(parts) > 1 else ""
    
    # Handle each command type
    if command == "nick":
        # /nick <new_username>
        new_name = rest.strip()
        if not new_name:
            return ParsedCommand(CommandType.UNKNOWN, payload=text)
        return ParsedCommand(CommandType.NICK, payload=new_name)
    
    elif command == "whisper" or command == "msg" or command == "dm":
        # /whisper <target_user> <message>
        whisper_parts = rest.split(maxsplit=1)
        if len(whisper_parts) < 1:
            return ParsedCommand(CommandType.UNKNOWN, payload=text)
        
        target_user = whisper_parts[0].strip()
        message = whisper_parts[1].strip() if len(whisper_parts) > 1 else ""
        
        if not target_user:
            return ParsedCommand(CommandType.UNKNOWN, payload=text)
        
        return ParsedCommand(CommandType.WHISPER, target=target_user, payload=message)
    
    elif command == "help":
        # /help - no parameters
        return ParsedCommand(CommandType.HELP)
    
    elif command == "list" or command == "users":
        # /list or /users - list online users
        return ParsedCommand(CommandType.LIST)
    
    elif command == "quit" or command == "exit":
        # /quit or /exit - disconnect
        return ParsedCommand(CommandType.QUIT)
    
    else:
        # Unknown command
        return ParsedCommand(CommandType.UNKNOWN, payload=text)


def format_system_message(text: str) -> str:
    """Format a system/server notice message.
    
    Args:
        text: Message text to format
        
    Returns:
        Formatted system message with [SYSTEM] prefix
        
    Example:
        >>> format_system_message("User joined")
        "[SYSTEM] User joined"
    """
    return f"[SYSTEM] {text}"


def format_direct_message(sender: str, text: str) -> str:
    """Format a private/direct message.
    
    Args:
        sender: Username of the message sender
        text: Message content
        
    Returns:
        Formatted direct message with sender identification
        
    Example:
        >>> format_direct_message("alice", "hello")
        "[Private from alice] hello"
    """
    return f"[Private from {sender}] {text}"


def get_help_text() -> str:
    """Get formatted help text listing available commands.
    
    Returns:
        Formatted help text with all available commands and their usage
    """
    help_text = """\
Available Commands:
  /help              - Show this help message
  /nick <name>       - Change your username
  /whisper <user> <msg> - Send a private message to another user
  /list              - List online users
  /quit              - Disconnect from the chatroom
  
Regular text messages are broadcasted to all users in the chatroom.
"""
    return help_text
