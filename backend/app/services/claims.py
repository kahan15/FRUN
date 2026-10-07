from datetime import timedelta
from uuid import uuid4

import structlog
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.geo.anticheat import inspect_run
from app.geo.loops import RouteComplexityError, extract_loops, polygonal
from app.repositories.game import Game
from app.repositories.users import Users

log = structlog.get_logger()
# One square centimetre suppresses floating-point boundary dust, far below GPS resolution.
# The deferred SQL guard uses the same tolerance.
AREA_EPSILON_M2 = 0.0001


def expiry(now, config):
    if config.monthly_reset:
        return now.replace(
            year=now.year + (now.month == 12),
            month=now.month % 12 + 1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    return now + timedelta(days=config.territory_days)


class Claims:
    def __init__(self, game: Game, users: Users):
        self.game, self.users = game, users

    def upload(self, user, upload):
        cfg = settings()
        self.game.game_lock()
        if not self.users.by_id(user["id"]):
            raise AppError("unauthorized", "This account is no longer available.", 401)
        existing = self.game.existing_run(upload.client_run_id)
        if existing:
            if existing["user_id"] != user["id"]:
                raise AppError("run_id_conflict", "This run identifier is unavailable.", 409)
            return {**existing["result"], "was_duplicate": True}
        if self.game.recent_count(user["id"]) >= cfg.uploads_per_hour:
            raise AppError("rate_limited", "Upload limit reached. Your phone can retry later.", 429)
        now = self.game.now()
        verdict = inspect_run(upload, user["sex"], cfg)
        if upload.ended_at > now + timedelta(minutes=5):
            verdict.reject("future_timestamp")
        faces = []
        if verdict.status != "rejected":
            try:
                faces = extract_loops(
                    verdict.segments,
                    simplify_m=cfg.simplify_m,
                    close_gap_m=cfg.close_gap_m,
                    min_fragment_m2=cfg.min_fragment_m2,
                    max_extent_m=cfg.max_extent_m,
                    max_vertices=cfg.max_loop_vertices,
                    max_intersections=cfg.max_loop_intersections,
                )
            except RouteComplexityError:
                verdict.reject("route_too_complex")
            except ValueError:
                verdict.reject("unsupported_geographic_extent")
        if verdict.status != "rejected" and not faces:
            verdict.reasons.append("no_valid_loop")
        result = {
            "id": uuid4(),
            "client_run_id": upload.client_run_id,
            "status": verdict.status,
            "reasons": verdict.reasons,
            "fragment_count": len(faces),
            "new_area_m2": 0.0,
            "refreshed_area_m2": 0.0,
            "blocked_area_m2": 0.0,
            "stolen_area_m2": 0.0,
            "steals": [],
            "distance_m": verdict.distance_m,
            "duration_s": verdict.duration_s,
            "was_duplicate": False,
            "created_at": now,
        }
        self.game.insert_run(user["id"], upload, verdict, result)
        if verdict.status != "rejected" and faces:
            self.game.expire()
            self.resolve(user, polygonal(unary_union(faces)), result, now, cfg, upload.started_at)
        self.game.finish_run(result)
        if verdict.status != "accepted":
            log.info(
                "run_review",
                run_id=str(result["id"]),
                status=verdict.status,
                reasons=verdict.reasons,
            )
        return result

    def resolve(self, user, claim, result, now, cfg, started_at=None):
        self.game.prune_contests()
        rows = self.game.intersections(claim, user["id"])
        friend_ids = self.users.friend_ids(user["id"])
        contests = self.game.contests(user["id"])
        expires = expiry(now, cfg)
        original_area = self.game.area(claim)

        # Only accepted friends participate. Hidden independent land never blocks or changes.
        for row in rows:
            if row["owner_id"] not in friend_ids:
                continue
            related = [c for c in contests if row["owner_id"] in (c["owner_a"], c["owner_b"])]
            contested = polygonal(unary_union([c["shape"] for c in related]))
            eligible = polygonal(
                unary_union(
                    [
                        c["shape"]
                        for c in related
                        if started_at is not None and started_at >= c["accepted_at"]
                    ]
                )
            )
            # An older offline run cannot settle a newly created contest, even after cooldown.
            blocked = self.game.operation("ST_Difference", contested, eligible)
            if row["claimed_at"] + timedelta(hours=cfg.cooldown_hours) > now:
                protected = self.game.operation("ST_Difference", row["shape"], eligible)
                blocked = polygonal(unary_union([blocked, protected]))
            claim = self.game.operation("ST_Difference", claim, blocked)
        result["blocked_area_m2"] = max(0, original_area - self.game.area(claim))

        stolen, won_shapes = {}, []
        for row in rows:
            if row["owner_id"] not in friend_ids:
                continue
            overlap = self.game.operation("ST_Intersection", claim, row["shape"])
            amount = self.game.area(overlap)
            if amount <= AREA_EPSILON_M2:
                continue
            remaining = self.game.operation("ST_Difference", row["shape"], claim)
            self.game.carve(row, remaining, user["id"], now)
            won_shapes.append(overlap)
            entry = stolen.setdefault(
                row["owner_id"], {"victim_username": row["username"], "area_m2": 0.0}
            )
            entry["area_m2"] += amount
        for victim, entry in stolen.items():
            self.game.notify(victim, user["username"], entry["area_m2"], result["id"])
            result["steals"].append(entry)
        # Geographic total is a union; per-victim losses may overlap in a three-way contest.
        won = polygonal(unary_union(won_shapes))
        result["stolen_area_m2"] = self.game.area(won)

        for row in rows:
            if row["owner_id"] != user["id"]:
                continue
            overlap = self.game.operation("ST_Intersection", claim, row["shape"])
            amount = self.game.area(overlap)
            if amount > AREA_EPSILON_M2:
                settled = self.game.operation("ST_Intersection", overlap, won)
                self.game.renew_slice(row, overlap, settled, expires, now, result["id"])
                result["refreshed_area_m2"] += amount
            claim = self.game.operation("ST_Difference", claim, row["shape"])

        for fragment in claim.geoms:
            geometry = polygonal(fragment)
            if self.game.area(geometry) > AREA_EPSILON_M2:
                self.game.add_territory(user["id"], result["id"], geometry, now, expires)
                result["new_area_m2"] += self.game.area(geometry)
        self.game.prune_contests()
