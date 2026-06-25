from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QLocale, QDate, Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem, QWidget, QHBoxLayout, QCheckBox
import sys

# --- IMPORT SERVICES ---
from app.services.DuocService import get_duoc_by_duoc_id
from app.services.DichVuService import get_gia_dich_vu, get_dich_vu_by_dich_vu_id
from app.services.LoaiGiaService import get_list_loai_gia

from app.controllers.dich_vu_controller import get_checkbox_state
from app.core.in_hoa_don import create_and_open_pdf_for_printing
from app.services.BenhNhanService import get_benh_nhan_by_id
from app.services.DoiTuongService import get_list_doi_tuong
from app.styles.styles import TUOI_STYLE, TAI_VU_STYLE, ADD_BTN_STYLE, COMPLETER_THUOC_STYLE
from app.ui.TabTaiVu import Ui_formTaiVu
from app.utils.chuyen_tien_thanh_chu import chuyen_tien_thanh_chu
from app.utils.config_manager import ConfigManager
from app.utils.cong_thuc_tinh_bhyt import tinh_tien_mien_giam
from app.utils.export_excel import export_and_show_dialog
from app.utils.scanner_utils import parse_scanned_data
from app.utils.utils import format_currency_vn, unformat_currency_to_float, calculate_age, populate_list_to_combobox
from app.utils.write_json_line import write_json_lines, MODE_JSON
from app.configs.table_dich_vu_configs import *

MAX_DOUBLE_VALUE = sys.float_info.max


def create_checkbox_widget(is_checked: bool, func=None):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    checkbox = QCheckBox()
    checkbox.setChecked(is_checked)
    if func:
        checkbox.clicked.connect(func)
    layout.addWidget(checkbox)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.setContentsMargins(0, 0, 0, 0)
    return widget


