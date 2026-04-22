#!/usr/bin/env python3
import json
import subprocess
import sys

try:
    input_data = json.load(sys.stdin)
    file_path = input_data["tool_input"]["file_path"]
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

if not file_path.endswith(".py"):
    print(f"⏭️  Skipping {file_path} (not a Python file)")
    sys.exit(0)

result = subprocess.run(["uv", "run", "scripts/validate_tests.py", file_path], capture_output=True)

if result.returncode == 0:
    print(f"✅ {file_path} passed test validation")
else:
    print(result.stderr, file=sys.stderr)
    exit(2)
