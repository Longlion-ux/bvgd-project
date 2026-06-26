import os
import json
import math

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtSerialPort import QSerialPort
from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtCore import QRegularExpression, QDate, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QIntValidator, QRegularExpressionValidator
from PyQt6.QtWidgets import QTableWidgetItem, QPushButton, QHBoxLayout, QWidget, QMessageBox, QLineEdit
from datetime import datetime

from app.core.in_phieu_toa_thuoc import create_and_open_pdf_for_printing

from app.services.BenhNhanService import get_benh_nhan_by_id
from app.services.DoiTuongService import get_list_doi_tuong
from app.services.PhongBanService import get_list_phong_ban

from app.styles.styles import DELETE_BTN_STYLE, ADD_BTN_STYLE, TUOI_STYLE, COMPLETER_THUOC_STYLE

from app.ui.TabKhamBenh import Ui_formKhamBenh
from app.ui.ThongBaoThongTuyenBHYT import Ui_Dialog as Ui_ThongBaoThongTuyenBHYT

from app.utils.config_manager import ConfigManager
from app.utils.cong_thuc_tinh_bhyt import tinh_tien_mien_giam
from app.utils.scanner_utils import parse_scanned_data
from app.utils.constants import MA_Y_TE_LENGTH, CLS_CODE
from app.utils.ui_helpers import IcdCompleterHandler, DuocCompleterHandler
from app.utils.utils import populate_combobox, \
    calculate_age, format_currency_vn, unformat_currency_to_float, populate_list_to_combobox
from app.utils.export_excel import export_and_show_dialog

from app.configs.table_thuoc_configs import *
from app.utils.constants import GIAI_QUYET_FILE_PATH
from app.utils.write_json_line import write_json_lines, MODE_JSON, TARGET_DIR, get_todays_csv_rows

from app.utils.thong_tuyen_bhyt import thong_tuyen_bhyt
from app.services.DoiTuongService import get_doi_tuong_by_id

def _get_int_value(table: QtWidgets.QTableWidget, row: int, col: int) -> int:
    """Hàm tiện ích để lấy giá trị số từ QLineEdit, trả về 0 nếu rỗng/lỗi."""
    widget = table.cellWidget(row, col)
    if widget and widget.text().strip():
        try:
            return int(widget.text())
        except ValueError:
            pass
    return 0

class ComboBoxFilter(QtCore.QObject):
    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.FocusIn:
            if isinstance(source, QtWidgets.QLineEdit):
                combo = source.parent()
                if isinstance(combo, QtWidgets.QComboBox) and combo.isEnabled():
                    combo.showPopup()
                    QTimer.singleShot(0, source.selectAll)

        return super().eventFilter(source, event)

