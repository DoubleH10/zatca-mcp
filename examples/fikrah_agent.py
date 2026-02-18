#!/usr/bin/env python3
"""
Fikra CLI has moved into the package and is now a global command.

Install and run:
    pip install -e ".[dev]"
    fikra

Or invoke directly:
    python -m zatca_mcp.cli
"""

from zatca_mcp.cli import main

if __name__ == "__main__":
    main()
