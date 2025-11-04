# Architecture: Reverse MCP Integration (Correct Implementation)

## High-Level Overview

```
                    ┌─────────────────┐
                    │   AI Client     │
                    │ (Claude/Cursor) │
                    └────────┬────────┘
                             │
             ┌───────────────┴───────────────┐
             │                               │
        [Reverse MCP]                  [Legacy STDIO]
             │                               │
             ▼                               ▼
    ┌─────────────────┐            ┌─────────────────┐
    │  MCP-Link       │            │  server.py      │
    │  Server         │            │  (FastMCP)      │
    │  (Aura Friday)  │            └────────┬────────┘
    └────────┬────────┘                     │
             │                              │ TCP Socket
             │ SSE + POST                   │ Port 9876
             ▼                              │
    ┌─────────────────┐                    │
    │  addon.py       │◄───────────────────┘
    │  (Blender)      │
    │  • Reverse MCP  │
    │  • Legacy socket│
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │    Blender      │
    │    (bpy)        │
    └─────────────────┘
```

##

 Key Difference from Previous Implementation

### ✅ CORRECT (Current Implementation):

**Reverse MCP Mode:**
```
AI → MCP-Link Server → addon.py (direct integration) → Blender
```
- **addon.py** discovers and connects to MCP-Link Server
- **addon.py** registers tools and handles reverse calls
- **server.py is NOT running** - not needed!
- **No port 9876 socket** created

**Legacy Mode (Fallback):**
```
AI → server.py (STDIO) → TCP Socket 9876 → addon.py → Blender
```
- User runs `uvx blender-mcp` which starts **server.py**
- **addon.py** creates TCP socket on port 9876
- Works exactly as original BlenderMCP

### ❌ WRONG (Previous Attempt):

```
AI → MCP-Link Server → reverse_bridge.py → TCP Socket 9876 → addon.py → Blender
```
- Had unnecessary middleware layer
- Still used port 9876 even in Reverse MCP mode
- More complex, less efficient

## Detailed Flow: Reverse MCP Mode

```
1. User clicks "Connect to MCP server" in Blender
   │
   ▼
2. addon.py: BlenderMCPServer.start()
   │
   ▼
3. addon.py: _try_start_reverse_mcp()
   ├─ Find native messaging manifest
   ├─ Run native binary to get config
   ├─ Extract server URL & auth token
   ├─ Connect to SSE endpoint
   ├─ Start SSE reader thread
   ├─ Check for 'remote' tool
   ├─ Register Blender tools:
   │  • blender_get_scene_info
   │  • blender_get_object_info
   │  • blender_execute_code
   └─ Start reverse call listener thread
   │
   ▼
4. Blender addon now directly integrated with MCP-Link!
   │
   ▼
5. When AI calls a tool:
   AI → MCP-Link Server
        │
        ▼ SSE (reverse call)
   addon.py: _reverse_call_listener()
        │
        ▼
   addon.py: _handle_reverse_tool_call()
        │
        ▼
   Execute in Blender (bpy)
        │
        ▼ Result
   addon.py: send_tool_reply()
        │
        ▼ POST
   MCP-Link Server → AI
```

## Detailed Flow: Legacy Mode (Fallback)

```
1. User clicks "Connect to MCP server" in Blender
   │
   ▼
2. addon.py: BlenderMCPServer.start()
   │
   ▼
3. addon.py: _try_start_reverse_mcp()
   └─ Returns False (MCP-Link not found)
   │
   ▼
4. addon.py: Creates TCP socket on port 9876
   addon.py: Waits for connection
   │
   ▼
5. User has configured Claude/Cursor with:
   "command": "uvx", "args": ["blender-mcp"]
   │
   ▼
6. server.py starts (FastMCP via STDIO)
   │
   ▼
7. server.py: Connects to addon.py via TCP socket
   │
   ▼
8. When AI calls a tool:
   AI → server.py (STDIO)
        │
        ▼
   server.py: Tool handler function
        │
        ▼ TCP Socket
   addon.py: Receives JSON command
        │
        ▼
   Execute in Blender (bpy)
        │
        ▼ TCP Socket
   server.py: Receives result
        │
        ▼ STDIO
   AI receives result
```

## File Structure

```
blender-mcp/
├── addon.py                     # ✅ MODIFIED - Now includes Reverse MCP
│   ├── Reverse MCP client functions
│   ├── BlenderMCPServer class (dual-mode)
│   └── All Blender tool implementations
│
├── src/blender_mcp/
│   ├── server.py                # ✅ UNCHANGED - Only used in legacy mode
│   └── __init__.py              # ✅ UNCHANGED
│
├── main.py                      # ✅ UNCHANGED
├── pyproject.toml               # ✅ UNCHANGED
│
└── Documentation/
    ├── README.md
    ├── ARCHITECTURE.md (this file)
    ├── REVERSE_MCP_INTEGRATION.md
    └── QUICK_START_REVERSE_MCP.md
```

## Code Organization in addon.py