class KhamBenhTabController(QtWidgets.QWidget):

    req_dang_ky_cls = pyqtSignal()

    req_load_service_bill = pyqtSignal(dict)
    req_reset_dich_vu = pyqtSignal()

    # <editor-fold desc="Khoi tao man hinh kham benh">
    def __init__(self, tab_widget_container, parent=None):
        super().__init__(parent)
        self.ma_y_te = None
        self.dia_chi = None
        self.doi_tuong_id = None

        self.input_drug_name = None
        self.input_drug_so_luong = None

        self.duoc_handler = None
        self.icd_handler = IcdCompleterHandler(self, min_search_length=0)

        self.cb_event_filter = ComboBoxFilter(self)

        # <editor-fold desc="Init UI">
        self.ui_kham = Ui_formKhamBenh()
        self.ui_kham.setupUi(tab_widget_container)
        self.ui_kham.ds_da_kham.setRowCount(0)
        # </editor-fold>

        self.duoc_handler = DuocCompleterHandler(
            table_widget=self.ui_kham.ds_thuoc,
            parent=self,
            min_search_length=0,
            popup_min_width=1000)

        # --- CẤU HÌNH PHÂN TRANG ---
        self.current_page_index = 1  # Trang hiện tại
        self.items_per_page = 10  # Số dòng mỗi trang
        self.total_pages = 1  # Tổng số trang

        # <editor-fold desc="Load data, connect signals,...">
        self.init()
        self.setup_ngay_gio_kham_realtime_clock()
        self.setup_prescription_table()

        self.config_manager = ConfigManager()
        self._load_saved_settings()
        self._connect_signals()
        self.apply_stylesheet()
        self.check_enable_btn_dang_ky()
        self.update_table_display()
        # </editor-fold>

        self.is_processing_scan = False
        self._scanner_open_retry_count = 0
        self._scanner_open_in_progress = False
        self._scanner_open_attempted = False
        self._scanner_open_timer = QTimer(self)
        self._scanner_open_timer.setSingleShot(True)
        self._scanner_open_timer.timeout.connect(self._attempt_open_serial_port)

    # </editor-fold>

    # <editor-fold desc="Reset thông tin màn hình">
    def reset_data(self):
        self.ma_y_te = ''
        self.ui_kham.ma_y_te.clear()
        self.ui_kham.ho_ten_bn.clear()
        self.ui_kham.dia_chi.clear()
        self.ui_kham.tuoi.clear()
        self.ui_kham.so_bhyt.clear()
        self.ui_kham.sdt.clear()
        # self.ui_kham.cb_doi_tuong.setCurrentIndex(0)
        self.ui_kham.cb_doi_tuong.setCurrentText('')
        self.doi_tuong_id = None

        current_date = QDate.currentDate()
        self.ui_kham.bhyt_from.setDate(current_date)
        self.ui_kham.bhyt_to.setDate(current_date)
        self.ui_kham.ngay_sinh.setDate(current_date)
        self.ui_kham.cccd.clear()

        self.ui_kham.mach.clear()
        self.ui_kham.nhiet_do.clear()
        self.ui_kham.nhiet_do.clear()
        self.ui_kham.huyet_ap_1.clear()
        self.ui_kham.huyet_ap_2.clear()
        self.ui_kham.chieu_cao.clear()
        self.ui_kham.can_nang.clear()
        self.ui_kham.duong_huyet.clear()
        self.ui_kham.spo2.clear()

        self.ui_kham.chan_doan.clear()
        self.ui_kham.ma_icd.clear()  # Đã thay đổi
        self.ui_kham.ma_icd_phu.clear()
        self.ui_kham.cb_cach_giai_quyet.setCurrentIndex(0)

        self.ui_kham.is_hen_kham.setChecked(False)
        self.ui_kham.so_ngay_hen.clear()
        self.ui_kham.ngay_hen_kham.setDate(QtCore.QDate.currentDate())

        self.update_tuoi()
        self.ui_kham.ma_y_te.setFocus()
        self.handle_update_doi_tuong()
    # </editor-fold>

    # <editor-fold desc="Load thong tin lan dau khoi tao man hinh">
    def init(self):
        # <editor-fold desc=Đổ dữ liệu vào các combo_box">
        populate_combobox(self.ui_kham.cb_cach_giai_quyet, 'TenGiaiQuyet', 'MaGiaiQuyet', GIAI_QUYET_FILE_PATH)

        doi_tuong_data = get_list_doi_tuong()
        populate_list_to_combobox(self.ui_kham.cb_doi_tuong,
                                  data=doi_tuong_data,
                                  display_col=2, key_col=0)
        phong_ban_data = get_list_phong_ban()
        populate_list_to_combobox(self.ui_kham.cb_phong_kham,
                                  data=phong_ban_data,
                                  display_col=2, key_col=0)
        # </editor-fold>

        # <editor-fold desc="Cấu hình combo_box">
        target_combos = [
            self.ui_kham.cb_phong_kham,
            self.ui_kham.cb_doi_tuong,
            self.ui_kham.cb_cach_giai_quyet,
            self.ui_kham.cb_gioi_tinh
        ]

        for cb in target_combos:
            cb.setEditable(True)  # Bắt buộc Editable để có LineEdit và SelectAll

            # Tự động chọn dòng đầu tiên nếu dữ liệu rỗng
            if cb.count() > 0 and cb.currentIndex() < 0:
                cb.setCurrentIndex(0)

            # Quan trọng: Cài đặt filter cho LineEdit bên trong ComboBox
            # Vì khi gõ hoặc click, ta tương tác với LineEdit này
            if cb.lineEdit():
                cb.lineEdit().installEventFilter(self.cb_event_filter)
        # </editor-fold>

        # <editor-fold desc="set validator">
        int_validator = QIntValidator(0, 9999)
        self.ui_kham.so_ngay_hen.setValidator(int_validator)
        self.ui_kham.mach.setValidator(int_validator)
        self.ui_kham.nhiet_do.setValidator(int_validator)
        self.ui_kham.nhip_tho.setValidator(int_validator)
        self.ui_kham.huyet_ap_1.setValidator(int_validator)
        self.ui_kham.huyet_ap_2.setValidator(int_validator)
        self.ui_kham.chieu_cao.setValidator(int_validator)
        self.ui_kham.can_nang.setValidator(int_validator)
        self.ui_kham.duong_huyet.setValidator(int_validator)
        self.ui_kham.spo2.setValidator(int_validator)
        self.ui_kham.sdt.setValidator(QRegularExpressionValidator(QRegularExpression(r'^\d{10}$')))

        self.ui_kham.ma_y_te.setMaxLength(8)
        self.ui_kham.ma_y_te.setValidator(QRegularExpressionValidator(QRegularExpression(r'^[A-Za-z0-9]*$')))

        # 2. Số CCCD: Tối đa 12 ký tự, CHỈ cho phép nhập SỐ
        self.ui_kham.cccd.setMaxLength(12)
        self.ui_kham.cccd.setValidator(QRegularExpressionValidator(QRegularExpression(r'^\d*$')))

        # 3. Số BHYT: Tối đa 15 ký tự, chỉ cho phép Chữ và Số
        self.ui_kham.so_bhyt.setMaxLength(15)
        self.ui_kham.so_bhyt.setValidator(QRegularExpressionValidator(QRegularExpression(r'^[A-Za-z0-9]*$')))

        self.ui_kham.so_ngay_hen.setReadOnly(True)
        # </editor-fold>

        self.reset_data()
    # </editor-fold>

    # <editor-fold desc="Setup event cho cac vung nhap lieu va cac nut">
    def _connect_signals(self):
        """Kết nối tất cả các tín hiệu và slot."""
        self.ui_kham.ma_y_te.textEdited.connect(self.load_thong_tin_benh_nhan)
        self.ui_kham.cb_phong_kham.currentIndexChanged.connect(self._save_settings)
        self.ui_kham.ten_bac_si.textEdited.connect(self._save_settings)
        self.ui_kham.is_hen_kham.clicked.connect(self.update_ngay_hen)
        self.ui_kham.so_ngay_hen.textEdited.connect(self.update_ngay_hen_kham_date)
        self.ui_kham.cb_doi_tuong.currentIndexChanged.connect(self.handle_update_doi_tuong)

        self.ui_kham.btn_in_phieu.clicked.connect(self.print_drug_bill)
        self.ui_kham.btn_reset_all.clicked.connect(self.reset_all)
        self.ui_kham.btn_xoa_toa_thuoc.clicked.connect(self.reset_prescription_table)
        self.ui_kham.btn_export.clicked.connect(lambda: export_and_show_dialog(self))

        self.ui_kham.cb_cach_giai_quyet.currentIndexChanged.connect(self.check_enable_btn_dang_ky)
        self.ui_kham.btn_dang_ky.clicked.connect(self.req_dang_ky_cls.emit)

        self.ui_kham.ngay_sinh.dateChanged.connect(self.update_tuoi)

        self.icd_handler.connect_to(self.ui_kham.ma_icd)
        self.icd_handler.activated_with_data.connect(self._on_icd_selected)

        self.ui_kham.ma_y_te_da_kham.textChanged.connect(self.reset_paging_and_load)
        self.ui_kham.ho_ten_da_kham.textChanged.connect(self.reset_paging_and_load)

        self.ui_kham.btn_refresh.clicked.connect(self.reset_paging_and_load)
        self.ui_kham.btn_prev_page.clicked.connect(self.on_prev_page)
        self.ui_kham.btn_next_page.clicked.connect(self.on_next_page)
        self.ui_kham.ds_da_kham.cellDoubleClicked.connect(self.on_patient_double_click)
        self.ui_kham.btn_check_bhyt.clicked.connect(self.handle_btn_check_bhyt)

    def handle_update_doi_tuong(self):
        curr_ten_doi_tuong = self.ui_kham.cb_doi_tuong.currentText().strip()
        prev_doi_tuong_id = self.doi_tuong_id
        curr_doi_tuong_id = self.ui_kham.cb_doi_tuong.currentData()

        if curr_ten_doi_tuong == '':
            self.duoc_handler.set_ma_doi_tuong('')
            self.doi_tuong_id = None
            return

        if not curr_doi_tuong_id: return

        if not prev_doi_tuong_id:
            self.duoc_handler.set_ma_doi_tuong(str(curr_doi_tuong_id))
            self.doi_tuong_id = str(curr_doi_tuong_id)
            return

        prev_doi_tuong_data = get_doi_tuong_by_id(prev_doi_tuong_id)
        curr_doi_tuong_data = get_doi_tuong_by_id(curr_doi_tuong_id)

        def check_is_bao_hiem(data):
            if data and len(data) > 3:
                gioi_han = data[3]
                return gioi_han is not None and gioi_han != 0
            return False

        is_prev_bh = check_is_bao_hiem(prev_doi_tuong_data)
        is_curr_bh = check_is_bao_hiem(curr_doi_tuong_data)

        if prev_doi_tuong_id and is_prev_bh != is_curr_bh:
            msg = QMessageBox.question(
                self,
                "Xác nhận thay đổi",
                "Loại đối tượng đã thay đổi (Bảo hiểm <-> Không bảo hiểm).\n"
                "Bạn có muốn xoá danh sách thuốc hiện tại để tính toán lại không?"
            )

            if msg == QMessageBox.StandardButton.Yes:
                self.reset_prescription_table()
                self.doi_tuong_id = curr_doi_tuong_id
                self.duoc_handler.set_ma_doi_tuong(str(curr_doi_tuong_id))
                print("Đã xoá danh sách thuốc.")
            else:
                idx_doi_tuong = self.ui_kham.cb_doi_tuong.findData(prev_doi_tuong_id)
                if idx_doi_tuong >= 0: self.ui_kham.cb_doi_tuong.setCurrentIndex(idx_doi_tuong)
                print("Giữ nguyên danh sách thuốc và quay lại đối tượng trước đó.")

        return

    def check_enable_btn_dang_ky(self):
        """Chỉ bật nút Đăng ký khi cách giải quyết là Cận Lâm Sàng"""
        ma_giai_quyet = self.ui_kham.cb_cach_giai_quyet.currentData()

        if ma_giai_quyet == CLS_CODE:
            self.ui_kham.btn_dang_ky.setEnabled(True)
            # Optional: Đổi style để làm nổi bật nút nếu cần
        else:
            self.ui_kham.btn_dang_ky.setEnabled(False)

    def reset_paging_and_load(self):
        """Khi tìm kiếm, luôn quay về trang 1"""
        self.current_page_index = 1
        self.update_table_display()

    def handle_btn_check_bhyt(self):
        ma_the_bhyt = self.ui_kham.so_bhyt.text().strip()
        ho_ten = self.ui_kham.ho_ten_bn.text().strip()
        nam_sinh = self.ui_kham.ngay_sinh.date().toString('yyyy')

        fields_to_check = [
            (self.ui_kham.so_bhyt, "Số BHYT"),
            (self.ui_kham.ho_ten_bn, "Họ tên bệnh nhân"),
        ]

        if not self.ui_kham.ngay_sinh.date().isValid():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập Năm sinh hợp lệ để thông tuyến BHYT.")
            self.ui_kham.ngay_sinh.setFocus()
            return False

        for field, name in fields_to_check:
            if not field.text().strip():
                QMessageBox.warning(self, "Thiếu dữ liệu", f"Vui lòng nhập {name} để thông tuyến BHYT.")
                field.setFocus()
                return False

        result = thong_tuyen_bhyt(ma_the_bhyt, ho_ten, nam_sinh)
        if type(result) == str:
            result = json.loads(result)
        
        maKetQua = result.get('maKetQua', '')
        ghiChu = result.get('ghiChu', '')

        if maKetQua == '700':
            ghiChu = "Không có kết nối internet, vui lòng kiểm tra kết nối mạng."

        # Show Dialog
        dialog = QtWidgets.QDialog(self)
        ui = Ui_ThongBaoThongTuyenBHYT()
        ui.setupUi(dialog)

        ui.maKetQua.setText(f"Mã kết quả: {maKetQua}")
        ui.ghiChu.setText(ghiChu)

        if maKetQua != '000':
            idx_doi_tuong = self.ui_kham.cb_doi_tuong.findData(20)
            if idx_doi_tuong >= 0: self.ui_kham.cb_doi_tuong.setCurrentIndex(idx_doi_tuong)

            dialog.setStyleSheet("QLabel {\n"
                                 "color: red;\n"
                                 "font-size: 12pt;\n"
                                 "font-weight: bold;\n"
                                 "}")

        dialog.exec()
        return
    # </editor-fold>

    # <editor-fold desc="Load & Save setting phòng khám">
    def _save_settings(self):
        """Lưu Mã phòng khám và Tên bác sĩ hiện tại vào QSettings."""
        phong_kham_code = self.ui_kham.cb_phong_kham.currentText()
        ten_bac_si_hien_tai = self.ui_kham.ten_bac_si.text()
        self.config_manager.save_last_selection(phong_kham_code, ten_bac_si_hien_tai)

    def _load_saved_settings(self):
        """Tải giá trị đã lưu và áp dụng chúng cho các widget."""
        phong_kham_saved, bac_si_saved = self.config_manager.load_last_selection()

        if phong_kham_saved:
            index = self.ui_kham.cb_phong_kham.findText(phong_kham_saved)
            if index != -1:
                self.ui_kham.cb_phong_kham.setCurrentIndex(index)

        if bac_si_saved:
            self.ui_kham.ten_bac_si.setText(bac_si_saved)

    # </editor-fold>

    def apply_stylesheet(self):
        self.ui_kham.btn_in_phieu.setStyleSheet(ADD_BTN_STYLE)
        self.ui_kham.btn_reset_all.setStyleSheet(ADD_BTN_STYLE)

        self.ui_kham.btn_xoa_toa_thuoc.setStyleSheet(DELETE_BTN_STYLE)
        self.ui_kham.btn_dang_ky.setStyleSheet(ADD_BTN_STYLE)
        self.ui_kham.btn_export.setStyleSheet(ADD_BTN_STYLE)
        self.ui_kham.btn_check_bhyt.setStyleSheet(ADD_BTN_STYLE)

        self.ui_kham.cb_phong_kham.setStyleSheet(COMPLETER_THUOC_STYLE)
        self.ui_kham.cb_doi_tuong.setStyleSheet(COMPLETER_THUOC_STYLE)

        self.ui_kham.ma_icd.setStyleSheet(COMPLETER_THUOC_STYLE)
        self.ui_kham.cb_gioi_tinh.setStyleSheet(COMPLETER_THUOC_STYLE)
        self.ui_kham.cb_cach_giai_quyet.setStyleSheet(COMPLETER_THUOC_STYLE)
        # self.ui_kham.ma_icd.completer().popup().setStyleSheet(COMPLETER_THUOC_STYLE)

    # <editor-fold desc="Load thông tin bệnh nhân">
    def update_tuoi(self):
        ui = self.ui_kham
        ngay_sinh = ui.ngay_sinh.date()
        tuoi = str(calculate_age(ngay_sinh.toString('dd/MM/yyyy')))
        ui.tuoi.setText(tuoi)
        ui.tuoi.setStyleSheet(TUOI_STYLE)

    def set_thong_tin_benh_nhan(self, benh_nhan_data: tuple):
        ui = self.ui_kham

        self.ma_y_te = str(benh_nhan_data[0]).upper()
        ho_ten = benh_nhan_data[1]
        gioi_tinh = benh_nhan_data[2]
        nam_sinh = benh_nhan_data[3]
        sdt = benh_nhan_data[4]
        dia_chi = benh_nhan_data[5]
        bhyt = benh_nhan_data[6]

        ngay_sinh = QDate(int(nam_sinh), 1, 1) if nam_sinh is not None else QDate.currentDate()

        ui.ma_y_te.setText(self.ma_y_te)
        ui.ho_ten_bn.setText(str(ho_ten) if ho_ten is not None else '')
        ui.cb_gioi_tinh.setCurrentText('Nữ' if gioi_tinh == 'G' else 'Nam')
        ui.ngay_sinh.setDate(ngay_sinh)
        ui.sdt.setText(str(sdt) if sdt is not None else '')
        ui.dia_chi.setText(str(dia_chi) if dia_chi is not None else '')
        ui.so_bhyt.setText(str(bhyt) if bhyt is not None else '')
        self.update_tuoi()

    def load_thong_tin_benh_nhan(self, ma_y_te: str):
        """Lọc dữ liệu bệnh nhân và cập nhật giao diện."""
        if len(ma_y_te) != MA_Y_TE_LENGTH:
            return

        benh_nhan_data = get_benh_nhan_by_id(ma_y_te)
        if benh_nhan_data is None:
            QMessageBox.warning(self, 'Thông báo', f'Không tìm thấy bệnh nhân với mã y tế {ma_y_te}')
            return

        self.set_thong_tin_benh_nhan(benh_nhan_data)

    # </editor-fold>

    # <editor-fold desc="Setup đồng hồ ngày giờ khám">
    def setup_ngay_gio_kham_realtime_clock(self):
        """Thiết lập QTimer để cập nhật ngay_gio_kham mỗi giây."""
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_ngay_gio_kham_datetime_edit)
        self.timer.start(1000)
        self.update_ngay_gio_kham_datetime_edit()

    def update_ngay_gio_kham_datetime_edit(self):
        """Hàm cập nhật QDateTimeEdit với thời gian hệ thống."""
        self.ui_kham.ngay_gio_kham.setDateTime(QtCore.QDateTime.currentDateTime())

    # </editor-fold>

    # <editor-fold desc="Handle & Cập nhật ngày hẹn khám">
    def update_ngay_hen(self):
        """Xử lý logic khi checkbox hẹn khám được click."""
        is_checked = self.ui_kham.is_hen_kham.isChecked()
        self.ui_kham.so_ngay_hen.setReadOnly(not is_checked)
        if not is_checked:
            self.ui_kham.so_ngay_hen.setText('')
            self.ui_kham.ngay_hen_kham.setDate(QtCore.QDate.currentDate())
        else:
            self.update_ngay_hen_kham_date(self.ui_kham.so_ngay_hen.text())

    def update_ngay_hen_kham_date(self, days_text: str):
        """Tính toán ngày hẹn khám dựa trên số ngày nhập vào."""
        try:
            days = int(days_text)
            if days < 0:
                days = 0

            new_date = QtCore.QDate.currentDate().addDays(days)
            self.ui_kham.ngay_hen_kham.setDate(new_date)

        except ValueError:
            if not days_text:
                self.ui_kham.ngay_hen_kham.setDate(QtCore.QDate.currentDate())
            pass  # Giữ giá trị cũ nếu nhập ký tự không phải số

    # </editor-fold>

    # <editor-fold desc="Setup table toa thuôc">
    def setup_prescription_table(self):
        """Thiết lập cấu trúc cột và khởi tạo dòng nhập liệu."""
        self.ui_kham.ds_thuoc.setColumnCount(DRUG_COL_COUNT)
        self.ui_kham.ds_thuoc.setHorizontalHeaderLabels(HEADER_THUOC)

        # ẨN CỘT MÃ THUỐC (Chỉ dùng cho dữ liệu, không hiển thị cho người dùng)
        self.ui_kham.ds_thuoc.setColumnHidden(COL_MA_THUOC, True)
        self.ui_kham.ds_thuoc.setColumnHidden(COL_DUOC_ID, True)

        # Thiết lập chiều rộng
        self.ui_kham.ds_thuoc.setColumnWidth(COL_TEN_THUOC, COL_TEN_THUOC_WIDTH)

        self.add_input_row()

    # </editor-fold>

    # <editor-fold desc="Hàm xử lý chọn thuốc">
    def _on_duoc_selected(self, raw_data: tuple, row_index: int):
        """
        Xử lý khi một thuốc được chọn từ completer.
        Điền dữ liệu vào dòng nhập liệu (dòng 0).
        """
        if not raw_data or row_index != 0:
            return

        table = self.ui_kham.ds_thuoc

        # Data từ DuocService:
        # (Duoc_Id, MaDuoc, TenDuocDayDu, DonGia, TenDonViTinh, CachDung)
        try:
            duoc_id = str(raw_data[0])
            ma_duoc = str(raw_data[1])
            ten_duoc = str(raw_data[2])
            don_gia = float(raw_data[3])
            don_vi_tinh = str(raw_data[4])
            cach_dung = str(raw_data[5])
        except (IndexError, TypeError, ValueError) as e:
            print(f"Lỗi xử lý dữ liệu dược: {e}, data: {raw_data}")
            return

        duoc_id_widget = table.cellWidget(row_index, COL_DUOC_ID)
        if duoc_id_widget and isinstance(duoc_id_widget, QLineEdit):
            duoc_id_widget.setText(duoc_id)

        # 1. Cột MÃ THUỐC (COL_MA_THUOC) - ẨN
        ma_thuoc_widget = table.cellWidget(row_index, COL_MA_THUOC)
        if ma_thuoc_widget and isinstance(ma_thuoc_widget, QLineEdit):
            ma_thuoc_widget.setText(ma_duoc)

        # 2. Cột TÊN THUỐC (COL_TEN_THUOC)
        ten_thuoc_widget = table.cellWidget(row_index, COL_TEN_THUOC)
        if ten_thuoc_widget and isinstance(ten_thuoc_widget, QLineEdit):
            # Block signal để tránh kích hoạt lại tìm kiếm
            ten_thuoc_widget.blockSignals(True)
            ten_thuoc_widget.setText(ten_duoc)
            ten_thuoc_widget.blockSignals(False)

        # 3. Cột Đơn vị tính (COL_DON_VI_TINH)
        unit_widget = table.cellWidget(row_index, COL_DON_VI_TINH)
        if unit_widget and isinstance(unit_widget, QLineEdit):
            unit_widget.setText(don_vi_tinh)

        # 4. Cột Đơn giá (COL_DON_GIA)
        price_widget = table.cellWidget(row_index, COL_DON_GIA)
        if price_widget and isinstance(price_widget, QLineEdit):
            price_widget.setText(format_currency_vn(don_gia))

        # 5. Cột Đường dùng (COL_DUONG_DUNG)
        duong_dung_widget = table.cellWidget(row_index, COL_DUONG_DUNG)
        if duong_dung_widget and isinstance(duong_dung_widget, QLineEdit):
            duong_dung_widget.setText(cach_dung)

        # Tự động focus vào ô tiếp theo (Sáng)
        sang_widget = table.cellWidget(row_index, COL_SANG)
        if sang_widget:
            sang_widget.setFocus()

    # </editor-fold>

    # <editor-fold desc="Cập nhật tính toán số lượng thuốc">
    def calculate_quantity(self, input_row_index: int) -> int:
        """Tính toán Số lượng = (Sáng + Trưa + Chiều + Tối) x Số Ngày."""
        table = self.ui_kham.ds_thuoc

        so_ngay = _get_int_value(table, input_row_index, COL_SO_NGAY)
        tong_lieu = sum([_get_int_value(table, input_row_index, col)
                         for col in [COL_SANG, COL_TRUA, COL_CHIEU, COL_TOI]])

        return tong_lieu * so_ngay

    def update_quantity(self):
        """Cập nhật Số lượng khi liều lượng hoặc số ngày thay đổi."""
        quantity = self.calculate_quantity(0)
        self.input_drug_so_luong.setText(str(quantity))

    # </editor-fold>

    # <editor-fold desc="Thêm dòng input row mới vào đầu bảng">
    def add_input_row(self):
        """Tạo dòng nhập liệu mới tại index 0 (luôn là dòng đầu tiên)."""
        table = self.ui_kham.ds_thuoc
        table.insertRow(0)
        item = QtWidgets.QTableWidgetItem()
        item.setText("")
        table.setVerticalHeaderItem(0, item)

        # 1a. TẠO CỘT MÃ THUỐC (ReadOnly, rỗng)
        duoc_id = QLineEdit()
        ma_thuoc = QLineEdit()
        duoc_id.setReadOnly(True)
        ma_thuoc.setReadOnly(True)
        table.setCellWidget(0, COL_DUOC_ID, duoc_id)
        table.setCellWidget(0, COL_MA_THUOC, ma_thuoc)

        # 1b. Tạo QLineEdit TÊN THUỐC và gán QCompleter
        input_drug_name = QLineEdit()

        # Kết nối QLineEdit với DuocCompleterHandler
        self.duoc_handler.connect_to(input_drug_name)

        # Kết nối tín hiệu khi chọn một mục
        # Chúng ta cần `raw_data` và `row_index` (luôn là 0)
        self.duoc_handler.activated_with_data.connect(
            lambda text, raw_data: self._on_duoc_selected(raw_data, 0)
        )

        # Gán LineEdit vào ô TÊN THUỐC
        table.setCellWidget(0, COL_TEN_THUOC, input_drug_name)

        # Cập nhật biến tham chiếu
        self.input_drug_name = input_drug_name

        # 2. Các cột dữ liệu còn lại (Bắt đầu từ cột Đơn vị tính, index 2)
        # DRUG_COL_COUNT - 1 là cột cuối cùng (Huỷ)
        for col in range(COL_DON_VI_TINH, DRUG_COL_COUNT - 1):  # Bắt đầu từ COL_DON_VI_TINH (index 2)
            line_edit = QLineEdit()

            # Thiết lập READ-ONLY (Đơn vị tính, Đơn giá, Số lượng)
            if HEADER_THUOC[col] in COLUMN_REQUIRE_READ_ONLY:
                line_edit.setReadOnly(True)

            # ... (Các kết nối và validator khác không đổi) ...
            if HEADER_THUOC[col] in COLUMN_REQUIRE_ONLY_NUMBER:
                line_edit.setValidator(QtGui.QIntValidator())

            table.setCellWidget(0, col, line_edit)

            if COL_SANG <= col <= COL_SO_NGAY:
                line_edit.textEdited.connect(self.update_quantity)

            if col >= COL_SANG:
                line_edit.returnPressed.connect(lambda: self.finalize_drug_entry(0))

            if col == COL_SO_LUONG:
                self.input_drug_so_luong = line_edit

        # Cột Hủy ở dòng nhập liệu (dòng nhập liệu không cần nút Hủy)
        table.setCellWidget(0, COL_HUY, QWidget())

    # </editor-fold>

    # <editor-fold desc="Thêm dòng thuốc mới vào bảng thuốc">
    def validate_drug_entry(self, input_row_index: int) -> bool:
        """Xác thực dữ liệu nhập vào trước khi thêm vào bảng tĩnh."""
        table = self.ui_kham.ds_thuoc

        drug_name_widget = table.cellWidget(input_row_index, COL_TEN_THUOC)

        # 1. Kiểm tra Tên Thuốc
        if not drug_name_widget or not drug_name_widget.text().strip():
            QMessageBox.warning(self, "Lỗi nhập liệu", "Vui lòng nhập và chọn Tên Thuốc.")
            drug_name_widget.setFocus()
            return False


        # 2. Kiểm tra Mã Thuốc
        ma_thuoc_widget = table.cellWidget(input_row_index, COL_MA_THUOC)
        if not ma_thuoc_widget or not ma_thuoc_widget.text().strip():
            QMessageBox.warning(self, "Lỗi xác thực",
                                f"Tên thuốc '{drug_name_widget.text()}' không hợp lệ. \n"
                                f"Vui lòng chọn thuốc từ danh sách gợi ý.")
            drug_name_widget.setFocus()
            drug_name_widget.selectAll()
            return False

        so_ngay = _get_int_value(table, input_row_index, COL_SO_NGAY)
        if so_ngay == 0:
            QMessageBox.warning(self, "Lỗi nhập liệu", "Số Ngày phải lớn hơn 0.")
            table.cellWidget(input_row_index, COL_SO_NGAY).setFocus()
            return False

        tong_lieu = self.calculate_quantity(input_row_index)

        if tong_lieu == 0:
            QMessageBox.warning(self, "Lỗi nhập liệu", "Ít nhất phải nhập liều Sáng, Trưa, Chiều, hoặc Tối.")
            table.cellWidget(input_row_index, COL_SANG).setFocus()
            return False

        if self.calculate_quantity(input_row_index) == 0:
            QMessageBox.warning(self, "Lỗi nhập liệu", "Số lượng tính toán phải lớn hơn 0.")
            table.cellWidget(input_row_index, COL_SO_NGAY).setFocus()
            return False

        return True

    def _extract_drug_data(self, input_row_index: int) -> list:
        """Trích xuất toàn bộ dữ liệu từ dòng nhập liệu (trừ cột Hủy) và tính Số lượng."""
        table = self.ui_kham.ds_thuoc
        final_drug_data = []
        so_luong_tinh_toan = self.calculate_quantity(input_row_index)

        # DRUG_COL_COUNT - 1 là số cột dữ liệu (không bao gồm cột Hủy)
        for col in range(DRUG_COL_COUNT - 1):
            # Mã thuốc và Tên thuốc là widget, Số lượng được tính toán
            if col == COL_MA_THUOC:
                widget = table.cellWidget(input_row_index, COL_MA_THUOC)
                final_drug_data.append(widget.text() if widget else "")
            elif col == COL_TEN_THUOC:
                widget = table.cellWidget(input_row_index, COL_TEN_THUOC)
                final_drug_data.append(widget.text() if widget else "")
            elif col == COL_SO_LUONG:
                final_drug_data.append(str(so_luong_tinh_toan))
            else:
                line_edit = table.cellWidget(input_row_index, col)
                final_drug_data.append(line_edit.text() if line_edit else "")

        return final_drug_data

    def _insert_static_drug_row(self, table: QtWidgets.QTableWidget, data_row_index: int, drug_data: list):
        """Chèn dòng dữ liệu tĩnh và nút Hủy vào bảng."""
        table.insertRow(data_row_index)

        for col, value in enumerate(drug_data):
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            table.setItem(data_row_index, col, item)

        # Thêm nút Hủy
        delete_btn = QPushButton(HEADER_THUOC[COL_HUY])
        delete_btn.setStyleSheet(DELETE_BTN_STYLE)
        delete_btn.clicked.connect(self.handle_delete_row)

        widget_container = QWidget()
        layout = QHBoxLayout(widget_container)
        layout.addWidget(delete_btn)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        table.setCellWidget(data_row_index, COL_HUY, widget_container)

    def finalize_drug_entry(self, input_row_index: int):
        """Xác thực, đọc dữ liệu, chuyển dòng nhập liệu thành tĩnh và tạo dòng nhập liệu mới."""
        if not self.validate_drug_entry(input_row_index):
            return

        table = self.ui_kham.ds_thuoc

        # 1. Trích xuất dữ liệu
        final_drug_data = self._extract_drug_data(input_row_index)

        # 2. Xóa dòng nhập liệu cũ
        table.removeRow(input_row_index)

        # 3. Chèn dòng dữ liệu tĩnh mới
        self._insert_static_drug_row(table, data_row_index=0, drug_data=final_drug_data)

        # 4. Tạo lại dòng nhập liệu mới tại index 0
        self.add_input_row()
        self.update_row_numbers()

        # 5. Tự động focus lại
        if self.input_drug_name:
            self.input_drug_name.setFocus()

    # </editor-fold>

    # <editor-fold desc="Xoá dòng thuốc trong bảng thuốc">
    def handle_delete_row(self):
        """Xử lý sự kiện khi nút Hủy (xóa dòng) được click."""
        table = self.ui_kham.ds_thuoc
        button = self.sender()
        if button is None or not isinstance(button, QPushButton):
            return

        # Tìm dòng chứa nút bấm
        widget_container = button.parent()
        global_pos = widget_container.mapToGlobal(QtCore.QPoint(0, 0))
        local_pos = table.viewport().mapFromGlobal(global_pos)
        row_index = table.indexAt(local_pos).row()

        if row_index <= 0 or row_index >= table.rowCount():
            return

        reply = QMessageBox.question(self, "Xác nhận",
                                     f"Bạn có chắc muốn hủy dòng thuốc số {row_index}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            table.removeRow(row_index)

        self.update_row_numbers()

    # </editor-fold>

    # <editor-fold desc="Cập nhật số dòng thuốc trong bảng">
    def update_row_numbers(self):
        """Đánh số lại các dòng dữ liệu sau khi thêm hoặc xóa."""
        table = self.ui_kham.ds_thuoc
        # Bắt đầu từ dòng 1 (vì dòng 0 là dòng nhập liệu)
        for i in range(1, table.rowCount()):
            item = QtWidgets.QTableWidgetItem(str(i))
            table.setVerticalHeaderItem(i, item)

    # </editor-fold>

    def _on_icd_selected(self, selected_text: str, raw_data: object):
        """
        Xử lý khi một mục ICD được chọn từ handler.
        raw_data chính là tuple ('A01', 'Bệnh tả')
        """
        if raw_data:
            ma_icd = raw_data[0] # Lấy mã
            self.ui_kham.ma_icd.blockSignals(True)
            self.ui_kham.ma_icd.setText(ma_icd)
            self.ui_kham.ma_icd.blockSignals(False)
        else:
            # Fallback nếu không có raw data
            ma_icd = selected_text.split(' - ')[0].strip()
            self.ui_kham.ma_icd.blockSignals(True)
            self.ui_kham.ma_icd.setText(ma_icd)
            self.ui_kham.ma_icd.blockSignals(False)

    def reset_prescription_table(self):
        """Xóa tất cả các dòng thuốc tĩnh (từ dòng 1 trở đi) và giữ lại dòng nhập liệu."""
        table = self.ui_kham.ds_thuoc

        # Xóa tất cả các dòng (ngoại trừ dòng nhập liệu tại index 0)
        # Bắt đầu từ dòng cuối cùng (rowCount() - 1) lùi về dòng 1
        for i in range(table.rowCount() - 1, 0, -1):
            table.removeRow(i)

        # Đảm bảo rằng luôn có đúng 1 dòng nhập liệu sau khi reset
        if table.rowCount() == 0:
            self.add_input_row()

        self.update_row_numbers()
        self.input_drug_name.setFocus()

    def reset_all(self):
        self.reset_prescription_table()
        self.reset_data()

    # <editor-fold desc="Xử lý nút in toa thuốc">
    def get_thong_tin_kham(self):
        ui = self.ui_kham
        ngay_gio_kham = ui.ngay_gio_kham.dateTime().toString("dd/MM/yyyy HH:mm:ss")

        # Xử lý Huyết áp
        huyet_ap = f"{ui.huyet_ap_1.text().strip()}/{ui.huyet_ap_2.text().strip()}"
        if huyet_ap == '/': huyet_ap = ''

        ngay_hen_kham = ui.ngay_hen_kham.date().toString("dd/MM/yyyy")
        is_checked = ui.is_hen_kham.isChecked()
        so_ngay_hen = ui.so_ngay_hen.text()
        so_ngay_hen = 0 if not so_ngay_hen else int(so_ngay_hen)
        dr_note_text = (f"Hẹn tái khám {ui.so_ngay_hen.text().strip()} ngày "
                        f"({ngay_hen_kham})") if is_checked and so_ngay_hen > 0 else ""

        table = ui.ds_thuoc
        drug_list = []
        tong_tien_thuoc = 0.0

        # Bắt đầu từ dòng 1 (vì dòng 0 là dòng nhập liệu)
        for row in range(1, table.rowCount()):
            drug_row_data = {}

            # Thu thập các cột dữ liệu khác từ bảng
            for col_index, header in enumerate(HEADER_THUOC):
                # Bỏ qua cột Hủy
                if header == COL_HUY_HEADER:
                    continue

                # Sử dụng FIELD_MAPPING để đặt tên field tiếng Anh
                field_name = FIELD_MAPPING.get(header, header)

                item = table.item(row, col_index)
                drug_row_data[field_name] = item.text().strip() if item else ""

            drug_list.append(drug_row_data)

        mapped_drugs = []
        for idx, drug in enumerate(drug_list):
            mapped_drugs.append({
                'STT': str(idx + 1),
                'DuocId': drug.get('DuocId', ''),
                'MaThuoc': drug.get('MaThuoc', ''),
                'TenThuoc': drug.get('TenThuoc', ''),
                'TenThuocPhu': drug.get('DuongDung', ''),
                'DonViTinh': drug.get('DonViTinh', ''),
                'Sang': drug.get('Sang', '0'),
                'Trua': drug.get('Trua', '0'),
                'Chieu': drug.get('Chieu', '0'),
                'Toi': drug.get('Toi', '0'),
                'SoNgay': drug.get('SoNgay', '0'),
                'SoLuong': drug.get('SoLuong', '0'),
                'DonGia': drug.get('DonGia', '0'),
            })

            so_luong = drug.get('SoLuong', '0')
            don_gia = drug.get('DonGia', '0')
            tong_tien_thuoc += int(so_luong) * unformat_currency_to_float(don_gia)

        ma_doi_tuong = str(ui.cb_doi_tuong.currentData())
        tong_bhyt_thanh_toan = tinh_tien_mien_giam(tong_tien_thuoc, tong_tien_thuoc, ma_doi_tuong)
        tong_benh_nhan_thanh_toan = tong_tien_thuoc - tong_bhyt_thanh_toan

        data = {
            'PhongKham': ui.cb_phong_kham.currentText(),
            'TenBacSi': ui.ten_bac_si.text().strip(),
            'NgayTiepNhan': ngay_gio_kham,
            'NgayKham': ui.ngay_gio_kham.date().toString('dd'),
            'ThangKham': ui.ngay_gio_kham.date().toString('MM'),
            'NamKham': ui.ngay_gio_kham.date().toString('yyyy'),

            'MaYTe': ui.ma_y_te.text().strip().upper(),
            'HoTen': ui.ho_ten_bn.text().strip(),
            'GioiTinh': ui.cb_gioi_tinh.currentText(),
            'Tuoi': ui.tuoi.text().strip(),
            'DiaChi': ui.dia_chi.text().strip(),
            'SDT': ui.sdt.text().strip(),
            'BHYT': ui.so_bhyt.text().strip().upper(),
            'CCCD': ui.cccd.text().strip(),
            'MaDoiTuong': ui.cb_doi_tuong.currentData(),
            'DoiTuong': ui.cb_doi_tuong.currentText(),

            'ChanDoan': ui.chan_doan.text().strip()
                + ('; ' + ui.ma_icd.text().strip() if ui.ma_icd.text().strip() != '' else '')
                + ('; ' + ui.ma_icd_phu.text().strip() if ui.ma_icd_phu.text().strip() != '' else ''),
            'Mach': ui.mach.text().strip(),
            'HA': huyet_ap,
            'NhietDo': ui.nhiet_do.text().strip(),
            'CanNang': ui.can_nang.text().strip(),

            'SoNgayHenTaiKham': ui.so_ngay_hen.text().strip(),
            'NgayHenTaiKham': ui.ngay_hen_kham.date().toString("dd/MM/yyyy"),
            'DrNote': dr_note_text,
            'ToaThuoc': mapped_drugs,
            'TongTienThuoc': format_currency_vn(tong_tien_thuoc),
            'TongBHYTChiTra': format_currency_vn(tong_bhyt_thanh_toan),
            'TongBenhNhanTra': format_currency_vn(tong_benh_nhan_thanh_toan),
        }

        return data

    def validate_patient_info(self) -> bool:
        ui = self.ui_kham

        if not self.doi_tuong_id or not ui.cb_doi_tuong.currentText():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng chọn đối tượng.")
            ui.cb_doi_tuong.setFocus()
            return False

        # Danh sách các trường cần xác thực: (widget, tên hiển thị)
        fields_to_check = [
            (ui.ho_ten_bn, "Họ tên bệnh nhân"),
            (ui.dia_chi, "Địa chỉ"),
            (ui.cccd, "Căn cước công dân"),
            # (ui.sdt, "Số điện thoại"),
            (ui.chan_doan, "Chẩn đoán"),
        ]

        if not ui.ngay_sinh.date().isValid():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập Ngày sinh hợp lệ.")
            ui.ngay_sinh.setFocus()
            return False

        # Kiểm tra các trường QLineEdit
        for field, name in fields_to_check:
            if not field.text().strip():
                QMessageBox.warning(self, "Thiếu dữ liệu", f"Vui lòng nhập {name}!")
                field.setFocus()
                return False

        return True

    def print_drug_bill(self):
        """
            Thu thập tất cả dữ liệu từ form Khám bệnh và bảng thuốc
            để chuẩn bị cho việc in ấn hoặc lưu trữ.
        """
        if not self.validate_patient_info():
            return

        data = self.get_thong_tin_kham()

        if len(data.get('ToaThuoc')) < 1:
            QMessageBox.warning(self,
                                "Thiếu dữ liệu",
                                f"Chưa chọn thuốc nào trong toa thuốc.")
            return

        # json_data = json.dumps(data, indent=4, ensure_ascii=False)
        write_json_lines(data, MODE_JSON.PHIEU_TOA_THUOC_MODE)

        # Bổ sung logic in hoặc lưu trữ ở đây
        # QMessageBox.information(self, "Thông báo", "Đã thu thập dữ liệu form thành công. Sẵn sàng cho việc in/lưu.")

        create_and_open_pdf_for_printing(data)

        self.ui_kham.ma_y_te.setFocus()
        self.update_table_display()

        # --- THÔNG BÁO HỎI RESET MÀN HÌNH ---
        # reply = QMessageBox.question(self, "Xác nhận",
        #                              f"Khám cho bệnh nhân mới?",
        #                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        #
        # if reply == QMessageBox.StandardButton.Yes:
        #     self.reset_all()

    # </editor-fold>

    # <editor-fold desc="Lấy thông tin bệnh nhân và phòng khám chuyển sang màn hình đăng ký dịch vụ">

    def get_hanh_chinh_data(self) -> dict:
        """
        Thu thập các thông tin hành chính cơ bản của bệnh nhân
        để chuyển sang tab/màn hình khác.
        """
        ui = self.ui_kham

        data = {
            'MaYTe': self.ma_y_te,
            'HoTenBN': ui.ho_ten_bn.text().strip(),
            'GioiTinh': ui.cb_gioi_tinh.currentText(),
            'NgaySinh': ui.ngay_sinh.date().toString('yyyy'),

            'SoBHYT': ui.so_bhyt.text().strip(),
            'BHYT_Tu': ui.bhyt_from.date().toString("dd/MM/yyyy"),
            'BHYT_Den': ui.bhyt_to.date().toString("dd/MM/yyyy"),
            'DiaChi': ui.dia_chi.text().strip(),
            'SDT': ui.sdt.text().strip(),
            'CCCD': ui.cccd.text().strip(),

            'Tuoi': ui.tuoi.text().strip(),
            'MaDoiTuong': ui.cb_doi_tuong.currentData(),
            'TenDoiTuong': ui.cb_doi_tuong.currentText(),

            'MaPhongKham': ui.cb_phong_kham.currentData(),
            'PhongKham': ui.cb_phong_kham.currentText(),
            'TenBacSi': ui.ten_bac_si.text().strip(),
            'NgayGioKham': ui.ngay_gio_kham.dateTime().toString("dd/MM/yyyy HH:mm:ss"),

            'MaGiaiQuyet': ui.cb_cach_giai_quyet.currentData(),
            'ChanDoan': ui.chan_doan.text().strip()
                        + ('; ' + ui.ma_icd.text().strip() if ui.ma_icd.text().strip() != '' else '')
                        + ('; ' + ui.ma_icd_phu.text().strip() if ui.ma_icd_phu.text().strip() != '' else ''),
        }

        return data

    # </editor-fold>

    # <editor-fold desc="Lazy Load & Pagination danh sách đã khám trong ngày">

    def update_table_display(self):
        table = self.ui_kham.ds_da_kham
        table.setRowCount(0)

        # 1. Lấy dữ liệu thô từ CSV
        raw_rows = get_todays_csv_rows()

        # 2. Lọc dữ liệu (Search) - [CẬP NHẬT TÊN WIDGET ĐÚNG]
        keyword_id = self.ui_kham.ma_y_te_da_kham.text().strip().lower()
        keyword_name = self.ui_kham.ho_ten_da_kham.text().strip().lower()

        filtered_rows = []
        if not keyword_id and not keyword_name:
            filtered_rows = raw_rows
        else:
            for row in raw_rows:
                # Dữ liệu trong CSV: user_id, user_name
                u_id = row.get('user_id', '').lower()
                u_name = row.get('user_name', '').lower()

                # Logic tìm kiếm gần đúng (chứa từ khóa)
                match_id = keyword_id in u_id if keyword_id else True
                match_name = keyword_name in u_name if keyword_name else True

                if match_id and match_name:
                    filtered_rows.append(row)

        # 3. Tính toán phân trang
        total_items = len(filtered_rows)
        # Nếu items_per_page chưa set, mặc định là 10 (tránh lỗi chia cho 0 hoặc 1 như trong file gốc của bạn đang set là 1)
        if self.items_per_page < 1: self.items_per_page = 10

        self.total_pages = math.ceil(total_items / self.items_per_page)
        if self.total_pages < 1: self.total_pages = 1

        # Validate trang hiện tại
        if self.current_page_index > self.total_pages: self.current_page_index = self.total_pages
        if self.current_page_index < 1: self.current_page_index = 1

        # Hiển thị số trang lên UI
        self.ui_kham.current_page.setText(str(self.current_page_index))
        self.ui_kham.num_page.setText(str(self.total_pages))

        # Cập nhật trạng thái nút
        self.ui_kham.btn_prev_page.setEnabled(self.current_page_index > 1)
        self.ui_kham.btn_next_page.setEnabled(self.current_page_index < self.total_pages)

        if total_items == 0:
            return

        # 4. Cắt dữ liệu (Slicing) cho trang hiện tại
        start_idx = (self.current_page_index - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = filtered_rows[start_idx:end_idx]

        # 5. Đọc JSON chi tiết và Hiển thị
        date_str = datetime.now().strftime("%Y-%m-%d")
        day_dir = os.path.join(TARGET_DIR, date_str)

        for row_data in page_items:
            # Lấy thông tin cơ bản từ CSV
            ma_y_te = row_data.get('user_id', '')
            full_name = row_data.get('user_name', '')
            file_name = row_data.get('file_name', '')
            age = ""
            gender = ""
            bhyt = ""

            # --- LAZY LOAD JSON ---
            json_path = os.path.join(day_dir, file_name)
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                        bills = data.get('bills', {})
                        bill = bills.get('drug_bill') or bills.get('service_bill') or bills.get('invoice')
                        if bill:
                            age = bill.get('Tuoi', '')
                            gender = bill.get('GioiTinh', '')
                            bhyt = bill.get('BHYT', '')
                            # Nếu trong bill có tên đầy đủ hơn thì lấy
                            if bill.get('HoTen'):
                                full_name = bill.get('HoTen')
                except:
                    pass

            row_idx = table.rowCount()
            table.insertRow(row_idx)

            vals = [ma_y_te, full_name, age, gender, bhyt]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)  # Readonly
                table.setItem(row_idx, col, item)

    def on_prev_page(self):
        if self.current_page_index > 1:
            self.current_page_index -= 1
            self.update_table_display()

    def on_next_page(self):
        if self.current_page_index < self.total_pages:
            self.current_page_index += 1
            self.update_table_display()

    # </editor-fold>

    # <editor-fold desc="Load lại dữ liệu từ JSON khi Double Click">

    def on_patient_double_click(self, row, col):
        """Sự kiện chính: Xác định bệnh nhân và load dữ liệu."""
        # 1. Lấy Mã Y Tế từ cột 0 của dòng được click
        item_id = self.ui_kham.ds_da_kham.item(row, 0)
        if not item_id:
            return

        self.reset_all()
        self.req_reset_dich_vu.emit()

        user_id = item_id.text().strip()

        # 2. Xác định đường dẫn file JSON
        # Lưu ý: Logic này giả định load dữ liệu của ngày hiện tại (theo cấu trúc folder của bạn)
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_id = "".join(c for c in user_id if c.isalnum() or c in ('-', '_'))
        json_filename = f"{safe_id}.json"
        json_path = os.path.join(TARGET_DIR, date_str, json_filename)

        if not os.path.exists(json_path):
            QMessageBox.warning(self, "Lỗi", f"Không tìm thấy file dữ liệu: {json_filename}")
            return

        # 3. Đọc và đổ dữ liệu
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                full_data = json.load(f)

            # Lấy phần phiếu khám (drug_bill)
            bills = full_data.get('bills', {})
            drug_bill = bills.get('drug_bill')
            service_bill = bills.get('service_bill')

            if service_bill:
                self.fill_form_data(service_bill, load_prescription=False)
                self.req_load_service_bill.emit(service_bill)

            if drug_bill:
                self.fill_form_data(drug_bill, load_prescription=True)

        except Exception as e:
            print(f"Lỗi load lại json: {e}")
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc file dữ liệu: {e}")

    def fill_form_data(self, data: dict, load_prescription: bool = True):
        """Map dữ liệu từ Dictionary vào UI."""
        ui = self.ui_kham

        # --- 1. Thông tin Hành Chính ---
        self.ma_y_te = data.get('MaYTe', '')
        ui.ma_y_te.setText(data.get('MaYTe', ''))
        ui.ho_ten_bn.setText(data.get('HoTen', ''))
        ui.dia_chi.setText(data.get('DiaChi', ''))
        ui.sdt.setText(data.get('SDT', ''))
        ui.so_bhyt.setText(data.get('BHYT', ''))
        ui.cccd.setText(data.get('CCCD', ''))
        ui.tuoi.setText(data.get('Tuoi', ''))
        ui.cb_gioi_tinh.setCurrentText(data.get('GioiTinh', ''))

        # Xử lý ComboBox Đối tượng, Phòng khám (Dùng findText để set chuẩn)
        idx_doi_tuong = ui.cb_doi_tuong.findText(data.get('DoiTuong', ''))
        if idx_doi_tuong >= 0: ui.cb_doi_tuong.setCurrentIndex(idx_doi_tuong)
        self.handle_update_doi_tuong()

        idx_pk = ui.cb_phong_kham.findText(data.get('PhongKham', ''))
        if idx_pk >= 0: ui.cb_phong_kham.setCurrentIndex(idx_pk)

        ui.ten_bac_si.setText(data.get('TenBacSi', ''))

        # --- 2. Chỉ số sinh tồn ---
        ui.mach.setText(data.get('Mach', ''))
        ui.nhiet_do.setText(data.get('NhietDo', ''))
        ui.can_nang.setText(data.get('CanNang', ''))

        # Tách huyết áp (Ví dụ: 120/80)
        ha = data.get('HA', '')
        if '/' in ha:
            parts = ha.split('/')
            ui.huyet_ap_1.setText(parts[0])
            ui.huyet_ap_2.setText(parts[1])
        else:
            ui.huyet_ap_1.setText(ha)
            ui.huyet_ap_2.setText('')

        # --- 3. Chẩn đoán & Hẹn khám ---
        # Tách Mã ICD và Chẩn đoán (Do lúc lưu ta ghép: "Tên bệnh; A01")
        full_chan_doan = data.get('ChanDoan', '')
        parts_cd = full_chan_doan.split(';')
        if len(parts_cd) > 1:
            ui.chan_doan.setText(parts_cd[0].strip())
            # Giả định phần sau cùng là mã ICD nếu có
            ui.ma_icd.setText(parts_cd[-1].strip())
        else:
            ui.chan_doan.setText(full_chan_doan)

        # Hẹn khám
        so_ngay_hen = data.get('SoNgayHenTaiKham', '0')
        if so_ngay_hen and str(so_ngay_hen) != '0':
            ui.is_hen_kham.setChecked(True)
            ui.so_ngay_hen.setText(str(so_ngay_hen))
            self.update_ngay_hen()  # Gọi hàm update để tính ngày cụ thể
        else:
            ui.is_hen_kham.setChecked(False)
            ui.so_ngay_hen.clear()
            self.update_ngay_hen()

        if load_prescription:
            self.reset_prescription_table()
            toa_thuoc = data.get('ToaThuoc', [])

            # Đảo ngược danh sách để insert đúng thứ tự (vì hàm insert luôn chèn row 0 nhưng data lại append xuống dưới)
            # Tuy nhiên hàm _insert_static_drug_row của bạn chèn vào index chỉ định,
            # nên ta cần loop xuôi và chèn vào cuối (trước dòng trống input).

            # Cách an toàn nhất với cấu trúc hiện tại:
            # Table của bạn: Row 0 là Input. Row 1 -> N là dữ liệu.
            # Ta sẽ chèn lần lượt vào sau dòng 0.

            row_idx = 1
            for drug in toa_thuoc:
                # Map lại dữ liệu từ JSON key sang list value theo đúng thứ tự cột
                # Cấu trúc list mong đợi: [DuocId, MaThuoc, TenThuoc, DonVi, Sang, Trua, Chieu, Toi, SoNgay, SoLuong, DonGia, Note, DuongDung]
                # Lưu ý: Cần đối chiếu chính xác với HEADER_THUOC trong table_thuoc_configs

                # Tạo list rỗng với kích thước chuẩn
                drug_values = [""] * (DRUG_COL_COUNT - 1)  # -1 vì không có cột Hủy trong data trích xuất

                # Fill dữ liệu vào list (Hardcode mapping dựa trên logic save)
                drug_values[COL_DUOC_ID] = drug.get('DuocId', '')
                drug_values[COL_MA_THUOC] = drug.get('MaThuoc', '')
                drug_values[COL_TEN_THUOC] = drug.get('TenThuoc', '')
                drug_values[COL_DON_VI_TINH] = drug.get('DonViTinh', '')
                drug_values[COL_SANG] = drug.get('Sang', '0')
                drug_values[COL_TRUA] = drug.get('Trua', '0')
                drug_values[COL_CHIEU] = drug.get('Chieu', '0')
                drug_values[COL_TOI] = drug.get('Toi', '0')
                drug_values[COL_SO_NGAY] = drug.get('SoNgay', '0')
                drug_values[COL_SO_LUONG] = drug.get('SoLuong', '0')
                drug_values[COL_DON_GIA] = drug.get('DonGia', '0')
                drug_values[COL_DUONG_DUNG] = drug.get('TenThuocPhu',
                                                       '')  # Lúc lưu bạn map DuongDung vào TenThuocPhu

                # Gọi hàm có sẵn để chèn
                self._insert_static_drug_row(ui.ds_thuoc, row_idx, drug_values)
                row_idx += 1

            self.update_row_numbers()
            self.ui_kham.ma_y_te.setFocus()

        # </editor-fold>

    def get_scanner_port_name(self):
        """Tự động bắt cổng COM nghi ngờ là máy quét nhất mà không cần ID cứng"""
        from PyQt6.QtSerialPort import QSerialPortInfo
        
        available_ports = QSerialPortInfo.availablePorts()
        if not available_ports:
            return None

        # Danh sách từ khóa thường xuất hiện trong tên/mô tả của máy quét mã vạch
        target_keywords = ['newland', 'barcode', 'scanner', 'symbol', 'honeywell', 'datalogic']
        
        # Ưu tiên tuyệt đối những cổng có tên hãng máy quét
        for port in available_ports:
            desc = port.description().lower()
            manu = port.manufacturer().lower()
            if any(keyword in desc for keyword in target_keywords) or any(keyword in manu for keyword in target_keywords):
                return port.portName()

        # Nếu không tìm thấy, thử kiểm tra các cổng có mô tả phổ biến của chip USB-to-Serial (CH340, PL2303)
        for port in available_ports:
            desc = port.description().lower()
            if 'usb serial device' in desc or 'ch340' in desc or 'pl2303' in desc:
                return port.portName()

        # Không tự động thử các cổng chung như COM4 khi chưa xác định là máy quét.
        return None

    def _schedule_serial_open(self, delay_ms=0):
        self._scanner_open_attempted = False
        self._scanner_open_in_progress = False
        if self._scanner_open_timer.isActive():
            return
        self._scanner_open_timer.start(delay_ms)

    def _attempt_open_serial_port(self):
        if self._scanner_open_in_progress or self._scanner_open_attempted:
            return

        self._scanner_open_attempted = True
        self._scanner_open_in_progress = True
        try:
            if not hasattr(self, 'serial') or self.serial is None:
                self.serial = QSerialPort(self)
                self.serial.readyRead.connect(self.read_serial_data)

            if self.serial.isOpen():
                return

            target_port = self.get_scanner_port_name()
            if not target_port:
                return

            self.serial.setPortName(target_port)
            self.serial.setBaudRate(9600)
            self.serial.setDataBits(QSerialPort.DataBits.Data8)
            self.serial.setParity(QSerialPort.Parity.NoParity)
            self.serial.setStopBits(QSerialPort.StopBits.OneStop)
            self.serial.setFlowControl(QSerialPort.FlowControl.NoFlowControl)
            if self.serial.open(QSerialPort.OpenModeFlag.ReadOnly):
                self._scanner_open_retry_count = 0
            else:
                self._scanner_open_retry_count += 1
                self.serial.close()
        finally:
            self._scanner_open_in_progress = False

    def setup_serial_scanner(self):
        """Khởi tạo và cấu hình cổng COM đọc dữ liệu từ máy quét"""
        self._schedule_serial_open(0)

    def open_serial_port(self):
        """Mở lại cổng COM tại Tab Khám bệnh"""
        self._scanner_open_attempted = False
        self._scanner_open_in_progress = False
        self._schedule_serial_open(0)

    def close_serial_port(self):
        """Đóng cổng COM khi ẩn Tab Khám bệnh"""
        self._scanner_open_timer.stop()
        self._scanner_open_attempted = False
        self._scanner_open_in_progress = False
        if hasattr(self, 'serial') and self.serial is not None:
            if self.serial.isOpen():
                self.serial.close()
                print("Đã đóng cổng kết nối tại Tab Khám Bệnh.")

    def read_serial_data(self):
        """Đọc tích lũy dữ liệu cổng COM"""
        if not hasattr(self, 'serial_buffer'):
            self.serial_buffer = b""
        self.serial_buffer += self.serial.readAll().data()
        try:
            text = self.serial_buffer.decode('utf-8', errors='ignore')
        except UnicodeDecodeError:
            return
        if '\r' in text or '\n' in text:
            clean_text = text.strip()
            if "|" in clean_text and len(clean_text.split("|")) >= 6:
                self.parse_cccd_qr_data(clean_text)
            self.serial_buffer = b""

    def parse_cccd_qr_data(self, qr_text):
        """"Xử lý dữ liệu QR CCCD từ máy quét và ánh xạ sang các ô nhập liệu"""
        if self.is_processing_scan:
            return
        self.is_processing_scan = True

        try:
            scanned_data = parse_scanned_data(qr_text)
            if not scanned_data:
                return

            cccd_code = scanned_data.get('cccd', '')
            ho_ten = scanned_data.get('ho_ten', '')
            gioi_tinh = scanned_data.get('gioi_tinh', '')
            ngay_sinh_raw = scanned_data.get('ngay_sinh', '')
            dia_chi = scanned_data.get('dia_chi', '')

            if cccd_code:
                self.ui_kham.cccd.setText(cccd_code)
            if ho_ten:
                self.ui_kham.ho_ten_bn.setText(ho_ten)
            if dia_chi:
                self.ui_kham.dia_chi.setText(dia_chi)

            # Gán giới tính
            if hasattr(self, '_normalize_gioi_tinh'):
                gioi_tinh_chuan = self._normalize_gioi_tinh(gioi_tinh)
            else:
                text_gt = str(gioi_tinh or '').strip().lower()
                mapping_gt = {'nam': 'Nam', 'nu': 'Nữ', 'nữ': 'Nữ', 'g': 'Nữ', 'm': 'Nam'}
                gioi_tinh_chuan = mapping_gt.get(text_gt, 'Nam')
            if gioi_tinh_chuan:
                self.ui_kham.cb_gioi_tinh.setCurrentText(gioi_tinh_chuan)

            # Xử lý năm sinh
            date_parsed = self._parse_cccd_date(ngay_sinh_raw)
            if date_parsed.isValid():
                year_of_birth = date_parsed.year()
                self.ui_kham.ngay_sinh.setDate(QDate(year_of_birth, 1, 1))
                # Gọi hàm tính tuổi của tab khám bệnh nếu có
                if hasattr(self, 'update_tuoi'):
                    self.update_tuoi()

        except Exception as e:
            QMessageBox.warning(self, "Lỗi quét mã", f"Lỗi phân tích dữ liệu CCCD tại phòng khám: {str(e)}")
        finally:
            QTimer.singleShot(1500, lambda: setattr(self, 'is_processing_scan', False))

    def _parse_cccd_date(self, date_str):
        """Hàm parse date từ mã QR CCCD"""
        date_str = str(date_str).strip()
        if len(date_str) == 8 and date_str.isdigit():
            day = int(date_str[0:2])
            month = int(date_str[2:4])
            year = int(date_str[4:8])
            res_date = QDate(year, month, day)
            if res_date.isValid():
                return res_date
        for fmt in ('dd/MM/yyyy', 'dd-MM-yyyy'):
            parsed = QDate.fromString(date_str, fmt)
            if parsed.isValid():
                return parsed
        return QDate()

    # </editor-fold>