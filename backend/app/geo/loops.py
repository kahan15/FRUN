from functools import lru_cache
from math import floor

from pyproj import CRS, Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, transform, unary_union
from shapely.strtree import STRtree


class RouteComplexityError(ValueError):
    """The route exceeds the bounded geometry work allowed for a single capture."""


def check_complexity(lines, max_vertices, max_intersections):
    count = sum(len(line.coords) for line in lines)
    if count > max_vertices:
        raise RouteComplexityError("Too many simplified route vertices")
    edges = [
        LineString([a, b]) for line in lines for a, b in zip(line.coords, list(line.coords)[1:])
    ]
    tree = STRtree(edges)
    intersections = 0
    for index, edge in enumerate(edges):
        # Query one edge at a time, never materialize a quadratic all-pairs matrix.
        # Include shared endpoints for a conservative bound on noding/union work.
        intersections += sum(
            int(other) > index for other in tree.query(edge, predicate="intersects")
        )
        if intersections > max_intersections:
            raise RouteComplexityError("Too many route intersections")


@lru_cache(maxsize=128)
def transformers(epsg: int) -> tuple[Transformer, Transformer]:
    metric = CRS.from_epsg(epsg)
    return (
        Transformer.from_crs(4326, metric, always_xy=True),
        Transformer.from_crs(metric, 4326, always_xy=True),
    )


def projection(lon: float, lat: float) -> tuple[Transformer, Transformer]:
    if not -80 <= lat <= 84:
        raise ValueError("Runs outside UTM's supported latitude range are not supported yet.")
    zone = min(60, max(1, floor((lon + 180) / 6) + 1))
    return transformers((32600 if lat >= 0 else 32700) + zone)


def polygonal(geometry) -> MultiPolygon:
    clean = geometry.buffer(0)
    if clean.is_empty:
        return MultiPolygon()
    if isinstance(clean, Polygon):
        return MultiPolygon([clean])
    if isinstance(clean, MultiPolygon):
        return clean
    return MultiPolygon([g for g in clean.geoms if isinstance(g, Polygon)])


def extract_loops(
    segments: list[list[tuple[float, float]]],
    *,
    simplify_m: float = 4,
    close_gap_m: float = 30,
    min_fragment_m2: float = 200,
    max_extent_m: float = 100000,
    max_vertices: int = 10000,
    max_intersections: int = 20000,
) -> list[Polygon]:
    coordinates = [p for segment in segments for p in segment]
    if len(coordinates) < 3:
        return []
    lons, lats = zip(*coordinates)
    if max(lons) - min(lons) > 180:
        raise ValueError("Antimeridian-crossing tracks are not supported yet.")
    if min(lats) < -80 or max(lats) > 84:
        raise ValueError("Run exceeds supported latitudes.")
    forward, inverse = projection(sum(lons) / len(lons), sum(lats) / len(lats))
    projected = [forward.transform(*p) for p in coordinates]
    xs, ys = zip(*projected)
    if max(max(xs) - min(xs), max(ys) - min(ys)) > max_extent_m:
        raise ValueError("Run exceeds the supported geographic extent.")
    metric_segments = []
    for segment in segments:
        if len(segment) < 3:
            continue
        line = transform(forward.transform, LineString(segment))
        minx, miny, maxx, maxy = line.bounds
        if max(maxx - minx, maxy - miny) > max_extent_m:
            raise ValueError("Run exceeds the supported geographic extent.")
        # Simplifying before noding prevents a traffic-light GPS knot becoming many claims.
        line = line.simplify(simplify_m, preserve_topology=False)
        points = list(line.coords)
        if len(points) < 3:
            continue
        if 0 < LineString([points[0], points[-1]]).length <= close_gap_m:
            points.append(points[0])
        metric_segments.append(LineString(points))
    check_complexity(metric_segments, max_vertices, max_intersections)
    # Never bridge a pause or lost GPS segment; each traced segment must seal its own faces.
    faces = [
        face
        for segment in metric_segments
        for face in polygonize(unary_union(segment))
        if face.area >= min_fragment_m2
    ]  # Jitter floor, not a gameplay minimum.
    if not faces:
        return []
    # Faces from separate tracking segments may overlap; union before awarding any area.
    clean = polygonal(unary_union(faces))
    return [transform(inverse.transform, p) for p in clean.geoms]
