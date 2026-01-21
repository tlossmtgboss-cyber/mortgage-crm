"""
Gmail Integration Service

Handles Gmail OAuth authentication, email sync, sending, and contact management.
"""

import os
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/contacts.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]


class GmailService:
    """Service for Gmail API operations"""

    def __init__(self):
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI',
            'https://app.perenniaai.com/api/v1/gmail/callback')

        # Client config for OAuth flow
        self.client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.redirect_uri]
            }
        }

    def get_auth_url(self, state: str = None) -> str:
        """
        Generate Gmail OAuth authorization URL

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL for Gmail OAuth
        """
        flow = Flow.from_client_config(
            self.client_config,
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )

        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state
        )

        return auth_url

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token data including access_token, refresh_token, etc.
        """
        import requests

        # Use direct HTTP request to avoid scope mismatch errors
        token_url = "https://oauth2.googleapis.com/token"

        response = requests.post(token_url, data={
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        })

        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            raise Exception(f"Token exchange failed: {response.text}")

        token_data = response.json()

        return {
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token'),
            'token_uri': token_url,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scopes': token_data.get('scope', '').split(),
            'expiry': None  # Will be set when credentials are refreshed
        }

    def get_credentials(self, token_data: Dict[str, Any]) -> Credentials:
        """
        Create Credentials object from stored token data

        Args:
            token_data: Stored token data from database

        Returns:
            Google Credentials object
        """
        credentials = Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_data.get('client_id', self.client_id),
            client_secret=token_data.get('client_secret', self.client_secret),
            scopes=token_data.get('scopes', SCOPES)
        )

        # Refresh if expired
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        return credentials

    def get_user_info(self, credentials: Credentials) -> Dict[str, Any]:
        """
        Get user profile information

        Args:
            credentials: Google Credentials object

        Returns:
            User profile data including email and name
        """
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()

        return {
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'picture': user_info.get('picture'),
            'id': user_info.get('id')
        }

    def list_messages(self, credentials: Credentials,
                      query: str = None,
                      max_results: int = 50,
                      page_token: str = None) -> Dict[str, Any]:
        """
        List Gmail messages

        Args:
            credentials: Google Credentials object
            query: Gmail search query (e.g., 'is:unread', 'from:client@email.com')
            max_results: Maximum number of messages to return
            page_token: Token for pagination

        Returns:
            List of message metadata
        """
        try:
            service = build('gmail', 'v1', credentials=credentials)

            params = {
                'userId': 'me',
                'maxResults': max_results
            }

            if query:
                params['q'] = query
            if page_token:
                params['pageToken'] = page_token

            results = service.users().messages().list(**params).execute()

            messages = results.get('messages', [])
            next_page_token = results.get('nextPageToken')

            return {
                'messages': messages,
                'nextPageToken': next_page_token,
                'resultSizeEstimate': results.get('resultSizeEstimate', 0)
            }

        except HttpError as error:
            logger.error(f"Error listing Gmail messages: {error}")
            raise

    def get_message(self, credentials: Credentials, message_id: str) -> Dict[str, Any]:
        """
        Get full message details

        Args:
            credentials: Google Credentials object
            message_id: Gmail message ID

        Returns:
            Full message data including headers and body
        """
        try:
            service = build('gmail', 'v1', credentials=credentials)

            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Parse message
            headers = message.get('payload', {}).get('headers', [])

            parsed = {
                'id': message.get('id'),
                'threadId': message.get('threadId'),
                'labelIds': message.get('labelIds', []),
                'snippet': message.get('snippet'),
                'internalDate': message.get('internalDate'),
                'subject': None,
                'from': None,
                'to': None,
                'date': None,
                'body_text': None,
                'body_html': None
            }

            # Extract headers
            for header in headers:
                name = header.get('name', '').lower()
                value = header.get('value')

                if name == 'subject':
                    parsed['subject'] = value
                elif name == 'from':
                    parsed['from'] = value
                elif name == 'to':
                    parsed['to'] = value
                elif name == 'date':
                    parsed['date'] = value

            # Extract body
            payload = message.get('payload', {})
            parsed['body_text'], parsed['body_html'] = self._extract_body(payload)

            return parsed

        except HttpError as error:
            logger.error(f"Error getting Gmail message: {error}")
            raise

    def _extract_body(self, payload: Dict) -> tuple:
        """Extract text and HTML body from message payload"""
        text_body = None
        html_body = None

        if 'body' in payload and payload['body'].get('data'):
            # Single part message
            body_data = payload['body']['data']
            decoded = base64.urlsafe_b64decode(body_data).decode('utf-8')

            if payload.get('mimeType') == 'text/html':
                html_body = decoded
            else:
                text_body = decoded

        elif 'parts' in payload:
            # Multipart message
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')

                if part.get('body', {}).get('data'):
                    body_data = part['body']['data']
                    decoded = base64.urlsafe_b64decode(body_data).decode('utf-8')

                    if mime_type == 'text/plain':
                        text_body = decoded
                    elif mime_type == 'text/html':
                        html_body = decoded

                # Handle nested parts
                if 'parts' in part:
                    nested_text, nested_html = self._extract_body(part)
                    if nested_text and not text_body:
                        text_body = nested_text
                    if nested_html and not html_body:
                        html_body = nested_html

        return text_body, html_body

    def send_email(self, credentials: Credentials,
                   to: str,
                   subject: str,
                   body_text: str = None,
                   body_html: str = None,
                   cc: str = None,
                   bcc: str = None,
                   reply_to: str = None,
                   thread_id: str = None) -> Dict[str, Any]:
        """
        Send an email through Gmail

        Args:
            credentials: Google Credentials object
            to: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body
            cc: CC recipients
            bcc: BCC recipients
            reply_to: Reply-to address
            thread_id: Thread ID if replying to a thread

        Returns:
            Sent message data
        """
        try:
            service = build('gmail', 'v1', credentials=credentials)

            # Get sender email
            user_info = self.get_user_info(credentials)
            sender = user_info.get('email')

            # Create message
            if body_html:
                message = MIMEMultipart('alternative')
                if body_text:
                    message.attach(MIMEText(body_text, 'plain'))
                message.attach(MIMEText(body_html, 'html'))
            else:
                message = MIMEText(body_text or '', 'plain')

            message['to'] = to
            message['from'] = sender
            message['subject'] = subject

            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            if reply_to:
                message['reply-to'] = reply_to

            # Encode message
            raw_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode('utf-8')

            body = {'raw': raw_message}

            if thread_id:
                body['threadId'] = thread_id

            # Send
            sent = service.users().messages().send(
                userId='me',
                body=body
            ).execute()

            logger.info(f"Email sent to {to}, message ID: {sent.get('id')}")

            return {
                'id': sent.get('id'),
                'threadId': sent.get('threadId'),
                'labelIds': sent.get('labelIds', [])
            }

        except HttpError as error:
            logger.error(f"Error sending Gmail message: {error}")
            raise

    def get_contacts(self, credentials: Credentials,
                     max_results: int = 100,
                     page_token: str = None) -> Dict[str, Any]:
        """
        Get Google contacts

        Args:
            credentials: Google Credentials object
            max_results: Maximum contacts to return
            page_token: Pagination token

        Returns:
            List of contacts
        """
        try:
            service = build('people', 'v1', credentials=credentials)

            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=max_results,
                personFields='names,emailAddresses,phoneNumbers,organizations',
                pageToken=page_token
            ).execute()

            connections = results.get('connections', [])
            contacts = []

            for person in connections:
                contact = {
                    'resourceName': person.get('resourceName'),
                    'name': None,
                    'emails': [],
                    'phones': [],
                    'organization': None
                }

                # Get name
                names = person.get('names', [])
                if names:
                    contact['name'] = names[0].get('displayName')

                # Get emails
                emails = person.get('emailAddresses', [])
                contact['emails'] = [e.get('value') for e in emails if e.get('value')]

                # Get phones
                phones = person.get('phoneNumbers', [])
                contact['phones'] = [p.get('value') for p in phones if p.get('value')]

                # Get organization
                orgs = person.get('organizations', [])
                if orgs:
                    contact['organization'] = orgs[0].get('name')

                contacts.append(contact)

            return {
                'contacts': contacts,
                'nextPageToken': results.get('nextPageToken'),
                'totalPeople': results.get('totalPeople', 0)
            }

        except HttpError as error:
            logger.error(f"Error getting Google contacts: {error}")
            raise

    def sync_emails(self, credentials: Credentials,
                    since_date: datetime = None,
                    max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Sync emails from Gmail

        Args:
            credentials: Google Credentials object
            since_date: Only get emails after this date
            max_results: Maximum emails to sync

        Returns:
            List of parsed email messages
        """
        # Build query
        query_parts = []

        if since_date:
            date_str = since_date.strftime('%Y/%m/%d')
            query_parts.append(f'after:{date_str}')

        # Focus on inbox and sent
        query_parts.append('in:inbox OR in:sent')

        query = ' '.join(query_parts) if query_parts else None

        # Get message list
        result = self.list_messages(credentials, query=query, max_results=max_results)

        emails = []
        for msg in result.get('messages', []):
            try:
                full_message = self.get_message(credentials, msg['id'])
                emails.append(full_message)
            except Exception as e:
                logger.error(f"Error fetching message {msg['id']}: {e}")
                continue

        return emails


# Singleton instance
gmail_service = GmailService()
