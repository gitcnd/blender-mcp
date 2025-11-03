#!/usr/bin/env python3
"""
Test script for validating Reverse MCP integration.
This script tests the logic without requiring actual connections.
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_module_imports():
  """Test that all modules can be imported correctly."""
  logger.info("Testing module imports...")
  
  try:
    from blender_mcp import reverse_mcp_client
    logger.info("✓ reverse_mcp_client imported successfully")
  except ImportError as e:
    logger.error(f"✗ Failed to import reverse_mcp_client: {e}")
    return False
  
  try:
    from blender_mcp import reverse_bridge
    logger.info("✓ reverse_bridge imported successfully")
  except ImportError as e:
    logger.error(f"✗ Failed to import reverse_bridge: {e}")
    return False
  
  try:
    from blender_mcp import server
    logger.info("✓ server module imported successfully")
  except ImportError as e:
    logger.error(f"✗ Failed to import server: {e}")
    return False
  
  return True


def test_reverse_mcp_detection():
  """Test that Reverse MCP detection logic works."""
  logger.info("\nTesting Reverse MCP detection...")
  
  try:
    from blender_mcp.server import REVERSE_MCP_AVAILABLE
    
    if REVERSE_MCP_AVAILABLE:
      logger.info("✓ Reverse MCP is available")
      return True
    else:
      logger.warning("⚠ Reverse MCP not available (this is OK if modules aren't installed)")
      return True
      
  except ImportError as e:
    logger.error(f"✗ Failed to check Reverse MCP availability: {e}")
    return False


def test_connection_classes():
  """Test that connection classes are properly defined."""
  logger.info("\nTesting connection classes...")
  
  try:
    from blender_mcp.server import BlenderConnection
    logger.info("✓ BlenderConnection class available")
    
    # Check if it has the expected methods
    expected_methods = ['connect', 'disconnect', 'send_command']
    for method in expected_methods:
      if not hasattr(BlenderConnection, method):
        logger.error(f"✗ BlenderConnection missing method: {method}")
        return False
    logger.info("✓ BlenderConnection has all expected methods")
    
  except ImportError as e:
    logger.error(f"✗ Failed to import BlenderConnection: {e}")
    return False
  
  try:
    from blender_mcp.reverse_bridge import ReverseBlenderConnection
    logger.info("✓ ReverseBlenderConnection class available")
    
    # Check if it has the expected methods (same interface as BlenderConnection)
    for method in expected_methods:
      if not hasattr(ReverseBlenderConnection, method):
        logger.error(f"✗ ReverseBlenderConnection missing method: {method}")
        return False
    logger.info("✓ ReverseBlenderConnection has all expected methods")
    
  except ImportError as e:
    logger.error(f"✗ Failed to import ReverseBlenderConnection: {e}")
    return False
  
  return True


def test_fallback_logic():
  """Test that fallback logic is present in the code."""
  logger.info("\nTesting fallback logic...")
  
  try:
    from blender_mcp import server
    
    # Check that USE_REVERSE_MCP flag exists
    if not hasattr(server, 'USE_REVERSE_MCP'):
      logger.error("✗ USE_REVERSE_MCP flag not found")
      return False
    logger.info("✓ USE_REVERSE_MCP flag exists")
    
    # Check that get_blender_connection exists
    if not hasattr(server, 'get_blender_connection'):
      logger.error("✗ get_blender_connection function not found")
      return False
    logger.info("✓ get_blender_connection function exists")
    
    # Read the source to verify fallback logic
    import inspect
    source = inspect.getsource(server.get_blender_connection)
    
    if 'REVERSE_MCP_AVAILABLE' not in source:
      logger.error("✗ Fallback logic not checking REVERSE_MCP_AVAILABLE")
      return False
    logger.info("✓ Fallback logic checks REVERSE_MCP_AVAILABLE")
    
    if 'ReverseBlenderConnection' not in source:
      logger.error("✗ Fallback logic doesn't try ReverseBlenderConnection")
      return False
    logger.info("✓ Fallback logic tries ReverseBlenderConnection")
    
    if 'BlenderConnection' not in source:
      logger.error("✗ Fallback logic doesn't fall back to BlenderConnection")
      return False
    logger.info("✓ Fallback logic falls back to BlenderConnection")
    
    return True
    
  except Exception as e:
    logger.error(f"✗ Error testing fallback logic: {e}")
    return False


def test_tool_registration_structure():
  """Test that tool registration structure is correct."""
  logger.info("\nTesting tool registration structure...")
  
  try:
    from blender_mcp.reverse_bridge import ReverseBlenderConnection
    import inspect
    
    # Get the _register_all_tools method source
    source = inspect.getsource(ReverseBlenderConnection._register_all_tools)
    
    # Check for expected tools
    expected_tools = [
      'blender_get_scene_info',
      'blender_get_object_info', 
      'blender_get_viewport_screenshot',
      'blender_execute_code'
    ]
    
    for tool in expected_tools:
      if tool not in source:
        logger.error(f"✗ Tool not found in registration: {tool}")
        return False
    
    logger.info(f"✓ All {len(expected_tools)} expected tools found in registration")
    
    # Check for required fields in registration
    required_fields = ['tool_name', 'readme', 'description', 'parameters', 'callback_endpoint', 'TOOL_API_KEY']
    for field in required_fields:
      if field not in source:
        logger.error(f"✗ Required field missing from registration: {field}")
        return False
    
    logger.info(f"✓ All required registration fields present")
    
    return True
    
  except Exception as e:
    logger.error(f"✗ Error testing tool registration: {e}")
    return False


def test_interface_compatibility():
  """Test that both connection classes have compatible interfaces."""
  logger.info("\nTesting interface compatibility...")
  
  try:
    from blender_mcp.server import BlenderConnection
    from blender_mcp.reverse_bridge import ReverseBlenderConnection
    
    # Get method signatures
    legacy_methods = set(dir(BlenderConnection))
    reverse_methods = set(dir(ReverseBlenderConnection))
    
    # Check that key methods exist in both
    key_methods = {'connect', 'disconnect', 'send_command'}
    
    if not key_methods.issubset(legacy_methods):
      logger.error(f"✗ BlenderConnection missing key methods: {key_methods - legacy_methods}")
      return False
    
    if not key_methods.issubset(reverse_methods):
      logger.error(f"✗ ReverseBlenderConnection missing key methods: {key_methods - reverse_methods}")
      return False
    
    logger.info("✓ Both connection classes have compatible interfaces")
    return True
    
  except Exception as e:
    logger.error(f"✗ Error testing interface compatibility: {e}")
    return False


def main():
  """Run all tests."""
  logger.info("="*60)
  logger.info("Reverse MCP Integration Test Suite")
  logger.info("="*60)
  
  tests = [
    ("Module Imports", test_module_imports),
    ("Reverse MCP Detection", test_reverse_mcp_detection),
    ("Connection Classes", test_connection_classes),
    ("Fallback Logic", test_fallback_logic),
    ("Tool Registration Structure", test_tool_registration_structure),
    ("Interface Compatibility", test_interface_compatibility),
  ]
  
  results = []
  for name, test_func in tests:
    try:
      result = test_func()
      results.append((name, result))
    except Exception as e:
      logger.error(f"Test '{name}' crashed: {e}")
      results.append((name, False))
  
  # Summary
  logger.info("\n" + "="*60)
  logger.info("Test Summary")
  logger.info("="*60)
  
  passed = sum(1 for _, result in results if result)
  total = len(results)
  
  for name, result in results:
    status = "✓ PASS" if result else "✗ FAIL"
    logger.info(f"{status}: {name}")
  
  logger.info("="*60)
  logger.info(f"Results: {passed}/{total} tests passed")
  logger.info("="*60)
  
  if passed == total:
    logger.info("🎉 All tests passed! Integration looks good.")
    return 0
  else:
    logger.error(f"⚠ {total - passed} test(s) failed. Please review the errors above.")
    return 1


if __name__ == "__main__":
  sys.exit(main())

