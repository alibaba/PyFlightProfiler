"""Build script."""

import shutil
from distutils.errors import CCompilerError, DistutilsExecError, DistutilsPlatformError
from pathlib import Path

from setuptools import Extension
from setuptools.command.build_ext import build_ext


def _copy_skills():
    """Copy skills/ into flight_profiler/skills/ for packaging."""
    root = Path(__file__).parent
    src = root / "skills"
    dst = root / "flight_profiler" / "skills"
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


_copy_skills()

extensions = [
    Extension(
        name="flight_profiler.ext.gilstat_C",
        include_dirs=["csrc"],
        sources=["csrc/symbol.cpp", "csrc/gilstat/gilstat.cpp"],
    ),
    Extension(
        name="flight_profiler.ext.stack_C",
        include_dirs=["csrc"],
        sources=["csrc/symbol.cpp", "csrc/stack/stack.cpp"],
    ),
    Extension(
        name="flight_profiler.ext.trace_profile_C",
        sources=["csrc/trace/trace_profile.c"],
    ),
]


class BuildFailed(Exception):
    pass


class ExtBuilder(build_ext):
    def run(self):
        try:
            build_ext.run(self)
        except (DistutilsPlatformError, FileNotFoundError):
            pass

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except (CCompilerError, DistutilsExecError, DistutilsPlatformError, ValueError):
            pass


def build(setup_kwargs):
    setup_kwargs.update(
        {
            "ext_modules": extensions,
            "cmdclass": {"build_ext": ExtBuilder},
            "package_data": {"flight_profiler": ["skills/**/*.md"]},
        }
    )
