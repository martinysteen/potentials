# Script til at kopiere fra en Google Cloud Folder og til en Windows-baseret folder
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import io
from googleapiclient.http import MediaIoBaseDownload

SOURCE_FOLDER_ID = '1eOjCF6kVZrby1j0pe7qeLzADixmHyYlP'
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

def download_file(service, file_id, file_name, folder_path):
    # Downloads a file from Google Drive.

    file_path = os.path.join(folder_path, file_name)
    
    # Check if the file already exists and delete it if it does
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"2. File '{file_name}' found and deleted.")
    
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"3. Downloading new copy of {file_name} ({int(status.progress() * 100)}%)")

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
    print(f'*** Source GoogleDrive-folder til download: {folder["name"]} med id {folder_id} ***')  
    
    file_list = list_files_in_folder(service, folder_id)
    if not file_list:
        print('*** No files found in Google Drive folder ***')
    else:
        print('Download proces:')
        for file in file_list:
            print(f"1. Locating {file['name']} ({file['id']})")
            # download_file initially deletes the file in scope from target folder
            download_file(service, file['id'], file['name'], local_path)

if __name__ == '__main__':
    #local_path = '.\\app\\input'
    my_local_path = './app/input'
    main(my_local_path)