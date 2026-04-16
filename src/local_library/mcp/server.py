"""MCP server — wraps Library API for Claude Code integration."""

# pattern: Imperative Shell

import logging
import sys

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("local-library")


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Starting local-library MCP server")
    mcp.run(transport="stdio")
