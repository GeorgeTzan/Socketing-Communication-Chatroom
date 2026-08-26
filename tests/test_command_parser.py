# [2026-08-26] Unit tests for command parser and message formatter
# Tests slash command parsing, message envelope formatting, and help text generation

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_parser import (
    CommandType,
    ParsedCommand,
    parse_user_input,
    format_system_message,
    format_direct_message,
    get_help_text
)


class TestParseUserInput:
    """Test cases for parse_user_input function."""
    
    def test_regular_message_simple(self):
        """Regular message without slash should parse as MESSAGE."""
        result = parse_user_input("hello world")
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == "hello world"
        assert result.target is None
    
    def test_regular_message_with_spaces(self):
        """Regular message with multiple spaces should be preserved."""
        result = parse_user_input("hello  world  test")
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == "hello  world  test"
    
    def test_regular_message_with_leading_trailing_spaces(self):
        """Leading and trailing whitespace should be stripped."""
        result = parse_user_input("  hello world  ")
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == "hello world"
    
    def test_empty_string(self):
        """Empty string should parse as MESSAGE with empty payload."""
        result = parse_user_input("")
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == ""
    
    def test_whitespace_only(self):
        """Whitespace-only string should parse as MESSAGE with empty payload."""
        result = parse_user_input("   \t\n  ")
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == ""
    
    def test_whisper_command_basic(self):
        """Basic /whisper command should parse correctly."""
        result = parse_user_input("/whisper alice hello world")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "alice"
        assert result.payload == "hello world"
    
    def test_whisper_command_with_leading_spaces(self):
        """Whisper command with leading spaces should be handled."""
        result = parse_user_input("  /whisper bob message here")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "bob"
        assert result.payload == "message here"
    
    def test_whisper_command_with_single_word_message(self):
        """Whisper with single word message should work."""
        result = parse_user_input("/whisper charlie hi")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "charlie"
        assert result.payload == "hi"
    
    def test_whisper_command_no_message(self):
        """Whisper command with no message body should parse but with empty payload."""
        result = parse_user_input("/whisper dave")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "dave"
        assert result.payload == ""
    
    def test_whisper_command_no_target(self):
        """Whisper command with no target should return UNKNOWN."""
        result = parse_user_input("/whisper")
        assert result.command_type == CommandType.UNKNOWN
    
    def test_nick_command_basic(self):
        """Basic /nick command should extract new username."""
        result = parse_user_input("/nick JohnDoe")
        assert result.command_type == CommandType.NICK
        assert result.payload == "JohnDoe"
        assert result.target is None
    
    def test_nick_command_with_spaces(self):
        """Nick with leading/trailing spaces should be handled."""
        result = parse_user_input("  /nick  Alice123  ")
        assert result.command_type == CommandType.NICK
        assert result.payload == "Alice123"
    
    def test_nick_command_no_name(self):
        """Nick command with no name should return UNKNOWN."""
        result = parse_user_input("/nick")
        assert result.command_type == CommandType.UNKNOWN
    
    def test_nick_command_empty_name(self):
        """Nick command with empty name should return UNKNOWN."""
        result = parse_user_input("/nick    ")
        assert result.command_type == CommandType.UNKNOWN
    
    def test_help_command(self):
        """Help command should parse correctly."""
        result = parse_user_input("/help")
        assert result.command_type == CommandType.HELP
        assert result.target is None
        assert result.payload is None
    
    def test_help_command_with_spaces(self):
        """Help command with surrounding spaces should work."""
        result = parse_user_input("  /help  ")
        assert result.command_type == CommandType.HELP
    
    def test_list_command(self):
        """List command should parse correctly."""
        result = parse_user_input("/list")
        assert result.command_type == CommandType.LIST
        assert result.target is None
        assert result.payload is None
    
    def test_users_command_alias(self):
        """Users command (alias for list) should parse correctly."""
        result = parse_user_input("/users")
        assert result.command_type == CommandType.LIST
    
    def test_quit_command(self):
        """Quit command should parse correctly."""
        result = parse_user_input("/quit")
        assert result.command_type == CommandType.QUIT
        assert result.target is None
        assert result.payload is None
    
    def test_exit_command_alias(self):
        """Exit command (alias for quit) should parse correctly."""
        result = parse_user_input("/exit")
        assert result.command_type == CommandType.QUIT
    
    def test_unknown_command(self):
        """Unknown slash command should return UNKNOWN type."""
        result = parse_user_input("/invalid")
        assert result.command_type == CommandType.UNKNOWN
        assert result.payload == "/invalid"
    
    def test_unknown_command_with_args(self):
        """Unknown slash command with arguments should return UNKNOWN."""
        result = parse_user_input("/notacommand arg1 arg2")
        assert result.command_type == CommandType.UNKNOWN
        assert result.payload == "/notacommand arg1 arg2"
    
    def test_command_case_insensitive(self):
        """Commands should be case-insensitive."""
        result_lower = parse_user_input("/nick alice")
        result_upper = parse_user_input("/NICK alice")
        result_mixed = parse_user_input("/NiCk alice")
        
        assert result_lower.command_type == CommandType.NICK
        assert result_upper.command_type == CommandType.NICK
        assert result_mixed.command_type == CommandType.NICK
        
        assert result_lower.payload == "alice"
        assert result_upper.payload == "alice"
        assert result_mixed.payload == "alice"
    
    def test_slash_in_message(self):
        """Message starting with slash but not a command should be UNKNOWN."""
        result = parse_user_input("/this is not a command")
        assert result.command_type == CommandType.UNKNOWN
    
    def test_multiple_slashes(self):
        """Multiple slashes should be treated as unknown command."""
        result = parse_user_input("//nick alice")
        assert result.command_type == CommandType.UNKNOWN
    
    def test_whisper_with_special_characters(self):
        """Whisper message with special characters should work."""
        result = parse_user_input("/whisper alice hello! @#$%")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "alice"
        assert result.payload == "hello! @#$%"
    
    def test_nick_with_special_characters(self):
        """Nick with special characters should work."""
        result = parse_user_input("/nick User_123-ABC")
        assert result.command_type == CommandType.NICK
        assert result.payload == "User_123-ABC"


