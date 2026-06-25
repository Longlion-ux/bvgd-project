import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.controllers.app_controller import AppController


class AppControllerScannerTabTests(unittest.TestCase):
    def test_handle_tab_changed_activates_tai_vu_tab(self):
        controller = AppController.__new__(AppController)
        controller.scanner_port_manager = Mock()
        controller.ui_main = SimpleNamespace(
            tabWidget=SimpleNamespace(widget=lambda index: "tai_vu_widget"),
            tab_kham_benh="kham_benh_widget",
            tab_tiep_nhan="tiep_nhan_widget",
            tab_tai_vu="tai_vu_widget",
        )

        controller.handle_tab_changed(2)

        controller.scanner_port_manager.activate_tab.assert_called_once_with("tai_vu")


if __name__ == "__main__":
    unittest.main()
