#!/usr/bin/env python3
"""
Test script to verify chat service can communicate with workflow service
"""

import asyncio
import aiohttp
import json


async def test_workflow_integration():
    """Test the workflow service integration"""

    workflow_service_url = "http://localhost:8002"

    print("Testing workflow service integration...")

    # Test 1: Health check
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{workflow_service_url}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print(f"✓ Workflow service health check: {health_data}")
                else:
                    print(f"✗ Workflow service health check failed: {response.status}")
                    return False
    except Exception as e:
        print(f"✗ Failed to connect to workflow service: {e}")
        return False

    # Test 2: Check triggers endpoint
    try:
        payload = {
            "tenant_id": "test-tenant-123",
            "message": "I need help with pricing",
            "session_id": "test-session-456"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{workflow_service_url}/api/v1/triggers/check",
                json=payload
            ) as response:
                if response.status == 200:
                    trigger_data = await response.json()
                    print(f"✓ Workflow trigger check: {trigger_data}")
                else:
                    print(f"✗ Workflow trigger check failed: {response.status}")
                    return False
    except Exception as e:
        print(f"✗ Failed to check workflow triggers: {e}")
        return False

    # Test 3: Get session state endpoint
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{workflow_service_url}/api/v1/executions/session/test-session-456/state",
                params={"tenant_id": "test-tenant-123"}
            ) as response:
                if response.status in [200, 404]:  # 404 is OK (no active workflow)
                    if response.status == 200:
                        state_data = await response.json()
                        print(f"✓ Workflow state check: {state_data}")
                    else:
                        print("✓ Workflow state check: No active workflow (404 - expected)")
                else:
                    print(f"✗ Workflow state check failed: {response.status}")
                    return False
    except Exception as e:
        print(f"✗ Failed to get workflow state: {e}")
        return False

    print("\n🎉 All workflow integration tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_workflow_integration())
    exit(0 if success else 1)