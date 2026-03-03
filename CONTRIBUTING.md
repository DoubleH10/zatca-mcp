# Contributing to ZATCA MCP

Thanks for your interest in contributing! This is the first open-source MCP server for Saudi e-invoicing, and contributions are welcome.

## Getting Started

```bash
git clone https://github.com/DoubleH10/zatca-mcp.git
cd zatca-mcp
pip install -e ".[dev,phase2]"
```

## Running Tests

```bash
pytest tests/ -v                         # All tests
pytest tests/ -v -m "not sandbox"        # Skip live ZATCA sandbox tests
```

## Code Quality

We use ruff for linting/formatting and mypy for type checking:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/zatca_mcp/ --ignore-missing-imports
```

All checks run in CI across Python 3.10, 3.11, and 3.12.

## Making Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests as needed
4. Ensure all tests pass and linting is clean
5. Open a PR with a clear description of what you changed and why

## Good First Issues

Check the [good first issue](https://github.com/DoubleH10/zatca-mcp/labels/good%20first%20issue) label for beginner-friendly tasks.

## Questions?

Open an issue or start a discussion. We're happy to help you get started.
