import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import baselines as bl  # noqa: E402
import selector_s4 as s4  # noqa: E402
import selector_s4_cost as cost  # noqa: E402
import simple_selector as ss  # noqa: E402
import x0_screen as xs  # noqa: E402


class CostPopulation(unittest.TestCase):
    def test_cost_object_universe_equals_frozen_s4_plan(self):
        objects, path_entries = cost.collect_population(
            bl, ss, xs, Path("/pilot"), Path("/x0")
        )
        plan = s4.build_plan()
        expected = set()
        for target in plan["targets"]:
            expected.add(target["target_object_id"])
            expected.update(target["lanes"]["exhaustive"])
        self.assertEqual(set(objects), expected)
        self.assertTrue(path_entries)
        self.assertTrue(all(meta["bytes"] >= 0 for meta in objects.values()))


if __name__ == "__main__":
    unittest.main()
