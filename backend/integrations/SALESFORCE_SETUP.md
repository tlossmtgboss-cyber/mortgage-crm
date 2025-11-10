# Salesforce OAuth Integration Setup

This guide explains how to set up the Salesforce OAuth integration for the Mortgage CRM.

## Prerequisites

1. Salesforce Developer Account or Production Account
2. System Administrator access to create Connected Apps

## Step 1: Create a Salesforce Connected App

1. Log into your Salesforce account
2. Navigate to **Setup** > **Apps** > **App Manager**
3. Click **New Connected App**
4. Fill in the following details:
   - **Connected App Name**: Mortgage CRM Integration
   - **API Name**: Mortgage_CRM_Integration
   - **Contact Email**: Your email address

5. **Enable OAuth Settings**:
   - Check "Enable OAuth Settings"
   - **Callback URL**:
     - For production: `https://your-backend-url.com/api/v1/salesforce/oauth/callback`
     - For development: `http://localhost:8000/api/v1/salesforce/oauth/callback`

6. **Selected OAuth Scopes** - Add these:
   - `Access and manage your data (api)`
   - `Perform requests on your behalf at any time (refresh_token, offline_access)`

7. Click **Save**
8. Wait 2-10 minutes for the Connected App to be fully registered

## Step 2: Get Your Credentials

1. After saving, click on **Manage Consumer Details**
2. Verify your identity (Salesforce will send a verification code)
3. Copy the following values:
   - **Consumer Key** (Client ID)
   - **Consumer Secret** (Client Secret)

## Step 3: Configure Environment Variables

Add these environment variables to your `.env` file:

```bash
# Salesforce OAuth Configuration
SALESFORCE_CLIENT_ID="your_consumer_key_here"
SALESFORCE_CLIENT_SECRET="your_consumer_secret_here"
SALESFORCE_REDIRECT_URI="https://your-backend-url.com/api/v1/salesforce/oauth/callback"
SALESFORCE_DOMAIN="login.salesforce.com"  # Use "test.salesforce.com" for sandbox
```

For Railway deployment, add these as environment variables in the Railway dashboard.

## Step 4: Test the Integration

1. Start your backend server
2. Log into the Mortgage CRM frontend
3. Navigate to the Onboarding Wizard or Settings
4. Click "Connect Salesforce"
5. Authorize the app when prompted
6. You should be redirected back with a success message

## API Endpoints

The following endpoints are available:

- `GET /api/v1/salesforce/oauth/start` - Initiates OAuth flow
- `GET /api/v1/salesforce/oauth/callback` - OAuth callback endpoint
- `GET /api/v1/salesforce/status` - Check connection status
- `DELETE /api/v1/salesforce/disconnect` - Disconnect integration

## Using the Salesforce Client

Example usage in Python:

```python
from integrations.salesforce_service import salesforce_client

# Query records
results = salesforce_client.query(
    access_token=token,
    instance_url=instance_url,
    soql_query="SELECT Id, Name, Email FROM Contact LIMIT 10"
)

# Create a record
new_contact = salesforce_client.create_record(
    access_token=token,
    instance_url=instance_url,
    sobject_type="Contact",
    data={
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@example.com"
    }
)

# Update a record
salesforce_client.update_record(
    access_token=token,
    instance_url=instance_url,
    sobject_type="Contact",
    record_id="003XXXXXXXXXXXXXXX",
    data={"Phone": "(555) 123-4567"}
)
```

## Troubleshooting

### Error: "redirect_uri_mismatch"
- Ensure the Callback URL in Salesforce matches exactly with your `SALESFORCE_REDIRECT_URI` environment variable
- Check for trailing slashes and http vs https

### Error: "invalid_client_id"
- Verify your Consumer Key is correct
- Wait 2-10 minutes after creating the Connected App for it to fully register

### Error: "API not enabled"
- Ensure you have API access enabled in your Salesforce org
- Check that the required OAuth scopes are selected in the Connected App

## Security Best Practices

1. **Never commit credentials** to version control
2. Use environment variables for all sensitive data
3. Rotate credentials periodically
4. Use separate Connected Apps for development and production
5. Monitor OAuth token usage in Salesforce Setup

## Additional Resources

- [Salesforce OAuth 2.0 Documentation](https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_web_server_flow.htm)
- [Connected App Documentation](https://help.salesforce.com/s/articleView?id=sf.connected_app_overview.htm)
- [Salesforce REST API](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/)
