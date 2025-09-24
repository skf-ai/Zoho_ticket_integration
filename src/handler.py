import json
from . import zoho_client

def lambda_handler(event, context):
    """AWS Lambda handler function."""
    print(f"Received event: {json.dumps(event)}")

    # Extract ticket details from the event
    subject = event.get('subject', 'Default Subject')
    description = event.get('description', 'Default Description')
    contact_id = event.get('contact_id', 'Default Contact ID')

    # Create the Zoho ticket
    ticket = zoho_client.create_ticket(subject, description, contact_id)

    if ticket:
        return {
            'statusCode': 200,
            'body': json.dumps(ticket)
        }
    else:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to create ticket'})
        }

if __name__ == "__main__":
    # --- THIS IS WHERE YOU PROVIDE YOUR INPUTS ---
    # To test locally, create a sample event dictionary.
    # This contact ID was found to be valid in the last test run.
    test_event = {
        'subject': 'Local Test Ticket from Python',
        'description': 'This is a test ticket created by running the script locally.',
        'contact_id': '146318000000235208'
    }

    print("--- Running local test ---")
    # Call the handler function with the test event
    result = lambda_handler(test_event, {})
    print("--- Test finished ---")
    print("Response:")
    print(json.dumps(result, indent=4))
