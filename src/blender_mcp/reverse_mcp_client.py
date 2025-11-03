"""
Reverse MCP client for connecting to Aura Friday MCP-Link Server.
This module provides the client-side implementation for registering Blender tools
with the MCP-Link server and handling reverse tool calls.
"""

import os
import sys
import json
import platform
import ssl
import uuid
import threading
import time
import queue
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from urllib.parse import urlparse
import http.client
import subprocess
import logging

logger = logging.getLogger(__name__)


def find_native_messaging_manifest() -> Optional[Path]:
  """
  Find the native messaging manifest file for com.aurafriday.shim.
  Searches platform-specific locations where Chrome looks for manifests.
  
  Returns:
    Path to the manifest file, or None if not found
  """
  system_name = platform.system().lower()
  possible_paths = []
  
  if system_name == "windows":
    appdata_local = os.environ.get('LOCALAPPDATA')
    if appdata_local:
      possible_paths.append(Path(appdata_local) / "AuraFriday" / "com.aurafriday.shim.json")
    possible_paths.append(Path.home() / "AppData" / "Local" / "AuraFriday" / "com.aurafriday.shim.json")
    
  elif system_name == "darwin":  # macOS
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
  
  for path in possible_paths:
    if path.exists():
      return path
  
  return None


def read_native_messaging_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
  """Read and parse the native messaging manifest JSON file."""
  try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f"Error reading manifest: {e}")
    return None


def discover_mcp_server_endpoint(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
  """
  Discover the MCP server endpoint by running the native messaging binary.
  The binary outputs JSON config immediately, then waits for input.
  """
  binary_path = manifest.get('path')
  if not binary_path:
    logger.error("No 'path' in manifest")
    return None
  
  binary_path = Path(binary_path)
  if not binary_path.exists():
    logger.error(f"Native binary not found: {binary_path}")
    return None
  
  try:
    creation_flags = 0
    if platform.system() == 'Windows':
      try:
        creation_flags = subprocess.CREATE_NO_WINDOW
      except AttributeError:
        pass
    
    proc = subprocess.Popen(
      [str(binary_path)],
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      stdin=subprocess.PIPE,
      text=False,
      bufsize=0,
      creationflags=creation_flags
    )
    
    json_data = None
    start_time = time.time()
    timeout = 5.0
    accumulated = b""
    
    while time.time() - start_time < timeout:
      try:
        chunk = proc.stdout.read(1)
        if chunk:
          accumulated += chunk
          
          try:
            try:
              text = accumulated.decode('utf-8')
            except UnicodeDecodeError:
              text = accumulated.decode('latin-1', errors='ignore')
            
            json_start = text.find('{')
            if json_start != -1:
              json_str = text[json_start:]
              try:
                json_data = json.loads(json_str)
                break
              except json.JSONDecodeError:
                pass
          except:
            pass
        else:
          time.sleep(0.01)
      except:
        time.sleep(0.01)
    
    if json_data is None:
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
          logger.error("No valid JSON received within timeout")
          return None
    
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
    logger.error(f"Failed to run native binary: {e}")
    return None


def extract_server_url_from_config(config_json: Dict[str, Any]) -> Optional[str]:
  """Extract the MCP server URL from the configuration JSON."""
  try:
    mcp_servers = config_json.get('mcpServers', {})
    if not mcp_servers:
      return None
    
    first_server = next(iter(mcp_servers.values()), None)
    if not first_server:
      return None
    
    return first_server.get('url')
    
  except Exception as e:
    logger.error(f"Failed to extract URL from config: {e}")
    return None


def connect_to_sse_endpoint(server_url: str, auth_header: str) -> Optional[Dict[str, Any]]:
  """
  Connect to the SSE endpoint and extract the message endpoint from the initial event.
  Returns a dictionary with connection info including queues for message routing.
  """
  try:
    parsed_url = urlparse(server_url)
    host = parsed_url.netloc
    path = parsed_url.path
    use_https = parsed_url.scheme == 'https'
    
    if use_https:
      context = ssl.create_default_context()
      context.check_hostname = False
      context.verify_mode = ssl.CERT_NONE
      conn = http.client.HTTPSConnection(host, context=context, timeout=30)
    else:
      conn = http.client.HTTPConnection(host, timeout=30)
    
    headers = {
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Authorization': auth_header,
    }
    
    conn.request('GET', path, headers=headers)
    response = conn.getresponse()
    
    if response.status != 200:
      logger.error(f"SSE connection failed with status {response.status}")
      conn.close()
      return None
    
    session_id = None
    message_endpoint = None
    event_type = None
    
    for _ in range(10):
      line = response.readline().decode('utf-8').strip()
      
      if line.startswith('event:'):
        event_type = line.split(':', 1)[1].strip()
      elif line.startswith('data:'):
        data = line.split(':', 1)[1].strip()
        if event_type == 'endpoint':
          message_endpoint = data
          if 'session_id=' in message_endpoint:
            session_id = message_endpoint.split('session_id=')[1].split('&')[0]
          break
      elif line == '':
        if message_endpoint:
          break
    
    if not message_endpoint or not session_id:
      logger.error("Could not extract message endpoint from SSE stream")
      conn.close()
      return None
    
    reverse_queue = queue.Queue()
    pending_responses = {}
    pending_responses_lock = threading.Lock()
    stop_event = threading.Event()
    
    def sse_reader_thread():
      """Background thread to read SSE messages and route them."""
      try:
        while not stop_event.is_set():
          line = response.readline()
          if not line:
            break
          
          line_str = line.decode('utf-8', errors='ignore').strip()
          
          if line_str.startswith(':'):
            continue
          
          if line_str.startswith('data:'):
            data_str = line_str.split(':', 1)[1].strip()
            try:
              json_data = json.loads(data_str)
              
              if 'reverse' in json_data:
                reverse_queue.put(json_data)
              elif 'id' in json_data:
                request_id = json_data['id']
                with pending_responses_lock:
                  if request_id in pending_responses:
                    pending_responses[request_id].put(json_data)
              
            except json.JSONDecodeError:
              pass
      except Exception as e:
        if not stop_event.is_set():
          logger.error(f"SSE reader thread error: {e}")
    
    reader_thread = threading.Thread(target=sse_reader_thread, daemon=True)
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
      'auth_header': auth_header,
    }
    
  except Exception as e:
    logger.error(f"Failed to connect to SSE endpoint: {e}")
    return None


