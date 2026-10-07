from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import transform, unary_union
from synthetic_routes import freeform_loop

from app.geo.anticheat import inspect_run, record_time
from app.geo.loops import RouteComplexityError, extract_loops, projection
from app.schemas.contracts import Fix, RunUpload

FWD, INV = projection(-122.42, 37.77)
X, Y = FWD.transform(-122.42, 37.77)


def coordinates(points):
    return [INV.transform(X + x, Y + y) for x, y in points]


def loops(points, **kwargs):
    return extract_loops([coordinates(points)], **kwargs)


def area(polygons):
    return transform(FWD.transform, unary_union(polygons)).area


def test_square():
    result = loops([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    assert len(result) == 1
    assert area(result) == pytest.approx(10000, abs=0.01)


def test_freeform_boundary_follows_recorded_path_not_a_rectangle_or_hull():
    points = freeform_loop()
    expected = Polygon(points)
    result = transform(FWD.transform, unary_union(loops(points)))
    # Compare in the same local metre coordinates as the fixture.
    from shapely.affinity import translate

    result = translate(result, xoff=-X, yoff=-Y)
    assert result.is_valid and len(result.exterior.coords) > 8
    assert result.boundary.hausdorff_distance(LineString(points)) <= 4.01
    assert result.area < expected.envelope.area * 0.8
    assert expected.convex_hull.difference(result).area > expected.area * 0.05


def test_concave_route_does_not_award_the_unvisited_cutout():
    points = [(0, 0), (160, 0), (160, 40), (40, 40), (40, 160), (0, 160), (0, 0)]
    result = transform(FWD.transform, unary_union(loops(points)))
    assert result.area == pytest.approx(11200, abs=0.01)
    assert result.covers(Point(X + 20, Y + 100))
    assert not result.covers(Point(X + 100, Y + 100))


def test_complex_routes_rejected_before_noding(monkeypatch):
    def forbidden_union(*args, **kwargs):
        pytest.fail("Expensive noding must not run after the complexity budget is exceeded")

    monkeypatch.setattr("app.geo.loops.unary_union", forbidden_union)
    with pytest.raises(RouteComplexityError):
        loops(freeform_loop(), max_vertices=10)
    with pytest.raises(RouteComplexityError):
        loops([(0, 0), (100, 100), (0, 100), (100, 0), (0, 0)], max_intersections=1)


@pytest.mark.parametrize(
    "points",
    [
        [(0, 0), (100, 0), (200, 0)],
        [(0, 0), (100, 0), (0, 0)],
        [(0, 0), (30, 1), (50, -1), (100, 1), (0, 0)],
    ],
)
def test_no_loop(points):
    assert loops(points) == []


def test_figure_eight():
    result = loops([(0, 0), (100, 100), (0, 100), (100, 0), (0, 0)])
    assert len(result) == 2
    assert area(result) == pytest.approx(5000, abs=0.01)


def test_lollipop():
    result = loops([(-100, 0), (0, 0), (100, 0), (100, 100), (0, 100), (0, 0), (-100, 0)])
    assert len(result) == 1
    assert area(result) == pytest.approx(10000, abs=0.01)


def test_near_miss():
    assert len(loops([(0, 0), (100, 0), (100, 100), (0, 100), (0, 15)])) == 1


def test_open_lap():
    assert loops([(0, 0), (300, 0), (300, 300), (0, 300), (0, 200)]) == []


def test_nested_loops_do_not_double_count():
    result = loops(
        [
            (0, 0),
            (200, 0),
            (200, 200),
            (0, 200),
            (0, 0),
            (50, 50),
            (150, 50),
            (150, 150),
            (50, 150),
            (50, 50),
            (0, 0),
        ]
    )
    assert area(result) == pytest.approx(40000, abs=0.1)


def test_pauses_cannot_close_a_fake_loop():
    result = extract_loops(
        [coordinates([(0, 0), (100, 0), (100, 100)]), coordinates([(100, 100), (0, 100), (0, 0)])]
    )
    assert result == []


def test_overlapping_segments_union():
    square = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]
    result = extract_loops([coordinates(square), coordinates(square)])
    assert area(result) == pytest.approx(10000, abs=0.1)


def config():
    return SimpleNamespace(
        accuracy_m=30,
        teleport_m=250,
        teleport_seconds=120,
        burst_ms=12.5,
        pace_margin=0.05,
        min_stride_m=0.4,
        max_stride_m=2.6,
    )


def synthetic_run(distance, seconds, steps=None):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    count = max(2, int(distance / 10))
    points = []
    for i in range(count + 1):
        lon, lat = INV.transform(X + distance * i / count, Y)
        points.append(
            Fix(
                latitude=lat,
                longitude=lon,
                accuracy=5,
                timestamp=start + timedelta(seconds=seconds * i / count),
            )
        )
    return RunUpload(
        client_run_id=uuid4(),
        started_at=start,
        ended_at=start + timedelta(seconds=seconds),
        points=points,
        step_count=steps,
    )


@pytest.mark.parametrize(
    "distance,seconds,status",
    [
        (5000, 1800, "accepted"),
        (5000, 810, "accepted"),
        (42195, 6600, "rejected"),
        (42195, 12600, "accepted"),
    ],
)
def test_paces(distance, seconds, status):
    assert inspect_run(synthetic_run(distance, seconds), "M", config()).status == status


def test_stride_flags_but_awards():
    assert inspect_run(synthetic_run(5000, 1800, 500), "X", config()).status == "flagged"


def test_all_dropped():
    run = synthetic_run(1000, 400)
    for p in run.points:
        p.accuracy = 50
    assert "insufficient_accurate_fixes" in inspect_run(run, "X", config()).reasons


def test_teleport():
    run = synthetic_run(1000, 60)
    run.points = [run.points[0], run.points[-1]]
    # A long unobserved interval is a break, never a straight claim edge.
    verdict = inspect_run(run, "X", config())
    assert verdict.distance_m == 0
    assert len(verdict.segments) == 2


def test_timestamps():
    run = synthetic_run(1000, 400)
    run.points[2].timestamp = run.points[0].timestamp
    assert "non_monotonic_timestamps" in inspect_run(run, "X", config()).reasons


def test_curve_monotonic_and_separate():
    distances = [10 * 1.03**n for n in range(350)]
    for sex in ("M", "F", "X"):
        times = [record_time(d, sex) for d in distances]
        assert all(b > a for a, b in zip(times, times[1:]))
    assert all(record_time(d, "F") > record_time(d, "M") for d in distances)


def test_supported_regions():
    with pytest.raises(ValueError):
        extract_loops([[(179, 0), (-179, 0), (-179, 1)]])
    with pytest.raises(ValueError):
        projection(0, 89)


def test_low_accuracy_sample_breaks_continuity():
    run = synthetic_run(100, 100)
    run.points[5].accuracy = 100
    verdict = inspect_run(run, "X", config())
    assert len(verdict.segments) == 2
    assert verdict.distance_m == pytest.approx(80, abs=0.1)


def test_bad_timestamp_in_discarded_point_is_still_rejected():
    run = synthetic_run(100, 100)
    run.points[5].accuracy = 100
    run.points[5].timestamp = run.points[0].timestamp
    assert "non_monotonic_timestamps" in inspect_run(run, "X", config()).reasons


def test_gap_cannot_forge_closure_even_if_client_reuses_segment():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        Fix(longitude=lon, latitude=lat, accuracy=5, timestamp=start + timedelta(seconds=t))
        for (lon, lat), t in zip(
            coordinates([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]), [0, 30, 60, 150, 180]
        )
    ]
    run = RunUpload(
        client_run_id=uuid4(), started_at=start, ended_at=points[-1].timestamp, points=points
    )
    verdict = inspect_run(run, "X", config())
    assert extract_loops(verdict.segments) == []


def test_extent_includes_separate_segments():
    square = [(0, 0), (100, 0), (100, 100), (0, 0)]
    far = [(x + 200000, y) for x, y in square]
    with pytest.raises(ValueError):
        extract_loops([coordinates(square), coordinates(far)])
