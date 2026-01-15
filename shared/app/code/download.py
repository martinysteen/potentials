"""
Generic Google Drive downloader module.
Downloads specified CSV files from a Google Drive folder to a local directory.
Supports both direct folder_id and config-based folder name lookup.
"""
from typing import List, Optional, Dict, Any
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import io
import json
from googleapiclient.http import MediaIoBaseDownload

# If modifying these scopes, delete the file token.json (this contains the secret token).
SCOPES = ['https://www.googleapis.com/auth/drive']

# Credentials stored in shared/app/creds/ directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # Go up from code/ to app/ to shared/
CREDS_DIR = os.path.join(SHARED_ROOT, 'app', 'creds')
CONFIG_DIR = os.path.join(SHARED_ROOT, 'app', 'config')
TOKEN_PATH = os.path.join(CREDS_DIR, 'token.json')
CREDENTIALS_PATH = os.path.join(CREDS_DIR, 'download_creds.json')
GDRIVE_CONFIG_PATH = os.path.join(CONFIG_DIR, 'gdrive_folders.json')


def authenticate_google_drive() -> Credentials:
    """
    Authenticates with Google Drive using OAuth2.
    Uses token.json if available, otherwise initiates OAuth flow.
    Credentials stored in shared/app/creds/ directory.

    Returns:
        Credentials object for Google Drive API
    """
    # Ensure creds directory exists
    os.makedirs(CREDS_DIR, exist_ok=True)

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Credentials file not found: {CREDENTIALS_PATH}\n"
                    f"Please place your Google Drive OAuth credentials at this location."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    return creds


def load_folder_config() -> Dict[str, Any]:
    """
    Loads Google Drive folder configuration from JSON file.

    Returns:
        Dictionary with folder configurations

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is malformed
    """
    if not os.path.exists(GDRIVE_CONFIG_PATH):
        raise FileNotFoundError(
            f"Google Drive config file not found: {GDRIVE_CONFIG_PATH}\n"
            f"Please ensure the configuration file exists."
        )

    with open(GDRIVE_CONFIG_PATH, 'r') as f:
        config = json.load(f)

    return config.get('folders', {})


def get_folder_id(folder_name_or_id: str) -> str:
    """
    Gets folder ID from config by folder name, or returns the input if it's already an ID.

    Args:
        folder_name_or_id: Either a folder name (e.g., "repositoryRTBI/Longi")
                          or a direct folder ID (e.g., "1XkGl...")

    Returns:
        Google Drive folder ID

    Raises:
        ValueError: If folder name not found in config
    """
    # If it looks like a folder ID (starts with alphanumeric), return as-is
    if len(folder_name_or_id) > 20 and folder_name_or_id[0].isalnum():
        return folder_name_or_id

    # Otherwise, look it up in config
    folders = load_folder_config()
    if folder_name_or_id not in folders:
        available = ', '.join(folders.keys())
        raise ValueError(
            f"Folder '{folder_name_or_id}' not found in configuration.\n"
            f"Available folders: {available}"
        )

    return folders[folder_name_or_id]['id']


def download_file(service, file_id: str, file_name: str, folder_path: str) -> None:
    """
    Downloads a file from Google Drive to local folder.
    If file exists locally, it is deleted first.

    Args:
        service: Google Drive API service object
        file_id: Google Drive file ID
        file_name: Name to save file as locally
        folder_path: Local directory path to save file
    """
    file_path = os.path.join(folder_path, file_name)

    # Check if the file already exists and delete it if it does
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"  2. File '{file_name}' found and deleted.")

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"  3. Downloading new copy of {file_name} ({int(status.progress() * 100)}%)")


def find_file_in_folder(service, folder_id: str, file_name: str) -> Optional[str]:
    """
    Searches for a specific file by name in a Google Drive folder.

    Args:
        service: Google Drive API service object
        folder_id: Google Drive folder ID to search in
        file_name: Name of file to find

    Returns:
        File ID if found, None otherwise
    """
    query = f"'{folder_id}' in parents and trashed=false and name='{file_name}' and mimeType='text/csv'"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get('files', [])

    if files:
        return files[0]['id']  # Return first match
    return None


def download_files(folder_name_or_id: str, file_names: List[str], local_path: str) -> int:
    """
    Downloads specified CSV files from Google Drive folder to local directory.

    Args:
        folder_name_or_id: Either folder name from config (e.g., "repositoryRTBI/Longi")
                          or direct Google Drive folder ID
        file_names: List of CSV filenames to download
        local_path: Local directory path to save files

    Returns:
        0 on success, 1 on failure
    """
    try:
        # Resolve folder name to ID (or pass through if already an ID)
        folder_id = get_folder_id(folder_name_or_id)

        # Authenticate with Google Drive
        creds = authenticate_google_drive()
        service = build('drive', 'v3', credentials=creds)

        # Get folder name for logging
        folder = service.files().get(fileId=folder_id, fields="name").execute()
        print(f'Source Google Drive folder: {folder["name"]} (ID: {folder_id})')

        # Ensure local directory exists
        os.makedirs(local_path, exist_ok=True)

        # Download each requested file
        print(f'Downloading {len(file_names)} file(s) to {local_path}:')
        missing_files = []

        for file_name in file_names:
            print(f"  1. Locating {file_name}")
            file_id = find_file_in_folder(service, folder_id, file_name)

            if file_id:
                download_file(service, file_id, file_name, local_path)
            else:
                print(f"  *** WARNING: File '{file_name}' not found in Google Drive folder ***")
                missing_files.append(file_name)

        if missing_files:
            print(f"\n*** {len(missing_files)} file(s) not found: {', '.join(missing_files)} ***")
            return 1

        print(f"\nSuccessfully downloaded {len(file_names)} file(s)")
        return 0

    except Exception as e:
        print(f"*** ERROR during download: {e} ***")
        return 1


def main() -> int:
    """
    Test/example usage of the download module.
    Runs multiple test scenarios sequentially.

    Returns:
        Exit code (0=success, 1=failure)
    """
    # Define test cases - add more as needed
    # Now using folder names from config instead of hardcoded IDs
    test_cases = [
        {
            'name': 'Base data files',
            'folder': 'repositoryRTBI',
            'files': ['PotDat.csv', 'cal.csv'],
            'local_path': '../input'
        },
        {
            'name': 'Longi derived files',
            'folder': 'repositoryRTBI/Longi',
            'files': ['longi_rank.csv', 'longi_per1m.csv'],
            'local_path': '../input'
        },
    ]

    # Run all tests
    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"=== Download Module Test {i}: {test['name']} ===")
        print(f"Folder: {test['folder']}")
        print(f"Files: {test['files']}")
        print(f"Destination: {test['local_path']}\n")

        exit_code = download_files(test['folder'], test['files'], test['local_path'])
        results.append(exit_code)

        if exit_code == 0:
            print(f"\n=== Test {i} PASSED ===\n")
        else:
            print(f"\n=== Test {i} FAILED ===\n")

    # Overall result
    print("="*50)
    passed = sum(1 for r in results if r == 0)
    total = len(results)

    if all(r == 0 for r in results):
        print(f"=== ALL TESTS PASSED ({passed}/{total}) ===")
        return 0
    else:
        print(f"=== SOME TESTS FAILED ({passed}/{total} passed) ===")
        return 1


if __name__ == '__main__':
    exit(main())
