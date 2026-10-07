import argparse
import json
from getpass import getpass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import HASHER
from app.db.session import engine
from app.geo.anticheat import inspect_run
from app.repositories.admin import Admin
from app.repositories.users import Users
from app.schemas.contracts import RunUpload


def main():
    parser = argparse.ArgumentParser(
        description="Local laptop administration; no remote admin API."
    )
    sub = parser.add_subparsers(dest="action", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--limit", type=int, default=50)
    replay = sub.add_parser("replay")
    replay.add_argument("run_id", type=UUID)
    review = sub.add_parser("review")
    review.add_argument("run_id", type=UUID)
    review.add_argument("notes")
    password = sub.add_parser("password")
    password.add_argument("username")
    args = parser.parse_args()
    with Session(engine()) as db, db.begin():
        repo = Admin(db)
        if args.action == "audit":
            print(json.dumps(repo.audit_runs(max(1, min(1000, args.limit))), default=str, indent=2))
        elif args.action == "replay":
            run = repo.raw_run(args.run_id)
            if not run:
                raise SystemExit("Run not found")
            verdict = inspect_run(
                RunUpload.model_validate(run["raw_upload"]), run["sex"], settings()
            )
            print(
                json.dumps(
                    {
                        "status": verdict.status,
                        "reasons": verdict.reasons,
                        "distance_m": verdict.distance_m,
                        "duration_s": verdict.duration_s,
                    },
                    indent=2,
                )
            )
        elif args.action == "review":
            if not repo.review(args.run_id, args.notes):
                raise SystemExit("Run not found")
            print("Review note saved. Awarded geometry was not changed.")
        elif args.action == "password":
            user = Users(db).by_login(args.username)
            if not user:
                raise SystemExit("Runner not found")
            value = getpass("New password: ")
            if not 10 <= len(value) <= 128 or value != getpass("Repeat password: "):
                raise SystemExit("Passwords must match and contain 10–128 characters")
            repo.password(user["id"], HASHER.hash(value))
            print("Password updated and existing sessions revoked.")


if __name__ == "__main__":
    main()
