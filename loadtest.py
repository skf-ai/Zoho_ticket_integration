"""Load / concurrency test against the DEPLOYED system.

Fires Meta-identical, correctly HMAC-signed webhook payloads at the real
/whatsapp endpoint concurrently, and measures latency + failures. This is the
honest way to load-test the pipeline without fifty phones.

Needs WHATSAPP_APP_SECRET in .env (copy from Secrets Manager; local only,
gitignored) to sign requests the way Meta does.

Modes (combine as needed):

  py -3.12 loadtest.py --url https://.../Prod --health 50
      50 concurrent /health hits. Free. Pure infrastructure warm-up check.

  py -3.12 loadtest.py --url https://.../Prod --burst 20
      20 concurrent inbound messages from DISTINCT fake students asking a
      knowledge-base question. Exercises Lambda scale-out, DynamoDB, the AI.
      NOTE: replies to fake numbers cannot be delivered by Meta, so the
      handler reports those sends as failed -> expect 5xx here; what you are
      verifying is: no crashes, sane latency, every request logged cleanly.
      Adds N test conversations to the admin panel stats (auto-expire in 90d).

  py -3.12 loadtest.py --url https://.../Prod --burst 10 --to 9195000XXXXX
      Same, but all messages come "from" YOUR number: replies really arrive
      on your phone (10 at once), and all workers hammer ONE conversation
      item -- the toughest concurrency case for the state store.

  py -3.12 loadtest.py --url https://.../Prod --dupes 10
      The SAME message id delivered 10x concurrently (Meta redelivery storm).
      Expect: exactly one processed; the rest deduplicated without error.

Keep sizes modest (<=50): each AI-processed message costs ~Rs 0.20 and
OpenAI rate limits are a shared resource.
"""

import argparse
import hashlib
import hmac
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

ENV_PATH = ".env"
QUESTION = "How do I log in to the LMS?"


def load_env():
    env = {}
    try:
        with open(ENV_PATH, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def make_payload(wa_id, message_id, text):
    return json.dumps({
        "entry": [{"changes": [{"value": {
            "messages": [{
                "from": wa_id,
                "id": message_id,
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": text},
            }],
            "contacts": [{"wa_id": wa_id,
                          "profile": {"name": f"LoadTest {wa_id[-4:]}"}}],
        }}]}]
    })


def sign(secret, body):
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_message(url, secret, wa_id, message_id, text):
    body = make_payload(wa_id, message_id, text)
    started = time.time()
    try:
        resp = requests.post(
            f"{url}/whatsapp", data=body,
            headers={"Content-Type": "application/json",
                     "X-Hub-Signature-256": sign(secret, body)},
            timeout=40,
        )
        return resp.status_code, time.time() - started
    except requests.RequestException as e:
        return f"EXC:{type(e).__name__}", time.time() - started


def get_health(url):
    started = time.time()
    try:
        resp = requests.get(f"{url}/health", timeout=20)
        return resp.status_code, time.time() - started
    except requests.RequestException as e:
        return f"EXC:{type(e).__name__}", time.time() - started


def report(name, results):
    codes = {}
    for code, _ in results:
        codes[str(code)] = codes.get(str(code), 0) + 1
    times = sorted(t for _, t in results)
    p50 = statistics.median(times)
    p95 = times[max(int(len(times) * 0.95) - 1, 0)]
    print(f"\n== {name}: {len(results)} requests ==")
    print(f"   status codes : {codes}")
    print(f"   latency p50  : {p50:.2f}s   p95: {p95:.2f}s   max: {times[-1]:.2f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="ApiBaseUrl, e.g. https://xxx/Prod")
    ap.add_argument("--health", type=int, default=0, help="N concurrent /health hits")
    ap.add_argument("--burst", type=int, default=0, help="N concurrent inbound messages")
    ap.add_argument("--dupes", type=int, default=0, help="same message id, N deliveries")
    ap.add_argument("--to", default="", help="use YOUR wa_id for burst (replies arrive)")
    args = ap.parse_args()
    url = args.url.rstrip("/")

    if args.burst > 50 or args.dupes > 50 or args.health > 200:
        raise SystemExit("Keep it modest: burst/dupes <= 50, health <= 200.")

    env = load_env()
    secret = env.get("WHATSAPP_APP_SECRET", "")
    if (args.burst or args.dupes) and not secret:
        raise SystemExit("WHATSAPP_APP_SECRET missing in .env -- copy it from "
                         "Secrets Manager (local only; .env is gitignored).")

    if args.health:
        with ThreadPoolExecutor(max_workers=min(args.health, 50)) as pool:
            results = list(pool.map(lambda _: get_health(url), range(args.health)))
        report(f"/health x{args.health}", results)
        ok = sum(1 for c, _ in results if c == 200)
        print(f"   PASS if all 200: {'PASS' if ok == len(results) else 'CHECK'}")

    if args.burst:
        def one(i):
            wa_id = args.to or f"91900000{7000 + i:04d}"
            return post_message(url, secret, wa_id,
                                f"wamid.loadtest.{uuid.uuid4().hex}", QUESTION)
        with ThreadPoolExecutor(max_workers=min(args.burst, 25)) as pool:
            results = list(pool.map(one, range(args.burst)))
        report(f"burst x{args.burst}" + (" (your number)" if args.to else " (fake students)"),
               results)
        if args.to:
            print("   PASS: all 200 and the replies arrive on your phone.")
        else:
            print("   PASS: no EXC entries and CloudWatch shows clean handling.\n"
                  "   (5xx here is EXPECTED: replies to fake numbers cannot deliver.)")

    if args.dupes:
        message_id = f"wamid.dupetest.{uuid.uuid4().hex}"
        wa_id = args.to or "919000007999"
        def dupe(_):
            return post_message(url, secret, wa_id, message_id, QUESTION)
        with ThreadPoolExecutor(max_workers=min(args.dupes, 25)) as pool:
            results = list(pool.map(dupe, range(args.dupes)))
        report(f"duplicate storm x{args.dupes} (one message id)", results)
        print("   PASS: exactly ONE processing in CloudWatch; the rest "
              "deduplicated; at most one reply on the phone.")


if __name__ == "__main__":
    main()
