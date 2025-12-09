"""
Test script for the PII Sanitizer module.

Verifies that the sanitizer correctly detects and anonymizes
sensitive information commonly found in Qlik Replicate logs.

Run with: python test_sanitizer.py
"""

import sys
from typing import List, Tuple


def test_sanitizer():
    """Run sanitization tests on sample log data."""
    
    # Import the sanitizer
    try:
        from backend.llm.sanitizer import (
            get_sanitizer, 
            sanitize_text, 
            sanitize_dict, 
            sanitize_list
        )
        print("Successfully imported sanitizer module")
    except ImportError as e:
        print(f"Failed to import sanitizer: {e}")
        print("\nMake sure you have installed the dependencies:")
        print("  pip install presidio-analyzer presidio-anonymizer")
        return False
    
    # Initialize sanitizer
    try:
        sanitizer = get_sanitizer()
        print("Successfully initialized LogSanitizer")
    except Exception as e:
        print(f"Failed to initialize sanitizer: {e}")
        return False
    
    # Test cases: (input, expected_patterns_to_be_masked)
    test_cases: List[Tuple[str, List[str]]] = [
        # Hostnames / FQDNs
        (
            "Connected to server HSP-DBM-APP05.cs.sbsit.eu on port 1433",
            ["[HOSTNAME]"]
        ),
        # IP Addresses
        (
            "Connection from 192.168.1.100 to 10.0.0.50",
            ["[IP_ADDRESS]"]
        ),
        # UNC Paths
        (
            "Log file at \\\\fileserver\\logs\\replicate\\task.log",
            ["[UNC_PATH]"]
        ),
        # Connection Strings
        (
            "Connection: UID=admin;SERVER=dbserver.local;Database=prod",
            ["[REDACTED]"]
        ),
        # License Information
        (
            "Licensed to Acme Corporation, expires 2025-12-31",
            ["[COMPANY]"]
        ),
        # Email Addresses
        (
            "Contact support at admin@company.com for assistance",
            ["[EMAIL]"]
        ),
        # Combined example
        (
            "Connected to target server.database.corp.com (192.168.10.50)",
            ["[HOSTNAME]", "[IP_ADDRESS]"]
        ),
    ]
    
    print("\n" + "="*60)
    print("Running sanitization tests...")
    print("="*60 + "\n")
    
    passed = 0
    failed = 0
    
    for i, (input_text, expected_tags) in enumerate(test_cases, 1):
        result = sanitize_text(input_text)
        
        # Check if expected tags are in the result
        all_tags_found = all(tag in result for tag in expected_tags)
        
        if all_tags_found:
            print(f"Test {i}: PASSED")
            print(f"  Input:  {input_text[:70]}...")
            print(f"  Output: {result[:70]}...")
            passed += 1
        else:
            print(f"Test {i}: FAILED")
            print(f"  Input:    {input_text}")
            print(f"  Output:   {result}")
            print(f"  Expected: {expected_tags}")
            failed += 1
        print()
    
    # Test dict sanitization
    print("="*60)
    print("Testing dictionary sanitization...")
    print("="*60 + "\n")
    
    test_dict = {
        "server": "db.production.com",
        "ip": "10.0.0.1",
        "numeric": 12345,
    }
    
    result_dict = sanitize_dict(test_dict)
    print(f"Input:  {test_dict}")
    print(f"Output: {result_dict}")
    
    dict_passed = "[HOSTNAME]" in result_dict["server"] and "[IP_ADDRESS]" in result_dict["ip"]
    if dict_passed:
        print("Dictionary sanitization: PASSED")
        passed += 1
    else:
        print("Dictionary sanitization: FAILED")
        failed += 1
    
    # Summary
    print("\n" + "="*60)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = test_sanitizer()
    sys.exit(0 if success else 1)
