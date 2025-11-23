"""Outlook/Microsoft Graph API Client for Email Monitor"""

import requests
from datetime import datetime


class OutlookClient:
    def __init__(self, tenant_id, client_id, client_secret, mailbox):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.mailbox = mailbox
        self.token = None
        self._get_token()

    def _get_token(self):
        """Get access token"""
        url = f'https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token'
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials'
        }

        response = requests.post(url, data=data)
        response.raise_for_status()
        self.token = response.json()['access_token']

    def fetch_messages_since(self, timestamp):
        """Fetch messages after timestamp"""
        endpoint = f'https://graph.microsoft.com/v1.0/users/{self.mailbox}/messages'
        headers = {'Authorization': f'Bearer {self.token}'}

        iso_date = timestamp.isoformat()
        params = {
            '$filter': f'receivedDateTime ge {iso_date}',
            '$top': 100,
            '$orderby': 'receivedDateTime DESC',
            '$select': 'id,subject,from,toRecipients,ccRecipients,receivedDateTime,bodyPreview'
        }

        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()

        return response.json().get('value', [])

    def extract_email_data(self, message):
        """Extract structured data from Outlook message"""
        return {
            'message_id': message['id'],
            'from': message['from']['emailAddress']['address'],
            'to': ', '.join([r['emailAddress']['address']
                            for r in message.get('toRecipients', [])]),
            'cc': ', '.join([r['emailAddress']['address']
                            for r in message.get('ccRecipients', [])]),
            'subject': message.get('subject', ''),
            'body_preview': message.get('bodyPreview', '')[:500],
            'received_date': datetime.fromisoformat(
                message['receivedDateTime'].replace('Z', '+00:00')
            )
        }
