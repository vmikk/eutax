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

    def test_upload(self, file_path: str) -> Optional[str]:
        """Test file upload endpoint"""
        self.print_header(f"Testing File Upload: {os.path.basename(file_path)}")
        
        if not os.path.exists(file_path):
            self.print_failure(f"File not found: {file_path}")
            return None
            
        try:
            with open(file_path, "rb") as file:
                files = {"file": (os.path.basename(file_path), file)}
                response = requests.post(
                    f"{self.base_url}/api/v1/upload",
                    headers=self.headers,
                    files=files
                )
                
                if response.status_code == 201:
                    upload_data = response.json()
                    file_id = upload_data.get("file_id")
                    upload_status = upload_data.get("upload_status")
                    
                    if file_id and upload_status == "success":
                        self.print_success(f"Upload successful - File ID: {file_id}")
                        self.print_info(f"Response:\n{upload_data}")
                        return file_id
                    else:
                        self.print_failure(f"Upload response invalid - Status: {upload_status}")
                        return None
                else:
                    self.print_failure(f"Upload failed with status code: {response.status_code}")
                    self.print_info(f"Response: {response.text}")
                    return None
        except Exception as e:
            self.print_failure(f"Upload request failed: {str(e)}")
            return None

    def test_create_job(self, file_id: str, tool: str, algorithm: str, database: str, 
                        max_target_seqs: int = 20, num_threads: int = 2) -> Optional[str]:
        """Test job creation endpoint"""
        self.print_header(f"Creating Job: {tool}/{algorithm} against {database}")
        
        payload = {
            "file_id": file_id,
            "tool": tool,
            "algorithm": algorithm,
            "database": database,
            "parameters": {
                "max_target_seqs": max_target_seqs,
                "num_threads": num_threads
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/jobs",
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload
            )
            
            if response.status_code == 202:
                job_data = response.json()
                job_id = job_data.get("job_id")
                if job_id:
                    self.print_success(f"Job queued successfully - Job ID: {job_id}")
                    self.print_info(f"Response:\n{job_data}")
                    return job_id
                else:
                    self.print_failure("Job creation response missing job_id")
                    return None
            else:
                self.print_failure(f"Job creation failed with status code: {response.status_code}")
                self.print_info(f"Response: {response.text}")
                return None
        except Exception as e:
            self.print_failure(f"Job creation request failed: {str(e)}")
            return None

    def test_job_status(self, job_id: str, wait_for_completion: bool = True) -> Optional[str]:
        """Test job status endpoint and optionally wait for job completion"""
        self.print_header(f"Checking Job Status: {job_id}")
        
        if wait_for_completion:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Waiting for job completion..."),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Waiting", total=None)
                
                while True:
                    try:
                        response = requests.get(
                            f"{self.base_url}/api/v1/jobs/{job_id}/status",
                            headers=self.headers
                        )
                        
                        if response.status_code == 200:
                            status_data = response.json()
                            status = status_data.get("status", "unknown")
                            
                            if status in ["finished", "failed"]:
                                progress.update(task, completed=True)
                                break
                                
                            time.sleep(2)
                        else:
                            progress.update(task, completed=True)
                            self.print_failure(f"Job status check failed with status code: {response.status_code}")
                            return None
                    except Exception as e:
                        progress.update(task, completed=True)
                        self.print_failure(f"Job status request failed: {str(e)}")
                        return None
        else:
            try:
                response = requests.get(
                    f"{self.base_url}/api/v1/jobs/{job_id}/status",
                    headers=self.headers
                )
                
                if response.status_code != 200:
                    self.print_failure(f"Job status check failed with status code: {response.status_code}")
                    return None
            except Exception as e:
                self.print_failure(f"Job status request failed: {str(e)}")
                return None
        
        # Get final status
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/jobs/{job_id}/status",
                headers=self.headers
            )
            
            if response.status_code == 200:
                status_data = response.json()
                status = status_data.get("status", "unknown")
                self.print_success(f"Job status: {status}")
                
                # Create a rich table for detailed status
                table = Table(title="Job Status Details")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")
                
                for key, value in status_data.items():
                    if isinstance(value, str) and key != "job_id":
                        table.add_row(key, value)
                
                self.console.print(table)
                return status
            else:
                self.print_failure(f"Final job status check failed with status code: {response.status_code}")
                return None
        except Exception as e:
            self.print_failure(f"Final job status request failed: {str(e)}")
            return None

