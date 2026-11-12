"""Agent Token Receipt - Every token has a receipt.

A local-first, open-source Python tool that collects verifiable AI usage data
from coding-agent sessions and generates crisp thermal-receipt-style PDFs.
"""

__version__ = "0.2.0"
__all__ = ["cli", "main", "__version__"]


def __getattr__(name: str):
    if name in ("cli", "main"):
        from cli import main as cli_module

        return getattr(cli_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
