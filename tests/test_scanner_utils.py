import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QLineEdit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from app.utils.scanner_utils import (
    parse_scanned_data,
    should_skip_scanner_input,
    normalize_scanned_text,
)
from app.controllers.tiep_nhan_controller import TiepNhanTabController


class ScannerUtilsTests(unittest.TestCase):
    def test_parse_scanned_data_extracts_cccd_fields(self):
        raw = "038095011111|123456789|Nguyễn Văn A|Nam|15101995|Số 123 Đường Lê Lợi, TP.HCM|20102021"
        parsed = parse_scanned_data(raw)

        self.assertEqual(parsed["cccd"], "038095011111")
        self.assertEqual(parsed["ho_ten"], "Nguyễn Văn A")
        self.assertEqual(parsed["gioi_tinh"], "Nam")
        self.assertEqual(parsed["ngay_sinh"], "15101995")
        self.assertEqual(parsed["dia_chi"], "Số 123 Đường Lê Lợi, TP.HCM")

    def test_normalize_scanned_text_handles_unicode(self):
        raw = "Traần Nguyễn Gia Long"
        normalized = normalize_scanned_text(raw)
        self.assertIn("Trần Nguyễn Gia Long", normalized)

    def test_parse_scanned_data_handles_key_value_payloads(self):
        raw = "MaYTe:09081018|BHYT:HC4790205263520|MaDT:43|Ten:Phan Nguyen Quoc Tuan|Tuoi:46|GT:Nam|DC:220/24/16e Hoang Hoa Tham|SDT:0984129162|Tien:78.309,000 VND|Loai:THUOC|DS:3973:1"
        parsed = parse_scanned_data(raw)

        self.assertEqual(parsed["ma_y_te"], "09081018")
        self.assertEqual(parsed["ho_ten"], "Phan Nguyen Quoc Tuan")
        self.assertEqual(parsed["gioi_tinh"], "Nam")
        self.assertEqual(parsed["bill_type"], "THUOC")
        self.assertEqual(parsed["ds_string"], "3973:1")

    def test_parse_scanned_data_handles_simple_bill_payloads(self):
        raw = "DON_THUOC|2026-06-25|Nguyễn Văn A|Paracetamol 500mg|Uống sau ăn 2 viên/lần, 3 lần/ngày"
        parsed = parse_scanned_data(raw)

        self.assertEqual(parsed["bill_type"], "THUOC")
        self.assertEqual(parsed["ho_ten"], "Nguyễn Văn A")

    def test_should_skip_scanner_input_for_protected_field(self):
        widget = QLineEdit()
        widget.setObjectName("ma_y_te")
        self.assertTrue(should_skip_scanner_input(widget))

        other = QLineEdit()
        other.setObjectName("ho_ten")
        self.assertFalse(should_skip_scanner_input(other))

    def test_tiep_nhan_controller_processes_scanned_data_without_focus_requirement(self):
        controller = TiepNhanTabController.__new__(TiepNhanTabController)
        controller.is_processing_scan = False
        controller.ui_tiep_nhan = SimpleNamespace(
            cccd=QLineEdit(),
            ho_ten=QLineEdit(),
            dia_chi=QLineEdit(),
            gioi_tinh=SimpleNamespace(setCurrentText=lambda value: None),
            nam_sinh=SimpleNamespace(setDate=lambda value: None),
        )
        controller.update_tuoi = lambda: None

        controller.parse_cccd_qr_data("038095011111|123456789|Nguyễn Văn A|Nam|15101995|Số 123 Đường Lê Lợi")

        self.assertEqual(controller.ui_tiep_nhan.cccd.text(), "038095011111")
        self.assertEqual(controller.ui_tiep_nhan.ho_ten.text(), "Nguyễn Văn A")
        self.assertEqual(controller.ui_tiep_nhan.dia_chi.text(), "Số 123 Đường Lê Lợi")


if __name__ == "__main__":
    unittest.main()
