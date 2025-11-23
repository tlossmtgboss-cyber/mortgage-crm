"""Gmail API Client for Email Monitor"""

from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
import json


class GmailClient:
    def __init__(self, credentials_json):
        creds_dict = json.loads(credentials_json) if isinstance(credentials_json, str) else credentials_json
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        self.service = build('gmail', 'v1', credentials=credentials)

    def fetch_messages_since(self, timestamp):
        """Fetch messages after timestamp"""
        query = f'after:{int(timestamp.timestamp())}'
        results = self.service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100
        ).execute()

        messages = results.get('messages', [])
        return [self._get_message(msg['id']) for msg in messages]

    def _get_message(self, msg_id):
        """Get full message details"""
        msg = self.service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()
        return msg

    def extract_email_data(self, message):
        """Extract structured data from Gmail message"""
        headers = {h['name'].lower(): h['value']
                   for h in message['payload']['headers']}

        body_preview = message.get('snippet', '')[:500]

        return {
            'message_id': message['id'],
            'from': headers.get('from', ''),
            'to': headers.get('to', ''),
            'cc': headers.get('cc', ''),
            'subject': headers.get('subject', ''),
            'body_preview': body_preview,
            'received_date': datetime.fromtimestamp(
                int(message['internalDate']) / 1000
            )
        }
