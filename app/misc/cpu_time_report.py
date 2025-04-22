#!/usr/bin/env python3

"""
Script to calculate total CPU time from job_summaries database and convert it to hours.

Usage:
  python /app/app/misc/cpu_time_report.py
"""

import argparse
import sqlite3

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Calculate total CPU time from job summaries')
    parser.add_argument('--db-path', type=str, default='/app/outputs/job_summaries.db',
                        help='Path to the job_summaries database (default: /app/outputs/job_summaries.db)')
    args = parser.parse_args()
    
    # Connect to the database
    try:
        conn = sqlite3.connect(args.db_path)
        cursor = conn.cursor()
        
        # Query the sum of all CPU times
        cursor.execute("SELECT SUM(cpu_time_seconds) FROM job_summaries WHERE cpu_time_seconds IS NOT NULL")
        result = cursor.fetchone()
        
        total_cpu_seconds = result[0] if result[0] is not None else 0
        
        # Convert seconds to hours and round to 1 decimal place
        total_cpu_hours = round(total_cpu_seconds / 3600, 1)
        
        # Print the result
        print(f"{total_cpu_hours}")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
