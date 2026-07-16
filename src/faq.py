"""FAQ categories and answers.

Edit the ANSWER text below with your real content. Each category maps to the
button the user taps. "others" has no canned answer — it collects a free-text
query that goes straight to a ticket.

Category ids are used as WhatsApp interactive-button ids, so keep them short and
without spaces.
"""

# Order here is the order buttons appear in the WhatsApp menu.
# WhatsApp interactive "button" messages allow max 3 buttons; for 4+ options use
# a "list" message. We have 4 categories, so the bot uses a list message.
CATEGORIES = [
    {
        "id": "login_issue",
        "title": "Login Issue",
        "answer": (
            "TODO: Steps to fix a login issue.\n"
            "1. ...\n2. ...\n"
            "If this didn't help, tap 'No' and we'll raise a ticket for you."
        ),
    },
    {
        "id": "login_creds",
        "title": "Login Credentials Not Received",
        "answer": (
            "TODO: What to do if credentials weren't received.\n"
            "1. Check your registered email/spam.\n2. ...\n"
            "If this didn't help, tap 'No' and we'll raise a ticket for you."
        ),
    },
    {
        "id": "other_faq",
        "title": "Other FAQ Categories",
        "answer": (
            "TODO: A general FAQ answer or a link to the knowledge base.\n"
            "If this didn't help, tap 'No' and we'll raise a ticket for you."
        ),
    },
    {
        # No canned answer — go straight to collecting a free-text query.
        "id": "others",
        "title": "Others",
        "answer": None,
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
