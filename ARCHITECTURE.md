# Architecture: Reverse MCP Integration

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AI Client                                │
│                   (Claude / Cursor / etc)                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ (Chooses path automatically)
                     │
         ┌───────────┴───────────┐
         │                       │
    [Reverse MCP]           [Legacy STDIO]
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  MCP-Link       │     │  BlenderMCP     │
│  Server         │     │  Server         │
│  (Aura Friday)  │     │  (direct)       │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │ SSE + POST           │ STDIO
         ▼                       │
┌─────────────────┐             │
│  BlenderMCP     │◄────────────┘
│  Server         │
│  (reverse_      │
│   bridge)       │
└────────┬────────┘
         │
         │ TCP Socket (both paths converge here)
         ▼
┌─────────────────┐
│  Blender Addon  │
│  (addon.py)     │
│  Port 9876      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Blender      │
│    (bpy)        │
└─────────────────┘
```

## Detailed: Reverse MCP Mode

```
┌───────────────────────────────────────────────────────────────┐
│                      AI Client (Claude)                        │
└──────────────┬────────────────────────────────────────────────┘
               │
               │ MCP protocol
               ▼
┌──────────────────────────────────────────────────────────────┐
│              Aura Friday MCP-Link Server                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • Tool Registry (with blender_* tools)               │   │
│  │ • SSE Broadcaster (sends tool calls)                 │   │
│  │ • POST Receiver (receives tool replies)             │   │
│  │ • Authentication & Authorization                     │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────┬─────────────────────────────────┬───────────────┘
             │                                 │
             │ SSE (Server-Sent Events)       │ POST replies
             │ Tool calls →                    │ ← Results
             ▼                                 │
┌────────────────────────────────────────────────────────────────┐
│         BlenderMCP Server (reverse_bridge.py)                  │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  Initialization:                                       │   │
│  │  1. Find native messaging manifest                    │   │
│  │  2. Discover MCP-Link server endpoint                 │   │
│  │  3. Connect to SSE endpoint                           │   │
│  │  4. Register all Blender tools                        │   │
│  │  5. Start listener thread                             │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  Reverse Call Handler (listener thread):              │   │
│  │  • Listen on reverse_queue (from SSE)                 │   │
│  │  • Extract: tool_name, call_id, input_data            │   │
│  │  • Map tool_name → Blender command                    │   │
│  │  • Forward to Blender addon via TCP socket            │   │
│  │  • Format result for MCP                              │   │
│  │  • POST reply back to MCP-Link server                 │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────┬───────────────────────────────────────────────────┘
             │
             │ TCP Socket (localhost:9876)
             │ JSON commands ↓ / responses ↑
             ▼
┌────────────────────────────────────────────────────────────────┐
│              Blender Addon Socket Server                       │
│  • Accepts connections on port 9876                            │
│  • Receives JSON commands                                      │
│  • Schedules execution in main thread (bpy.app.timers)        │
│  • Returns JSON responses                                      │
└────────────┬───────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────┐
│                      Blender (bpy)                             │
│  • Executes commands in Blender context                        │
│  • Returns results                                             │
└────────────────────────────────────────────────────────────────┘
```

## Detailed: Legacy STDIO Mode

```
┌───────────────────────────────────────────────────────────────┐
│                      AI Client (Claude)                        │
└──────────────┬────────────────────────────────────────────────┘
               │
               │ MCP protocol (STDIO)
               │ stdin/stdout
               ▼
┌────────────────────────────────────────────────────────────────┐
│         BlenderMCP Server (server.py)                          │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  FastMCP Server:                                       │   │
│  │  • Receives tool calls via stdin                       │   │
│  │  • Processes with @mcp.tool() decorated functions      │   │
│  │  • Sends results via stdout                            │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  BlenderConnection (direct socket):                    │   │
│  │  • Connects to Blender addon socket                    │   │
│  │  • send_command(type, params)                          │   │
│  │  • Waits for response                                  │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────┬───────────────────────────────────────────────────┘
             │
             │ TCP Socket (localhost:9876)
             │ JSON commands ↓ / responses ↑
             ▼
