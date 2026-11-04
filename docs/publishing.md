# Local PyPI release

The GitHub repository is named forge-mcp; the PyPI distribution is forge-mcp-registry because the forge-mcp project name is already in use.

## Build and verify

Start from a clean checkout of the release branch. Confirm the version in pyproject.toml, then run:

    python -m pip install --upgrade build twine
    python -m pytest -q
    python -m ruff check src/forge_mcp tests
    python -m build
    python -m twine check dist/*

The build creates one wheel and one source distribution in dist/.

## Upload locally

Create a PyPI API token for the forge-mcp-registry project. Upload from the same shell:

    python -m twine upload dist/*

When prompted, use __token__ as the username and paste the API token as the password. Twine hides the password input. Do not put the token in source files, shell scripts, GitHub files, or committed environment files.

## Versioning

PyPI releases are immutable. Increase the version in pyproject.toml for each upload, rebuild from a clean dist/, and never reuse an already-uploaded version.

## Distribution name

Install with:

    python -m pip install forge-mcp-registry

The Python import package remains forge_mcp; the command is forge-mcp.
