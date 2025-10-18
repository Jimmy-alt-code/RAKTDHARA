#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify SMTP configuration
"""
import requests
import json
import time
import sys

# Set UTF-8 encoding for Windows
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())

# Wait a moment for the server to start
print("Waiting for server to start...")
time.sleep(3)

# Test SMTP configuration
def test_smtp():
    print("Testing SMTP Configuration...")
    
    # Test endpoint
    url = "http://127.0.0.1:5000/api/test-smtp"
    
    # Test data - replace with your email
    test_data = {
        "test_email": "raktdhara123@gmail.com"  # Using the same email for testing
    }
    
    try:
        print(f"Sending test email to: {test_data['test_email']}")
        response = requests.post(url, json=test_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("SUCCESS! SMTP configuration is working!")
                print(f"Test email sent successfully!")
                print(f"Message ID: {result.get('message_id', 'N/A')}")
                print(f"Recipient: {result.get('recipient', 'N/A')}")
                print(f"Subject: {result.get('subject', 'N/A')}")
            else:
                print("FAILED! SMTP configuration has issues:")
                print(f"Error: {result.get('error', 'Unknown error')}")
        else:
            print(f"HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Connection Error: Could not connect to the server")
        print("Make sure the Flask server is running on http://127.0.0.1:5000")
    except requests.exceptions.Timeout:
        print("Timeout: Request took too long")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")

def test_email_templates():
    print("\nTesting Email Templates...")
    
    # Test donation request template
    url = "http://127.0.0.1:5000/api/send-email"
    
    test_data = {
        "template_type": "donation_request",
        "recipient_email": "raktdhara123@gmail.com",
        "data": {
            "donor_name": "Test Donor",
            "blood_type": "O+",
            "donor_blood_type": "O+",
            "location": "Mumbai",
            "urgency": "High",
            "contact_phone": "+91-9876543210"
        }
    }
    
    try:
        print("Sending donation request template...")
        response = requests.post(url, json=test_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("Donation request template sent successfully!")
            else:
                print(f"Template test failed: {result.get('error')}")
        else:
            print(f"HTTP Error: {response.status_code}")
            
    except Exception as e:
        print(f"Template test error: {str(e)}")

if __name__ == "__main__":
    print("RAKT DHARA SMTP Test Suite")
    print("=" * 50)
    
    # Test basic SMTP configuration
    test_smtp()
    
    # Test email templates
    test_email_templates()
    
    print("\n" + "=" * 50)
    print("Test completed!")
    print("Check your email inbox for the test messages")
