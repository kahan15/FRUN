"""Optional APNs worker. Disabled in Compose unless the push profile is selected."""

import time
from pathlib import Path

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.repositories.outbox import Outbox


def main():
    cfg = settings()
    if not all((cfg.apns_key_path, cfg.apns_key_id, cfg.apns_team_id, cfg.apns_topic)):
        raise SystemExit(
            "Set APNS_KEY_PATH, APNS_KEY_ID, APNS_TEAM_ID and APNS_TOPIC before enabling push."
        )
    key = Path(cfg.apns_key_path).read_text()
    base = (
        "https://api.sandbox.push.apple.com" if cfg.apns_sandbox else "https://api.push.apple.com"
    )
    with httpx.Client(http2=True, timeout=10) as client:
        token, token_time = "", 0.0
        while True:
            if time.time() - token_time > 3000:
                token_time = time.time()
                token = jwt.encode(
                    {"iss": cfg.apns_team_id, "iat": int(token_time)},
                    key,
                    algorithm="ES256",
                    headers={"kid": cfg.apns_key_id},
                )
            found = False
            with Session(engine()) as db, db.begin():
                repo = Outbox(db)
                note = repo.pending()
                if note:
                    found = True
                    devices = repo.devices(note)
                    failures = []
                    for device in devices:
                        try:
                            response = client.post(
                                f"{base}/3/device/{device['apns_token']}",
                                headers={
                                    "authorization": f"bearer {token}",
                                    "apns-topic": cfg.apns_topic,
                                    "apns-push-type": "alert",
                                    "apns-priority": "10",
                                    "apns-id": str(note["id"]),
                                    "apns-collapse-id": str(note["id"]),
                                },
                                json={
                                    "aps": {
                                        "alert": {"title": note["title"], "body": note["body"]},
                                        "sound": "default",
                                    },
                                    "notification_id": str(note["id"]),
                                    **note["payload"],
                                },
                            )
                            if response.status_code == 200:
                                repo.delivered(note["id"], device["id"])
                            elif response.status_code == 410 or (
                                response.status_code == 400
                                and response.json().get("reason") == "BadDeviceToken"
                            ):
                                repo.deactivate(device["id"])
                            else:
                                failures.append(f"apns_http_{response.status_code}")
                        except httpx.HTTPError:
                            failures.append("apns_network_error")
                    if failures:
                        repo.retry(note["id"], note["attempts"], ",".join(failures))
                    elif devices:
                        repo.finish(note["id"])
                    else:
                        repo.retry(note["id"], max(note["attempts"], 10), "no_pending_devices")
            if not found:
                time.sleep(5)


if __name__ == "__main__":
    main()
