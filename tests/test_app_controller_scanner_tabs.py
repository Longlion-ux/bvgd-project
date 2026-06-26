import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.controllers.app_controller import AppController
from app.controllers.kham_benh_controller import KhamBenhTabController
from app.core.tiep_nhan_benh_nhan import remove_history_record_by_identity


class AppControllerScannerTabTests(unittest.TestCase):
    def test_handle_tab_changed_activates_tai_vu_tab(self):
        controller = AppController.__new__(AppController)
        controller.scanner_port_manager = Mock()
        controller._controllers_ready = True
        controller.ui_main = SimpleNamespace(
            tabWidget=SimpleNamespace(widget=lambda index: "tai_vu_widget"),
            tab_kham_benh="kham_benh_widget",
            tab_tiep_nhan="tiep_nhan_widget",
            tab_tai_vu="tai_vu_widget",
        )

        controller.handle_tab_changed(2)

        controller.scanner_port_manager.activate_tab.assert_called_once_with("tai_vu")

    def test_open_serial_port_allows_reopen_after_previous_attempt(self):
        controller = KhamBenhTabController.__new__(KhamBenhTabController)
        controller._scanner_open_timer = Mock()
        controller._scanner_open_timer.isActive.return_value = False
        controller._scanner_open_in_progress = False
        controller._scanner_open_attempted = True

        controller.open_serial_port()

        self.assertFalse(controller._scanner_open_attempted)
        self.assertFalse(controller._scanner_open_in_progress)
        controller._scanner_open_timer.start.assert_called_once_with(0)

    def test_remove_history_record_by_identity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "history.csv"
            pd.DataFrame([
                {
                    "timestamp_luu": "2026-06-26 10:00:00",
                    "STT": "1",
                    "MaYTe": "12345678",
                    "HoTen": "Nguyen Van A",
                    "Tuoi": "30",
                    "GioiTinh": "Nam",
                    "PhongTiepNhan": "Phòng A",
                    "NgayTiepNhan": "2026-06-26 10:00:00",
                    "DoiTuong": "BHYT",
                    "SoBHYT": "123",
                    "CCCD": "",
                },
                {
                    "timestamp_luu": "2026-06-26 10:05:00",
                    "STT": "2",
                    "MaYTe": "87654321",
                    "HoTen": "Tran Van B",
                    "Tuoi": "40",
                    "GioiTinh": "Nữ",
                    "PhongTiepNhan": "Phòng B",
                    "NgayTiepNhan": "2026-06-26 10:05:00",
                    "DoiTuong": "Viện phí",
                    "SoBHYT": "456",
                    "CCCD": "987654321",
                },
            ]).to_csv(file_path, index=False)

            record_to_remove = {
                "timestamp_luu": "2026-06-26 10:05:00",
                "STT": "2",
                "MaYTe": "87654321",
                "HoTen": "Tran Van B",
                "Tuoi": "40",
                "GioiTinh": "Nữ",
                "PhongTiepNhan": "Phòng B",
                "NgayTiepNhan": "2026-06-26 10:05:00",
                "DoiTuong": "Viện phí",
                "SoBHYT": "456",
                "CCCD": "987654321",
            }

            removed = remove_history_record_by_identity(str(file_path), record_to_remove)
            self.assertTrue(removed)

            remaining = pd.read_csv(file_path)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(str(remaining.iloc[0]['MaYTe']), '12345678')


if __name__ == "__main__":
    unittest.main()
