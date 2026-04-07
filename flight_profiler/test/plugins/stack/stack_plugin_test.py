import os
import tempfile
import time
import unittest

from flight_profiler.test.plugins.profile_integration import ProfileIntegration
from flight_profiler.utils.env_util import is_linux

# Async test script content - placed outside flight_profiler directory to avoid filtering
ASYNC_TEST_SCRIPT = '''
import asyncio
import sys

async def long_running_task():
    """A long running async task that can be detected."""
    while True:
        await asyncio.sleep(1)

async def nested_coroutine_inner():
    """Inner nested coroutine."""
    await asyncio.sleep(10)

async def nested_coroutine_outer():
    """Outer nested coroutine that awaits inner."""
    await nested_coroutine_inner()

async def main():
    """Main async entry point."""
    task1 = asyncio.create_task(long_running_task(), name="TestLongRunningTask")
    task2 = asyncio.create_task(nested_coroutine_outer(), name="TestNestedCoroutine")
    await asyncio.sleep(60)

if __name__ == "__main__":
    print("plugin unit test script started")
    sys.stdout.flush()
    asyncio.run(main())
'''


class StackPluginTest(unittest.TestCase):

    def test_stack(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "stack_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd("stack")
            process = integration.client_process
            find = False
            start = time.time()
            target_literal: str = (
                "Current thread" if not is_linux() else "Traceback for thread"
            )
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find(target_literal) >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()

    def test_stack_filepath(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "stack_server_script.py")
        stack_file = os.path.join(current_directory, "stack.log")
        integration = ProfileIntegration()
        integration.start(file, 15)
        target_literal: str = (
            "Current thread" if not is_linux() else "Traceback for thread"
        )
        try:
            if is_linux():
                integration.execute_profile_cmd(f"stack -f {stack_file}")
            else:
                integration.execute_profile_cmd(f"stack {stack_file}")
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find(f"Write stack to {stack_file} successfully!") >= 0:
                        find = True
                        break
                else:
                    break

            another_find = False
            with open(stack_file, "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.find(target_literal) >= 0:
                        another_find = True
                        break
            self.assertTrue(find)
            self.assertTrue(another_find)
        except:
            raise
        finally:
            os.remove(stack_file)
            integration.stop()

    def test_stack_native_frames(self):
        if not is_linux():
            return
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "stack_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd("stack --native")
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("(C)") >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()

    def test_stack_async(self):
        """Test stack -a command to detect asyncio tasks.

        Note: The test script is created in a temp directory (outside flight_profiler)
        to avoid being filtered by _is_flight_profiler_task().
        """
        # Create temp script file outside flight_profiler directory
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='_async_test.py', delete=False
        ) as f:
            f.write(ASYNC_TEST_SCRIPT)
            temp_script = f.name

        integration = ProfileIntegration()
        try:
            integration.start(temp_script, 20)
            integration.execute_profile_cmd("stack -a")
            process = integration.client_process
            find_header = False
            find_task = False
            start = time.time()
            while time.time() - start < 20:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if "Async Coroutine/Task Stacks" in line:
                        find_header = True
                    if "TestLongRunningTask" in line or "TestNestedCoroutine" in line:
                        find_task = True
                    if find_header and find_task:
                        break
                else:
                    break

            self.assertTrue(find_header, "Did not find 'Async Coroutine/Task Stacks' header")
            self.assertTrue(find_task, "Did not find any test async task")
        except Exception:
            raise
        finally:
            integration.stop()
            os.unlink(temp_script)


if __name__ == "__main__":
    test = StackPluginTest()
    test.test_stack()
    test.test_stack_filepath()
    test.test_stack_async()
