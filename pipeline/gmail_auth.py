"""
Gmail OAuth2 Authentication Helper
===================================
Run this ONCE to authenticate. After that, all scripts run automatically.

Setup steps:
  1. Go to https://console.cloud.google.com
  2. Create (or select) a project
  3. APIs & Services → Library → search "Gmail API" → Enable
  4. APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
  5. Application type: Desktop app → Create
  6. Download JSON → save as: pipeline/credentials.json
  7. Run: py gmail_auth.py
  8. Browser opens → sign in with raz@tovplay.org → click Allow
  9. token.json is saved → all future runs are 100% automatic

Usage from other scripts:
  from gmail_auth import get_gmail_service
  service = get_gmail_service()
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

PIPELINE_DIR     = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(PIPELINE_DIR, "credentials.json")
TOKEN_FILE       = os.path.join(PIPELINE_DIR, "token.json")


def get_gmail_service():
    """
    Returns an authenticated Gmail API service object.
    Automatically refreshes tokens. Opens browser only on first run.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"\n❌ credentials.json not found at:\n   {CREDENTIALS_FILE}\n\n"
                    "Follow setup steps in the docstring above."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


if __name__ == "__main__":
    print("Authenticating with Gmail...")
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"\n✅ Authenticated as: {profile['emailAddress']}")
    print(f"   token.json saved to: {TOKEN_FILE}")
    print("\nAll sending scripts will now run automatically (no browser needed).")
