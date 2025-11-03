# Quick Start: Using BlenderMCP with Reverse MCP

## TL;DR

This BlenderMCP fork automatically detects and uses the **Aura Friday MCP-Link Server** if available, otherwise works normally. No configuration needed.

## What You See

### With MCP-Link Server (Enhanced Mode)

When you start BlenderMCP, look for this in the logs:

```
============================================================
✓ CONNECTION MODE: Reverse MCP (Advanced)
  Connected via Aura Friday MCP-Link Server
  Tools are registered and accessible via MCP-Link
============================================================
```

**Benefits:**
- Better reliability
- Support for multiple AI clients
- Enhanced features

### Without MCP-Link Server (Standard Mode)

```
============================================================
CONNECTION MODE: Legacy STDIO
  Direct socket connection to Blender
============================================================
```

**This is fine!** Everything works exactly as the original BlenderMCP.

## Installation Options

### Option 1: Standard (Legacy Mode)

Just use the original installation instructions from the main README. Everything works.

### Option 2: Enhanced (Reverse MCP Mode)

1. **Install Aura Friday MCP-Link Server**
   ```
   Download from: https://github.com/aurafriday/mcp-link-server/releases
   ```

2. **Install BlenderMCP** (same as always)
   ```bash
   # Follow the main README
   ```

3. **Start Blender and the addon** (same as always)

4. **Start BlenderMCP** (same as always)
   ```bash
   uvx blender-mcp
   ```

The system automatically detects and uses MCP-Link Server!

## Verification

Check your terminal logs when BlenderMCP starts:

- Look for `"Attempting to connect via Reverse MCP"`
- If successful: `"✓ Successfully connected via Reverse MCP!"`
- If not: `"Using legacy direct socket connection"` (this is fine!)

## Switching Between Modes

### To Use Reverse MCP
- Install the MCP-Link Server
- Restart BlenderMCP

### To Use Legacy Mode
- Don't install MCP-Link Server, or
- Stop the MCP-Link Server, or
- Rename the manifest file temporarily

The system automatically adapts!

## Troubleshooting

### "Reverse MCP not activating"

**Check:**
1. Is MCP-Link Server installed and running?
2. Can you see the manifest file?
   - Windows: `%LOCALAPPDATA%\AuraFriday\com.aurafriday.shim.json`
   - Mac: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.aurafriday.shim.json`
   - Linux: `~/.config/google-chrome/NativeMessagingHosts/com.aurafriday.shim.json`

**If not found:** System automatically uses legacy mode (this is fine!)

### "Connection issues"

Both modes require:
- ✅ Blender running
- ✅ Blender addon enabled
- ✅ Addon server started ("Connect to MCP server" button clicked)

Check these first!

## FAQ

### Do I need MCP-Link Server?

**No!** It's optional. BlenderMCP works perfectly without it.

### What's the difference?

| Feature | Legacy Mode | Reverse MCP |
|---------|-------------|-------------|
| Basic functionality | ✅ | ✅ |
| Multiple AI clients | ❌ | ✅ |
| Enhanced reliability | ❌ | ✅ |
| Advanced features | ❌ | ✅ |
| Setup complexity | Simple | Medium |

### Will this break my setup?

**No!** If you don't install MCP-Link Server, everything works exactly as before.

### How do I know which mode I'm using?

Look at the startup logs in your terminal. There's a clear banner showing the mode.

### Can I switch between modes?

**Yes!** Just install/uninstall MCP-Link Server and restart BlenderMCP. No configuration changes needed.

## More Information

- Full documentation: [REVERSE_MCP_INTEGRATION.md](REVERSE_MCP_INTEGRATION.md)
- Technical details: [INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md)
- Original README: [README.md](README.md)

## That's It!

The system "just works" - it uses the advanced mode if available, otherwise the standard mode. No decisions needed!

