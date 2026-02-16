import unittest
from unittest.mock import patch

import main


class ModelSwitchCancelOrderTests(unittest.TestCase):
    def test_cycle_model_cancels_before_probe(self):
        cfg = {"model": "gpt-4o", "available_models": ["gpt-4o", "gpt-5.2"]}
        order = []

        def _cancel(_reason: str) -> bool:
            order.append("cancel")
            return True

        def _probe(_model: str):
            order.append("probe")
            return False, "probe failed"

        with patch.object(main, "get_config", return_value=cfg), patch.object(
            main, "_cancel_active_solve", side_effect=_cancel
        ), patch.object(main, "_probe_model_runtime", side_effect=_probe), patch.object(
            main, "set_status", return_value=None
        ):
            main.cycle_model_worker(icon=None)

        self.assertGreaterEqual(len(order), 2)
        self.assertEqual(order[0], "cancel")
        self.assertEqual(order[1], "probe")

    def test_ui_model_change_cancels_before_probe(self):
        cfg = {"model": "gpt-4o", "available_models": ["gpt-4o", "gpt-5.2"]}
        order = []

        def _cancel(_reason: str) -> bool:
            order.append("cancel")
            return True

        def _probe(_model: str):
            order.append("probe")
            return False, "probe failed"

        with patch.object(main, "get_config", return_value=cfg), patch.object(
            main, "_cancel_active_solve", side_effect=_cancel
        ), patch.object(main, "_probe_model_runtime", side_effect=_probe), patch.object(
            main, "set_status", return_value=None
        ):
            main._set_model_from_ui(icon=None, model_name="gpt-5.2", source="tray")

        self.assertGreaterEqual(len(order), 2)
        self.assertEqual(order[0], "cancel")
        self.assertEqual(order[1], "probe")


if __name__ == "__main__":
    unittest.main()
