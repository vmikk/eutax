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

    def test_download_results(self, job_id: str) -> bool:
        """Test results download endpoint"""
        self.print_header(f"Downloading Results for Job: {job_id}")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/jobs/{job_id}/results/json",
                headers=self.headers
            )
            
            if response.status_code == 200:
                results_data = response.json()
                
                # Save results to file
                results_file = f"test_results/job_{job_id}_results.json"
                with open(results_file, "w") as f:
                    json.dump(results_data, f, indent=2)
                
                self.print_success(f"Results downloaded successfully to {results_file}")
                
                # Display summary of results
                if "results" in results_data and "summary" in results_data:
                    summary = results_data["summary"]
                    self.print_info(f"Total queries: {summary.get('total_queries', 'N/A')}")
                    self.print_info(f"Total hits: {summary.get('total_hits', 'N/A')}")
                
                return True
            else:
                self.print_failure(f"Results download failed with status code: {response.status_code}")
                if response.status_code == 404:
                    self.print_info("This might be normal if the job had no results")
                return False
        except Exception as e:
            self.print_failure(f"Results download request failed: {str(e)}")
            return False

    def run_parameter_test_suite(self, test_file: str):
        """Run tests with various parameter combinations"""
        self.print_header("EUTAX API test suite")
        
        # Parameter combinations to test
        test_cases = [
            {"tool": "blast", "algorithm": "megablast", "database": "eukaryome_its"},
            {"tool": "blast", "algorithm": "blastn", "database": "eukaryome_its"},
            {"tool": "vsearch", "algorithm": "usearch_global", "database": "eukaryome_its"},
            {"tool": "vsearch", "algorithm": "search_exact", "database": "eukaryome_its"}
        ]
        
        # First check server health
        if not self.test_health():
            self.print_failure("Server health check failed. Aborting test suite.")
            return
        
        # Upload the test file once
        file_id = self.test_upload(test_file)
        if not file_id:
            self.print_failure("File upload failed. Aborting test suite.")
            return
        
        # Create a results table
        results_table = Table(title="Parameter Test Results")
        results_table.add_column("Tool", style="cyan")
        results_table.add_column("Algorithm", style="cyan")
        results_table.add_column("Database", style="cyan")
        results_table.add_column("Job ID", style="blue")
        results_table.add_column("Status", style="green")
        results_table.add_column("Results", style="yellow")
        
        # Run tests for each parameter combination
        for case in test_cases:
            tool = case["tool"]
            algorithm = case["algorithm"]
            database = case["database"]
            
            # Create job
            job_id = self.test_create_job(file_id, tool, algorithm, database)
            if not job_id:
                results_table.add_row(tool, algorithm, database, "FAILED", "N/A", "N/A", "N/A")
                continue
            
            # Check status and wait for completion
            status = self.test_job_status(job_id, wait_for_completion=True)
            
            # Download results if job completed successfully
            results_status = "N/A"
            if status == "finished":
                if self.test_download_results(job_id):
                    results_status = "Downloaded"
                else:
                    results_status = "Failed to download"
         
            # Add short delay between tests
            time.sleep(1)
        
        # Print results table
        self.console.print(results_table)
        
        # Write summary to file
        summary_file = f"test_results/test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(summary_file, "w") as f:
            f.write(f"API Test Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Server: {self.base_url}\n")
            f.write(f"Test file: {test_file}\n\n")
            
            for case in test_cases:
                f.write(f"Tool: {case['tool']}, Algorithm: {case['algorithm']}, Database: {case['database']}\n")
        
        self.print_success(f"Test suite completed. Summary written to {summary_file}")