```python
# ============================================================================
# Section 1: Imports (added http.client, ssl, uuid, queue, etc.)
# ============================================================================

# ============================================================================
# Section 2: Reverse MCP Client Functions
# ============================================================================
def find_native_messaging_manifest()
def discover_mcp_server_endpoint()
def connect_to_sse_endpoint()
def send_jsonrpc_request()
def send_tool_reply()

# ============================================================================
# Section 3: BlenderMCPServer Class (Enhanced)
# ============================================================================
class BlenderMCPServer:
    def __init__():
        # Added: Reverse MCP attributes
        
    def start():
        # NEW: Try Reverse MCP first
        # FALLBACK: Legacy socket server
        
    def _try_start_reverse_mcp():           # NEW
    def _start_sse_reader():                # NEW
    def _register_blender_tools():          # NEW
    def _reverse_call_listener():           # NEW
    def _handle_reverse_tool_call():        # NEW
    def _cleanup_reverse_mcp():             # NEW
    
    def stop():
        # Enhanced: Clean up both modes
        
    def _server_loop():                     # UNCHANGED (legacy)
    def _handle_client():                   # UNCHANGED (legacy)
    def execute_command():                  # UNCHANGED (used by both)
    def get_scene_info():                   # UNCHANGED (used by both)
    def get_object_info():                  # UNCHANGED (used by both)
    def execute_code():                     # UNCHANGED (used by both)
    # ... all other tool methods unchanged
```

## Mode Detection Logic

```python
def start(self):
    if self._try_start_reverse_mcp():
        self.mode = "reverse_mcp"
        # ✓ Connected to MCP-Link Server
        # ✓ Tools registered
        # ✓ Listening for reverse calls
        # ✗ No TCP socket created
        # ✗ server.py not needed
        return
    
    # Fallback to legacy
    self.mode = "legacy"
    # ✓ TCP socket on port 9876
    # ✓ Waiting for server.py connection
```

## Threading Model

### Reverse MCP Mode

```
Main Blender Thread
└─ UI / Scene operations

Background Thread 1: SSE Reader
├─ Reads SSE stream continuously
├─ Routes reverse calls to reverse_queue
└─ Routes responses to pending_responses

Background Thread 2: Reverse Call Listener
├─ Blocks on reverse_queue.get()
├─ Processes tool calls
├─ Executes in Blender via bpy.app.timers
└─ Sends POST replies
```

### Legacy Mode

```
Main Blender Thread
└─ UI / Scene operations

Background Thread 1: Server Loop
├─ Accepts TCP connections
└─ Spawns client handler threads

Background Thread N: Client Handler
├─ Receives JSON commands
├─ Schedules execution via bpy.app.timers
└─ Sends JSON responses
```

## Benefits of This Architecture

### Reverse MCP Mode
1. **✅ True Direct Integration** - No middleware, no extra process
2. **✅ Eliminates Port 9876** - No TCP socket needed
3. **✅ One Less Process** - server.py not running
4. **✅ More Efficient** - Fewer hops in communication
5. **✅ Self-Sufficient** - addon.py handles everything

### Legacy Mode
6. **✅ Perfect Backward Compatibility** - Works exactly as before
7. **✅ No Breaking Changes** - Existing users unaffected
8. **✅ Automatic Fallback** - Seamless when MCP-Link unavailable

## Comparison Table

| Aspect | Reverse MCP | Legacy |
|--------|-------------|--------|
| Processes | 1 (Blender only) | 2 (Blender + server.py) |
| Port 9876 | ❌ Not used | ✅ Required |
| server.py | ❌ Not running | ✅ Running |
| Communication | SSE + POST | STDIO + TCP |
| Setup | Auto-detect | Manual config |
| Efficiency | High (direct) | Medium (2 hops) |
| Multi-client | ✅ Yes | ❌ No |

## Tool Registration

### Reverse MCP Mode

Tools are registered directly with MCP-Link Server:

```python
{
    "tool_name": "blender_get_scene_info",
    "readme": "Get detailed information...",
    "description": "Retrieves comprehensive...",
    "parameters": {...},
    "callback_endpoint": "blender-mcp://blender_get_scene_info",
    "TOOL_API_KEY": "blender_mcp_auth_key_v1"
}
```

Tools become available to ANY AI connected to MCP-Link Server.

### Legacy Mode

Tools are discovered via FastMCP's `@mcp.tool()` decorators in server.py.
Standard MCP protocol via STDIO.

## Security

### Reverse MCP Mode
- ✅ Authentication via MCP-Link Server tokens
- ✅ Tool-specific API keys
- ✅ SSL/TLS for SSE connections
- ✅ Callback endpoint validation

### Legacy Mode
- ⚠️ No authentication on port 9876 socket
- ⚠️ Localhost-only binding
- ⚠️ Should not expose to network

## Future Enhancements

Possible improvements:

1. **More Tools**: Add all Blender tools (PolyHaven, Hyper3D, Sketchfab)
2. **Screenshot Support**: Handle images in reverse calls
3. **WebSocket**: Alternative to SSE
4. **Multi-Blender**: Support multiple instances
5. **Hot Reload**: Register new tools without restart

## Migration Path

For existing users:

1. **No changes required** - addon.py will use legacy mode if MCP-Link not installed
2. **Optional upgrade** - Install MCP-Link Server to get Reverse MCP
3. **Automatic detection** - System chooses best mode on startup

## Summary

The key insight of this architecture is:

> **The addon itself should be smart enough to choose its communication method**

Rather than:
- Building middleware to bridge MCP-Link → Blender
- Keeping port 9876 socket even when using MCP-Link

We instead:
- Made addon.py discover and use MCP-Link directly
- Eliminated the middleware entirely
- Kept legacy socket as clean fallback

This results in:
- **Simpler** - Fewer moving parts
- **Faster** - Direct integration
- **Cleaner** - No unnecessary layers
- **Compatible** - Works both ways
