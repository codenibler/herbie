from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import asyncio
import logging
import os

from dotenv import load_dotenv 

load_dotenv(override=True)

CALENDAR_SCOPE = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_CLIENT_ID = os.getenv("CALENDAR_CLIENT_ID")
CALENDAR_CLIENT_SECRET = os.getenv("CALENDAR_CLIENT_SECRET")
CALENDAR_TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "Europe/Amsterdam")
client_config = {
    "installed": {
        "client_id": CALENDAR_CLIENT_ID,
        "client_secret": CALENDAR_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

def get_service():
    creds = None

    # This is USER permission, not app credentials
    if os.path.exists("toolbox/gcalendar_tokens.json"):
        creds = Credentials.from_authorized_user_file("toolbox/gcalendar_tokens.json", CALENDAR_SCOPE)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(client_config, CALENDAR_SCOPE)
            creds = flow.run_local_server(port=0)

        with open("toolbox/gcalendar_tokens.json", "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

def make_calendar_event(title, from_date, to_date):

    """ ADD CHECK: IF ANY FIELD IS MISSING, RETURN A MESSAGE TO HERBIE TO RE-REQUEST PARAMETERS """

    service = get_service()
    event = {
        "summary": title,
        "start": {
            "dateTime": from_date,
            "timeZone": CALENDAR_TIMEZONE,
        },
        "end": {
            "dateTime": to_date,
            "timeZone": CALENDAR_TIMEZONE,
        },
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    logging.info(f"Created GCalendar Event: {created["htmlLink"]}")
