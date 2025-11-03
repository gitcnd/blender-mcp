"""Blender integration through the Model Context Protocol."""

__version__ = "0.1.0"

# Expose key classes and functions for easier imports
from .server import BlenderConnection, get_blender_connection

# Try to expose Reverse MCP components if available
try:
  from .reverse_bridge import ReverseBlenderConnection
  from . import reverse_mcp_client
  __all__ = ['BlenderConnection', 'get_blender_connection', 'ReverseBlenderConnection', 'reverse_mcp_client']
except ImportError:
  __all__ = ['BlenderConnection', 'get_blender_connection']