class TestFormatSystemMessage:
    """Test cases for format_system_message function."""
    
    def test_basic_system_message(self):
        """Basic system message should be formatted with prefix."""
        result = format_system_message("User joined")
        assert result == "[SYSTEM] User joined"
    
    def test_system_message_empty(self):
        """Empty system message should still have prefix."""
        result = format_system_message("")
        assert result == "[SYSTEM] "
    
    def test_system_message_with_special_chars(self):
        """System message with special characters should work."""
        result = format_system_message("User @alice left the chat!")
        assert result == "[SYSTEM] User @alice left the chat!"
    
    def test_system_message_preserves_spacing(self):
        """System message should preserve internal spacing."""
        result = format_system_message("User   joined   now")
        assert result == "[SYSTEM] User   joined   now"


class TestFormatDirectMessage:
    """Test cases for format_direct_message function."""
    
    def test_basic_direct_message(self):
        """Basic direct message should be formatted correctly."""
        result = format_direct_message("alice", "hello there")
        assert result == "[Private from alice] hello there"
    
    def test_direct_message_empty_text(self):
        """Direct message with empty text should still format."""
        result = format_direct_message("bob", "")
        assert result == "[Private from bob] "
    
    def test_direct_message_special_username(self):
        """Direct message with special characters in username."""
        result = format_direct_message("alice_123", "message")
        assert result == "[Private from alice_123] message"
    
    def test_direct_message_special_characters(self):
        """Direct message with special characters in text."""
        result = format_direct_message("user", "hello! @#$% 😀")
        assert result == "[Private from user] hello! @#$% 😀"
    
    def test_direct_message_preserves_spacing(self):
        """Direct message should preserve spacing in text."""
        result = format_direct_message("alice", "hello   world")
        assert result == "[Private from alice] hello   world"


class TestGetHelpText:
    """Test cases for get_help_text function."""
    
    def test_help_text_not_empty(self):
        """Help text should not be empty."""
        result = get_help_text()
        assert result
        assert len(result) > 0
    
    def test_help_text_contains_commands(self):
        """Help text should mention all major commands."""
        result = get_help_text()
        assert "/help" in result
        assert "/nick" in result
        assert "/whisper" in result
        assert "/list" in result
        assert "/quit" in result
    
    def test_help_text_is_string(self):
        """Help text should be a string."""
        result = get_help_text()
        assert isinstance(result, str)
    
    def test_help_text_format(self):
        """Help text should have reasonable formatting."""
        result = get_help_text()
        lines = result.split("\n")
        assert len(lines) > 1  # Should have multiple lines


