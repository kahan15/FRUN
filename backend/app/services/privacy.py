from app.core.errors import AppError
from app.core.security import digest, password_matches
from app.repositories.privacy import Privacy
from app.repositories.users import Users


class AccountPrivacy:
    def __init__(self, repo: Privacy):
        self.repo = repo

    def delete(self, user, request):
        users = Users(self.repo.session)
        if users.throttle(digest("delete-account:" + str(user["id"]))) > 5:
            raise AppError(
                "rate_limited", "Too many deletion attempts. Try again in 15 minutes.", 429
            )
        self.repo.game_lock()
        current = users.one("SELECT * FROM users WHERE id=:id AND is_active FOR UPDATE", id=user["id"])
        if not current:
            raise AppError("unauthorized", "Please check the deletion status.", 401)
        if self.repo.receipt(request.request_id):
            raise AppError("deletion_id_conflict", "Use a new deletion request identifier.", 409)
        if not password_matches(current["password_hash"], request.password):
            raise AppError(
                "incorrect_password", "Enter your current password to delete your account.", 403
            )
        self.repo.erase_account(current, request.request_id)
        return {"completed": True}

    def status(self, request_id):
        # A random UUID capability discloses only completion, never identity or user data.
        # No account/session is needed after deletion revokes every session.
        return {"completed": self.repo.receipt(request_id) is not None}
