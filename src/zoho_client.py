import json
import requests
import os

# Load config
# Construct an absolute path to the config file.
# This makes the script runnable from any directory.
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')
with open(config_path) as f:
    config = json.load(f)

def get_access_token():
    """Refreshes Zoho access token using the refresh token."""
    print("Refreshing Zoho access token...")
    token_url = "https://accounts.zoho.in/oauth/v2/token"
    payload = {
        'refresh_token': config['zoho_refresh_token'],
        'client_id': config['zoho_client_id'],
        'client_secret': config['zoho_client_secret'],
        'grant_type': 'refresh_token'
    }
    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()  # Raise an exception for bad status codes
        token_data = response.json()
        if 'access_token' in token_data:
            print("Successfully refreshed access token.")
            return token_data['access_token']
        else:
            print(f"Error in token response: {token_data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error refreshing token: {e}")
        return None

def create_ticket(subject, description, contact_id):
    """Creates a ticket in Zoho Desk."""
    access_token = get_access_token()
    if not access_token:
        # If we failed to get a token, we cannot proceed.
        print("Could not create ticket because access token is missing.")
        return None

    headers = {
        'Authorization': f'Zoho-oauthtoken {access_token}',
        'orgId': config['zoho_org_id']
    }
    data = {
        'subject': subject,
        'description': description,
        'contactId': contact_id,
        'departmentId': config['zoho_department_id']
    }
    
    # Use the correct API endpoint for the .in data center
    response = requests.post('https://desk.zoho.in/api/v1/tickets', headers=headers, json=data)
    
    if response.status_code == 200:
        print("Ticket created successfully!")
        return response.json()
    else:
        print(f"Error creating ticket: {response.text}")
        return None
