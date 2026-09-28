"""Tiny stdio MCP server for tests/test_mcp.py (works with mcp 1.x and 2.x)."""

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

server = _Server("echo")


@server.tool()
def echo(text: str) -> str:
    """Echo the text back."""
    return f"echo: {text}"


@server.tool()
def add(a: int, b: int) -> str:
    """Add two integers."""
    return str(a + b)


@server.tool()
def shout(text: str) -> str:
    """Return a very long string (truncation test)."""
    return text.upper() * 500


if __name__ == "__main__":
    server.run()
