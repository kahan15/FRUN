import argparse
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.repositories.game import Game
from app.repositories.outbox import Outbox


def once():
    with Session(engine()) as db, db.begin():
        game = Game(db)
        game.game_lock()
        count = game.expire()
        game.prune_contests()
        Outbox(db).cleanup_attempts()
        game.execute("DELETE FROM password_recoveries WHERE expires_at<=clock_timestamp()")
    print(f"Expired {count} territories", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        once()
        if args.once:
            return
        time.sleep(settings().worker_interval_seconds)


if __name__ == "__main__":
    main()
