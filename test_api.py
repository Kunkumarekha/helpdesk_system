"""
Small smoke-test script.

Run the server first:
    uvicorn main:app --reload

Then run:
    python test_api.py

This uses only Python standard library.
"""

import json
import urllib.request

BASE_URL = "http://127.0.0.1:8000"


def request(method, path, data=None, token=None):
    body = None
    headers = {"Content-Type": "application/json"}

    if data is not None:
        body = json.dumps(data).encode()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode())
    except Exception as exc:
        print("Request failed:", exc)
        return None, None


print("1. Registering test user...")
status, result = request(
    "POST",
    "/auth/register",
    {
        "name": "Test User",
        "email": "testuser@example.com",
        "password": "Test@123",
        "role": "USER",
    },
)
print(status, result)

print("\n2. Logging in...")
status, result = request(
    "POST",
    "/auth/login",
    {
        "email": "testuser@example.com",
        "password": "Test@123",
    },
)
print(status, result)

if result and "access_token" in result:
    token = result["access_token"]

    print("\n3. Getting current user...")
    status, result = request("GET", "/auth/me", token=token)
    print(status, result)

    print("\nSmoke test completed.")