def send_jsonrpc_request(
  sse_connection: Dict[str, Any],
  method: str,
  params: Dict[str, Any],
  timeout_seconds: float = 10.0
) -> Optional[Dict[str, Any]]:
  """
  Send a JSON-RPC request via POST and wait for the response via SSE.
  """
  try:
    request_id = str(uuid.uuid4())
    
    response_queue = queue.Queue()
    with sse_connection['pending_responses_lock']:
      sse_connection['pending_responses'][request_id] = response_queue
    
    try:
      jsonrpc_request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params
      }
      
      request_body = json.dumps(jsonrpc_request)
      
      parsed_url = urlparse(sse_connection['server_url'])
      host = parsed_url.netloc
      use_https = parsed_url.scheme == 'https'
      
      if use_https:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        post_conn = http.client.HTTPSConnection(host, context=context, timeout=10)
      else:
        post_conn = http.client.HTTPConnection(host, timeout=10)
      
      headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(request_body)),
        'Authorization': sse_connection['auth_header'],
      }
      
      message_path = sse_connection['message_endpoint']
      post_conn.request('POST', message_path, body=request_body, headers=headers)
      post_response = post_conn.getresponse()
      
      if post_response.status != 202:
        logger.error(f"POST request failed with status {post_response.status}")
        post_conn.close()
        return None
      
      post_conn.close()
      
      try:
        response = response_queue.get(timeout=timeout_seconds)
        return response
      except queue.Empty:
        logger.error(f"Timeout waiting for response to {method}")
        return None
      
    finally:
      with sse_connection['pending_responses_lock']:
        sse_connection['pending_responses'].pop(request_id, None)
    
  except Exception as e:
    logger.error(f"Failed to send JSON-RPC request: {e}")
    return None


def send_tool_reply(
  sse_connection: Dict[str, Any],
  call_id: str,
  result: Dict[str, Any]
) -> bool:
  """Send a tools/reply back to the server."""
  try:
    reply_request = {
      "jsonrpc": "2.0",
      "id": call_id,
      "method": "tools/reply",
      "params": {
        "result": result
      }
    }
    
    request_body = json.dumps(reply_request)
    
    parsed_url = urlparse(sse_connection['server_url'])
    host = parsed_url.netloc
    use_https = parsed_url.scheme == 'https'
    
    if use_https:
      context = ssl.create_default_context()
      context.check_hostname = False
      context.verify_mode = ssl.CERT_NONE
      post_conn = http.client.HTTPSConnection(host, context=context, timeout=10)
    else:
      post_conn = http.client.HTTPConnection(host, timeout=10)
    
    headers = {
      'Content-Type': 'application/json',
      'Content-Length': str(len(request_body)),
      'Authorization': sse_connection['auth_header'],
    }
    
    message_path = sse_connection['message_endpoint']
    post_conn.request('POST', message_path, body=request_body, headers=headers)
    post_response = post_conn.getresponse()
    
    if post_response.status != 202:
      logger.error(f"tools/reply POST failed with status {post_response.status}")
      post_conn.close()
      return False
    
    post_conn.close()
    return True
    
  except Exception as e:
    logger.error(f"Failed to send tools/reply: {e}")
    return False