┌────────────────────────────────────────────────────────────────┐
│              Blender Addon Socket Server                       │
│  (same as Reverse MCP mode)                                    │
└────────────┬───────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────┐
│                      Blender (bpy)                             │
└────────────────────────────────────────────────────────────────┘
```

## Tool Registration Flow (Reverse MCP)

```
BlenderMCP Server Startup
         │
         ▼
   Try to connect
   to MCP-Link?
         │
         ├─YES──────────────────────────────────┐
         │                                       ▼
         │                         Find native messaging manifest
         │                                       │
         │                                       ▼
         │                         Run native binary to get config
         │                                       │
         │                                       ▼
         │                         Extract server URL & auth token
         │                                       │
         │                                       ▼
         │                         Connect to SSE endpoint
         │                                       │
         │                                       ▼
         │                         Register tools with MCP-Link:
         │                         ┌────────────────────────────┐
         │                         │ blender_get_scene_info     │
         │                         │ blender_get_object_info    │
         │                         │ blender_get_viewport_...   │
         │                         │ blender_execute_code       │
         │                         └────────────────────────────┘
         │                                       │
         │                                       ▼
         │                         Start reverse call listener
         │                                       │
         │                                       └─────┐
         │                                             │
         ├─NO (or failed)──────┐                     │
         │                     │                     │
         ▼                     ▼                     ▼
   Use Legacy Mode    Connect direct socket   Use Reverse MCP Mode
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
                               ▼
                    Connect to Blender addon
                               │
                               ▼
                         Server Ready
```

## Message Flow: Tool Call (Reverse MCP)

```
1. AI calls tool
   │
   ▼
2. MCP-Link Server receives call
   │
   ▼
3. MCP-Link forwards via SSE
   │ Event: {reverse: {tool: "blender_get_scene_info", call_id: "...", input: {...}}}
   │
   ▼
4. reverse_bridge receives on SSE stream
   │ • Queued in reverse_queue
   │ • Listener thread picks it up
   │
   ▼
5. reverse_bridge._handle_tool_call()
   │ • Maps tool name to Blender command
   │ • Calls self.send_command()
   │
   ▼
6. Send to Blender addon via TCP socket
   │ JSON: {type: "get_scene_info", params: {}}
   │
   ▼
7. Blender addon processes
   │ • Schedules in main thread
   │ • Executes command
   │ • Returns result
   │
   ▼
8. reverse_bridge receives result
   │ • Formats as MCP response
   │ • {content: [{type: "text", text: "..."}], isError: false}
   │
   ▼
9. POST reply to MCP-Link Server
   │ Method: tools/reply
   │ Params: {call_id: "...", result: {...}}
   │
   ▼
10. MCP-Link forwards to AI
    │
    ▼
11. AI receives result
```

## Connection State Machine

```
                    ┌─────────┐
                    │  Start  │
                    └────┬────┘
                         │
                         ▼
            ┌────────────────────────┐
            │ Check REVERSE_MCP_     │
            │    AVAILABLE flag      │
            └────┬──────────────┬────┘
                 │              │
           Yes   │              │ No
                 ▼              ▼
      ┌──────────────────┐  ┌──────────────────┐
      │ Try Reverse MCP  │  │ Use Legacy Mode  │
      └────┬─────────────┘  └─────────┬────────┘
           │                          │
           ▼                          │
      ┌──────────────────┐           │
      │ MCP-Link found? │           │
      └────┬─────────────┘           │
           │                          │
     Yes   │ No                       │
           │  │                       │
           ▼  ▼                       │
      ┌────┐ ┌─────────────┐         │
      │ ✓  │ │ Fallback to │         │
      │    │ │ Legacy Mode │         │
      └─┬──┘ └──────┬──────┘         │
        │           │                │
        │           └────────┬───────┘
        │                    │
        └────────┬───────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ Connect to      │
        │ Blender Addon   │
        └────┬────────────┘
             │
             ▼
        ┌─────────────────┐
        │  Server Ready   │
        └─────────────────┘
