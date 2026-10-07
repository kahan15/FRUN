from dataclasses import dataclass, field
from math import log

from pyproj import Geod

from app.schemas.contracts import Fix, RunUpload

GEOD = Geod(ellps="WGS84")
# Conservative performance anchors, not a claim to be an exhaustive current record registry.
# Provenance and interpolation limitations are documented in docs/decisions.md.
MEN = (
    (100.0, 9.58),
    (400.0, 43.03),
    (1500.0, 206.0),
    (5000.0, 755.36),
    (10000.0, 1571.0),
    (21097.5, 3402.0),
    (42195.0, 7170.0),
)
WOMEN = (
    (100.0, 10.49),
    (400.0, 47.60),
    (1500.0, 228.0),
    (5000.0, 838.06),
    (10000.0, 1734.14),
    (21097.5, 3772.0),
    (42195.0, 7796.0),
)


def record_time(distance_m: float, sex: str = "X", anchors=None) -> float:
    if distance_m <= 0:
        return 0
    table = anchors or (WOMEN if sex == "F" else MEN)
    left, right = table[0], table[1]
    for i in range(1, len(table)):
        left, right = table[i - 1], table[i]
        if distance_m <= right[0]:
            break
    exponent = log(right[1] / left[1]) / log(right[0] / left[0])
    return left[1] * (distance_m / left[0]) ** exponent


@dataclass
class Verdict:
    status: str = "accepted"
    reasons: list[str] = field(default_factory=list)
    points: list[Fix] = field(default_factory=list)
    distance_m: float = 0
    duration_s: float = 0
    dropped_point_count: int = 0
    segments: list[list[tuple[float, float]]] = field(default_factory=list)

    def reject(self, reason: str) -> None:
        self.status = "rejected"
        if reason not in self.reasons:
            self.reasons.append(reason)

    def flag(self, reason: str) -> None:
        if self.status != "rejected":
            self.status = "flagged"
        if reason not in self.reasons:
            self.reasons.append(reason)


def inspect_run(run: RunUpload, sex: str, config) -> Verdict:
    result = Verdict()
    result.points = [p for p in run.points if p.accuracy <= config.accuracy_m]
    result.dropped_point_count = len(run.points) - len(result.points)
    if run.ended_at <= run.started_at:
        result.reject("invalid_duration")
    if len(result.points) < 2:
        result.reject("insufficient_accurate_fixes")
        return result
    previous_raw = None
    previous_good = None
    gap = False
    for p in run.points:
        if not run.started_at <= p.timestamp <= run.ended_at:
            result.reject("fix_outside_run")
        if previous_raw is not None and (
            p.timestamp <= previous_raw.timestamp or p.segment < previous_raw.segment
        ):
            result.reject("non_monotonic_timestamps")
        previous_raw = p
        if p.accuracy > config.accuracy_m:
            gap = True
            continue
        a = previous_good
        dt = (p.timestamp - a.timestamp).total_seconds() if a else 0
        if (
            a is None
            or gap
            or a.segment != p.segment
            or dt > getattr(config, "max_fix_gap_seconds", 30)
        ):
            result.segments.append([])
        elif dt > 0:
            _, _, distance = GEOD.inv(a.longitude, a.latitude, p.longitude, p.latitude)
            result.distance_m += distance
            result.duration_s += dt
            if distance > config.teleport_m and dt < config.teleport_seconds:
                result.reject("teleport")
            if distance / dt > config.burst_ms:
                result.reject("burst_speed")
        result.segments[-1].append((p.longitude, p.latitude))
        previous_good = p
        gap = False
    if result.duration_s <= 0:
        result.reject("insufficient_continuous_fixes")
    if result.distance_m > 0:
        # A record curve is a heuristic, not proof of dishonesty. Margins absorb GPS inflation.
        anchors = getattr(config, "pace_records_women" if sex == "F" else "pace_records_men", None)
        if result.duration_s < record_time(result.distance_m, sex, anchors) * (
            1 - config.pace_margin
        ):
            if 100 <= result.distance_m <= 42195 * 1.01:
                result.reject("pace_ceiling")
            else:
                result.flag("pace_outside_verified_range")
        if run.step_count is not None:
            stride = result.distance_m / run.step_count if run.step_count else float("inf")
            if not config.min_stride_m <= stride <= config.max_stride_m:
                result.flag("unusual_stride")
    return result