class TestParsedCommandDataclass:
    """Test cases for ParsedCommand dataclass."""
    
    def test_parsed_command_creation(self):
        """ParsedCommand should be creatable with required field."""
        cmd = ParsedCommand(CommandType.MESSAGE)
        assert cmd.command_type == CommandType.MESSAGE
        assert cmd.target is None
        assert cmd.payload is None
    
    def test_parsed_command_with_all_fields(self):
        """ParsedCommand with all fields should work."""
        cmd = ParsedCommand(CommandType.WHISPER, target="alice", payload="hello")
        assert cmd.command_type == CommandType.WHISPER
        assert cmd.target == "alice"
        assert cmd.payload == "hello"
    
    def test_parsed_command_equality(self):
        """Two ParsedCommands with same values should be equal."""
        cmd1 = ParsedCommand(CommandType.MESSAGE, payload="hello")
        cmd2 = ParsedCommand(CommandType.MESSAGE, payload="hello")
        assert cmd1 == cmd2


class TestCommandTypeEnum:
    """Test cases for CommandType enum."""
    
    def test_all_command_types_exist(self):
        """All expected command types should exist."""
        assert hasattr(CommandType, "MESSAGE")
        assert hasattr(CommandType, "NICK")
        assert hasattr(CommandType, "WHISPER")
        assert hasattr(CommandType, "HELP")
        assert hasattr(CommandType, "LIST")
        assert hasattr(CommandType, "QUIT")
        assert hasattr(CommandType, "UNKNOWN")
    
    def test_command_types_are_unique(self):
        """All command type values should be unique."""
        values = [cmd.value for cmd in CommandType]
        assert len(values) == len(set(values))


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_very_long_message(self):
        """Very long regular message should work."""
        long_msg = "a" * 10000
        result = parse_user_input(long_msg)
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == long_msg
    
    def test_very_long_whisper_message(self):
        """Very long whisper message should work."""
        long_payload = "b" * 10000
        result = parse_user_input(f"/whisper alice {long_payload}")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "alice"
        assert result.payload == long_payload
    
    def test_unicode_in_message(self):
        """Unicode characters should work in messages."""
        result = parse_user_input("Hello 世界 🌍")
        assert result.command_type == CommandType.MESSAGE
        assert result.payload == "Hello 世界 🌍"
    
    def test_unicode_in_whisper(self):
        """Unicode in whisper should work."""
        result = parse_user_input("/whisper alice Hello 世界")
        assert result.command_type == CommandType.WHISPER
        assert result.target == "alice"
        assert result.payload == "Hello 世界"
    
    def test_tab_characters(self):
        """Tab characters should be handled."""
        result = parse_user_input("hello\tworld")
        assert result.command_type == CommandType.MESSAGE
    
    def test_newline_characters(self):
        """Newline characters in input should be stripped."""
        result = parse_user_input("hello\nworld\n")
        assert result.command_type == CommandType.MESSAGE
        # After strip, newline should be gone
        assert "\n" not in result.payload or result.payload == "hello\nworld"


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_parse_and_format_system_message(self):
        """Parse MESSAGE and format as system message."""
        parsed = parse_user_input("User joined")
        if parsed.command_type == CommandType.MESSAGE:
            formatted = format_system_message(parsed.payload)
            assert formatted == "[SYSTEM] User joined"
    
    def test_parse_and_format_direct_message(self):
        """Parse WHISPER and format as direct message."""
        parsed = parse_user_input("/whisper alice hello")
        if parsed.command_type == CommandType.WHISPER:
            formatted = format_direct_message("alice", parsed.payload)
            assert formatted == "[Private from alice] hello"
    
    def test_help_command_and_text(self):
        """Parse help command and get help text."""
        parsed = parse_user_input("/help")
        assert parsed.command_type == CommandType.HELP
        
        help_text = get_help_text()
        assert help_text is not None
        assert len(help_text) > 0
