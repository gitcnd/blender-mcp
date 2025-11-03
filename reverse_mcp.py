#!/usr/bin/env python3
"""
File: reverse_mcp.py
Project: Aura Friday MCP-Link Server - Remote Tool Provider Demo
Component: Registers a demo tool with the MCP server and handles reverse calls
Author: Christopher Nathan Drake (cnd)
Created: 2025-11-03
Last Modified: 2025-11-03 by cnd (Implemented remote tool provider)
SPDX-License-Identifier: Proprietary
Copyright: (c) 2025 Christopher Nathan Drake. All rights reserved.
"signature": "sigɯ",
"signdate": "2025-11-03T09:24:25.574Z",

VERSION: 2025.11.03.001 - Remote Tool Provider Demo

BUILD/RUN INSTRUCTIONS:
  No build required - Python is interpreted
  
  Requirements:
    - Python 3.7+ (tested with 3.11+)
    - Standard library only (no pip install needed)
  
  Run:
    python reverse_mcp.py [--background]
    python reverse_mcp.py --help

HOW TO USE THIS CODE:
  This code is a complete, self-contained reference template for integrating MCP (Model Context Protocol) 
  tool support into other applications like Fusion 360, Blender, Ghidra, and similar products.
  
  HOW THIS WORKS:
  ---------------
  1. You create a new add-on or extension or plugin or similar for the application you want to let an AI control on your behalf. (hereafter addIn)
  2. This template gives your new addIn the facility to discover the correct endpoint where a local controller MCP server is running, and then:
  3. lets your addIn register itself with that server as a new tool, which any AI using that MCP server can then discover and access and use.
  4. and finally, this template processes incoming tool requests form the AI, which you implement in your addIn, and this template sends the results of those tool-calls back to the AI.
  *. The server installer can be found at https://github.com/aurafriday/mcp-link-server/releases
  
  ARCHITECTURE OVERVIEW:
  ----------------------
  1. Native Messaging Discovery: Locates the MCP server by finding the Chrome native messaging manifest
     (com.aurafriday.shim.json) which is installed by the Aura Friday MCP-Link server.
  
  2. Server Configuration: Executes the native messaging binary to get the server's SSE endpoint URL
     and authentication token. The binary is a long-running stdio service, so we terminate it after
     reading the initial JSON config.
  
  3. SSE Connection: Establishes a persistent Server-Sent Events (SSE) connection to receive messages
     from the server. This runs in a background thread and routes incoming messages to the appropriate
     handlers.
  
  4. Dual-Channel Communication:
     - POST requests (via HTTP/HTTPS) to send JSON-RPC commands to the server
     - SSE stream (long-lived GET connection) to receive JSON-RPC responses and reverse tool calls
  
  5. Tool Registration: Uses the server's "remote" tool to register your custom tool with these components:
     - tool_name: Unique identifier for your tool
     - readme: Minimal summary for the AI (when to use this tool)
     - description: Comprehensive documentation for the AI (what it does, how to use it, examples)
     - parameters: JSON Schema defining the tool's input parameters
     - callback_endpoint: Identifier for routing reverse calls back to your client
     - TOOL_API_KEY: Authentication key for your tool
  
  6. Reverse Call Handling: After registration, your tool appears in the server's tool list. When an
     AI agent calls your tool, the server sends a "reverse" message via the SSE stream containing:
     - tool: Your tool's name
     - call_id: Unique ID for this invocation (used to send the reply)
     - input: The parameters passed by the AI
  
  7. Reply Mechanism: Your code processes the request and sends a "tools/reply" message back to the
     server with the call_id and result. The server forwards this to the AI.
  
  INTEGRATION STEPS:
  ------------------
  1. Copy this file to your project
  2. Modify the tool registration section (search for "demo_tool_python"):
     - Change tool_name to your tool's unique identifier
     - Update description and readme to explain your tool's purpose
     - Define your tool's parameters schema
     - Set a unique callback_endpoint and TOOL_API_KEY
  
  3. Replace the handle_echo_request() function with your tool's actual logic:
     - Extract parameters from the input_data
     - Perform your tool's operations (file I/O, API calls, computations, etc.)
     - Return a result dictionary with "content" array and "isError" boolean
  
  4. Run your tool provider script:
     - It will auto-discover the server, register your tool, and listen for calls
     - The tool remains registered as long as the script is running
     - Press Ctrl+C to cleanly shut down
  
  RESULT FORMAT:
  --------------
  All tool results must follow this structure:
  {
    "content": [
      {"type": "text", "text": "Your response text here"},
      {"type": "image", "data": "base64...", "mimeType": "image/png"}  # optional
    ],
    "isError": false  # or true if an error occurred
  }
  
  THREADING MODEL:
  ----------------
  - Main thread: Handles tool registration and processes reverse calls from the queue
  - SSE reader thread: Continuously reads the SSE stream and routes messages to queues
  - Each JSON-RPC request gets its own response queue for thread-safe blocking waits
  
  DEPENDENCIES:
  -------------
  Python 3.7+ with standard library only (no pip install required):
  - json, ssl, http.client: Network communication
  - threading, queue: Concurrent message handling
  - subprocess: Execute native messaging binary
  - pathlib, platform: Cross-platform file system operations
  
  ERROR HANDLING:
  ---------------
  - SSL certificate verification is disabled (self-signed certs are common in local servers)
  - Native binary timeout is 5 seconds (increase if needed)
  - SSE response timeout is 10 seconds per request (configurable)
  - All errors are logged to stderr for debugging

"""

