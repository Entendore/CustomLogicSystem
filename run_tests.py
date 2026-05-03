# run_tests.py
import sys
import pytest

def run_tests():
    # Run pytest programmatically
    # -v: verbose output
    # -s: show output (print statements)
    # tests/: directory to scan
    exit_code = pytest.main(["-v", "-s", "tests/"])
    return exit_code

if __name__ == '__main__':
    sys.exit(run_tests())