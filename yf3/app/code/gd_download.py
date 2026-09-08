# Script til at kopiere fra en Google Cloud Folder og til en Windows-baseret folder
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import io
from googleapiclient.http import MediaIoBaseDownload

SOURCE_FOLDER_ID = '1V9RIu1r2DM9k1wStl8HA4qOQm4vUnbHM'     # PotSystem/repositoryRTBI
# If modifying these scopes, delete the file token_creds.json (this contains the secret token).
SCOPES = ['https://www.googleapis.com/auth/drive']

# Path to shared credentials
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YF3_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # Go up from code/ to app/ to yf3/
SHARED_CREDS_DIR = os.path.join(os.path.dirname(YF3_ROOT), 'shared', 'app', 'creds')
CREDENTIALS_PATH = os.path.join(SHARED_CREDS_DIR, 'gd_creds.json')

def authenticate_google_drive():
    """Shows basic usage of the Drive v3 API."""
    creds = None
    # The file token_creds.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time
    if os.path.exists('token_creds.json'):
        creds = Credentials.from_authorized_user_file('token_creds.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token_creds.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def _looks_intact(file_path):
    """Cheap structural sanity check: not empty, not truncated to a stub.
    Every file in this Drive folder is this repository's European-CSV
    convention (';'-delimited, header + data rows), so the check is generic.
    Mirrors repository.py's _looks_intact, kept as its own copy here since
    yf3 downloads straight from Drive rather than through the shared mirror.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            header = f.readline()
            first_data_row = f.readline()
    except OSError as exc:
        return f"cannot read {os.path.basename(file_path)}: {exc}"
    if not header.strip():
        return f"{os.path.basename(file_path)} is empty"
    if header.count(";") < 1:
        return f"{os.path.basename(file_path)} header has no ';' fields, looks truncated ({header[:60]!r})"
    if not first_data_row.strip():
        return f"{os.path.basename(file_path)} has a header but no data rows"
    return None


def download_file(service, file_id, file_name, folder_path):
    # Downloads a file from Google Drive into a temp file first, and only
    # replaces the existing copy once the download passes a structural sanity
    # check -- protects against an upstream file caught mid-rebuild (seen in
    # practice: PotDat.csv reduced to a '-' stub for hours), which previously
    # deleted the last good copy before the bad replacement even landed.

    file_path = os.path.join(folder_path, file_name)
    tmp_path = file_path + '.download_tmp'

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(tmp_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"2. Downloading new copy of {file_name} ({int(status.progress() * 100)}%)")
    fh.close()

    problem = _looks_intact(tmp_path)
    if problem:
        problem = problem.replace(os.path.basename(tmp_path), file_name)
        os.remove(tmp_path)
        fallback = "keeping previous copy" if os.path.exists(file_path) else "no previous copy to fall back on"
        print(f"ERROR: {problem} -- {fallback} of {file_name}")
        return

    if os.path.exists(file_path):
        os.remove(file_path)
    os.replace(tmp_path, file_path)
    print(f"3. File '{file_name}' updated.")

def list_files_in_folder(service, folder_id):
    # Include MIME type in the query to filter for CSV files
    query = f"'{folder_id}' in parents and trashed=false and mimeType='text/csv'"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    return result.get('files', [])  # liste returneres

def main(local_path):
    # Procedure to move cvs-files from cloud-source to local_path (se __name__ med eksempler)
    # Initially you must authenticate yourself in the source-folder's drive
    creds = authenticate_google_drive()
    service = build('drive', 'v3', credentials=creds) # service is a representation of source-drive

    # Cloud-side: Source cvs-files resides in folder_id, target-folder is local_path
    folder_id = SOURCE_FOLDER_ID  
    folder = service.files().get(fileId=folder_id, fields="name").execute()
    print(f'Source GoogleDrive-folder til download: {folder["name"]} med id {folder_id}')  
    
    file_list = list_files_in_folder(service, folder_id)
    if not file_list:
        print('*** No files found in Google Drive folder ***')
    else:
        print('Download proces:')
        for file in file_list:
            print(f"1. Locating {file['name']} ({file['id']})")
            download_file(service, file['id'], file['name'], local_path)

if __name__ == '__main__':
    #local_path = '.\\app\\input'
    my_local_path = './app/input'
    main(my_local_path)