DOCO=""" 
This script demonstrates how to register a tool with the MCP server using the remote tool system.
It acts as a tool provider that:
1. Connects to the MCP server via native messaging discovery
2. Registers a "demo_tool_python" with the server
3. Listens for reverse tool calls from the server
4. Processes "echo" requests and sends back replies
5. Runs continuously until stopped with Ctrl+C

Usage: python reverse_mcp.py [--background]
"""

import os
import sys
import json
import platform
import struct
import ssl
import uuid
import threading
import time
import queue
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse, parse_qs
import http.client


def find_this_native_messaging_manifest_for_this_platform() -> Optional[Path]:
  """
  Find the native messaging manifest file for com.aurafriday.shim.
  Searches platform-specific locations where Chrome looks for manifests.
  
  Returns:
    Path to the manifest file, or None if not found
  """
  system_name = platform.system().lower()
  possible_paths = []
  
  if system_name == "windows":
    # Windows: Check registry first, then fallback to file locations
    # For simplicity, we'll check the file location directly
    appdata_local = os.environ.get('LOCALAPPDATA')
    if appdata_local:
      possible_paths.append(Path(appdata_local) / "AuraFriday" / "com.aurafriday.shim.json")
    possible_paths.append(Path.home() / "AppData" / "Local" / "AuraFriday" / "com.aurafriday.shim.json")
    
  elif system_name == "darwin":  # macOS
    # Check all browser-specific locations
    possible_paths.extend([
      Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / "Library" / "Application Support" / "Chromium" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / "Library" / "Application Support" / "Microsoft Edge" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / "Library" / "Application Support" / "Vivaldi" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
    ])
    
  else:  # Linux
    possible_paths.extend([
      Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / ".config" / "chromium" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / ".config" / "microsoft-edge" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
      Path.home() / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium" / "NativeMessagingHosts" / "com.aurafriday.shim.json",
    ])
  
  # Find the first existing manifest
  for path in possible_paths:
    if path.exists():
      return path
  
  return None


def read_this_native_messaging_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
  """
  Read and parse the native messaging manifest JSON file.
  
  Args:
    manifest_path: Path to the manifest file
    
  Returns:
    Parsed manifest dictionary, or None on error
  """
  try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    print(f"Error reading manifest: {e}", file=sys.stderr)
    return None


