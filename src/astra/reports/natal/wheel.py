"""Колесо натальной карты на ReportLab canvas.

Геометрия отделена от рисования и тестируется без canvas:
- screen_angle — перевод эклиптической долготы в экранный угол (ASC слева);
- relax_angles — 1-D разрешение коллизий подписей планет на кольце.

Кольца (доли радиуса R): зодиак 0.86–1.0, тики 0.82–0.86,
планеты ~0.68, хорды аспектов внутри 0.55.
"""

from __future__ import annotations

import math

from astra.astro.schemas import FullNatalChart
from astra.reports.natal.glyphs import FONT_GLYPHS, POINT_GLYPH, SIGN_GLYPHS
from astra.reports.theme import (
    ASPECT_STYLES,
    BG_CARD_DEEP,
    CREAM,
    FONT,
    FONT_BOLD,
    GOLD,
    GOLD_DIM,
    GOLD_LIGHT,
    MUTED,
)

MIN_GAP_DEG = 7.0
CONNECTOR_THRESHOLD_DEG = 2.0

_ZODIAC_INNER = 0.86
_TICK_INNER = 0.82
_PLANET_RING = 0.68
_ASPECT_RING = 0.55
_HOUSE_NUM_RING = 0.76
_SIGN_GLYPH_RING = 0.93


def screen_angle(lon: float, rotation_lon: float) -> float:
    """Экранный угол (0°=восток, против часовой): rotation_lon попадает на запад (180°)."""
    return (180.0 + (lon - rotation_lon)) % 360.0


def polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def relax_angles(angles: list[float], min_gap: float = MIN_GAP_DEG) -> list[float]:
    """Раздвинуть углы на окружности до min_gap, сохранив порядок.

    Круг разрезается по наибольшему разрыву (кластер не может его пересекать),
    дальше — 1-D размещение: скученные точки раздвигаются симметрично вокруг
    центра кластера, одиночные не двигаются. Выход — в порядке входа.
    """
    n = len(angles)
    if n <= 1:
        return list(angles)
    if n * min_gap >= 360.0:
        # вырожденный случай: равномерно по кругу
        order = sorted(range(n), key=lambda i: angles[i])
        step = 360.0 / n
        out = [0.0] * n
        for rank, idx in enumerate(order):
            out[idx] = (angles[order[0]] + rank * step) % 360.0
        return out

    order = sorted(range(n), key=lambda i: angles[i])
    sorted_angles = [angles[i] % 360.0 for i in order]

    # разрез круга по наибольшему разрыву
    gaps = [(sorted_angles[(k + 1) % n] - sorted_angles[k]) % 360.0 for k in range(n)]
    cut = max(range(n), key=lambda k: gaps[k])
    base = sorted_angles[(cut + 1) % n]
    line = [(sorted_angles[(cut + 1 + k) % n] - base) % 360.0 for k in range(n)]

    # итеративное слияние кластеров (1-D constrained placement)
    for _ in range(n):
        clusters: list[list[int]] = [[0]]
        for k in range(1, n):
            if line[k] - line[k - 1] < min_gap - 1e-9:
                clusters[-1].append(k)
            else:
                clusters.append([k])
        if all(len(cl) == 1 for cl in clusters):
            break
        for cl in clusters:
            if len(cl) == 1:
                continue
            center = sum(line[k] for k in cl) / len(cl)
            start = center - min_gap * (len(cl) - 1) / 2.0
            for j, k in enumerate(cl):
                line[k] = start + j * min_gap

    out = [0.0] * n
    for k in range(n):
        original_idx = order[(cut + 1 + k) % n]
        out[original_idx] = (base + line[k]) % 360.0
    return out


def wheel_rotation(chart: FullNatalChart) -> float:
    if chart.has_time and chart.asc is not None:
        return chart.asc.lon
    return 0.0


def draw_natal_wheel(
    c,  # noqa: ANN001 — reportlab canvas
    chart: FullNatalChart,
    cx: float,
    cy: float,
    radius: float,
) -> None:
    rotation = wheel_rotation(chart)

    _draw_base_circles(c, cx, cy, radius)
    _draw_zodiac_ring(c, cx, cy, radius, rotation)
    _draw_degree_ticks(c, cx, cy, radius, rotation)
    if chart.has_time and chart.houses:
        _draw_houses(c, chart, cx, cy, radius, rotation)
    _draw_aspect_chords(c, chart, cx, cy, radius, rotation)
    _draw_planets(c, chart, cx, cy, radius, rotation)


