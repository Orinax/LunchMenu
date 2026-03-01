"""
Google Sheets API authentication helpers.

- Local dev: user OAuth flow storing token.json locally.
- Production: Application Default Credentials (ADC) / service account.
"""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_sheets_service() -> Any:
    """Return an authorised Google Sheets API service object."""
    from googleapiclient.discovery import build  # type: ignore

    credentials = _get_credentials()
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return service


def _get_credentials():
    """
    Try OAuth token file first (local dev), then fall back to ADC (production).
    """
    token_file = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json")
    creds_file = os.getenv("GOOGLE_OAUTH_CREDENTIALS_FILE", "credentials.json")

    # --- Local OAuth flow ---
    if Path(token_file).exists() and Path(creds_file).exists():
        from google.oauth2.credentials import Credentials  # type: ignore
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore

        creds = None
        if Path(token_file).exists():
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(token_file).write_text(creds.to_json())

        logger.info("Authenticated via local OAuth token")
        return creds

    # --- ADC / service account ---
    import google.auth  # type: ignore

    creds, project = google.auth.default(scopes=SCOPES)
    logger.info("Authenticated via Application Default Credentials (project=%s)", project)
    return creds
