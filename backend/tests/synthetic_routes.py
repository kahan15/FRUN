"""Synthetic paths only; these are not personal GPS recordings."""

from math import cos, pi, sin


def freeform_loop(samples=180):
    points = []
    for i in range(samples):
        angle = 2 * pi * i / samples
        radius = 90 + 22 * cos(3 * angle) + 14 * sin(5 * angle)
        points.append((radius * cos(angle), radius * sin(angle)))
    return points + [points[0]]