def _draw_base_circles(c, cx: float, cy: float, r: float) -> None:  # noqa: ANN001
    c.saveState()
    c.setFillColor(BG_CARD_DEEP)
    c.setFillAlpha(0.75)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.restoreState()
    for ring_r, alpha, width in (
        (r, 0.85, 1.0),
        (r * _ZODIAC_INNER, 0.5, 0.7),
        (r * _TICK_INNER, 0.3, 0.5),
        (r * _ASPECT_RING, 0.35, 0.5),
    ):
        c.saveState()
        c.setStrokeColor(GOLD)
        c.setStrokeAlpha(alpha)
        c.setLineWidth(width)
        c.circle(cx, cy, ring_r, fill=0, stroke=1)
        c.restoreState()


def _draw_zodiac_ring(c, cx: float, cy: float, r: float, rotation: float) -> None:  # noqa: ANN001
    inner = r * _ZODIAC_INNER
    for i in range(12):
        start_lon = i * 30.0
        # разделитель знаков
        angle = screen_angle(start_lon, rotation)
        x1, y1 = polar(cx, cy, inner, angle)
        x2, y2 = polar(cx, cy, r, angle)
        c.saveState()
        c.setStrokeColor(GOLD_DIM)
        c.setStrokeAlpha(0.55)
        c.setLineWidth(0.6)
        c.line(x1, y1, x2, y2)
        c.restoreState()

        # чередующаяся подложка сектора
        if i % 2 == 0:
            c.saveState()
            c.setFillColor(GOLD)
            c.setFillAlpha(0.045)
            path = c.beginPath()
            a0 = screen_angle(start_lon, rotation)
            path.moveTo(*polar(cx, cy, inner, a0))
            steps = 10
            for s in range(steps + 1):
                a = screen_angle(start_lon + 30.0 * s / steps, rotation)
                path.lineTo(*polar(cx, cy, inner, a))
            for s in range(steps, -1, -1):
                a = screen_angle(start_lon + 30.0 * s / steps, rotation)
                path.lineTo(*polar(cx, cy, r, a))
            path.close()
            c.drawPath(path, fill=1, stroke=0)
            c.restoreState()

        # глиф знака в середине сектора
        mid_angle = screen_angle(start_lon + 15.0, rotation)
        gx, gy = polar(cx, cy, r * _SIGN_GLYPH_RING, mid_angle)
        c.saveState()
        c.setFillColor(GOLD_LIGHT)
        c.setFont(FONT_GLYPHS, r * 0.075)
        c.drawCentredString(gx, gy - r * 0.028, SIGN_GLYPHS[i])
        c.restoreState()


