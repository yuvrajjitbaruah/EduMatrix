"""
Bug Condition Exploration Test for Supabase Security Fixes

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**

This test encodes the EXPECTED BEHAVIOR (all sensitive values loaded from environment variables).
It is designed to FAIL on unfixed code where credentials are hardcoded.

CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bug exists.
When the test fails, it surfaces counterexamples showing specific hardcoded credentials.
After the fix is implemented, this test should PASS, validating the fix.
"""

import os
import re
from pathlib import Path


def test_bug_condition_no_hardcoded_credentials():
    """
    Property 1: Bug Condition - Hardcoded Credentials Detection
    
    This test verifies that settings.py does NOT contain hardcoded credentials.
    It searches for specific patterns that indicate hardcoded sensitive values.
    
    EXPECTED OUTCOME ON UNFIXED CODE: This test will FAIL and surface counterexamples
    showing the exact line numbers and hardcoded values that need to be fixed.
    
    EXPECTED OUTCOME AFTER FIX: This test will PASS, confirming all sensitive values
    are loaded from environment variables.
    """
    settings_path = Path(__file__).parent / 'settings.py'
    
    with open(settings_path, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    violations = []
    
    # Check 1: Hardcoded database password (Requirement 1.1)
    if 'TheYuvraj6695@' in content:
        line_num = next(i+1 for i, line in enumerate(lines) if 'TheYuvraj6695@' in line)
        violations.append(f"Line {line_num}: Hardcoded database password found: 'TheYuvraj6695@'")
    
    # Check 2: Hardcoded database username (Requirement 1.1)
    if 'postgres.izqhvntpulghcxelwduz' in content:
        line_num = next(i+1 for i, line in enumerate(lines) if 'postgres.izqhvntpulghcxelwduz' in line)
        violations.append(f"Line {line_num}: Hardcoded database username found: 'postgres.izqhvntpulghcxelwduz'")
    
    # Check 3: Hardcoded database host (Requirement 1.1)
    if 'aws-1-ap-south-1.pooler.supabase.com' in content:
        line_num = next(i+1 for i, line in enumerate(lines) if 'aws-1-ap-south-1.pooler.supabase.com' in line)
        violations.append(f"Line {line_num}: Hardcoded database host found: 'aws-1-ap-south-1.pooler.supabase.com'")
    
    # Check 4: Hardcoded SECRET_KEY (Requirement 1.2)
    # Look for SECRET_KEY assignment without os.environ or os.getenv
    secret_key_pattern = r"SECRET_KEY\s*=\s*['\"]django-insecure-[^'\"]+['\"]"
    if re.search(secret_key_pattern, content):
        line_num = next(i+1 for i, line in enumerate(lines) if re.search(secret_key_pattern, line))
        violations.append(f"Line {line_num}: Hardcoded SECRET_KEY found (not loaded from environment variable)")
    
    # Check 5: Hardcoded SARVAM_API_KEY (Requirement 1.3)
    if 'sk_7ymerfh6_XXzCCUMgUPdMcX9ImNn0UdyI' in content:
        line_num = next(i+1 for i, line in enumerate(lines) if 'sk_7ymerfh6_XXzCCUMgUPdMcX9ImNn0UdyI' in line)
        violations.append(f"Line {line_num}: Hardcoded SARVAM_API_KEY found: 'sk_7ymerfh6_XXzCCUMgUPdMcX9ImNn0UdyI'")
    
    # Check 6: Hardcoded GOOGLE_AI_API_KEY (Requirement 1.3)
    if 'AIzaSyA97LJZ--uPANK2ZScs4kfEkTg6uQWHkTc' in content:
        line_num = next(i+1 for i, line in enumerate(lines) if 'AIzaSyA97LJZ--uPANK2ZScs4kfEkTg6uQWHkTc' in line)
        violations.append(f"Line {line_num}: Hardcoded GOOGLE_AI_API_KEY found: 'AIzaSyA97LJZ--uPANK2ZScs4kfEkTg6uQWHkTc'")
    
    # Check 7: DEBUG set to True without environment variable (Requirement 1.4)
    debug_pattern = r"^DEBUG\s*=\s*True\s*$"
    for i, line in enumerate(lines):
        if re.match(debug_pattern, line.strip()):
            violations.append(f"Line {i+1}: DEBUG = True without environment variable (insecure default)")
    
    # Check 8: ALLOWED_HOSTS = ['*'] without environment variable (Requirement 1.5)
    allowed_hosts_pattern = r"ALLOWED_HOSTS\s*=\s*\[\s*['\"]?\*['\"]?\s*\]"
    if re.search(allowed_hosts_pattern, content):
        line_num = next(i+1 for i, line in enumerate(lines) if re.search(allowed_hosts_pattern, line))
        violations.append(f"Line {line_num}: ALLOWED_HOSTS = ['*'] without environment variable (accepts all hosts)")
    
    # Check 9: SESSION_COOKIE_SECURE = False without environment variable (Requirement 1.6)
    session_cookie_pattern = r"SESSION_COOKIE_SECURE\s*=\s*False"
    if re.search(session_cookie_pattern, content):
        line_num = next(i+1 for i, line in enumerate(lines) if re.search(session_cookie_pattern, line))
        violations.append(f"Line {line_num}: SESSION_COOKIE_SECURE = False without environment variable (insecure)")
    
    # Check 10: CSRF_COOKIE_SECURE = False without environment variable (Requirement 1.6)
    csrf_cookie_pattern = r"CSRF_COOKIE_SECURE\s*=\s*False"
    if re.search(csrf_cookie_pattern, content):
        line_num = next(i+1 for i, line in enumerate(lines) if re.search(csrf_cookie_pattern, line))
        violations.append(f"Line {line_num}: CSRF_COOKIE_SECURE = False without environment variable (insecure)")
    
    # Check 11: X_FRAME_OPTIONS = 'ALLOWALL' without environment variable (Requirement 1.7)
    xframe_pattern = r"X_FRAME_OPTIONS\s*=\s*['\"]ALLOWALL['\"]"
    if re.search(xframe_pattern, content):
        line_num = next(i+1 for i, line in enumerate(lines) if re.search(xframe_pattern, line))
        violations.append(f"Line {line_num}: X_FRAME_OPTIONS = 'ALLOWALL' without environment variable (allows clickjacking)")
    
    # Assert no violations found (this will FAIL on unfixed code, surfacing all counterexamples)
    assert len(violations) == 0, (
        f"\n\nBUG CONDITION DETECTED: Found {len(violations)} hardcoded credentials/insecure settings:\n\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nThese counterexamples confirm the bug exists. "
        "After implementing the fix (loading from environment variables), this test should pass."
    )


if __name__ == '__main__':
    # Run the test to surface counterexamples
    try:
        test_bug_condition_no_hardcoded_credentials()
        print("✓ TEST PASSED: No hardcoded credentials found - bug is fixed!")
    except AssertionError as e:
        print("✗ TEST FAILED (EXPECTED ON UNFIXED CODE):")
        print(str(e))
        exit(1)
