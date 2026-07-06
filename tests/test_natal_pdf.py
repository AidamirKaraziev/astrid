"""Тесты PDF натала: покрытие глифов, геометрия колеса, smoke-сборка."""

import pytest

from astra.reports.natal.wheel import (
    MIN_GAP_DEG,
    relax_angles,
    screen_angle,
    wheel_rotation,
)


def _circular_gap(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


class TestGlyphCoverage:
    def test_bundled_font_covers_all_glyphs(self):
        """Урок синастрии: .notdef ушёл в прод незамеченным. Пиним покрытие."""
        from reportlab.pdfbase.ttfonts import TTFont

        from astra.reports.natal.fonts import bundled_fonts_dir, verify_glyph_coverage

        font = TTFont("GlyphTest", str(bundled_fonts_dir() / "DejaVuSans.ttf"))
        assert verify_glyph_coverage(font) == []

    def test_register_natal_fonts(self):
        from astra.reports.natal.fonts import register_natal_fonts

        register_natal_fonts()  # не должно бросить

    def test_every_chart_point_has_glyph(self):
        from astra.reports.natal.glyphs import POINT_GLYPH

        expected = {
            "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
            "Uranus", "Neptune", "Pluto", "Chiron", "Mean_Lilith",
            "True_North_Lunar_Node", "True_South_Lunar_Node",
        }
        assert set(POINT_GLYPH) == expected


class TestWheelGeometry:
    def test_screen_angle_asc_on_left(self):
        assert screen_angle(185.7, 185.7) == pytest.approx(180.0)
        # +90° по зодиаку → нижняя точка экрана (270°)
        assert screen_angle(275.7, 185.7) == pytest.approx(270.0)

    def test_relax_keeps_spread_angles(self):
        angles = [0.0, 90.0, 180.0, 270.0]
        assert relax_angles(angles) == pytest.approx(angles)

    def test_relax_separates_cluster(self):
        angles = [100.0, 101.0, 102.0, 250.0]
        out = relax_angles(angles)
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                assert _circular_gap(out[i], out[j]) >= MIN_GAP_DEG - 0.01
        # порядок входа сохранён (кластер раздвинут симметрично)
        assert out[0] < out[1] < out[2]
        assert _circular_gap(out[3], 250.0) < 1.0  # одиночная точка не сдвинута

    def test_relax_preserves_input_order_mapping(self):
        angles = [200.0, 10.0, 12.0]
        out = relax_angles(angles)
        assert _circular_gap(out[0], 200.0) < 1.0
        assert out[1] < out[2]

    def test_relax_wraparound_cluster(self):
        angles = [358.0, 359.0, 1.0, 2.0]
        out = relax_angles(angles)
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                assert _circular_gap(out[i], out[j]) >= MIN_GAP_DEG - 0.01

    def test_relax_degenerate_many_points(self):
        angles = [float(i) for i in range(60)]  # 60 точек по 1° — не влезают
        out = relax_angles(angles)
        assert len(out) == 60
        gaps = sorted(out)
        for a, b in zip(gaps, gaps[1:]):
            assert b - a >= 360.0 / 60 - 0.01


class TestNatalPdfSmoke:
    @pytest.fixture(scope="class")
    def sample_report(self):
        pytest.importorskip("kerykeion")
        from astra.reports.natal.sample_data import sample_natal_report

        return sample_natal_report()

    def test_wheel_rotation(self, sample_report):
        assert wheel_rotation(sample_report.chart) == sample_report.chart.asc.lon

    def test_pdf_builds_with_consistent_page_count(self, tmp_path, sample_report):
        from astra.reports.natal.builder import NatalPdfBuilder

        out = tmp_path / "natal.pdf"
        builder = NatalPdfBuilder(str(out), sample_report)
        builder.build()
        assert out.stat().st_size > 10_000
        # двойной проход: реальное число страниц совпало с симуляцией
        assert builder.page_num == builder.total_pages
        assert builder.total_pages >= 10

    def test_pdf_builds_without_birth_time(self, tmp_path):
        pytest.importorskip("kerykeion")
        import dataclasses
        from datetime import date

        from astra.astro.calculator import build_full_natal_chart
        from astra.reports.natal.builder import NatalPdfBuilder
        from astra.reports.natal.sample_data import sample_natal_report

        chart = build_full_natal_chart(
            name="Тест", birth_date=date(1990, 6, 15), birth_time=None,
            lat=55.7558, lon=37.6176, timezone="Europe/Moscow",
        )
        report = dataclasses.replace(
            sample_natal_report(),
            chart=chart,
            personality=sample_natal_report().personality[:2],  # без ASC-карточки
            accuracy_note="Время рождения не указано: асцендент и дома не рассчитаны.",
        )
        out = tmp_path / "natal_no_time.pdf"
        builder = NatalPdfBuilder(str(out), report)
        builder.build()
        assert builder.page_num == builder.total_pages
