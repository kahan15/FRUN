"""Decision tests complement, but do not replace, the real-PostGIS suite."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from shapely.geometry import box

from app.geo.loops import polygonal
from app.services.claims import Claims, expiry

NOW = datetime(2026, 1, 20, tzinfo=timezone.utc)


class MemoryGame:
    def __init__(self, rows):
        self.rows = rows
        self.new = []
        self.notes = []
        self.refreshed = []

    def intersections(self, claim, user_id):
        return [dict(r) for r in self.rows if r["shape"].intersects(claim)]

    def normalize(self, geometry):
        return geometry

    def prune_contests(self):
        pass

    def contests(self, user_id):
        return getattr(self, "contest_rows", [])

    def operation(self, op, a, b):
        return polygonal(a.difference(b) if op == "ST_Difference" else a.intersection(b))

    def area(self, shape):
        return shape.area

    def carve(self, row, shape, winner, now):
        next(r for r in self.rows if r["id"] == row["id"])["shape"] = shape

    def renew_slice(self, row, overlap, won, expires, now, run_id):
        self.refreshed.append((row["id"], overlap, won))

    def add_territory(self, uid, rid, shape, now, expires):
        self.new.append(shape)

    def notify(self, victim, username, area, rid):
        self.notes.append((victim, area))


def resolve(kind, protected=False, shape=None):
    user, friend, stranger = uuid4(), uuid4(), uuid4()
    owner = {"own": user, "friend": friend, "stranger": stranger}[kind]
    row = {
        "id": uuid4(),
        "owner_id": owner,
        "username": "other",
        "shape": shape or box(0, 0, 100, 100),
        "claimed_at": NOW - timedelta(hours=1 if protected else 7),
    }
    repo = MemoryGame([row])
    users = SimpleNamespace(friend_ids=lambda _: {friend})
    result = {
        "id": uuid4(),
        "new_area_m2": 0,
        "stolen_area_m2": 0,
        "refreshed_area_m2": 0,
        "steals": [],
    }
    config = SimpleNamespace(cooldown_hours=6, territory_days=30, monthly_reset=False)
    Claims(repo, users).resolve(
        {"id": user, "username": "runner"}, polygonal(box(50, 0, 150, 100)), result, NOW, config
    )
    return result, repo


def test_stranger_independent():
    result, repo = resolve("stranger")
    assert result["blocked_area_m2"] == 0
    assert result["new_area_m2"] == 10000
    assert repo.rows[0]["shape"].area == 10000
    assert repo.notes == []


def test_cooldown():
    result, repo = resolve("friend", protected=True)
    assert result["blocked_area_m2"] == 5000
    assert not repo.notes


def test_partial_carving_and_notification():
    result, repo = resolve("friend")
    assert result["stolen_area_m2"] == 5000
    assert repo.rows[0]["shape"].area == 5000
    assert len(repo.notes) == 1
    assert sum(p.intersection(repo.rows[0]["shape"]).area for p in repo.new) == 0


def test_refresh_without_area_gain():
    result, repo = resolve("own")
    assert result["refreshed_area_m2"] == 5000
    assert result["new_area_m2"] == 5000
    assert len(repo.refreshed) == 1


def test_adjacency_does_not_refresh_or_steal():
    result, repo = resolve("friend", shape=box(-50, 0, 50, 100))
    assert result["stolen_area_m2"] == 0
    assert result["new_area_m2"] == 10000
    assert not repo.notes


def test_expiry_modes():
    assert expiry(NOW, SimpleNamespace(monthly_reset=False, territory_days=30)) == NOW + timedelta(
        days=30
    )
    assert expiry(NOW, SimpleNamespace(monthly_reset=True)) == datetime(
        2026, 2, 1, tzinfo=timezone.utc
    )
    assert expiry(NOW.replace(month=12), SimpleNamespace(monthly_reset=True)).year == 2027


def test_contest_bypasses_cooldown_only_for_subsequent_run_and_captured_slice():
    a, b = uuid4(), uuid4()
    rows = [
        dict(
            id=uuid4(),
            owner_id=uid,
            username=str(uid),
            shape=polygonal(box(0, 0, 100, 100)),
            claimed_at=NOW,
            expires_at=NOW + timedelta(days=1),
        )
        for uid in (a, b)
    ]
    config = SimpleNamespace(cooldown_hours=6, territory_days=30, monthly_reset=False)
    for age, stolen in [(timedelta(seconds=-1), 0), (timedelta(seconds=1), 5000)]:
        repo = MemoryGame([dict(row) for row in rows])
        repo.contest_rows = [
            dict(owner_a=a, owner_b=b, accepted_at=NOW, shape=polygonal(box(0, 0, 100, 100)))
        ]
        result = dict(id=uuid4(), new_area_m2=0, refreshed_area_m2=0, steals=[])
        Claims(repo, SimpleNamespace(friend_ids=lambda _: {b})).resolve(
            dict(id=a, username="a"),
            polygonal(box(50, 0, 150, 100)),
            result,
            NOW + timedelta(seconds=10),
            config,
            NOW + age,
        )
        assert result["stolen_area_m2"] == stolen
        assert result["new_area_m2"] == 5000
        assert repo.rows[1]["shape"].area == 10000 - stolen
        if stolen:
            assert repo.refreshed[0][2].area == 5000  # winner receives fresh protection


def test_three_way_contest_counts_geographic_area_once():
    a, b, c = uuid4(), uuid4(), uuid4()
    repo = MemoryGame(
        [
            dict(
                id=uuid4(),
                owner_id=uid,
                username=str(uid),
                shape=polygonal(box(0, 0, 100, 100)),
                claimed_at=NOW,
            )
            for uid in (b, c)
        ]
    )
    repo.contest_rows = [
        dict(owner_a=b, owner_b=c, accepted_at=NOW, shape=polygonal(box(0, 0, 100, 100)))
    ]
    result = dict(id=uuid4(), new_area_m2=0, refreshed_area_m2=0, steals=[])
    Claims(repo, SimpleNamespace(friend_ids=lambda _: {b, c})).resolve(
        dict(id=a, username="a"),
        polygonal(box(0, 0, 100, 100)),
        result,
        NOW + timedelta(seconds=10),
        SimpleNamespace(cooldown_hours=6, territory_days=30, monthly_reset=False),
        NOW + timedelta(seconds=1),
    )
    assert result["stolen_area_m2"] == 10000
    assert sum(s["area_m2"] for s in result["steals"]) == 20000
    assert result["new_area_m2"] == 10000
