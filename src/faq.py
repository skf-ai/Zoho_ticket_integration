"""FAQ categories and answers for the LMS (Moodle) onboarding support desk.

Replace the two placeholders with your real values:
    <LMS_URL>        e.g. https://learn.siddhanta.org
    <SUPPORT_EMAIL>  e.g. support@srisiddhanta.org

Category ids are used as WhatsApp interactive-button/list ids, so keep them short
and without spaces. "others" has no canned answer — it collects a free-text query
that goes straight to a ticket.
"""

LMS_URL = "<LMS_URL>"
SUPPORT_EMAIL = "<SUPPORT_EMAIL>"

# Order here is the order options appear in the WhatsApp menu.
CATEGORIES = [
    {
        "id": "login_issue",
        "title": "Login Issue",
        "answer": (
            "Trouble logging in to the learning portal? Please try:\n\n"
            f"1. Go to {LMS_URL} and enter the exact username/email from your "
            "welcome message.\n"
            "2. Passwords are case-sensitive — check Caps Lock.\n"
            "3. Tap 'Forgot password' on the login page to reset it via your "
            "registered email.\n"
            "4. Try a different browser or incognito/private mode, and clear the "
            "cache.\n"
            "5. Make sure you have a stable internet connection."
        ),
    },
    {
        "id": "login_creds",
        "title": "Login Credentials Not Received",
        "answer": (
            "Haven't received your login credentials yet? Please check:\n\n"
            "1. Your email inbox *and* spam/junk folders for a message from "
            f"{SUPPORT_EMAIL}.\n"
            "2. That you registered with the correct email and phone number.\n"
            "3. Credentials are normally sent within 24 hours of enrolment.\n"
            "4. Search your inbox for 'welcome', 'LMS', or 'Moodle'."
        ),
    },
    {
        "id": "other_faq",
        "title": "Other FAQ Categories",
        "answer": (
            "Here are answers to the most common questions:\n\n"
            "• *Course not showing up?* Your enrolment may still be pending "
            "approval — log out and back in after a few minutes.\n"
            "• *Videos or content not loading?* Use a stable network, update your "
            "browser, and disable ad-blockers.\n"
            "• *Forgot password?* Use 'Forgot password' on the login page.\n"
            f"• *Using a phone?* Install the official Moodle app and enter {LMS_URL} "
            "as the site address.\n"
            "• *Certificate or grades?* These appear under your course once the "
            "instructor releases them."
        ),
    },
    {
        "id": "others",
        "title": "Others",
        "answer": None,  # go straight to collecting a free-text query
    },
]

# Fast lookup by id.
BY_ID = {c["id"]: c for c in CATEGORIES}


def category_title(category_id):
    c = BY_ID.get(category_id)
    return c["title"] if c else category_id


def category_answer(category_id):
    c = BY_ID.get(category_id)
    return c["answer"] if c else None
