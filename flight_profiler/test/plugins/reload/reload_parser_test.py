import unittest

from flight_profiler.plugins.reload.reload_parser import ReloadParams, ReloadParser


class TestReloadParser(unittest.TestCase):
    def setUp(self):
        self.parser = ReloadParser()

    def test_parse_reload_params_with_required_args(self):
        """Test parsing reload params with required arguments"""
        param_string = "--mod test_module --func test_function"
        params = self.parser.parse_reload_params(param_string)

        self.assertIsInstance(params, ReloadParams)
        self.assertEqual(params.module_name, "test_module")
        self.assertIsNone(params.class_name)
        self.assertEqual(params.func_name, "test_function")
        self.assertFalse(params.verbose)

    def test_parse_reload_params_with_class(self):
        """Test parsing reload params with class name"""
        param_string = "--mod test_module --cls TestClass --func test_method"
        params = self.parser.parse_reload_params(param_string)

        self.assertIsInstance(params, ReloadParams)
        self.assertEqual(params.module_name, "test_module")
        self.assertEqual(params.class_name, "TestClass")
        self.assertEqual(params.func_name, "test_method")
        self.assertFalse(params.verbose)

    def test_parse_reload_params_with_verbose(self):
        """Test parsing reload params with verbose flag"""
        param_string = "--mod test_module --func test_function --verbose"
        params = self.parser.parse_reload_params(param_string)

        self.assertIsInstance(params, ReloadParams)
        self.assertEqual(params.module_name, "test_module")
        self.assertIsNone(params.class_name)
        self.assertEqual(params.func_name, "test_function")
        self.assertTrue(params.verbose)

    def test_parse_reload_params_all_flags(self):
        """Test parsing reload params with all flags"""
        param_string = "--mod test_module --cls TestClass --func test_method -v"
        params = self.parser.parse_reload_params(param_string)

        self.assertIsInstance(params, ReloadParams)
        self.assertEqual(params.module_name, "test_module")
        self.assertEqual(params.class_name, "TestClass")
        self.assertEqual(params.func_name, "test_method")
        self.assertTrue(params.verbose)

    def test_parse_reload_params_missing_required_mod(self):
        """Test parsing reload params with missing required module"""
        param_string = "--func test_function"

        with self.assertRaises(Exception):
            self.parser.parse_reload_params(param_string)

    def test_parse_reload_params_missing_required_func(self):
        """Test parsing reload params with missing required function"""
        param_string = "--mod test_module"

        with self.assertRaises(Exception):
            self.parser.parse_reload_params(param_string)


if __name__ == '__main__':
    unittest.main()