```

## File Organization

```
blender-mcp/
├── src/
│   └── blender_mcp/
│       ├── __init__.py              # Module exports
│       ├── server.py                # Main MCP server + legacy connection
│       ├── reverse_mcp_client.py    # MCP-Link client library
│       └── reverse_bridge.py        # ReverseBlenderConnection
│
├── addon.py                         # Blender addon (unchanged)
├── main.py                          # Entry point (unchanged)
│
├── README.md                        # Main readme (updated)
├── REVERSE_MCP_INTEGRATION.md       # Full integration docs
├── ARCHITECTURE.md                  # This file
├── INTEGRATION_SUMMARY.md           # Technical summary
├── QUICK_START_REVERSE_MCP.md       # Quick start guide
│
└── test_reverse_integration.py      # Integration tests
```

## Key Components

### 1. reverse_mcp_client.py
**Purpose:** Low-level client for MCP-Link Server  
**Key Functions:**
- `find_native_messaging_manifest()`
- `discover_mcp_server_endpoint()`
- `connect_to_sse_endpoint()`
- `send_jsonrpc_request()`
- `send_tool_reply()`

### 2. reverse_bridge.py
**Purpose:** Bridge between MCP-Link and Blender  
**Key Class:** `ReverseBlenderConnection`  
**Key Methods:**
- `connect()` - Sets up everything
- `disconnect()` - Cleans up
- `send_command()` - Same interface as legacy
- `_register_all_tools()` - Registers with MCP-Link
- `_listen_for_reverse_calls()` - Handles incoming calls
- `_handle_tool_call()` - Forwards to Blender

### 3. server.py
**Purpose:** Main MCP server with dual-mode support  
**Key Function:** `get_blender_connection()`  
**Logic:**
```python
if REVERSE_MCP_AVAILABLE:
    try:
        reverse_conn = ReverseBlenderConnection(...)
        if reverse_conn.connect():
            return reverse_conn  # Use Reverse MCP
    except:
        pass  # Fall through
# Use legacy
return BlenderConnection(...)
```

## Threading Model

### Reverse MCP Mode

```
Main Thread
├─ FastMCP server
└─ Tool handlers
    └─ Call get_blender_connection()
        └─ Returns ReverseBlenderConnection
            └─ Has background threads:

Background Thread 1: SSE Reader
├─ Reads SSE stream continuously
├─ Routes reverse calls to reverse_queue
└─ Routes responses to pending_responses[id]

Background Thread 2: Reverse Call Listener
├─ Blocks on reverse_queue.get()
├─ Processes tool calls
├─ Forwards to Blender addon
└─ Sends replies back
```

### Legacy Mode

```
Main Thread
├─ FastMCP server
└─ Tool handlers
    └─ Call get_blender_connection()
        └─ Returns BlenderConnection
            └─ Direct synchronous socket calls
                (No background threads)
```

## Security Considerations

### Reverse MCP Mode
- ✅ Authentication via MCP-Link Server tokens
- ✅ Tool-specific API keys
- ✅ SSL/TLS for SSE connections
- ✅ Callback endpoint validation

### Legacy Mode
- ⚠️ No authentication on Blender socket
- ⚠️ Localhost-only by default
- ⚠️ Should not be exposed to network

## Performance Characteristics

| Aspect | Legacy Mode | Reverse MCP Mode |
|--------|-------------|------------------|
| Latency | Low (direct socket) | Medium (SSE + socket) |
| Throughput | High | Medium |
| Reliability | Medium (STDIO buffering) | High (SSE retry logic) |
| Multi-client | No | Yes |
| Scalability | Single client | Multiple clients |

## Error Handling

Both modes implement robust error handling:

1. **Connection Loss**
   - Reverse MCP: Automatic SSE reconnection
   - Legacy: Socket recreated on next call

2. **Tool Call Failures**
   - Both: Return error in response
   - Reverse MCP: Can retry at MCP-Link level

3. **Blender Crashes**
   - Both: Detect via socket closure
   - Both: Report error to AI

## Future Enhancements

Potential improvements for Reverse MCP:

1. **WebSocket Alternative**: Replace SSE with WebSocket for bidirectional
2. **Tool Hot-Reload**: Register new tools without restart
3. **Multi-Blender**: Support multiple Blender instances
4. **Authentication**: Per-user or per-session tokens
5. **Metrics**: Track tool usage and performance

