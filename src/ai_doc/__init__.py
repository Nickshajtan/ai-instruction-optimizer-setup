"""AI Documentation Optimizer."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ai-doc")
except PackageNotFoundError:
    __version__ = "0+unknown"
