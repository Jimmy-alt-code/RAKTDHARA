#!/usr/bin/env python3
"""
Test script for NGO Dashboard functionality
"""

import requests
import json

def test_ngo_endpoints():
    base_url = "http://localhost:5000/api"
    
    print("Testing NGO Dashboard Endpoints...")
    print("=" * 50)
    
    # Test 1: Statistics endpoint
    print("1. Testing /api/ngo/statistics")
    try:
        response = requests.get(f"{base_url}/ngo/statistics")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Statistics: {data['statistics']}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print()
    
    # Test 2: Dashboard endpoint
    print("2. Testing /api/ngo/dashboard")
    try:
        response = requests.get(f"{base_url}/ngo/dashboard")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Statistics: {data['statistics']}")
            print(f"   Recent requests count: {len(data['recent_requests'])}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print()
    
    # Test 3: Refresh endpoint
    print("3. Testing /api/ngo/refresh")
    try:
        response = requests.post(f"{base_url}/ngo/refresh")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Message: {data['message']}")
            print(f"   Statistics: {data['statistics']}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print()
    
    # Test 4: Dashboard page
    print("4. Testing /ngo-dashboard page")
    try:
        response = requests.get("http://localhost:5000/ngo-dashboard")
        print(f"   Status: {response.status_code}")
        print(f"   Content length: {len(response.text)}")
        if "NGO Partnership Management" in response.text:
            print("   ✓ Dashboard page contains expected content")
        else:
            print("   ✗ Dashboard page missing expected content")
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    test_ngo_endpoints()