class TaiVuTabController(QtWidgets.QWidget):
    req_dang_ky_cls = pyqtSignal()

    def __init__(self, tab_widget_container, parent=None):
        super().__init__(parent)

        self.bhyt = None

        # <editor-fold desc="Init UI">
        self.ui_tai_vu = Ui_formTaiVu()
        self.ui_tai_vu.setupUi(tab_widget_container)
        # </editor-fold>

        doi_tuong_data = get_list_doi_tuong()
        populate_list_to_combobox(self.ui_tai_vu.cb_doi_tuong,
                                  data=doi_tuong_data,
                                  display_col=2,  # TenDoiTuong
                                  key_col=0)  # DoiTuong_Id

        self.reset_all()
        self.setup_dong_ho()
        self.setup_validator()
        self.setup_table_dich_vu()

        self.config_manager = ConfigManager()
        self.load_saved_settings()

        self.connect_signals()
        self.set_stylesheet()
        self.update_tuoi()

    # <editor-fold desc="Set stylesheet">
    def set_stylesheet(self):
        ui = self.ui_tai_vu
        ui.ho_ten.setStyleSheet(TAI_VU_STYLE)
        ui.tuoi.setStyleSheet(TAI_VU_STYLE)
        ui.cb_doi_tuong.setStyleSheet(COMPLETER_THUOC_STYLE)
        ui.cb_hinh_thuc_tt.setStyleSheet(COMPLETER_THUOC_STYLE)
        ui.dia_chi.setStyleSheet(TAI_VU_STYLE)
        ui.so_tien_text.setStyleSheet(TUOI_STYLE)
        ui.thanh_chu_text.setStyleSheet("font-size: 12px;")

        ui.btn_in_hoa_don.setStyleSheet(ADD_BTN_STYLE)
        ui.btn_reset_all.setStyleSheet(ADD_BTN_STYLE)
        ui.btn_dang_ky.setStyleSheet(ADD_BTN_STYLE)
        ui.btn_export.setStyleSheet(ADD_BTN_STYLE)

    # </editor-fold>

    # <editor-fold desc="Save & load setting">
    def save_settings(self):
        nguoi_tao = self.ui_tai_vu.ho_ten_nguoi_tao.text()
        nguoi_thu = self.ui_tai_vu.ho_ten_nguoi_thu.text()
        self.config_manager.save_last_tai_vu_selection(nguoi_tao, nguoi_thu)

    def load_saved_settings(self):
        ten_nguoi_tao, ten_nguoi_thu = self.config_manager.load_last_tai_vu_selection()
        if ten_nguoi_tao:
            self.ui_tai_vu.ho_ten_nguoi_tao.setText(ten_nguoi_tao)
        if ten_nguoi_thu:
            self.ui_tai_vu.ho_ten_nguoi_thu.setText(ten_nguoi_thu)

    # </editor-fold>

    # <editor-fold desc="Setup validator">
    def setup_validator(self):
        validator = QDoubleValidator(0.00, MAX_DOUBLE_VALUE, 3, self)
        us_locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        validator.setLocale(us_locale)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.ui_tai_vu.tong_so_tien.setValidator(validator)

    # </editor-fold>

    # <editor-fold desc="Setup đồng hồ">
    def setup_dong_ho(self):
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_datetime_edit)
        self.timer.start(1000)
        self.update_datetime_edit()

    def update_datetime_edit(self):
        self.ui_tai_vu.ngay_tao.setDateTime(QtCore.QDateTime.currentDateTime())
        self.ui_tai_vu.ngay_thu.setDateTime(QtCore.QDateTime.currentDateTime())

    # </editor-fold>

    def get_scanner_port_name(self):
        available_ports = QSerialPortInfo.availablePorts()
        if not available_ports:
            return None

        target_keywords = ['newland', 'barcode', 'scanner', 'symbol', 'honeywell', 'datalogic']
        for port in available_ports:
            desc = port.description().lower()
            manu = port.manufacturer().lower()
            if any(keyword in desc for keyword in target_keywords) or any(keyword in manu for keyword in target_keywords):
                return port.portName()

        for port in available_ports:
            desc = port.description().lower()
            if 'usb serial device' in desc or 'ch340' in desc or 'pl2303' in desc:
                return port.portName()

        return available_ports[-1].portName()

    def setup_serial_scanner(self):
        if not hasattr(self, 'serial') or self.serial is None:
            self.serial = QSerialPort(self)
            self.serial.readyRead.connect(self.read_serial_data)

        if self.serial.isOpen():
            self.serial.close()

        target_port = self.get_scanner_port_name()
        if not target_port:
            print('Không tìm thấy cổng COM cho máy quét tại Tab Tài vụ.')
            return

        self.serial.setPortName(target_port)
        self.serial.setBaudRate(9600)
        if self.serial.open(QSerialPort.OpenModeFlag.ReadOnly):
            print(f'Đã kết nối máy quét thành công tại cổng {target_port} tại Tab Tài vụ.')
        else:
            print(f'Cảnh báo cổng {target_port} tại Tab Tài vụ: {self.serial.errorString()}')

    def open_serial_port(self):
        if hasattr(self, 'serial') and self.serial is not None:
            if not self.serial.isOpen():
                if self.serial.open(QSerialPort.OpenModeFlag.ReadOnly):
                    print(f'Đã mở lại cổng kết nối tại Tab Tài vụ.')
                else:
                    print(f'Tab Tài vụ: Lỗi mở lại cổng ({self.serial.errorString()})')
        else:
            self.setup_serial_scanner()

    def close_serial_port(self):
        if hasattr(self, 'serial') and self.serial is not None and self.serial.isOpen():
            self.serial.close()
            print('Đã đóng cổng kết nối tại Tab Tài vụ.')

    def read_serial_data(self):
        if not hasattr(self, 'serial_buffer'):
            self.serial_buffer = b''

        self.serial_buffer += self.serial.readAll().data()
        try:
            text = self.serial_buffer.decode('utf-8', errors='ignore')
        except UnicodeDecodeError:
            return

        if '\r' in text or '\n' in text:
            clean_text = text.strip()
            if clean_text:
                self.process_qr_data(clean_text)
            self.serial_buffer = b''

    def setup_table_dich_vu(self):
        table = self.ui_tai_vu.table_dich_vu
        table.horizontalHeader().setMinimumHeight(MIN_COLUMN_HEIGHT)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter |
                                                     Qt.TextFlag.TextWordWrap)
        self.ui_tai_vu.table_dich_vu.setColumnCount(DICH_VU_COL_COUNT)
        self.ui_tai_vu.table_dich_vu.setHorizontalHeaderLabels(HEADER_DICH_VU)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_DICH_VU_ID, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_MA_DV, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_MA_NHOM_DV, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_TY_LE_TT, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_CHON_IN, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_SO_PHIEU, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_LY_DO_KHONG_THU, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_NOI_THUC_HIEN, True)
        self.ui_tai_vu.table_dich_vu.setColumnHidden(COL_HUY, True)
        for i in range(len(HEADER_DICH_VU)):
            table.setColumnWidth(i, MIN_COLUMN_WIDTH)

        self.ui_tai_vu.table_dich_vu.setColumnWidth(COL_TEN_DV, COL_SERVICE_TABLE_DEFAULT_WIDTH * 2)

        self.ui_tai_vu.table_dich_vu.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ui_tai_vu.table_dich_vu.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui_tai_vu.table_dich_vu.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.ui_tai_vu.table_dich_vu.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.update_table_dich_vu_row_number()

    # <editor-fold desc="TÍNH TOÁN BHYT VÀ CẬP NHẬT BẢNG DỊCH VỤ">
    def _calculate_table_summary(self) -> dict:
        table = self.ui_tai_vu.table_dich_vu
        ma_doi_tuong = self.ui_tai_vu.cb_doi_tuong.currentData()
        total_thanh_tien = 0.0
        total_thanh_tien_huong_bao_hiem = 0.0
        max_row = table.rowCount()
        if (max_row > 0 and
                table.verticalHeaderItem(max_row - 1) and
                table.verticalHeaderItem(max_row - 1).text() == "TỔNG"):
            max_row -= 1

        for row in range(max_row):
            is_checked_khong_thu_tien = get_checkbox_state(table, row, COL_KHONG_THU_TIEN)
            is_checked_khong_ho_tro = get_checkbox_state(table, row, COL_KHONG_HO_TRO)
            item_thanh_tien = table.item(row, COL_THANH_TIEN_DOANH_THU)
            if is_checked_khong_thu_tien:
                item_thanh_tien.setText(format_currency_vn(0))
                continue
            item_don_gia = unformat_currency_to_float(table.item(row, COL_DON_GIA_DOANH_THU).text())
            item_so_luong = unformat_currency_to_float(table.item(row, COL_SO_LUONG).text())
            thanh_tien = item_don_gia * item_so_luong
            item_thanh_tien.setText(format_currency_vn(thanh_tien))
            total_thanh_tien += thanh_tien
            if not is_checked_khong_ho_tro:
                total_thanh_tien_huong_bao_hiem += thanh_tien

        total_bao_hiem_thanh_toan = 0.0
        total_benh_nhan_thanh_toan = 0.0
        for row in range(max_row):
            is_checked_khong_ho_tro = get_checkbox_state(table, row, COL_KHONG_HO_TRO)
            thanh_tien_dich_vu = unformat_currency_to_float(table.item(row, COL_THANH_TIEN_DOANH_THU).text())
            bao_hiem_thanh_toan = 0
            if not is_checked_khong_ho_tro:
                bao_hiem_thanh_toan = tinh_tien_mien_giam(
                    total_thanh_tien_huong_bao_hiem,
                    thanh_tien_dich_vu,
                    ma_doi_tuong
                )

            item_bh_tt = table.item(row, COL_BH_TT)
            item_bh_tt.setText(format_currency_vn(bao_hiem_thanh_toan))
            benh_nhan_thanh_toan = thanh_tien_dich_vu - bao_hiem_thanh_toan

            item_bn_tt = table.item(row, COL_BN_TT)
            item_bn_tt.setText(format_currency_vn(benh_nhan_thanh_toan))
            total_bao_hiem_thanh_toan += bao_hiem_thanh_toan
            total_benh_nhan_thanh_toan += benh_nhan_thanh_toan

        return {
            'ThanhTien': format_currency_vn(total_thanh_tien),
            'BHTong': format_currency_vn(total_bao_hiem_thanh_toan),
            'BNTong': format_currency_vn(total_benh_nhan_thanh_toan)
        }

    def _update_table_summary_row(self):
        table = self.ui_tai_vu.table_dich_vu
        summary_data = self._calculate_table_summary()
        row_count = table.rowCount()
        table.insertRow(row_count)
        new_summary_row_index = row_count
        total_header = QtWidgets.QTableWidgetItem("TỔNG")
        table.setVerticalHeaderItem(new_summary_row_index, total_header)
        table.setSpan(new_summary_row_index, 0, 1, COL_THANH_TIEN_DOANH_THU)
        item_label = QTableWidgetItem("TỔNG CỘNG:")
        item_label.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item_label.setFlags(item_label.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(new_summary_row_index, 0, item_label)
        summary_cols = [
            (COL_THANH_TIEN_DOANH_THU, summary_data['ThanhTien']),
            (COL_BH_TT, summary_data['BHTong']),
            (COL_BN_TT, summary_data['BNTong'])
        ]
        for col_index, value in summary_cols:
            item = QTableWidgetItem(f"{value}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(new_summary_row_index, col_index, item)

    def update_table_dich_vu_row_number(self):
        table = self.ui_tai_vu.table_dich_vu

        row_count = table.rowCount()
        for row in range(table.rowCount() - 1, -1, -1):
            header_item = table.verticalHeaderItem(row)
            if header_item and header_item.text() == "TỔNG":
                table.removeRow(row)
                row_count -= 1  # Giảm số dòng
                break

        for i in range(row_count):
            item = QtWidgets.QTableWidgetItem(str(i + 1))
            table.setVerticalHeaderItem(i, item)

        self._update_table_summary_row()

    # </editor-fold>

    # <editor-fold desc="Connect Signals">
    def connect_signals(self):
        ui = self.ui_tai_vu

        ui.ho_ten_nguoi_tao.textEdited.connect(self.save_settings)
        ui.ho_ten_nguoi_thu.textEdited.connect(self.save_settings)

        ui.nam_sinh.dateChanged.connect(self.update_tuoi)

        ui.tong_so_tien.textEdited.connect(self.format_tong_so_tien)
        ui.btn_in_hoa_don.clicked.connect(self.handle_in_hoa_don)
        ui.btn_reset_all.clicked.connect(self.reset_all)
        ui.btn_dang_ky.clicked.connect(self.req_dang_ky_cls.emit)
        ui.btn_export.clicked.connect(lambda: export_and_show_dialog(self))

        # --- THAY ĐỔI QUAN TRỌNG CHO MÁY QUÉT ---
        # Không dùng textEdited cho ma_y_te nữa vì máy quét gõ rất nhanh sẽ gây lag
        # Dùng returnPressed: Sự kiện khi nhấn Enter (Máy quét thường tự gửi Enter cuối cùng)
        ui.ma_y_te.returnPressed.connect(self.handle_scan_or_enter)

    # </editor-fold>

    # <editor-fold desc="Xử lý nhập liệu (Máy quét & Nhập tay)">
    def handle_scan_or_enter(self):
        """
        Hàm này xử lý 2 trường hợp:
        1. Máy quét bắn vào chuỗi dài (có chứa ký tự đặc biệt hoặc dấu phân cách).
        2. Người dùng nhập tay Mã Y Tế ngắn và nhấn Enter.
        """
        input_text = self.ui_tai_vu.ma_y_te.text().strip()

        if not input_text:
            return

        # Kiểm tra xem đây là chuỗi QR đầy đủ hay chỉ là Mã Y Tế nhập tay
        # Dấu hiệu nhận biết: Chuỗi QR của bạn có chứa dấu '|' hoặc dài hơn mã y tế chuẩn
        if "|" in input_text or ":" in input_text:
            # Trường hợp 1: Dữ liệu từ máy quét QR
            self.process_qr_data(input_text)
        else:
            # Trường hợp 2: Nhập tay Mã Y Tế (ví dụ: BN0001)
            self.load_thong_tin_benh_nhan(input_text)

    def process_qr_data(self, data: str):
        """
        Phân tích chuỗi dữ liệu từ máy quét và điền vào form.
        Format: 'MaYTe:BN0002|BHYT:...|Loai:TYPE|DS:ID:Q;ID:Q...'
        """
        ui = self.ui_tai_vu
        data_parts = {}

        try:
            scanned_data = parse_scanned_data(data)

            if scanned_data and (scanned_data.get('ma_y_te') or scanned_data.get('ho_ten') or scanned_data.get('bill_type') or scanned_data.get('ds_string')):
                if scanned_data.get('ma_y_te'):
                    ui.ma_y_te.setText(scanned_data.get('ma_y_te', ''))
                if scanned_data.get('ho_ten'):
                    ui.ho_ten.setText(scanned_data.get('ho_ten', ''))
                if scanned_data.get('dia_chi'):
                    ui.dia_chi.setText(scanned_data.get('dia_chi', ''))
                if scanned_data.get('tuoi'):
                    ui.tuoi.setText(str(scanned_data.get('tuoi', '')))
                if scanned_data.get('bhyt'):
                    self.bhyt = scanned_data.get('bhyt', '')

                ma_dt = scanned_data.get('ma_dt', '')
                if ma_dt:
                    index = ui.cb_doi_tuong.findData(ma_dt)
                    if index != -1:
                        ui.cb_doi_tuong.setCurrentIndex(index)
                    else:
                        index = ui.cb_doi_tuong.findText(ma_dt)
                        if index != -1:
                            ui.cb_doi_tuong.setCurrentIndex(index)

                tong_tien_raw = scanned_data.get('tien', '')
                if tong_tien_raw:
                    tong_tien_input = (tong_tien_raw.replace(' VND', '')
                                       .replace('.', '')
                                       .replace(',', '.'))
                    ui.tong_so_tien.setText(tong_tien_input)
                    self.format_tong_so_tien()

                bill_type = scanned_data.get('bill_type', '')
                ds_string = scanned_data.get('ds_string', '')
                if bill_type and ds_string:
                    self.load_items_from_qr(bill_type, ds_string)
                ui.tong_so_tien.setFocus()
                return

            # Tách chuỗi bằng dấu '|'
            pairs = data.split('|')
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    data_parts[key.strip()] = value.strip()

            # --- Điền dữ liệu Hành Chính ---
            extracted_ma_y_te = data_parts.get('MaYTe', '')
            ui.ma_y_te.setText(extracted_ma_y_te)

            ui.ho_ten.setText(data_parts.get('Ten', ''))
            ui.dia_chi.setText(data_parts.get('DC', ''))
            ui.tuoi.setText(data_parts.get('Tuoi', ''))
            self.bhyt = data_parts.get('BHYT', '')

            ma_dt = data_parts.get('MaDT', '')
            index = ui.cb_doi_tuong.findData(ma_dt)
            if index != -1:
                ui.cb_doi_tuong.setCurrentIndex(index)

            tong_tien_raw = data_parts.get('Tien', '')
            if tong_tien_raw:
                tong_tien_input = (tong_tien_raw.replace(' VND', '')
                                   .replace('.', '')
                                   .replace(',', '.'))
                ui.tong_so_tien.setText(tong_tien_input)
                self.format_tong_so_tien()

            # --- Xử lý Danh Sách Thuốc / Dịch Vụ ---
            bill_type = data_parts.get('Loai')
            ds_string = data_parts.get('DS')

            if bill_type and ds_string:
                self.load_items_from_qr(bill_type, ds_string)

            ui.tong_so_tien.setFocus()

        except Exception as e:
            QMessageBox.critical(self, "Lỗi Dữ Liệu", f"QR không đúng định dạng: {e}")
            self.reset_all()

    def load_items_from_qr(self, bill_type, ds_string):
        self.delete_all_rows()
        items = ds_string.split(';')
        doi_tuong_id = self.ui_tai_vu.cb_doi_tuong.currentData()

        # Cache LoaiGia names nếu là Dịch vụ (để hiển thị tên loại giá)
        loai_gia_map = {}
        if bill_type == 'DICH_VU':
            lgs = get_list_loai_gia()
            for lg in lgs:
                # lg: (LoaiGia_Id, MaLoaiGia, TenLoaiGia)
                loai_gia_map[str(lg[0])] = lg[2]

        for item_str in items:
            parts = item_str.split(':')
            row_data = {}

            if bill_type == 'THUOC':
                # Format: ID:Qty
                if len(parts) >= 2:
                    ma_duoc = parts[0]
                    qty = parts[1]
                    duoc_data = get_duoc_by_duoc_id(ma_duoc)
                    if duoc_data:
                        # Map dữ liệu thuốc sang cấu trúc bảng dịch vụ
                        # (Duoc_Id, MaDuoc, TenDuocDayDu, DonGia, TenDonViTinh, CachDung)
                        row_data = {
                            COL_MA_DV: duoc_data[1],
                            COL_MA_NHOM_DV: '',
                            COL_TEN_DV: duoc_data[2],
                            COL_DON_GIA_DOANH_THU: format_currency_vn(duoc_data[3]),
                            COL_SO_LUONG: qty,
                            COL_THANH_TIEN_DOANH_THU: '',
                            COL_MA_LOAI_GIA: '',
                            COL_LOAI_GIA: '',
                            COL_NOI_THUC_HIEN: '',
                            COL_BH_TT: '',
                            COL_BN_TT: '',
                            COL_KHONG_THU_TIEN: 0,
                            COL_KHONG_HO_TRO: 0
                        }

            elif bill_type == 'DICH_VU':
                # Format: ID:LoaiGia:Qty:KHT:KTT
                if len(parts) >= 5:
                    ma_dv = parts[0]
                    lg_id = parts[1]
                    qty = parts[2]
                    kht = int(parts[3])
                    ktt = int(parts[4])

                    # Lấy thông tin dịch vụ
                    # get_dich_vu_by_input_code trả về: (DichVu_Id, InputCode, TenDichVu, NhomDichVu_Id)
                    dv_data = get_dich_vu_by_dich_vu_id(str(doi_tuong_id), ma_dv)

                    if dv_data:
                        # Lấy đơn giá theo loại giá
                        gia_data = get_gia_dich_vu(dv_data[0], lg_id)
                        don_gia = gia_data[0] if gia_data else 0

                        row_data = {
                            COL_MA_DV: dv_data[1],
                            COL_MA_NHOM_DV: '',
                            COL_TEN_DV: dv_data[2],
                            COL_DON_GIA_DOANH_THU: format_currency_vn(don_gia),
                            COL_SO_LUONG: qty,
                            COL_THANH_TIEN_DOANH_THU: '',
                            COL_TY_LE_TT: '',
                            COL_MA_LOAI_GIA: lg_id,
                            COL_LOAI_GIA: loai_gia_map.get(str(lg_id), str(lg_id)),
                            COL_NOI_THUC_HIEN: '',
                            COL_BH_TT: '',
                            COL_BN_TT: '',
                            COL_KHONG_THU_TIEN: ktt,
                            COL_KHONG_HO_TRO: kht,
                            COL_SO_PHIEU: '',
                            COL_LY_DO_KHONG_THU: '',
                        }

            if row_data:
                self.add_row_to_table(row_data)

        # Cập nhật số thứ tự và TÍNH LẠI TỔNG TIỀN
        self.update_table_dich_vu_row_number()

    def add_row_to_table(self, data):
        ui = self.ui_tai_vu
        table = ui.table_dich_vu

        current_row_count = table.rowCount()
        table.insertRow(current_row_count)

        # 1. Fill Text Columns
        for col_idx, value in data.items():
            if col_idx in [COL_KHONG_THU_TIEN, COL_KHONG_HO_TRO]:
                continue
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(current_row_count, col_idx, item)

        # 2. Fill Checkboxes (KHT, KTT)
        ktt = data.get(COL_KHONG_THU_TIEN, 0)
        kht = data.get(COL_KHONG_HO_TRO, 0)

        cb_ktt = create_checkbox_widget(bool(ktt), None)
        cb_ktt.findChild(QCheckBox).setEnabled(False)
        table.setCellWidget(current_row_count, COL_KHONG_THU_TIEN, cb_ktt)

        cb_kht = create_checkbox_widget(bool(kht), None)
        cb_kht.findChild(QCheckBox).setEnabled(False)
        table.setCellWidget(current_row_count, COL_KHONG_HO_TRO, cb_kht)

    def load_thong_tin_benh_nhan(self, ma_y_te: str):
        """Load dữ liệu từ Database khi nhập tay ID"""
        benh_nhan_data = get_benh_nhan_by_id(ma_y_te)
        if benh_nhan_data is None:
            QMessageBox.warning(self, "Không tìm thấy", f"Không tìm thấy bệnh nhân: {ma_y_te}")
            return

        # print(benh_nhan_data)
        self.set_thong_tin_benh_nhan(benh_nhan_data)

    def update_tuoi(self):
        ui = self.ui_tai_vu
        ngay_sinh = ui.nam_sinh.date()
        tuoi = str(calculate_age(ngay_sinh.toString('dd/MM/yyyy')))
        ui.tuoi.setText(tuoi)
        ui.tuoi.setStyleSheet(TUOI_STYLE)

    def set_thong_tin_benh_nhan(self, benh_nhan_data: tuple):
        ui = self.ui_tai_vu
        ma_y_te = str(benh_nhan_data[0]).upper()
        ho_ten = benh_nhan_data[1]
        nam_sinh = benh_nhan_data[3]
        dia_chi = benh_nhan_data[5]

        nam_sinh = QDate(int(nam_sinh), 1, 1) if nam_sinh is not None else QDate.currentDate()

        ui.ma_y_te.setText(ma_y_te)
        ui.ho_ten.setText(ho_ten)
        ui.dia_chi.setText(dia_chi)
        ui.nam_sinh.setDate(nam_sinh)
        self.update_tuoi()

    # </editor-fold>

    # <editor-fold desc="Format tổng số tiền">
    def format_tong_so_tien(self):
        so_tien_input = self.ui_tai_vu.tong_so_tien.text()
        so_tien_input = so_tien_input.replace(',', '')

        if not so_tien_input:
            self.ui_tai_vu.so_tien_text.setText('<Số tiền>')
            self.ui_tai_vu.thanh_chu_text.setText('<Thành chữ>')
            return

        formatted_so_tien = format_currency_vn(so_tien_input)
        thanh_chu = chuyen_tien_thanh_chu(unformat_currency_to_float(formatted_so_tien))

        self.ui_tai_vu.tong_so_tien.setText(so_tien_input)
        self.ui_tai_vu.so_tien_text.setText(formatted_so_tien + ' VNĐ')
        self.ui_tai_vu.thanh_chu_text.setText(thanh_chu)

    # </editor-fold>

    # <editor-fold desc="Handle in hoá đơn">
    def get_thong_tin(self) -> dict:
        ui = self.ui_tai_vu
        data = dict()
        data['MaYTe'] = ui.ma_y_te.text()
        data['BHYT'] = str(self.bhyt)
        data['HoTen'] = ui.ho_ten.text()
        data['DiaChi'] = ui.dia_chi.toPlainText()
        data['MST'] = ui.mst.text()
        data['TenDonVi'] = ui.ten_cong_ty.text()
        data['TongTienThanhToan'] = ui.so_tien_text.text()
        data['SoTienBangChu'] = ui.thanh_chu_text.text()
        data['HinhThucThanhToan'] = ui.cb_hinh_thuc_tt.currentText()
        data['NguoiThuTien'] = ui.ho_ten_nguoi_thu.text().strip()
        return data

    def check_required_data(self, data: dict) -> bool:
        ui = self.ui_tai_vu
        required_fields = [
            (ui.ho_ten, 'Họ tên'),
            (ui.tong_so_tien, 'Tổng số tiền'),
        ]

        for field, name in required_fields:
            if not field.text().strip():
                QMessageBox.warning(self, "Thiếu dữ liệu", f"Vui lòng nhập {name}!")
                field.setFocus()
                return False
        return True

    def handle_in_hoa_don(self):
        data = self.get_thong_tin()
        if not self.check_required_data(data):
            return

        write_json_lines(data, MODE_JSON.HOA_DON_MODE)

        create_and_open_pdf_for_printing(data)

        self.ui_tai_vu.ma_y_te.setFocus()

        # reply = QMessageBox.question(self, "Xác nhận", "Reset màn hình?",
        #                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # if reply == QMessageBox.StandardButton.Yes:
        #     self.reset_all()

    # </editor-fold>

    # <editor-fold desc="Reset all">
    def delete_all_rows(self):
        table = self.ui_tai_vu.table_dich_vu
        # Xóa các dòng từ cuối lên đầu, trừ dòng tổng (nếu có)
        # Cách an toàn hơn là xóa cho đến khi rowCount == 1 (chỉ còn dòng tổng)
        while table.rowCount() > 1:
            table.removeRow(0)

        self.update_table_dich_vu_row_number()

    def reset_all(self):
        ui = self.ui_tai_vu
        ui.ma_y_te.clear()
        ui.ho_ten.clear()
        ui.dia_chi.clear()
        ui.mst.clear()
        ui.ten_cong_ty.clear()
        ui.tuoi.clear()
        ui.cb_doi_tuong.setCurrentIndex(0)
        ui.tong_so_tien.clear()
        ui.so_tien_text.setText("<Số tiền>")
        ui.thanh_chu_text.setText("<Thành chữ>")
        self.delete_all_rows()

        # QUAN TRỌNG: Set focus vào ô Mã Y Tế để sẵn sàng quét ngay sau khi reset
        ui.ma_y_te.setFocus()

    # </editor-fold>

    # <editor-fold desc="Lấy thông tin bệnh nhân và phòng khám chuyển sang màn hình đăng ký dịch vụ">
    def get_hanh_chinh_data(self) -> dict:
        """
        Thu thập các thông tin hành chính cơ bản của bệnh nhân
        để chuyển sang tab/màn hình khác.
        """
        ui = self.ui_tai_vu

        data = {
            'MaYTe': ui.ma_y_te.text(),
            'HoTenBN': ui.ho_ten.text().strip(),
            # 'GioiTinh': ui.cb_gioi_tinh.currentText(),
            'NgaySinh': ui.nam_sinh.date().toString('yyyy'),

            # 'SoBHYT': ui.so_bhyt.text().strip(),
            # 'BHYT_Tu': ui.bhyt_from.date().toString("dd/MM/yyyy"),
            # 'BHYT_Den': ui.bhyt_to.date().toString("dd/MM/yyyy"),
            'DiaChi': ui.dia_chi.toPlainText(),
            # 'SDT': ui.sdt.text().strip(),

            'Tuoi': ui.tuoi.text().strip(),
            'MaDoiTuong': ui.cb_doi_tuong.currentData(),
            'TenDoiTuong': ui.cb_doi_tuong.currentText(),

            # 'MaPhongKham': ui.cb_phong_kham.currentData(),
            # 'PhongKham': ui.cb_phong_kham.currentText(),
            # 'TenBacSi': ui.ten_bac_si.text().strip(),
            'NgayGioKham': ui.ngay_tao.dateTime().toString("dd/MM/yyyy HH:mm:ss"),
        }

        return data

    def validate_patient_info(self) -> bool:
        """
        Xác thực thông tin hành chính bệnh nhân: Họ tên, Địa chỉ, SĐT, Số BHYT.
        Trả về True nếu hợp lệ, False nếu thiếu và hiển thị cảnh báo.
        """
        ui = self.ui_tai_vu

        if not ui.ho_ten.text().strip():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập họ tên.")
            ui.ho_ten.setFocus()
            return False

        if not ui.dia_chi.toPlainText():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập địa chỉ.")
            ui.dia_chi.setFocus()
            return False

        if not ui.nam_sinh.date().isValid():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập năm sinh hợp lệ.")
            ui.nam_sinh.setFocus()
            return False

        return True
    # </editor-fold>