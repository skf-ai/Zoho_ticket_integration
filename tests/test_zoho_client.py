import unittest
from unittest.mock import patch
from src import zoho_client

class TestZohoClient(unittest.TestCase):

    @patch('src.zoho_client.requests.post')
    def test_create_ticket(self, mock_post):
        """Test the Zoho ticket creation function."""
        # This is a placeholder test. You'll need to expand on it.
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {'id': 'ticket123'}

        ticket = zoho_client.create_ticket('Test Subject', 'Test Description', '12345')

        self.assertIsNotNone(ticket)
        self.assertEqual(ticket['id'], 'ticket123')

if __name__ == '__main__':
    unittest.main()
