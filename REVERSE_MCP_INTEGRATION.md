# Reverse MCP Integration

## Overview

This BlenderMCP fork now includes **dual-mode support** with automatic fallback:

1. **Reverse MCP Mode (Advanced)**: Uses the Aura Friday MCP-Link Server for enhanced communication
2. **Legacy STDIO Mode**: Falls back to the original direct socket connection

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      BlenderMCP Server                           │
│                                                                   │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Startup: Try Reverse MCP First                        │    │
│  │  ↓                                                      │    │
│  │  Found Aura Friday MCP-Link Server?                    │    │
│  │  ├─ YES → Use Reverse MCP Mode                         │    │
│  │  └─ NO  → Use Legacy STDIO Mode                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Reverse MCP Mode (When Available)

```
AI (Claude/Cursor)
    ↓
Aura Friday MCP-Link Server (SSE + POST)
    ↓
BlenderMCP Server (reverse_bridge.py)
    ↓
Blender Addon (TCP socket)
    ↓
Blender (execution)
```

**Benefits:**
- Enhanced tool registration and discovery
- Better error handling and retry logic
- Support for multiple AI clients simultaneously
- Advanced authentication and security
- Future-proof for additional MCP features

### Legacy Mode (Fallback)

```
AI (Claude/Cursor) via STDIO
    ↓
BlenderMCP Server (direct socket)
    ↓
Blender Addon (TCP socket)
    ↓
Blender (execution)
```

## Installation

### Standard Installation (Legacy Mode)

Follow the original README instructions. The system will use legacy STDIO mode.

### Enhanced Installation (Reverse MCP Mode)

To enable Reverse MCP mode:

1. **Install Aura Friday MCP-Link Server**
   - Download from: https://github.com/aurafriday/mcp-link-server/releases
   - Follow the installation instructions for your platform

2. **Install BlenderMCP** (same as before)
   ```bash
   # Your existing installation process
   ```

3. **Start Blender and enable the addon** (same as before)

4. **Configure your AI client** (same as before)
   - Claude Desktop: Edit `claude_desktop_config.json`
   - Cursor: Edit MCP settings
   - VS Code: Use the MCP extension

When you start BlenderMCP, it will automatically detect and use the MCP-Link Server if available.

## Detecting Which Mode is Active

Check the server logs on startup:

### Reverse MCP Mode:
```
============================================================
BlenderMCP server starting up
============================================================
Looking for Aura Friday MCP-Link server...
Found manifest at: /path/to/manifest
Discovering MCP-Link server endpoint...
Found MCP-Link server at: https://...
Connecting to SSE endpoint...
Connected to SSE! Session ID: xxx
Checking for remote tool...
Remote tool found!
Connecting to Blender addon at localhost:9876...
Connected to Blender addon!
Registering Blender tools...
Registered: blender_get_scene_info
Registered: blender_get_object_info
Registered: blender_get_viewport_screenshot
Registered: blender_execute_code
All Blender tools registered successfully!
============================================================
✓ CONNECTION MODE: Reverse MCP (Advanced)
  Connected via Aura Friday MCP-Link Server
  Tools are registered and accessible via MCP-Link
============================================================
```

### Legacy Mode:
```
============================================================
BlenderMCP server starting up
============================================================
Using legacy direct socket connection to Blender
Created new persistent connection to Blender (legacy mode)
============================================================
CONNECTION MODE: Legacy STDIO
  Direct socket connection to Blender
============================================================
```

## Code Structure

### New Files

1. **`src/blender_mcp/reverse_mcp_client.py`**
   - Low-level client for communicating with Aura Friday MCP-Link Server
   - Handles native messaging manifest discovery
   - Manages SSE connections and JSON-RPC requests
   - Based on the reference implementation from `reverse_mcp.py`

2. **`src/blender_mcp/reverse_bridge.py`**
   - `ReverseBlenderConnection` class
   - Bridges MCP-Link Server ↔ Blender addon
   - Registers Blender tools as remote tools
   - Handles reverse tool calls and forwards to Blender
   - Maintains the same interface as `BlenderConnection` for compatibility

### Modified Files

1. **`src/blender_mcp/server.py`**
   - Added Reverse MCP detection and fallback logic
   - `get_blender_connection()` now tries Reverse MCP first
   - Enhanced logging to show active connection mode
   - No changes to tool implementations (they work with both modes)

2. **`src/blender_mcp/__init__.py`**
   - Exports Reverse MCP components if available
   - Graceful fallback if Reverse MCP modules fail to import

### Unchanged Files

- **`addon.py`**: No changes needed! The Blender addon is agnostic to the connection method
- **`main.py`**: No changes needed
- **`pyproject.toml`**: No changes needed (all dependencies are standard library)

## Tool Registration in Reverse MCP Mode

When using Reverse MCP, the following tools are automatically registered with the MCP-Link Server:

1. **`blender_get_scene_info`**
   - Get detailed scene information
   
2. **`blender_get_object_info`**
   - Get detailed object information
   
3. **`blender_get_viewport_screenshot`**
   - Capture viewport screenshots
   
4. **`blender_execute_code`**
   - Execute Python code in Blender

These tools are accessible to any AI client connected to the MCP-Link Server, with proper authentication.

## Troubleshooting

### Reverse MCP Not Activating

If you have MCP-Link Server installed but it's not being used:

1. Check that the server is running
2. Verify the native messaging manifest exists:
   - **Windows**: `%LOCALAPPDATA%\AuraFriday\com.aurafriday.shim.json`
   - **macOS**: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.aurafriday.shim.json`
   - **Linux**: `~/.config/google-chrome/NativeMessagingHosts/com.aurafriday.shim.json`
3. Check server logs for detailed error messages

### Forcing Legacy Mode

If you want to disable Reverse MCP and force legacy mode:

1. Stop/uninstall the Aura Friday MCP-Link Server, or
2. Rename/remove the native messaging manifest file

The system will automatically fall back to legacy mode.

### Connection Issues

- **Blender addon not connecting**: Make sure Blender is running and the addon is enabled and started
- **MCP-Link Server not found**: Install the server from the releases page
- **Port conflicts**: Check that port 9876 (default) is not in use by another application

## Benefits of Reverse MCP

1. **No STDIO Limitations**: Not constrained by standard input/output buffering
2. **Better Error Handling**: SSE + POST allows for more robust error recovery
3. **Multi-Client Support**: Multiple AIs can connect to the same Blender instance
4. **Enhanced Security**: Authentication tokens and proper authorization
5. **Future-Proof**: Ready for advanced MCP features as they become available
6. **Transparent**: Works with existing Blender addon without modifications

## Development

### Testing Reverse MCP Locally

```bash
# Start the MCP-Link Server (if you have it installed)
# Then start BlenderMCP as normal:
uvx blender-mcp
```

Check the logs to see which mode activated.

### Adding New Tools

To add a new tool that works in both modes:

1. Add the tool function in `server.py` (same as before)
2. Add the tool registration in `reverse_bridge.py` → `_register_all_tools()`
3. Add the tool mapping in `reverse_bridge.py` → `_handle_tool_call()`

The tool will automatically work in both Reverse MCP and Legacy modes.

## License

Same as the original BlenderMCP project.

## Credits

- Original BlenderMCP: Siddharth Ahuja
- Reverse MCP Integration: Based on Aura Friday MCP-Link Server architecture
- Reference implementation: `reverse_mcp.py` template

