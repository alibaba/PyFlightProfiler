# Test module for reload functionality
# This module contains functions that will be used to test the reload functionality

def test_function():
    """A simple test function"""
    return "original"

def fake_test_function():
    print(f"test")
    return "hello"


class TestClass:
    """A test class with methods to reload"""

    def test_method(self):
        """A simple test method"""
        return "original method"

    def another_method(self):
        """Another test method"""
        return "another original method"


def function_with_syntax_error():
    """A function that has intentional syntax error for testing error handling
    """
    # This is an intentional syntax error for testing
    return  # This will cause SyntaxError when reloaded with missing value
