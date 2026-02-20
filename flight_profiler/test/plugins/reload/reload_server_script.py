import sys
import time

# Import the test function
try:
    from test_module import test_func
except ImportError:
    # If test_module doesn't exist, define a default function
    def test_func():
        return "original"

print("plugin unit test script started\n")
sys.stdout.flush()

# Keep the script running
while True:
    time.sleep(1)
