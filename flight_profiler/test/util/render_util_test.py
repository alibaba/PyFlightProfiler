import importlib.metadata
import unittest

from flight_profiler.utils import render_util
from flight_profiler.utils.render_util import ENTRANCE_HINTS, package_version


class PackageVersionTest(unittest.TestCase):

    def test_a_version_string_is_returned(self):
        self.assertIsInstance(package_version(), str)
        self.assertTrue(package_version())

    def test_a_source_checkout_without_metadata_still_works(self):
        # render_util is imported by almost everything, and it reads the version
        # at module scope. Raising here would make the package unimportable from
        # a plain clone on PYTHONPATH -- including the test suite itself.
        original = render_util.version

        def no_metadata(name):
            raise importlib.metadata.PackageNotFoundError(name)

        render_util.version = no_metadata
        try:
            self.assertEqual("unknown", package_version())
        finally:
            render_util.version = original

    def test_the_welcome_banner_carries_the_version(self):
        hints = dict(ENTRANCE_HINTS)

        self.assertIn("version", hints)
        self.assertTrue(hints["version"])


if __name__ == "__main__":
    unittest.main()
