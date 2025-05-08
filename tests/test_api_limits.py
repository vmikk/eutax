#!/usr/bin/env python

# Rate limit tester for EUTAX API
# - sends requests to the get_job_status endpoint
# - checks for the presence of `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers
# - verifies that the "Remaining" count decrements with each request

## Usage
# ./tests/test_api_limits.py \
#   http://localhost:8000 \
#   API_KEY \
#   --job-id 00000000-0000-0000-0000-000000000000 \
#   --requests 50

import argparse
import sys
import time
import requests
from rich.console import Console
from rich.panel import Panel


def test_rate_limit(base_url: str, api_key: str, num_requests: int = 3, job_id: str = None) -> bool:
    """
    Sends repeated requests to the get_job_status endpoint and verifies rate limit headers
    """
    console = Console()
    headers = {"X-API-KEY": api_key}
    # Use provided job_id or fallback to dummy
    job_id_to_use = job_id if job_id else "00000000-0000-0000-0000-000000000000"
    url = f"{base_url.rstrip('/')}/api/v1/jobs/{job_id_to_use}/status"
    console.print(Panel("[bold blue]Testing rate limiting for `get_job_status`[/]", title="Rate limit test"))

    limit = None
    remaining = None
    success = True

    for i in range(num_requests):
        response = requests.get(url, headers=headers)
        
        # Handle unauthorized errors
        if response.status_code == 401:
            console.print(f"[bold red]✗[/] Request {i+1}: Unauthorized (HTTP 401) - check API key or authentication headers")
            success = False
            break

        # Handle Not Found responses (expected for dummy job IDs)
        if response.status_code == 404:
            console.print(f"[bold yellow]ℹ[/] Request {i+1}: Not Found (HTTP 404) - expected for dummy job")
            continue

        # Handle rate limit exceeded as expected
        if response.status_code == 429:
            console.print(f"[bold green]✓[/] Request {i+1}: Rate limit exceeded (HTTP 429) - expected behavior")
            return True

        # Check for rate limit headers
        if "X-RateLimit-Limit" not in response.headers or "X-RateLimit-Remaining" not in response.headers:
            console.print(f"[bold red]✗[/] Request {i+1}: Missing rate limit headers")
            success = False
            break

        try:
            curr_limit = int(response.headers["X-RateLimit-Limit"])
            curr_remaining = int(response.headers["X-RateLimit-Remaining"])
        except ValueError:
            console.print(f"[bold red]✗[/] Request {i+1}: Invalid rate limit header values")
            success = False
            break

        if i == 0:
            limit = curr_limit
            remaining = curr_remaining
            console.print(f"[bold green]✓[/] Limit: {limit}, Remaining after 1st request: {remaining}")
        else:
            expected_remaining = remaining - 1
            if curr_remaining == expected_remaining:
                console.print(f"[bold green]✓[/] Remaining decremented: {remaining} -> {curr_remaining}")
                remaining = curr_remaining
            else:
                console.print(f"[bold red]✗[/] Remaining did not decrement as expected: {remaining} -> {curr_remaining}")
                success = False
                break

        # Small delay to avoid bursting too fast
        time.sleep(0.1)

    if success:
        console.print("[bold green]All rate limit headers behave as expected.[/]")
    else:
        console.print("[bold red]Rate limit test failed.[/]")

    return success


def main():
    parser = argparse.ArgumentParser(description="Test rate limiting of EUTAX API")
    parser.add_argument("base_url", help="Base URL of the EUTAX API (e.g., http://localhost:8000)")
    parser.add_argument("api_key",  help="API key for authentication")
    parser.add_argument("--job-id", dest="job_id", help="Job ID to test; if omitted, uses dummy ID")
    parser.add_argument("--requests", type=int, default=10, help="Number of requests to send")
    args = parser.parse_args()

    success = test_rate_limit(args.base_url, args.api_key, args.requests, args.job_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
