import os
import time
import unittest

from flight_profiler.test.plugins.profile_integration import ProfileIntegration


class WatchPluginTest(unittest.TestCase):

    def test_watch_module_method(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "watch_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd(
                "watch __main__ test_func --expr {args,return_obj}"
            )
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("hello watch_plugin") >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()
    
    def test_watch_keyword_only_module_method(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "watch_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd(
                "watch __main__ kwonly_func --expr {args,return_obj}"
            )
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("kwonly_func_called") >= 0:
                        find = True
                        break
                else:
                    break
            
            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()

    def test_watch_module_class_nested_method(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "watch_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd(
                "watch __main__ A nested_method -nm nested_func_inner --expr {args,return_obj}"
            )
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("nested_method watch_plugin") >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()

    def test_watch_module_class_method(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "watch_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd(
                "watch __main__ A hello --expr {args,return_obj}"
            )
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("hello watch_plugin") >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()

    def test_watch_class_method(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "watch_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd(
                "watch __main__ A cls_method --expr {args,return_obj}"
            )
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("hello watch_plugin") >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()

    def test_watch_module_exp_method(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        file = os.path.join(current_directory, "watch_server_script.py")
        integration = ProfileIntegration()
        integration.start(file, 15)
        try:
            integration.execute_profile_cmd(
                "watch __main__ exp_func --expr {args,return_obj} -e"
            )
            process = integration.client_process
            find = False
            start = time.time()
            while time.time() - start < 15:
                output = process.stdout.readline()
                print(output)
                if output:
                    line = str(output)
                    if line.find("EXCEPTION") >= 0:
                        find = True
                        break
                else:
                    break

            self.assertTrue(find)
        except:
            raise
        finally:
            integration.stop()
            
    
