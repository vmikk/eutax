#!/usr/bin/env python

# Taxonomic annotation API tester
# (tests the API endpoints and parameter combinations)


import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.box import MINIMAL


class APITester:
    def __init__(self, base_url: str, api_key: str, test_data_path: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.test_data_path = test_data_path
        self.console = Console()
        self.headers = {"X-API-KEY": api_key}
        self.results: Dict[str, Dict] = {}
        
        # Create results directory if it doesn't exist
        os.makedirs("test_results", exist_ok=True)

    def print_header(self, text: str):
        """Print a section header with rich formatting"""
        self.console.print(Panel(f"[bold blue]{text}[/]", border_style="blue", box=MINIMAL))

    def print_success(self, message: str):
        """Print a success message"""
        self.console.print(f"[bold green]✓[/] {message}")

    def print_failure(self, message: str):
        """Print a failure message"""
        self.console.print(f"[bold red]✗[/] {message}")

    def print_info(self, message: str):
        """Print an info message"""
        self.console.print(f"[bold cyan]ℹ[/] {message}")

    def test_health(self) -> bool:
        """Test the health endpoint"""
        self.print_header("Testing Health Endpoint")
        
        try:
            response = requests.get(f"{self.base_url}/api/v1/health")
            if response.status_code == 200:
                status_data = response.json()
                if status_data.get("status") == "healthy":
                    self.print_success(f"Health check successful: healthy")
                    self.print_info(f"Response:\n{status_data}")
                    return True
                else:
                    self.print_failure(f"Health check failed: {status_data}")
                    return False
            else:
                self.print_failure(f"Health check failed with status code: {response.status_code}")
                return False
        except Exception as e:
            self.print_failure(f"Health check request failed: {str(e)}")
            return False

