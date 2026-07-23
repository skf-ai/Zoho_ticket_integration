"""Recovery from half-finished operations.

Two states exist only for the moment between reserving something and finishing
it: `creating` (reserved a ticket, waiting on Zoho) and `verification_prompting`
(reserved the resolve callback, about to message the student). Both normally
last milliseconds.

If the Lambda dies in between, the conversation is left in that state. Before
these tests existed, both were traps: the student was blocked from raising any
ticket for the rest of time, and one of them made the hourly sweeper fail on
every run forever, so the team's only alarm was permanently red.

The rule these tests pin down: say nothing while the operation might still be in
flight, then recover once the window has passed.
"""

import unittest
from datetime import datetime, timedelta, timezone

from src import llm, sla, workdays


def utc(**delta):
    return datetime.now(timezone.utc) + timedelta(**delta)


class TestStuckTicketCreation(unittest.TestCase):
    def _state(self, started_minutes_ago):
        return {
            "wa_id": "919999000001",
            "ticket_status": "creating",
            "ticket_creation_started_at": workdays.iso(
                utc(minutes=-started_minutes_ago)
            ),
        }

    def test_recent_reservation_is_left_alone(self):
        # The request may still be in flight. Declaring it stuck here would let a
        # second message create a duplicate Zoho ticket.
        decision = sla.decide(self._state(1))
        self.assertEqual(decision["action"], "none")

    def test_reservation_just_inside_the_window_is_left_alone(self):
        decision = sla.decide(self._state(sla.STUCK_CREATION_MINUTES - 1))
        self.assertEqual(decision["action"], "none")

    def test_reservation_is_rechecked_rather_than_forgotten(self):
        # Must schedule a wake-up, or the item drops out of the sweeper's view
        # and the student stays blocked forever.
        decision = sla.decide(self._state(1))
        self.assertIsNotNone(decision["next_at"])

    def test_abandoned_reservation_is_recovered(self):
        decision = sla.decide(self._state(sla.STUCK_CREATION_MINUTES + 1))
        self.assertEqual(decision["action"], "recover_stuck_creation")

    def test_reservation_with_no_timestamp_is_recovered(self):
        # Rather than leaving a student permanently unable to raise a ticket.
        decision = sla.decide({"ticket_status": "creating"})
        self.assertEqual(decision["action"], "recover_stuck_creation")

    def test_recovery_window_exceeds_the_lambda_timeout(self):
        # If the window were shorter than a Lambda run, we would declare a
        # perfectly healthy in-flight request stuck and duplicate its ticket.
        self.assertGreater(sla.STUCK_CREATION_MINUTES * 60, 29)


class TestStuckVerificationPrompt(unittest.TestCase):
    def _state(self, started_minutes_ago):
        return {
            "wa_id": "919999000001",
            "ticket_status": "verification_prompting",
            "verification_prompting_at": workdays.iso(
                utc(minutes=-started_minutes_ago)
            ),
        }

    def test_recent_prompt_is_left_alone(self):
        self.assertEqual(sla.decide(self._state(1))["action"], "none")

    def test_abandoned_prompt_is_recovered(self):
        decision = sla.decide(self._state(sla.STUCK_PROMPT_MINUTES + 1))
        self.assertEqual(decision["action"], "recover_stuck_verification")

    def test_prompt_with_no_timestamp_is_recovered(self):
        decision = sla.decide({"ticket_status": "verification_prompting"})
        self.assertEqual(decision["action"], "recover_stuck_verification")

    def test_prompting_status_is_never_silently_ignored(self):
        # The original bug: no branch existed for this status at all, so the
        # item was deferred a day at a time forever while the student waited.
        for minutes in (0, 1, 10, 60, 60 * 24):
            action = sla.decide(self._state(minutes))["action"]
            self.assertIn(action, ("none", "recover_stuck_verification"))


class TestTimeoutBudget(unittest.TestCase):
    """The mismatch that caused the stuck states in the first place.

    API Gateway hangs up at 29 seconds. The SDK multiplies our timeout by its
    own retry count, so a 12-second timeout with the default 2 retries meant a
    single call could run 36 seconds -- the Lambda was killed before the agent
    could catch the failure and send its fallback reply, leaving reservations
    behind. This test stops that regressing silently.
    """

    LAMBDA_LIMIT_SECONDS = 29
    FALLBACK_ALLOWANCE_SECONDS = 2

    def test_one_call_cannot_outlive_the_lambda(self):
        worst_case = llm._TIMEOUT_SECONDS * (1 + llm._MAX_RETRIES)
        self.assertLess(worst_case, self.LAMBDA_LIMIT_SECONDS)

    def test_two_calls_and_a_tool_still_leave_room_for_the_fallback(self):
        # The realistic worst turn: model, tool call, model, then a fallback
        # message if something failed.
        per_call = llm._TIMEOUT_SECONDS * (1 + llm._MAX_RETRIES)
        worst_turn = (per_call * 2) + 8 + self.FALLBACK_ALLOWANCE_SECONDS
        self.assertLessEqual(worst_turn, self.LAMBDA_LIMIT_SECONDS)


if __name__ == "__main__":
    unittest.main()
