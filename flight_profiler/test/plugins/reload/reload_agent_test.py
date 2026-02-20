import unittest

from flight_profiler.plugins.reload.reload_agent import (
    ReloadAgent,
    compare_code_objects_equal,
)


class TestReloadAgent(unittest.TestCase):
    def test_compare_code_objects_equal_same_code(self):
        """Test comparing identical code objects"""
        def func1():
            return "test"

        def func2():
            return "test"

        self.assertTrue(compare_code_objects_equal(func1.__code__, func2.__code__))

    def test_compare_code_objects_equal_different_code(self):
        """Test comparing different code objects"""
        def func1():
            return "test"

        def func2():
            return "different"

        self.assertFalse(compare_code_objects_equal(func1.__code__, func2.__code__))

    def test_reload_function_function_not_found(self):
        """Test reloading a non-existent function in an existing module"""
        result = ReloadAgent.reload_function("flight_profiler.test.plugins.reload.test_reload_module", None, "non_existent_function", False)
        self.assertIn("Cannot locate method", result)
        self.assertIn("non_existent_function", result)

    def test_reload_function_class_not_found(self):
        """Test reloading a function from a non-existent class"""
        result = ReloadAgent.reload_function("flight_profiler.test.plugins.reload.test_reload_module", "NonExistentClass", "test_method", False)
        self.assertIn("Cannot locate method", result)

    def test_reload_function_success_module_function(self):
        """Test successful reload of a module function"""
        # First, let's check the original function
        from flight_profiler.test.plugins.reload.test_reload_module import (
            fake_test_function,
            test_function,
        )
        test_function.__code__ = fake_test_function.__code__

        # Reload the function (it should be the same since source hasn't changed)
        result = ReloadAgent.reload_function("flight_profiler.test.plugins.reload.test_reload_module", None, "test_function", False)
        self.assertIn("Reload is done", result)

    def test_reload_function_success_class_method(self):
        """Test successful reload of a class method"""
        # Reload the method (it should be the same since source hasn't changed)
        from flight_profiler.test.plugins.reload.test_reload_module import TestClass
        TestClass.test_method.__code__ = TestClass.another_method.__code__
        result = ReloadAgent.reload_function("flight_profiler.test.plugins.reload.test_reload_module", "TestClass", "test_method", False)
        self.assertIn("Reload is done", result)

    def test_reload_function_no_change(self):
        """Test reloading a function that has not changed"""
        result = ReloadAgent.reload_function("flight_profiler.test.plugins.reload.test_reload_module", None, "test_function", False)
        self.assertIn("Method source has not changed", result)


if __name__ == '__main__':
    unittest.main()
