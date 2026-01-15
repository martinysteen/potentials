#!/usr/bin/env python3
"""
longi_upload.py - Upload output files to Google Drive using rclone

This module uploads processed results from ./output/ and ./across/ to Google Drive.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime


def validate_source(source: Path) -> bool:
    """
    Validate that source directory exists.

    Args:
        source: Path to source directory

    Returns:
        True if valid, False otherwise
    """
    if not source.exists():
        print(f"ERROR: Source directory does not exist: {source}")
        return False

    if not source.is_dir():
        print(f"ERROR: Source path is not a directory: {source}")
        return False

    print(f"1. Validated source directory: {source}")
    return True


def upload_to_gdrive(
    source: Path,
    destination: str,
    rclone_flags: list[str]
) -> int:
    """
    Sync files to Google Drive using rclone.

    Uses 'rclone sync' to make destination identical to source,
    ensuring any old files in destination are removed.

    Args:
        source: Source directory path
        destination: rclone destination (e.g., "GoogleDrive:path/to/folder")
        rclone_flags: List of additional rclone flags

    Returns:
        rclone exit code (0 = success)
    """
    print(f"2. Syncing from: {source}")
    print(f"   Syncing to: {destination}")
    print(f"   NOTE: Using 'sync' - destination will be made identical to source")

    # Build rclone command - using 'sync' instead of 'copy'
    cmd = ['rclone', 'sync', str(source), destination] + rclone_flags

    # Execute rclone
    try:
        print(f"3. Running rclone sync (flags: {', '.join(rclone_flags)})...")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Print rclone output
        if result.stdout:
            print(result.stdout, end='')

        print(f"   rclone exit code: {result.returncode}")

        if result.returncode == 0:
            print("SUCCESS: Files synced to Google Drive successfully")
        else:
            print(f"ERROR: rclone failed with exit code: {result.returncode}")

        return result.returncode

    except FileNotFoundError:
        print("ERROR: rclone command not found. Is rclone installed?")
        return 127
    except Exception as e:
        print(f"ERROR: Unexpected error during rclone execution: {e}")
        return 1


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, non-zero = error)
    """
    # Configuration - list of (source, destination, required) tuples
    RCLONE_FLAGS = [
        "--update",
        "--verbose",
        "--drive-skip-gdocs",
        "--exclude", "*.txt",
        "--exclude", "*.gdoc",
    ]

    UPLOAD_TASKS = [
        {
            "name": "output",
            "source": Path("/home/sm/potentials/longi/app/output"),
            "destination": "GoogleDrive:PotSystem/repositoryRTBI/Longi",
            "required": True,  # Fail if this upload fails
        },
        {
            "name": "across",
            "source": Path("/home/sm/potentials/longi/app/across"),
            "destination": "GoogleDrive:PotSystem/repositoryRTBI/Longi/across",
            "required": False,  # Optional - warn but continue if missing/failed
        },
    ]

    print(f"=== longi_upload.py START: {datetime.now()} ===")

    # Track overall success
    all_succeeded = True

    # Process each upload task
    for task in UPLOAD_TASKS:
        name = task["name"]
        source = task["source"]
        destination = task["destination"]
        required = task["required"]

        print(f"\n--- Uploading {name} directory ---")

        # Validate source
        if not validate_source(source):
            if required:
                print(f"ERROR: Required upload task '{name}' failed validation")
                print(f"=== longi_upload.py END: {datetime.now()} ===")
                return 1
            else:
                print(f"WARNING: Optional upload task '{name}' source missing, skipping...")
                continue

        # Upload to Google Drive
        exit_code = upload_to_gdrive(source, destination, RCLONE_FLAGS)

        if exit_code != 0:
            if required:
                print(f"ERROR: Required upload task '{name}' failed with exit code: {exit_code}")
                print(f"=== longi_upload.py END: {datetime.now()} ===")
                return exit_code
            else:
                print(f"WARNING: Optional upload task '{name}' failed with exit code: {exit_code}")
                all_succeeded = False

    # Final status
    final_exit_code = 0 if all_succeeded else 1

    print(f"\n=== longi_upload.py END: {datetime.now()} ===")

    return final_exit_code


if __name__ == "__main__":
    sys.exit(main())