def _draw_degree_ticks(c, cx: float, cy: float, r: float, rotation: float) -> None:  # noqa: ANN001
    outer = r * _ZODIAC_INNER
    for deg in range(0, 360, 5):
        is_ten = deg % 10 == 0
        inner = r * (_TICK_INNER if is_ten else (_TICK_INNER + 0.015))
        angle = screen_angle(float(deg), rotation)
        x1, y1 = polar(cx, cy, inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        c.saveState()
        c.setStrokeColor(GOLD_DIM)
        c.setStrokeAlpha(0.5 if is_ten else 0.28)
        c.setLineWidth(0.5 if is_ten else 0.35)
        c.line(x1, y1, x2, y2)
        c.restoreState()


def _draw_houses(
    c,  # noqa: ANN001
    chart: FullNatalChart,
    cx: float,
    cy: float,
    r: float,
    rotation: float,
) -> None:
    houses = chart.houses or []
    outer = r * _ZODIAC_INNER
    inner = r * 0.24
    for cusp in houses:
        angle = screen_angle(cusp.lon, rotation)
        is_angle_cusp = cusp.number in (1, 4, 7, 10)
        x1, y1 = polar(cx, cy, inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        c.saveState()
        c.setStrokeColor(GOLD if is_angle_cusp else MUTED)
        c.setStrokeAlpha(0.8 if is_angle_cusp else 0.3)
        c.setLineWidth(1.1 if is_angle_cusp else 0.45)
        c.line(x1, y1, x2, y2)
        c.restoreState()

    # подписи ASC/MC у концов осей
    if chart.asc is not None:
        ax, ay = polar(cx, cy, r * 1.06, screen_angle(chart.asc.lon, rotation))
        c.saveState()
        c.setFillColor(GOLD_LIGHT)
        c.setFont(FONT_BOLD, r * 0.055)
        c.drawCentredString(ax, ay - r * 0.02, "ASC")
        c.restoreState()
    if chart.mc is not None:
        mx, my = polar(cx, cy, r * 1.06, screen_angle(chart.mc.lon, rotation))
        c.saveState()
        c.setFillColor(GOLD_LIGHT)
        c.setFont(FONT_BOLD, r * 0.055)
        c.drawCentredString(mx, my - r * 0.02, "MC")
        c.restoreState()

    # номера домов в середине сектора
    n = len(houses)
    for i, cusp in enumerate(houses):
        nxt = houses[(i + 1) % n]
        span = (nxt.lon - cusp.lon) % 360.0
        mid_lon = (cusp.lon + span / 2.0) % 360.0
        hx, hy = polar(cx, cy, r * _HOUSE_NUM_RING, screen_angle(mid_lon, rotation))
        c.saveState()
        c.setFillColor(MUTED)
        c.setFont(FONT, r * 0.045)
        c.drawCentredString(hx, hy - r * 0.016, str(cusp.number))
        c.restoreState()


def _draw_aspect_chords(
    c,  # noqa: ANN001
    chart: FullNatalChart,
    cx: float,
    cy: float,
    r: float,
    rotation: float,
) -> None:
    lon_by_point = {p.name: p.lon for p in chart.points}
    if chart.asc is not None:
        lon_by_point["Ascendant"] = chart.asc.lon
    if chart.mc is not None:
        lon_by_point["Medium_Coeli"] = chart.mc.lon

    ring = r * _ASPECT_RING
    for asp in chart.aspects:
        lon1 = lon_by_point.get(asp.p1)
        lon2 = lon_by_point.get(asp.p2)
        if lon1 is None or lon2 is None:
            continue
        color, _, _ = ASPECT_STYLES.get(asp.aspect, (MUTED, "", ""))
        a1 = screen_angle(lon1, rotation)
        a2 = screen_angle(lon2, rotation)
        x1, y1 = polar(cx, cy, ring, a1)
        x2, y2 = polar(cx, cy, ring, a2)
        tight = asp.orb_deg < 2.0
        c.saveState()
        if asp.aspect == "соединение":
            # соединение — не хорда, а свечение в точке
            c.setFillColor(color)
            c.setFillAlpha(0.5 if tight else 0.35)
            c.circle(x1, y1, r * (0.03 if tight else 0.022), fill=1, stroke=0)
        else:
            c.setStrokeColor(color)
            c.setStrokeAlpha(0.75 if tight else 0.4)
            c.setLineWidth(1.1 if tight else 0.6)
            c.line(x1, y1, x2, y2)
        c.restoreState()


def _draw_planets(
    c,  # noqa: ANN001
    chart: FullNatalChart,
    cx: float,
    cy: float,
    r: float,
    rotation: float,
) -> None:
    points = [p for p in chart.points if p.name in POINT_GLYPH]
    true_angles = [screen_angle(p.lon, rotation) for p in points]
    display_angles = relax_angles(true_angles)

    for point, true_angle, display_angle in zip(points, true_angles, display_angles):
        # маркер истинной позиции на кольце аспектов
        mx, my = polar(cx, cy, r * _ASPECT_RING, true_angle)
        c.saveState()
        c.setFillColor(GOLD_LIGHT)
        c.setFillAlpha(0.9)
        c.circle(mx, my, r * 0.012, fill=1, stroke=0)
        c.restoreState()

        gx, gy = polar(cx, cy, r * _PLANET_RING, display_angle)

        # коннектор от маркера к сдвинутому глифу
        displaced = min(
            abs(display_angle - true_angle),
            360.0 - abs(display_angle - true_angle),
        )
        inner_x, inner_y = polar(cx, cy, r * (_ASPECT_RING + 0.02), true_angle)
        glyph_edge_x, glyph_edge_y = polar(cx, cy, r * (_PLANET_RING - 0.045), display_angle)
        c.saveState()
        c.setStrokeColor(MUTED)
        c.setStrokeAlpha(0.4 if displaced > CONNECTOR_THRESHOLD_DEG else 0.25)
        c.setLineWidth(0.4)
        c.line(inner_x, inner_y, glyph_edge_x, glyph_edge_y)
        c.restoreState()

        # глиф планеты
        c.saveState()
        c.setFillColor(CREAM)
        c.setFont(FONT_GLYPHS, r * 0.082)
        c.drawCentredString(gx, gy - r * 0.03, POINT_GLYPH[point.name])
        if point.retrograde:
            c.setFillColor(GOLD)
            c.setFont(FONT_BOLD, r * 0.038)
            c.drawString(gx + r * 0.045, gy + r * 0.02, "R")
        c.restoreState()