def discover_this_mcp_server_endpoint_by_running_native_binary(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
  """
  Discover the MCP server endpoint by running the native messaging binary,
  exactly as Chrome would do it.
  
  The binary is a long-running stdio service that outputs JSON config immediately,
  then waits for input. We read the JSON and terminate the process.
  
  Args:
    manifest: The parsed native messaging manifest
    
  Returns:
    The full JSON response from the native binary, or None on error
  """
  import subprocess
  
  binary_path = manifest.get('path')
  if not binary_path:
    print("ERROR: No 'path' in manifest", file=sys.stderr)
    return None
  
  binary_path = Path(binary_path)
  if not binary_path.exists():
    print(f"ERROR: Native binary not found: {binary_path}", file=sys.stderr)
    return None
  
  print(f"Running native binary: {binary_path}", file=sys.stderr)
  
  try:
    # Determine if we can use CREATE_NO_WINDOW (Python 3.7+, Windows only)
    creation_flags = 0
    if platform.system() == 'Windows':
      try:
        creation_flags = subprocess.CREATE_NO_WINDOW
      except AttributeError:
        # Python < 3.7 doesn't have CREATE_NO_WINDOW
        pass
    
    # Start the binary as a subprocess
    # Note: This is a long-running stdio service, not a one-shot command
    proc = subprocess.Popen(
      [str(binary_path)],
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      stdin=subprocess.PIPE,
      text=False,  # Read as bytes to handle encoding issues
      bufsize=0,   # Unbuffered
      creationflags=creation_flags
    )
    
    # Read output until we get valid JSON
    json_data = None
    
    try:
      start_time = time.time()
      timeout = 5.0
      accumulated = b""
      
      # Read character by character to avoid blocking
      while time.time() - start_time < timeout:
        # Try to read one byte at a time (non-blocking approach)
        try:
          chunk = proc.stdout.read(1)
          if chunk:
            accumulated += chunk
            
            # Try to decode and parse what we have so far
            try:
              # Try UTF-8 first, fall back to latin-1
              try:
                text = accumulated.decode('utf-8')
              except UnicodeDecodeError:
                text = accumulated.decode('latin-1', errors='ignore')
              
              # Look for complete JSON
              json_start = text.find('{')
              if json_start != -1:
                json_str = text[json_start:]
                try:
                  json_data = json.loads(json_str)
                  # Success! We got valid JSON
                  break
                except json.JSONDecodeError:
                  # Not complete yet, keep reading
                  pass
            except:
              # Decoding failed, keep accumulating
              pass
          else:
            # No data available, small sleep to avoid busy-wait
            time.sleep(0.01)
        except:
          # Read error, small sleep and retry
          time.sleep(0.01)
      
      if json_data is None:
        # Try one more time to parse what we have
        try:
          text = accumulated.decode('utf-8', errors='ignore')
        except:
          text = accumulated.decode('latin-1', errors='ignore')
        
        json_start = text.find('{')
        if json_start != -1:
          json_str = text[json_start:]
          try:
            json_data = json.loads(json_str)
          except json.JSONDecodeError:
            print(f"ERROR: No valid JSON received within timeout", file=sys.stderr)
            print(f"Output was: {text[:200]}", file=sys.stderr)
            return None
        else:
          print(f"ERROR: No JSON found in output", file=sys.stderr)
          print(f"Output was: {text[:200]}", file=sys.stderr)
          return None
      
    finally:
      # Terminate the process (it's waiting for stdin)
      try:
        proc.terminate()
        proc.wait(timeout=1.0)
      except:
        try:
          proc.kill()
        except:
          pass
    
    return json_data
    
  except Exception as e:
    print(f"ERROR: Failed to run native binary: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    return None


def extract_this_server_url_from_config(config_json: Dict[str, Any]) -> Optional[str]:
  """
  Extract the MCP server URL from the configuration JSON returned by the native binary.
  
  Args:
    config_json: The JSON configuration from the native binary
    
  Returns:
    The server URL, or None if not found
  """
  try:
    # The structure is: { "mcpServers": { "mypc": { "url": "..." } } }
    mcp_servers = config_json.get('mcpServers', {})
    if not mcp_servers:
      return None
    
    # Get the first server (usually "mypc")
    first_server = next(iter(mcp_servers.values()), None)
    if not first_server:
      return None
    
    return first_server.get('url')
    
  except Exception as e:
    print(f"ERROR: Failed to extract URL from config: {e}", file=sys.stderr)
    return None


def register_demo_tool(sse_connection: Dict[str, Any], server_url: str, auth_header: str) -> bool:
  """
  Register the demo_tool_python with the MCP server using the remote tool system.
  
  Args:
    sse_connection: Active SSE connection
    server_url: Base server URL
    auth_header: Authorization header
    
  Returns:
    True if registration successful, False otherwise
  """
  print("Registering demo_tool_python with MCP server...", file=sys.stderr)
  
  # Build the registration request
  registration_params = {
    "name": "remote",
    "arguments": {
      "input": {
        "operation": "register",
        "tool_name": "demo_tool_python",
        "readme": "Demo tool that echoes messages back.\n- Use this to test the remote tool system and verify bidirectional communication.", # MINIMAL: Tell the AI ONLY when to use this tool
        "description": f"Demo tool (Python implementation) for testing remote tool registration and end-to-end MCP communication. This tool echoes back any message sent to it, which verifies that: (1) tool registration worked correctly, (2) reverse calls from server to client are functioning, (3) the client can successfully reply to tool calls, and (4) the full bidirectional JSON-RPC communication channel is operational. This tool is implemented in {__file__} and serves as a reference template for integrating MCP tool support into other applications like Fusion 360, Blender, Ghidra, and similar products. To use: call this tool with a 'message' parameter containing any text, and it will return 'Echo: <your message>'. Example: {{\"message\": \"test\"}} returns {{\"content\": [{{\"type\": \"text\", \"text\": \"Echo: test\"}}]}}.", # COMPREHENSIVE: Tell the AI everything it needs to know to use this tool (how to call it, what it does, examples, etc.)
        "parameters": {
          "type": "object",
          "properties": {
            "message": {
              "type": "string",
              "description": "The message to echo back"
            }
          },
          "required": ["message"]
        },
        "callback_endpoint": "python-client://demo-tool-callback",
        "TOOL_API_KEY": "python_demo_tool_auth_key_12345"
      }
    }
  }
  
  response = send_this_jsonrpc_request_and_wait_for_this_response(
    sse_connection,
    server_url,
    auth_header,
    "tools/call",
    registration_params
  )
  
  if not response:
    print("ERROR: Failed to register demo_tool", file=sys.stderr)
    return False
  
  # Check if registration was successful
  if 'result' in response:
    result = response['result']
    if isinstance(result, dict):
      content = result.get('content', [])
      if content and len(content) > 0:
        text = content[0].get('text', '')
        if 'Successfully registered tool' in text:
          print(f"[OK] {text}", file=sys.stderr)
          return True
  
  print(f"ERROR: Unexpected registration response: {json.dumps(response, indent=2)}", file=sys.stderr)
  return False


def handle_echo_request(call_data: Dict[str, Any]) -> Dict[str, Any]:
  """
  Handle an echo request from the server.
  
  Args:
    call_data: The tool call data from the reverse message
    
  Returns:
    Result dictionary to send back
  """
  # Extract the message parameter
  arguments = call_data.get('params', {}).get('arguments', {})
  message = arguments.get('message', '(no message provided)')
  
  print(f"[ECHO] Received echo request: {message}", file=sys.stderr)
  
  # Create the response
  result = {
    "content": [{
      "type": "text",
      "text": f"Echo: {message}"
    }],
    "isError": False
  }
  
  return result


def send_tool_reply(sse_connection: Dict[str, Any], server_url: str, auth_header: str, 
                   call_id: str, result: Dict[str, Any]) -> bool:
  """
  Send a tools/reply back to the server.
  
  Args:
    sse_connection: Active SSE connection
    server_url: Base server URL
    auth_header: Authorization header
    call_id: The call_id from the reverse message
    result: The result to send back
    
  Returns:
    True if sent successfully, False otherwise
  """
  try:
    # Build the tools/reply request
    reply_request = {
      "jsonrpc": "2.0",
      "id": call_id,
      "method": "tools/reply",
      "params": {
        "result": result
      }
    }
    
    request_body = json.dumps(reply_request)
    
    # Parse the server URL to get host
    parsed_url = urlparse(server_url)
    host = parsed_url.netloc
    use_https = parsed_url.scheme == 'https'
    
    # Create a new connection for the POST request
    if use_https:
      context = ssl.create_default_context()
      context.check_hostname = False
      context.verify_mode = ssl.CERT_NONE
      post_conn = http.client.HTTPSConnection(host, context=context, timeout=10)
    else:
      post_conn = http.client.HTTPConnection(host, timeout=10)
    
    # Send POST request
    headers = {
      'Content-Type': 'application/json',
      'Content-Length': str(len(request_body)),
      'Authorization': auth_header,
    }
    
    message_path = sse_connection['message_endpoint']
    post_conn.request('POST', message_path, body=request_body, headers=headers)
    post_response = post_conn.getresponse()
    
    # Should get 202 Accepted
    if post_response.status != 202:
      print(f"ERROR: tools/reply POST failed with status {post_response.status}", file=sys.stderr)
      print(f"Response: {post_response.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
      post_conn.close()
      return False
    
    post_conn.close()
    print(f"[OK] Sent tools/reply for call_id {call_id}", file=sys.stderr)
    return True
    
  except Exception as e:
    print(f"ERROR: Failed to send tools/reply: {e}", file=sys.stderr)
    return False


def main_worker(background: bool = False) -> int:
  """
  Worker function that registers demo_tool and listens for reverse calls.
  
  Args:
    background: If True, run in background thread and return immediately
  
  Returns:
    Exit code (0 for success, non-zero for error)
  """
  print("=== Aura Friday Remote Tool Provider Demo ===", file=sys.stderr)
  print(f"PID: {os.getpid()}", file=sys.stderr)
  print("Registering demo_tool with MCP server\n", file=sys.stderr)
  
  # Step 1: Find the native messaging manifest
  print("Step 1: Finding native messaging manifest...", file=sys.stderr)
  manifest_path = find_this_native_messaging_manifest_for_this_platform()
  
  if not manifest_path:
    print("ERROR: Could not find native messaging manifest", file=sys.stderr)
    print("Expected locations (platform-specific):", file=sys.stderr)
    print("  Windows: %LOCALAPPDATA%\\AuraFriday\\com.aurafriday.shim.json", file=sys.stderr)
    print("  macOS: ~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.aurafriday.shim.json", file=sys.stderr)
    print("  Linux: ~/.config/google-chrome/NativeMessagingHosts/com.aurafriday.shim.json", file=sys.stderr)
    return 1
  
  print(f"[OK] Found manifest: {manifest_path}\n", file=sys.stderr)
  
  # Step 2: Read the manifest
  print("Step 2: Reading manifest...", file=sys.stderr)
  manifest = read_this_native_messaging_manifest(manifest_path)
  
  if not manifest:
    print("ERROR: Could not read manifest", file=sys.stderr)
    return 1
  
  print(f"[OK] Manifest loaded\n", file=sys.stderr)
  
  # Step 3: Run the native binary to get the server configuration
  print("Step 3: Discovering MCP server endpoint...", file=sys.stderr)
  config_json = discover_this_mcp_server_endpoint_by_running_native_binary(manifest)
  
  if not config_json:
    print("ERROR: Could not get configuration from native binary", file=sys.stderr)
    print("Is the Aura Friday MCP server running?", file=sys.stderr)
    return 1
  
  # Step 4: Extract the server URL from the configuration
  server_url = extract_this_server_url_from_config(config_json)
  
  if not server_url:
    print("ERROR: Could not extract server URL from configuration", file=sys.stderr)
    return 1
  
  print(f"[OK] Found server at: {server_url}\n", file=sys.stderr)
  
  # Step 5: Extract authorization header from config
  auth_header = None
  mcp_servers = config_json.get('mcpServers', {})
  if mcp_servers:
    first_server = next(iter(mcp_servers.values()), None)
    if first_server and 'headers' in first_server:
      auth_header = first_server['headers'].get('Authorization')
  
  if not auth_header:
    print("ERROR: No authorization header found in configuration", file=sys.stderr)
    return 1
  
  # Step 6: Connect to the SSE endpoint
  print("Step 4: Connecting to SSE endpoint...", file=sys.stderr)
  sse_connection = connect_to_this_sse_endpoint_and_get_this_message_endpoint(server_url, auth_header)
  
  if not sse_connection:
    print("ERROR: Could not connect to SSE endpoint", file=sys.stderr)
    return 1
  
  print(f"[OK] Connected! Session ID: {sse_connection['session_id']}\n", file=sys.stderr)
  
  # Step 7: Check if remote tool exists
  print("Step 5: Checking for remote tool...", file=sys.stderr)
  tools_response = send_this_jsonrpc_request_and_wait_for_this_response(
    sse_connection,
    server_url,
    auth_header,
    "tools/list",
    {}
  )
  
  if not tools_response:
    print("ERROR: Could not get tools list", file=sys.stderr)
    sse_connection['stop_event'].set()
    sse_connection['thread'].join(timeout=2)
    return 1
  
  # Check if remote tool exists
  tools = tools_response.get('result', {}).get('tools', [])
  has_remote = any(tool.get('name') == 'remote' for tool in tools)
  
  if not has_remote:
    print("ERROR: Server does not have 'remote' tool - cannot register demo_tool", file=sys.stderr)
    sse_connection['stop_event'].set()
    sse_connection['thread'].join(timeout=2)
    return 1
  
  print(f"[OK] Remote tool found\n", file=sys.stderr)
  
  # Step 8: Register demo_tool_python
  print("Step 6: Registering demo_tool_python...", file=sys.stderr)
  if not register_demo_tool(sse_connection, server_url, auth_header):
    print("ERROR: Failed to register demo_tool_python", file=sys.stderr)
    sse_connection['stop_event'].set()
    sse_connection['thread'].join(timeout=2)
    return 1
  
  print("\n" + "="*60, file=sys.stderr)
  print("[OK] demo_tool_python registered successfully!", file=sys.stderr)
  print("Listening for reverse tool calls... (Press Ctrl+C to stop)", file=sys.stderr)
  print("="*60 + "\n", file=sys.stderr)
  
  # Step 9: Listen for reverse calls (blocking on queue - no polling!)
  try:
    while True:
      try:
        # Block until a reverse call arrives (timeout allows checking for Ctrl+C)
        msg = sse_connection['reverse_queue'].get(timeout=1.0)
        
        if isinstance(msg, dict) and 'reverse' in msg:
          reverse_data = msg['reverse']
          tool_name = reverse_data.get('tool')
          call_id = reverse_data.get('call_id')
          input_data = reverse_data.get('input')
          
          print(f"\n[CALL] Reverse call received:", file=sys.stderr)
          print(f"       Tool: {tool_name}", file=sys.stderr)
          print(f"       Call ID: {call_id}", file=sys.stderr)
          print(f"       Input: {json.dumps(input_data, indent=2)}", file=sys.stderr)
          
          if tool_name == 'demo_tool_python':
            # Handle the echo request
            result = handle_echo_request(input_data)
            
            # Send the reply back
            send_tool_reply(sse_connection, server_url, auth_header, call_id, result)
          else:
            print(f"[WARN] Unknown tool: {tool_name}", file=sys.stderr)
      
      except queue.Empty:
        # No messages, just loop again (allows Ctrl+C to work)
        continue
      
  except KeyboardInterrupt:
    print("\n\n" + "="*60, file=sys.stderr)
    print("Shutting down...", file=sys.stderr)
    print("="*60, file=sys.stderr)
  finally:
    # Clean up SSE connection
    sse_connection['stop_event'].set()
    sse_connection['thread'].join(timeout=2)
  
  print("Done!", file=sys.stderr)
  return 0


def connect_to_this_sse_endpoint_and_get_this_message_endpoint(server_url: str, auth_header: str) -> Optional[Dict[str, Any]]:
  """
  Connect to the SSE endpoint and extract the message endpoint from the initial event.
  
  This implements the SSE handshake:
  1. GET /sse with Authorization header
  2. Receive "event: endpoint" with the session-specific message endpoint
  3. Keep the connection open for receiving responses
  
  Args:
    server_url: The SSE endpoint URL (e.g., "https://127-0-0-1.local.aurafriday.com:31173/sse")
    auth_header: The Authorization header value (e.g., "Bearer xxx")
    
  Returns:
    Dictionary with connection info, or None on error:
      {
        'session_id': str,
        'message_endpoint': str,
        'connection': http.client.HTTPSConnection or HTTPConnection,
        'response': http.client.HTTPResponse,
        'thread': threading.Thread (SSE reader thread),
        'stop_event': threading.Event (to stop the reader thread),
        'messages': queue-like list (received SSE messages)
      }
  """
  try:
    parsed_url = urlparse(server_url)
    host = parsed_url.netloc
    path = parsed_url.path
    use_https = parsed_url.scheme == 'https'
    
    # Create connection
    if use_https:
      # Create SSL context that doesn't verify certificates (for self-signed certs)
      context = ssl.create_default_context()
      context.check_hostname = False
      context.verify_mode = ssl.CERT_NONE
      conn = http.client.HTTPSConnection(host, context=context, timeout=30)
    else:
      conn = http.client.HTTPConnection(host, timeout=30)
    
    # Send GET request to SSE endpoint
    headers = {
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Authorization': auth_header,
    }
    
    conn.request('GET', path, headers=headers)
    response = conn.getresponse()
    
    if response.status != 200:
      print(f"ERROR: SSE connection failed with status {response.status}", file=sys.stderr)
      print(f"Response: {response.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
      conn.close()
      return None
    
    # Read the initial SSE event to get the message endpoint
    # Format: "event: endpoint\ndata: /messages/?session_id=xxx\n\n"
    session_id = None
    message_endpoint = None
    
    # Read line by line until we get the endpoint
    event_type = None
    for _ in range(10):  # Read up to 10 lines
      line = response.readline().decode('utf-8').strip()
      
      if line.startswith('event:'):
        event_type = line.split(':', 1)[1].strip()
      elif line.startswith('data:'):
        data = line.split(':', 1)[1].strip()
        if event_type == 'endpoint':
          message_endpoint = data
          # Extract session_id from the endpoint
          # Format: /messages/?session_id=xxx
          if 'session_id=' in message_endpoint:
            session_id = message_endpoint.split('session_id=')[1].split('&')[0]
          break
      elif line == '':
        # Empty line marks end of event
        if message_endpoint:
          break
    
    if not message_endpoint or not session_id:
      print("ERROR: Could not extract message endpoint from SSE stream", file=sys.stderr)
      conn.close()
      return None
    
    # Set up message routing queues
    reverse_queue = queue.Queue()  # For reverse tool calls
    pending_responses = {}  # {request_id: queue.Queue()} for waiting responses
    pending_responses_lock = threading.Lock()
    stop_event = threading.Event()
    
    def sse_reader_thread_function():
      """Background thread to read SSE messages and route them."""
      try:
        while not stop_event.is_set():
          line = response.readline()
          if not line:
            # Connection closed
            break
          
          line_str = line.decode('utf-8', errors='ignore').strip()
          
          # Skip ping messages
          if line_str.startswith(':'):
            continue
          
          if line_str.startswith('data:'):
            data_str = line_str.split(':', 1)[1].strip()
            try:
              # Try to parse as JSON
              json_data = json.loads(data_str)
              
              # Route message based on type
              if 'reverse' in json_data:
                # This is a reverse tool call - route to reverse queue
                reverse_queue.put(json_data)
              elif 'id' in json_data:
                # This is a response to a request - route to pending response queue
                request_id = json_data['id']
                with pending_responses_lock:
                  if request_id in pending_responses:
                    pending_responses[request_id].put(json_data)
                  # If no one is waiting for this response, just drop it
              
            except json.JSONDecodeError:
              # Not JSON, ignore
              pass
      except Exception as e:
        if not stop_event.is_set():
          print(f"\nSSE reader thread error: {e}", file=sys.stderr)
    
    reader_thread = threading.Thread(target=sse_reader_thread_function, daemon=True)
    reader_thread.start()
    
    return {
      'session_id': session_id,
      'message_endpoint': message_endpoint,
      'connection': conn,
      'response': response,
      'thread': reader_thread,
      'stop_event': stop_event,
      'reverse_queue': reverse_queue,
      'pending_responses': pending_responses,
      'pending_responses_lock': pending_responses_lock,
      'server_url': server_url,
    }
    
  except Exception as e:
    print(f"ERROR: Failed to connect to SSE endpoint: {e}", file=sys.stderr)
    return None


def send_this_jsonrpc_request_and_wait_for_this_response(
  sse_connection: Dict[str, Any],
  server_url: str,
  auth_header: str,
  method: str,
  params: Dict[str, Any],
  timeout_seconds: float = 10.0
) -> Optional[Dict[str, Any]]:
  """
  Send a JSON-RPC request via POST and wait for the response via SSE.
  
  This implements the MCP request/response pattern:
  1. POST to /messages/?session_id=xxx with JSON-RPC request
  2. Server responds with 202 Accepted
  3. Actual response comes via the SSE stream (routed by request ID)
  
  Args:
    sse_connection: Connection info from connect_to_this_sse_endpoint_and_get_this_message_endpoint()
    server_url: Base server URL
    auth_header: Authorization header value
    method: JSON-RPC method name (e.g., "tools/list")
    params: JSON-RPC params dictionary
    timeout_seconds: How long to wait for a response
    
  Returns:
    JSON-RPC response dictionary, or None on error/timeout
  """
  try:
    # Generate a unique request ID
    request_id = str(uuid.uuid4())
    
    # Create a queue for this request's response
    response_queue = queue.Queue()
    with sse_connection['pending_responses_lock']:
      sse_connection['pending_responses'][request_id] = response_queue
    
    try:
      # Build JSON-RPC request
      jsonrpc_request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params
      }
      
      request_body = json.dumps(jsonrpc_request)
      
      # Parse the server URL to get host and build full message endpoint URL
      parsed_url = urlparse(server_url)
      host = parsed_url.netloc
      use_https = parsed_url.scheme == 'https'
      
      # Create a new connection for the POST request
      if use_https:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        post_conn = http.client.HTTPSConnection(host, context=context, timeout=10)
      else:
        post_conn = http.client.HTTPConnection(host, timeout=10)
      
      # Send POST request
      headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(request_body)),
        'Authorization': auth_header,
      }
      
      message_path = sse_connection['message_endpoint']
      post_conn.request('POST', message_path, body=request_body, headers=headers)
      post_response = post_conn.getresponse()
      
      # Should get 202 Accepted
      if post_response.status != 202:
        print(f"ERROR: POST request failed with status {post_response.status}", file=sys.stderr)
        print(f"Response: {post_response.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
        post_conn.close()
        return None
      
      post_conn.close()
      
      # Wait for the response to arrive via SSE (blocking on queue)
      try:
        response = response_queue.get(timeout=timeout_seconds)
        return response
      except queue.Empty:
        print(f"ERROR: Timeout waiting for response to {method}", file=sys.stderr)
        return None
      
    finally:
      # Clean up the pending response queue
      with sse_connection['pending_responses_lock']:
        sse_connection['pending_responses'].pop(request_id, None)
    
  except Exception as e:
    print(f"ERROR: Failed to send JSON-RPC request: {e}", file=sys.stderr)
    return None


def main() -> int:
  """
  Main entry point with argument parsing.
  
  Returns:
    Exit code (0 for success, non-zero for error)
  """
  parser = argparse.ArgumentParser(
    description='Aura Friday Remote Tool Provider - Registers demo_tool_python with MCP server',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=DOCO
  )
  parser.add_argument(
    '--background',
    action='store_true',
    help='Run in background thread and return immediately (for testing/automation)'
  )
  
  args = parser.parse_args()
  
  if args.background:
    # Run in background thread
    print(f"Starting in background mode (PID: {os.getpid()})...", file=sys.stderr)
    worker_thread = threading.Thread(target=main_worker, args=(True,), daemon=False)
    worker_thread.start()
    
    # Wait a moment for initialization
    time.sleep(2)
    
    print(f"[OK] Background worker started (PID: {os.getpid()})", file=sys.stderr)
    print(f"  Use 'kill {os.getpid()}' to stop", file=sys.stderr)
    
    # Keep main thread alive
    try:
      worker_thread.join()
    except KeyboardInterrupt:
      print("\nShutting down background worker...", file=sys.stderr)
    
    return 0
  else:
    # Run in foreground (blocking)
    return main_worker(background=False)


if __name__ == "__main__":
  sys.exit(main())
