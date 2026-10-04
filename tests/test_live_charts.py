import math
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from render_live_convergence import render_svg  # noqa: E402


class LiveChartTests(unittest.TestCase):
    def chart(self, attempts=50):
        return {"title": "Measured distance", "unit": "lower is closer", "series": [
            {"id": key, "label": key, "values": [0.5] * (attempts + 1)}
            for key in ("candidate", "retained", "base", "style", "benchmark")
        ]}

    def test_all_five_conditions_include_every_attempt(self):
        root = ET.fromstring(render_svg([self.chart()], 50, "50 recorded attempts"))
        lines = root.findall(".//{http://www.w3.org/2000/svg}polyline")
        self.assertEqual({line.attrib["data-series-id"] for line in lines},
                         {"candidate", "retained", "base", "style", "benchmark"})
        self.assertTrue(all(len(line.attrib["points"].split()) == 51 for line in lines))

    def test_zero_attempts_and_flat_scores_remain_valid(self):
        root = ET.fromstring(render_svg([self.chart(0)], 0, "Initial draft"))
        self.assertEqual(len(root.findall(".//{http://www.w3.org/2000/svg}polyline")), 5)

    def test_unavailable_features_never_show_zero_match_lines(self):
        chart = self.chart()
        chart["availability"] = "unavailable"
        svg = render_svg([chart], 50, "Recorded run")
        self.assertNotIn("<polyline", svg)
        self.assertIn("Not measured", svg)

    def test_missing_observations_cannot_be_drawn(self):
        chart = self.chart()
        chart["series"][0]["values"].pop()
        with self.assertRaisesRegex(ValueError, "all attempted iterations"):
            render_svg([chart], 50, "Recorded run")

    def test_no_eligible_draft_leaves_a_gap_instead_of_zero(self):
        chart = self.chart(2)
        chart["series"][1]["values"] = [None, 0.5, None]
        root = ET.fromstring(render_svg([chart], 2, "Three observations"))
        retained = [line for line in root.findall(".//{http://www.w3.org/2000/svg}polyline")
                    if line.attrib["data-series-id"] == "retained"]
        self.assertEqual(len(retained), 1)
        self.assertEqual(len(retained[0].attrib["points"].split()), 1)

    def test_nonfinite_or_boolean_values_cannot_be_drawn(self):
        for value in (math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                chart = self.chart()
                chart["series"][0]["values"][0] = value
                with self.assertRaisesRegex(ValueError, "finite recorded measurements"):
                    render_svg([chart], 50, "Recorded run")

    def test_text_is_xml_escaped(self):
        chart = self.chart()
        chart["title"] = 'x < y & "z"'
        ET.fromstring(render_svg([chart], 50, "Test & measure <drafts>"))

    def test_negative_or_boolean_attempts_rejected(self):
        for attempts in (-1, True):
            with self.subTest(attempts=attempts), self.assertRaisesRegex(ValueError, "nonnegative integer"):
                render_svg([], attempts, "Recorded run")


if __name__ == "__main__":
    unittest.main()
