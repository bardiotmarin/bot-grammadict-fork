#!/usr/bin/env python3

"""
Simple test script to verify handler blacklist filtering functionality
"""

import sys
import os

# Add the GramAddict directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'GramAddict'))

from GramAddict.core.filter import Filter, FIELD_HANDLER_BLACKLIST_WORDS

def test_handler_blacklist():
    """Test the handler blacklist functionality"""

    # Create a mock filter with handler blacklist words
    class MockFilter(Filter):
        def __init__(self):
            self.conditions = {
                FIELD_HANDLER_BLACKLIST_WORDS: ['bot', 'spam', 'fake', 'sale']
            }

    # Test cases
    test_cases = [
        ("normaluser", False),      # Should not be blacklisted
        ("botuser123", True),       # Should be blacklisted (starts with 'bot')
        ("user_bot", True),         # Should be blacklisted (ends with 'bot')
        ("spamaccount", True),      # Should be blacklisted (starts with 'spam')
        ("fakepage", True),         # Should be blacklisted (starts with 'fake')
        ("salesguy", True),         # Should be blacklisted (starts with 'sale')
        ("wholesaler", True),       # Should be blacklisted (ends with 'sale')
        ("cooluser", False),        # Should not be blacklisted
        ("BOTUSER", True),          # Should be blacklisted (case insensitive)
    ]

    filter_instance = MockFilter()

    print("Testing handler blacklist filtering:")
    print("-" * 40)

    for username, expected in test_cases:
        result = filter_instance.is_handler_blacklisted(username)
        status = "✓" if result == expected else "✗"
        print(f"{status} {username:<12} -> {'SKIP' if result else 'PASS'} (expected: {'SKIP' if expected else 'PASS'})")

    print("\nTest completed!")

if __name__ == "__main__":
    test_handler_filter()