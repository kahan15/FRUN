from app.core.errors import AppError
from app.repositories.game import Game
from app.repositories.users import Users


class Friends:
    def __init__(self, repo: Users):
        self.repo = repo

    def change(self, action, user_id, other_id):
        if user_id == other_id:
            raise AppError("invalid_friend", "Choose another runner.")
        # Friendship changes use the same lock as claims so permission cannot change mid-carve.
        self.repo.game_lock()
        if not self.repo.by_id(user_id):
            raise AppError("unauthorized", "This account is no longer available.", 401)
        if not self.repo.by_id(other_id):
            raise AppError("not_found", "Runner not found.", 404)
        if action == "block":
            self.repo.block(user_id, other_id)
            return
        if action == "unblock":
            self.repo.unblock(user_id, other_id)
            return
        if self.repo.blocked(user_id, other_id):
            raise AppError("not_found", "Runner not found.", 404)
        existing = self.repo.friendship(user_id, other_id)
        if action == "request":
            if existing:
                raise AppError("friendship_exists", "A friendship or request already exists.", 409)
            self.repo.request(user_id, other_id)
        elif action == "accept":
            if (
                not existing
                or existing["status"] != "pending"
                or existing["addressee_id"] != user_id
            ):
                raise AppError("no_incoming_request", "No incoming request from this runner.", 409)
            self.repo.accept(user_id, other_id)
            Game(self.repo.session).create_contest(user_id, other_id)
        elif action == "remove":
            self.repo.remove(user_id, other_id)
