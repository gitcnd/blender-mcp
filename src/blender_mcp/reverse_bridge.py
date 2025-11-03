"""
Bridge between Reverse MCP (Aura Friday MCP-Link Server) and Blender addon.
This module provides ReverseBlenderConnection that registers Blender tools
with the MCP-Link server and forwards calls to the Blender addon.
"""

import json
import socket
import logging
import threading
import queue
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

from . import reverse_mcp_client as rmc

logger = logging.getLogger(__name__)

# Tool API key for authentication
BLENDER_TOOL_API_KEY = "blender_mcp_reverse_auth_key_v1"


@dataclass
class ReverseBlenderConnection:
  """
  Connection to Blender via Reverse MCP (Aura Friday MCP-Link Server).
  This class bridges between the MCP-Link server and the Blender addon socket.
  """
  host: str
  port: int
  sse_connection: Dict[str, Any] = None
  blender_sock: socket.socket = None
  server_url: str = None
  auth_header: str = None
  listener_thread: threading.Thread = None
  stop_event: threading.Event = None
  
  def connect(self) -> bool:
    """Connect to both the MCP-Link server and the Blender addon."""
    try:
      # Step 1: Find native messaging manifest
      logger.info("Looking for Aura Friday MCP-Link server...")
      manifest_path = rmc.find_native_messaging_manifest()
      if not manifest_path:
        logger.info("Aura Friday MCP-Link server not found")
        return False
      
      logger.info(f"Found manifest at: {manifest_path}")
      
      # Step 2: Read manifest
      manifest = rmc.read_native_messaging_manifest(manifest_path)
      if not manifest:
        logger.error("Could not read manifest")
        return False
      
      # Step 3: Discover server endpoint
      logger.info("Discovering MCP-Link server endpoint...")
      config_json = rmc.discover_mcp_server_endpoint(manifest)
      if not config_json:
        logger.info("Could not discover MCP-Link server endpoint")
        return False
      
      # Step 4: Extract server URL
      self.server_url = rmc.extract_server_url_from_config(config_json)
      if not self.server_url:
        logger.error("Could not extract server URL")
        return False
      
      logger.info(f"Found MCP-Link server at: {self.server_url}")
      
      # Step 5: Extract authorization header
      mcp_servers = config_json.get('mcpServers', {})
      if mcp_servers:
        first_server = next(iter(mcp_servers.values()), None)
        if first_server and 'headers' in first_server:
          self.auth_header = first_server['headers'].get('Authorization')
      
      if not self.auth_header:
        logger.error("No authorization header found")
        return False
      
      # Step 6: Connect to SSE endpoint
      logger.info("Connecting to SSE endpoint...")
      self.sse_connection = rmc.connect_to_sse_endpoint(self.server_url, self.auth_header)
      if not self.sse_connection:
        logger.error("Could not connect to SSE endpoint")
        return False
      
      logger.info(f"Connected to SSE! Session ID: {self.sse_connection['session_id']}")
      
      # Step 7: Check if remote tool exists
      logger.info("Checking for remote tool...")
      tools_response = rmc.send_jsonrpc_request(
        self.sse_connection,
        "tools/list",
        {}
      )
      
      if not tools_response:
        logger.error("Could not get tools list")
        self.disconnect()
        return False
      
      tools = tools_response.get('result', {}).get('tools', [])
      has_remote = any(tool.get('name') == 'remote' for tool in tools)
      
      if not has_remote:
        logger.error("Server does not have 'remote' tool")
        self.disconnect()
        return False
      
      logger.info("Remote tool found!")
      
      # Step 8: Connect to Blender addon socket
      logger.info(f"Connecting to Blender addon at {self.host}:{self.port}...")
      self.blender_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      try:
        self.blender_sock.connect((self.host, self.port))
        logger.info("Connected to Blender addon!")
      except Exception as e:
        logger.error(f"Could not connect to Blender addon: {e}")
        self.disconnect()
        return False
      
      # Step 9: Register Blender tools with MCP-Link server
      logger.info("Registering Blender tools...")
      if not self._register_all_tools():
        logger.error("Failed to register Blender tools")
        self.disconnect()
        return False
      
      # Step 10: Start listener thread for reverse calls
      self.stop_event = threading.Event()
      self.listener_thread = threading.Thread(target=self._listen_for_reverse_calls, daemon=True)
      self.listener_thread.start()
      
      logger.info("Reverse MCP bridge established successfully!")
      return True
      
    except Exception as e:
      logger.error(f"Error setting up Reverse MCP connection: {e}")
      self.disconnect()
      return False
  
  def disconnect(self):
    """Disconnect from both MCP-Link server and Blender addon."""
    if self.stop_event:
      self.stop_event.set()
    
    if self.listener_thread and self.listener_thread.is_alive():
      self.listener_thread.join(timeout=2)
    
    if self.sse_connection:
      try:
        self.sse_connection['stop_event'].set()
        self.sse_connection['thread'].join(timeout=2)
        self.sse_connection['connection'].close()
      except:
        pass
      self.sse_connection = None
    
    if self.blender_sock:
      try:
        self.blender_sock.close()
      except:
        pass
      self.blender_sock = None
    
    logger.info("Reverse MCP bridge disconnected")
  
  def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Send a command to Blender addon and return the response.
    This method maintains the same interface as the legacy BlenderConnection.
    """
    if not self.blender_sock:
      raise ConnectionError("Not connected to Blender")
    
    command = {
      "type": command_type,
      "params": params or {}
    }
    
    try:
      logger.debug(f"Sending command to Blender: {command_type}")
      
      # Send command to Blender addon
      self.blender_sock.sendall(json.dumps(command).encode('utf-8'))
      
      # Set timeout for receiving
      self.blender_sock.settimeout(15.0)
      
      # Receive response
      response_data = self._receive_full_response(self.blender_sock)
      response = json.loads(response_data.decode('utf-8'))
      
      if response.get("status") == "error":
        logger.error(f"Blender error: {response.get('message')}")
        raise Exception(response.get("message", "Unknown error from Blender"))
      
      return response.get("result", {})
      
    except socket.timeout:
      logger.error("Timeout waiting for Blender response")
      self.blender_sock = None
      raise Exception("Timeout waiting for Blender response")
    except Exception as e:
      logger.error(f"Error communicating with Blender: {e}")
      self.blender_sock = None
      raise Exception(f"Communication error with Blender: {e}")
  
  def _receive_full_response(self, sock, buffer_size=8192):
    """Receive the complete response, potentially in multiple chunks."""
    chunks = []
    sock.settimeout(15.0)
    
    try:
      while True:
        try:
          chunk = sock.recv(buffer_size)
          if not chunk:
            if not chunks:
              raise Exception("Connection closed before receiving any data")
            break
          
          chunks.append(chunk)
          
          # Check if we've received a complete JSON object
          try:
            data = b''.join(chunks)
            json.loads(data.decode('utf-8'))
            return data
          except json.JSONDecodeError:
            continue
        except socket.timeout:
          break
    except Exception as e:
      logger.error(f"Error during receive: {e}")
      raise
    
    if chunks:
      data = b''.join(chunks)
      try:
        json.loads(data.decode('utf-8'))
        return data
      except json.JSONDecodeError:
        raise Exception("Incomplete JSON response received")
    else:
      raise Exception("No data received")
  
  def _register_all_tools(self) -> bool:
    """Register all Blender tools with the MCP-Link server."""
    tools_to_register = [
      {
        "tool_name": "blender_get_scene_info",
        "readme": "Get detailed information about the current Blender scene.\n- Use this to understand what's in the scene before making changes.",
        "description": "Retrieves comprehensive information about the current Blender scene including object count, object names, types, locations, and materials. This tool should be called before performing any scene manipulation to understand the current state.",
        "parameters": {
          "type": "object",
          "properties": {},
          "required": []
        }
      },
      {
        "tool_name": "blender_get_object_info",
        "readme": "Get detailed information about a specific object.\n- Use this to inspect object properties, transforms, and materials.",
        "description": "Retrieves detailed information about a specific object in the Blender scene including its type, location, rotation, scale, visibility, materials, and mesh data (vertices, edges, polygons).",
        "parameters": {
          "type": "object",
          "properties": {
            "object_name": {
              "type": "string",
              "description": "The name of the object to get information about"
            }
          },
          "required": ["object_name"]
        }
      },
      {
        "tool_name": "blender_get_viewport_screenshot",
        "readme": "Capture a screenshot of the Blender 3D viewport.\n- Use this to see what the scene looks like visually.",
        "description": "Captures a screenshot of the current Blender 3D viewport and returns it as an image. The screenshot can be resized to a maximum dimension.",
        "parameters": {
          "type": "object",
          "properties": {
            "max_size": {
              "type": "integer",
              "description": "Maximum size in pixels for the largest dimension (default: 800)",
              "default": 800
            }
          },
          "required": []
        }
      },
      {
        "tool_name": "blender_execute_code",
        "readme": "Execute Python code in Blender.\n- Use this for complex operations not covered by other tools.",
        "description": "Executes arbitrary Python code in Blender's context. Has access to bpy module. Returns captured stdout. Use this for complex operations, creating objects, modifying materials, etc.",
        "parameters": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string",
              "description": "The Python code to execute in Blender"
            }
          },
          "required": ["code"]
        }
      }
    ]
    
    # Register each tool
    for tool_spec in tools_to_register:
      logger.info(f"Registering tool: {tool_spec['tool_name']}")
      
      registration_params = {
        "name": "remote",
        "arguments": {
          "input": {
            "operation": "register",
            "tool_name": tool_spec['tool_name'],
            "readme": tool_spec['readme'],
            "description": tool_spec['description'],
            "parameters": tool_spec['parameters'],
            "callback_endpoint": f"blender-mcp://reverse-bridge/{tool_spec['tool_name']}",
            "TOOL_API_KEY": BLENDER_TOOL_API_KEY
          }
        }
      }
      
      response = rmc.send_jsonrpc_request(
        self.sse_connection,
        "tools/call",
        registration_params
      )
      
      if not response:
        logger.error(f"Failed to register tool: {tool_spec['tool_name']}")
        return False
      
      # Check if registration was successful
      if 'result' in response:
        result = response['result']
        if isinstance(result, dict):
          content = result.get('content', [])
          if content and len(content) > 0:
            text = content[0].get('text', '')
            if 'Successfully registered tool' in text:
              logger.info(f"Registered: {tool_spec['tool_name']}")
              continue
      
      logger.error(f"Unexpected registration response for {tool_spec['tool_name']}")
      return False
    
    logger.info("All Blender tools registered successfully!")
    return True
  
  def _listen_for_reverse_calls(self):
    """Listen for reverse tool calls from the MCP-Link server and forward to Blender."""
    logger.info("Starting reverse call listener...")
    
    while not self.stop_event.is_set():
      try:
        msg = self.sse_connection['reverse_queue'].get(timeout=1.0)
        
        if isinstance(msg, dict) and 'reverse' in msg:
          reverse_data = msg['reverse']
          tool_name = reverse_data.get('tool')
          call_id = reverse_data.get('call_id')
          input_data = reverse_data.get('input')
          
          logger.info(f"Reverse call received: {tool_name}")
          
          # Handle the tool call
          result = self._handle_tool_call(tool_name, input_data)
          
          # Send reply back to MCP-Link server
          rmc.send_tool_reply(self.sse_connection, call_id, result)
      
      except queue.Empty:
        continue
      except Exception as e:
        logger.error(f"Error in reverse call listener: {e}")
        if self.stop_event.is_set():
          break
    
    logger.info("Reverse call listener stopped")
  
  def _handle_tool_call(self, tool_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle a reverse tool call by forwarding to Blender addon."""
    try:
      # Map tool names to Blender command types
      tool_mapping = {
        "blender_get_scene_info": ("get_scene_info", {}),
        "blender_get_object_info": ("get_object_info", {"name": input_data.get("params", {}).get("arguments", {}).get("object_name")}),
        "blender_get_viewport_screenshot": ("get_viewport_screenshot", {
          "max_size": input_data.get("params", {}).get("arguments", {}).get("max_size", 800),
          "filepath": f"/tmp/blender_screenshot_reverse_{id(self)}.png",
          "format": "png"
        }),
        "blender_execute_code": ("execute_code", {"code": input_data.get("params", {}).get("arguments", {}).get("code")}),
      }
      
      if tool_name not in tool_mapping:
        return {
          "content": [{
            "type": "text",
            "text": f"Unknown tool: {tool_name}"
          }],
          "isError": True
        }
      
      command_type, params = tool_mapping[tool_name]
      
      # Send command to Blender
      blender_result = self.send_command(command_type, params)
      
      # Format result for MCP-Link server
      if tool_name == "blender_get_viewport_screenshot":
        # Handle screenshot specially - read file and encode as base64
        import base64
        filepath = params.get("filepath")
        try:
          with open(filepath, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
          
          return {
            "content": [{
              "type": "image",
              "data": image_data,
              "mimeType": "image/png"
            }],
            "isError": False
          }
        except Exception as e:
          return {
            "content": [{
              "type": "text",
              "text": f"Error reading screenshot: {str(e)}"
            }],
            "isError": True
          }
      else:
        # Return text result
        return {
          "content": [{
            "type": "text",
            "text": json.dumps(blender_result, indent=2)
          }],
          "isError": False
        }
      
    except Exception as e:
      logger.error(f"Error handling tool call {tool_name}: {e}")
      return {
        "content": [{
          "type": "text",
          "text": f"Error: {str(e)}"
        }],
        "isError": True
      }

