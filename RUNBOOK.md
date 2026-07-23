# Operations Runbook

## Pre-deployment gate

1. `python -m pytest -q` passes.
2. `rg "<LMS_URL>|<SUPPORT_EMAIL>" knowledge` returns nothing.
3. The Secrets Manager JSON contains every key listed in `README.md`.
4. Meta has approved all four templates in `deployment/whatsapp-templates.md`.
5. The WhatsApp token is a permanent System User token, not a temporary token.
6. The Zoho workflow sends `X-Webhook-Secret` with the configured shared secret.
7. The LMS administrator number is E.164 digits only, including country code.

## Controlled live test

Use one approved student/test number and take screenshots or timestamps for each
step.

1. Open `/health`; require HTTP 200 and `"ready": true`.
2. Send a knowledge-base question. Confirm a short grounded answer arrives.
3. Send an admin-only problem and explicitly request escalation.
4. Confirm exactly one Zoho ticket appears with the correct contact and category.
5. Send the same Meta payload/message ID again; confirm no second ticket/reply.
6. Confirm DynamoDB contains the ticket ID and a due-index entry.
7. Invoke the sweeper Lambda once from the AWS console after making the item due
   in a test environment. Confirm the administrator receives the template.
8. Mark the Zoho ticket Resolved. Confirm the student receives the verification
   template and DynamoDB changes to `awaiting_verification`.
9. Reply "no, it is still broken". Confirm Zoho remains open and the SLA restarts.
10. Resolve again and reply "yes, it works now". Confirm Zoho and DynamoDB close.
11. Confirm CloudWatch contains no phone number except the masked last four digits.

Do not shorten production deadlines just to test them. Use a separate test stack
or the local fake clock for deadline-boundary testing.

## Bot stopped replying

1. Check `/health`.
2. Check the `whatsapp-zoho-webhook` CloudWatch log group.
3. Check Meta webhook delivery status and signature configuration.
4. Verify the permanent WhatsApp token and `whatsapp_app_secret`.
5. Check Anthropic balance/key. An AI outage should produce the fallback reply.
6. Check DynamoDB for `msg#<message-id>`. Failed processing claims are released;
   completed claims remain for 24 hours.

## Administrator received no reminder

1. Check the `whatsapp-zoho-sweeper` invocation metric and silent alarm.
2. Confirm the ticket has `due_bucket=DUE` and a due `next_action_at` value.
3. Confirm the `due-index` exists and `lms_admin_wa_id` is correct.
4. Check Meta template approval and the send error in the sweeper log.
5. Inspect the sweeper dead-letter queue if EventBridge exhausted retries.

## Ticket creation is stuck

The reservation deliberately does not auto-retry because Zoho may have created a
ticket immediately before a network timeout; blind retrying can create a second
ticket. Search Zoho using the student's phone and timestamp. If the ticket exists,
write its ID and normal open-ticket fields into the v2 DynamoDB row. If it does
not exist, set `ticket_status` to `none` and remove `ticket_creation_started_at`,
`due_bucket`, and `next_action_at`, then ask the student to retry. Record the
incident before editing state.

## Rotate credentials

Update the existing Secrets Manager secret value. Lambda containers cache it, so
publish/redeploy the functions afterward to force new containers. Never print or
paste secrets into tickets, commits, logs or chat.

## Rollback

Redeploy the last known-good Git commit using the manual GitHub Deploy workflow.
Do not delete or recreate the DynamoDB table. If inbound behavior is unsafe,
temporarily unsubscribe Meta's `messages` webhook while preserving the endpoint
and data. If only reminders are unsafe, disable the EventBridge hourly rule.

## Data recovery

DynamoDB point-in-time recovery is enabled. Processed-message rows expire after
24 hours; conversation/ticket rows do not expire automatically. Closed-ticket
retention and deletion must follow the NPO's documented privacy policy.
