import os
import shutil
import time
import unittest

from flight_profiler.test.plugins.profile_integration import ProfileIntegration


class ReloadPluginTest(unittest.TestCase):

    def setUp(self):
        # Path to the test module that will be reloaded
        self.test_module_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_module.py"
        )
        self.test_module_modified_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_module_modified.py"
        )
        self.test_module_backup_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_module_backup.py"
        )

        # Backup the original module
        shutil.copy2(self.test_module_path, self.test_module_backup_path)

    def tearDown(self):
        # Restore the original module
        shutil.move(self.test_module_backup_path, self.test_module_path)

    def test_reload_function(self):
        """Test the reload functionality by:
        1. Starting a test script
        2. Modifying a module file
        3. Executing the reload command
        4. Verifying the reload was successful
        5. Restoring the original file
        """
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "reload_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)

        try:
            # Step 1: Modify the test module file
            shutil.copy2(self.test_module_modified_path, self.test_module_path)

            # Step 2: Execute reload command
            # Reload the test_func function from __main__ module
            integration.execute_profile_cmd("reload --mod test_module --func test_func")
            process = integration.client_process

            # Step 3: Check for success message
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                if output:
                    line = str(output)
                    print(line)  # For debugging
                    if "Reload is done" in line:
                        find = True
                        break
                else:
                    break

            # Step 4: Verify the reload was successful
            self.assertTrue(find, "Reload success message not found")

        except Exception as e:
            raise e
        finally:
            # Step 5: Stop the integration
            integration.stop()


if __name__ == "__main__":
    unittest.main()
