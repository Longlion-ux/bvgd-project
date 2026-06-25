import re
import math

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtSerialPort import QSerialPort
from PyQt6.QtGui import QKeySequence, QRegularExpressionValidator, QShortcut
from PyQt6.QtCore import QRegularExpression, QDate, QDateTime, QEvent, QTimer
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem, QPushButton

from app.styles.styles import ADD_BTN_STYLE, TUOI_STYLE, COMPLETER_THUOC_STYLE

from app.core.tiep_nhan_benh_nhan import luu_du_lieu_tiep_nhan, load_history_records
from app.core.in_phieu_tiep_nhan import create_and_open_pdf_for_printing

from app.services.BenhNhanService import get_benh_nhan_by_id
from app.services.DoiTuongService import get_list_doi_tuong
from app.services.PhongBanService import get_list_phong_ban

from app.ui.TabTiepNhan import Ui_formTiepNhan
from app.utils.export_excel import export_tiep_nhan_and_show_dialog
from app.utils.scanner_utils import parse_scanned_data, should_skip_scanner_input
from app.utils.utils import calculate_age

from app.utils.config_manager import ConfigManager

class ComboBoxFilter(QtCore.QObject):
    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.FocusIn:
            if isinstance(source, QtWidgets.QLineEdit):
                combo = source.parent()
                if isinstance(combo, QtWidgets.QComboBox) and combo.isEnabled():
                    combo.showPopup()
                    QTimer.singleShot(0, source.selectAll)

        return super().eventFilter(source, event)
    
class CCCDScannerFilter(QtCore.QObject):
    scanCompleted = QtCore.pyqtSignal(str)

    def __init__(self, parent_widget, parent=None):
        super().__init__(parent)
        self.parent_widget = parent_widget
        self.buffer = ""
        self.last_key_time = 0
        self.is_scanning = False

    def eventFilter(self, obj, event):
        # Chỉ xử lý khi Tab Tiếp Nhận đang hiển thị
        if not self.parent_widget.isVisible():
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.KeyPress:
            current_time = QtCore.QDateTime.currentMSecsSinceEpoch()
            interval = current_time - self.last_key_time
            self.last_key_time = current_time

            char = event.text()
            key = event.key()

            # Nếu khoảng cách giữa các phím cực nhỏ (< 50ms) -> Chắc chắn là máy quét
            if interval < 50:
                if not self.is_scanning:
                    self.is_scanning = True
                    # KHẮC PHỤC RÒ RỈ PHÍM ĐẦU TIÊN:
                    # Xóa ký tự đầu tiên lỡ bị gõ vào widget đang focus trước khi bộ lọc kịp chặn dội phím
                    active_widget = QtWidgets.QApplication.focusWidget()
                    if isinstance(active_widget, QtWidgets.QLineEdit):
                        text = active_widget.text()
                        if text:
                            active_widget.setText(text[:-1])
            else:
                # Người gõ bình thường (> 50ms) thì reset bộ đệm, trừ phím Enter kết thúc quét
                if key not in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    self.is_scanning = False
                    self.buffer = ""

            # CHỐNG UNIKEY & TRÁNH GHI ĐÈ VÀO Ô ĐANG FOCUS:
            # Nếu đang trong luồng quét, nuốt sạch toàn bộ phím không cho ghi lên UI đang focus
            if self.is_scanning:
                if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    # Kết thúc quá trình quét khi nhận phím Enter từ máy quét
                    if "|" in self.buffer and len(self.buffer.split("|")) >= 6:
                        self.scanCompleted.emit(self.buffer)
                        self.buffer = ""
                        self.is_scanning = False
                        return True
                    self.buffer = ""
                    self.is_scanning = False
                else:
                    if char:
                        self.buffer += char
                return True

        return super().eventFilter(obj, event)

class TiepNhanTabController(QtWidgets.QWidget):
    @staticmethod
    def _is_valid_phone(value):
        return bool(re.fullmatch(r'\d{10}', value))

    @staticmethod
    def _is_valid_cccd(value):
        return bool(re.fullmatch(r'\d{9,12}', value))

    @staticmethod
    def _is_valid_bhyt(value):
        return bool(re.fullmatch(r'[A-Za-z0-9]{1,15}', value))

    def __init__(self, tab_widget_container, parent=None):
        super().__init__(parent)
        self.tab_widget_container = tab_widget_container
        self.ui_tiep_nhan = Ui_formTiepNhan()
        self.ui_tiep_nhan.setupUi(tab_widget_container)
        self.current_page_index = 1
        self.items_per_page = 10
        self.total_pages = 1
        self.history_records = []
        self.filtered_history_records = []
        
        # 1. Khởi tạo cấu hình bổ trợ và nạp dữ liệu danh sách trước
        self.config_manager = ConfigManager()
        self._load_combo_data()
        self._load_gioi_tinh_options()
        self.init()
        
        # 2. Cài đặt các thành phần giao diện khác
        self.setup_ngay_gio_tiep_nhan_realtime_clock()
        self.reset_form()
        self.load_history_table()
        self._set_validators()
        self._apply_styles()
        self._connect_signals()

        # 3. Khôi phụ cài đặt
        self._load_saved_settings()

        # 4. Cài đặt bộ quét cổng COM
        self.is_processing_scan = False

    def init(self):
        self.cb_event_filter = ComboBoxFilter()
        
        # Cấu hình combo_box
        target_combos = [
            self.ui_tiep_nhan.cb_phong_kham,
            self.ui_tiep_nhan.doi_tuong,
            self.ui_tiep_nhan.gioi_tinh
        ]

        for cb in target_combos:
            # 1. Bật chế độ cho phép gõ văn bản và cấm tự chèn mục mới
            cb.setEditable(True)
            cb.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)

            # 2. Tự động chọn dòng đầu tiên nếu dữ liệu rỗng
            if cb.count() > 0 and cb.currentIndex() < 0:
                cb.setCurrentIndex(0)

            # 3. Gán bộ lọc sự kiện Focus để tự popup khi người dùng nhấp chuột vào ô
            if cb.lineEdit():
                cb.lineEdit().installEventFilter(self.cb_event_filter)

            # 4. Tạo bộ gợi ý (QCompleter) sử dụng chính Model dữ liệu hiện tại của Combobox
            completer = QtWidgets.QCompleter(cb.model(), cb)
            
            # 5. Cấu hình thuật toán tìm kiếm gần khớp (chứa chuỗi - MatchContains) và không phân biệt hoa thường
            completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
            
            # 6. Áp dụng Style Sheet và gắn bộ gợi ý hoàn chỉnh vào combobox
            completer.popup().setStyleSheet(COMPLETER_THUOC_STYLE)
            cb.setCompleter(completer)

    def _load_combo_data(self):
        self.ui_tiep_nhan.cb_phong_kham.clear()
        for row in get_list_phong_ban():
            self.ui_tiep_nhan.cb_phong_kham.addItem(f"{row[1]} - {row[2]}", row[1])

        self.ui_tiep_nhan.doi_tuong.clear()
        for row in get_list_doi_tuong():
            self.ui_tiep_nhan.doi_tuong.addItem(str(row[2]), row[1])
        self.ui_tiep_nhan.doi_tuong.setCurrentIndex(-1)

    def _load_gioi_tinh_options(self):
        self.ui_tiep_nhan.gioi_tinh.clear()
        for value in ['Nam', 'Nữ']:
            self.ui_tiep_nhan.gioi_tinh.addItem(value, value)

    def _set_validators(self):
        self.ui_tiep_nhan.ma_y_te.setMaxLength(8)
        self.ui_tiep_nhan.ma_y_te.setValidator(QRegularExpressionValidator(QRegularExpression(r'^[A-Za-z0-9]*$')))

        self.ui_tiep_nhan.sdt.setMaxLength(10)
        self.ui_tiep_nhan.sdt.setValidator(QRegularExpressionValidator(QRegularExpression(r'^\d{0,10}$')))

        self.ui_tiep_nhan.cccd.setMaxLength(12)
        self.ui_tiep_nhan.cccd.setValidator(QRegularExpressionValidator(QRegularExpression(r'^\d{0,12}$')))

        self.ui_tiep_nhan.so_bhyt.setMaxLength(15)
        self.ui_tiep_nhan.so_bhyt.setValidator(QRegularExpressionValidator(QRegularExpression(r'^[A-Za-z0-9]{0,15}$')))

    def _apply_styles(self):
        for button in [
            self.ui_tiep_nhan.btn_save,
            self.ui_tiep_nhan.btn_reset,
            self.ui_tiep_nhan.btn_export,
            self.ui_tiep_nhan.btn_prev_page,
            self.ui_tiep_nhan.btn_next_page,
        ]:
            button.setStyleSheet(ADD_BTN_STYLE)
        
        for combobox in [
            self.ui_tiep_nhan.cb_phong_kham,
            self.ui_tiep_nhan.doi_tuong,
            self.ui_tiep_nhan.gioi_tinh,
        ]:
            combobox.setStyleSheet(COMPLETER_THUOC_STYLE)

        self.ui_tiep_nhan.stt.setPlaceholderText('')
        self.ui_tiep_nhan.current_page.setReadOnly(True)
        self.ui_tiep_nhan.num_page.setReadOnly(True)
        self.ui_tiep_nhan.current_page.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.ui_tiep_nhan.num_page.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.ui_tiep_nhan.current_page.setText('1')
        self.ui_tiep_nhan.num_page.setText('1')

    def _connect_signals(self):
        self.ui_tiep_nhan.ma_y_te.editingFinished.connect(self.auto_fill_benh_nhan)
        self.ui_tiep_nhan.cb_phong_kham.currentIndexChanged.connect(self._save_settings)
        self.ui_tiep_nhan.doi_tuong.currentIndexChanged.connect(self._save_settings)
        self.ui_tiep_nhan.ten_bac_si.textEdited.connect(self._save_settings)
        self.ui_tiep_nhan.btn_save.clicked.connect(self.handle_save_and_print)
        self.ui_tiep_nhan.btn_reset.clicked.connect(self.reset_form)
        self.ui_tiep_nhan.btn_export.clicked.connect(self.handle_export_excel)
        self.ui_tiep_nhan.nam_sinh.dateChanged.connect(self.update_tuoi)
        self.ui_tiep_nhan.ma_y_te_search.textChanged.connect(self._on_search_triggered)
        self.ui_tiep_nhan.ho_ten_search.textChanged.connect(self._on_search_triggered)
        self.ui_tiep_nhan.btn_refresh_history.clicked.connect(self._on_refresh_history)
        self.ui_tiep_nhan.btn_prev_page.clicked.connect(self.on_prev_page)
        self.ui_tiep_nhan.btn_next_page.clicked.connect(self.on_next_page)
        self.ui_tiep_nhan.table.cellClicked.connect(self.on_history_row_clicked)
        self.ui_tiep_nhan.table.cellDoubleClicked.connect(self.on_history_row_double_clicked)
        self.ui_tiep_nhan.table.cellDoubleClicked.connect(self.on_history_row_double_clicked)
        
        self.shortcut_reset = QShortcut(QKeySequence('Ctrl+N'), self.tab_widget_container)
        self.shortcut_reset.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut_reset.activated.connect(self.reset_form)

        self.shortcut_save = QShortcut(QKeySequence('Ctrl+P'), self.tab_widget_container)
        self.shortcut_save.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut_save.activated.connect(self.handle_save_and_print)

    # <editor-fold desc="Load & Save setting tiếp nhận">
    def _save_settings(self):
        """Lưu Mã phòng khám và Tên bác sĩ hiện tại vào QSettings."""
        phong_kham_code = self.ui_tiep_nhan.cb_phong_kham.currentText()
        ten_bac_si_hien_tai = self.ui_tiep_nhan.ten_bac_si.text()
        self.config_manager.save_last_selection(phong_kham_code, ten_bac_si_hien_tai)

    def _load_saved_settings(self):
        """Tải giá trị đã lưu và áp dụng chúng cho các widget."""
        phong_kham_saved, bac_si_saved = self.config_manager.load_last_selection()

        if phong_kham_saved:
            index = self.ui_tiep_nhan.cb_phong_kham.findText(phong_kham_saved)
            if index != -1:
                self.ui_tiep_nhan.cb_phong_kham.setCurrentIndex(index)

        if bac_si_saved:
            self.ui_tiep_nhan.ten_bac_si.setText(bac_si_saved)

    def auto_fill_benh_nhan(self):
        code = self.ui_tiep_nhan.ma_y_te.text().strip()
        if len(code) != 8:
            return
        row = get_benh_nhan_by_id(code)
        if not row:
            QMessageBox.warning(self, 'Thông báo', 'Không tìm thấy mã y tế, vui lòng nhập thủ công.')
            return
        self.ui_tiep_nhan.ho_ten.setText(str(row[1] or ''))
        self.ui_tiep_nhan.gioi_tinh.setCurrentText('Nữ' if str(row[2]).strip().upper() == 'G' else 'Nam')
        try:
            birth_year = int(str(row[3] or '').strip())
            self.ui_tiep_nhan.nam_sinh.setDate(QDate(birth_year, 1, 1))
        except Exception:
            self.ui_tiep_nhan.nam_sinh.setDate(QDate.currentDate())
        self.ui_tiep_nhan.sdt.setText(self._clean_numeric_string(row[4], expected_length=10))
        self.ui_tiep_nhan.dia_chi.setText(str(row[5] or ''))
        self.ui_tiep_nhan.so_bhyt.setText(self._clean_numeric_string(row[6]))
        self.update_tuoi()

    def update_tuoi(self):
        ui = self.ui_tiep_nhan
        nam_sinh = ui.nam_sinh.date()
        current_year = QDate.currentDate().year()
        birth_year = nam_sinh.year()

        tuoi_calc = current_year - birth_year
        if tuoi_calc < 0:
            tuoi_calc = 0
            
        tuoi = str(tuoi_calc)
        ui.tuoi.setText(tuoi)
        ui.tuoi.setStyleSheet(TUOI_STYLE)

    def validate_required_fields(self) -> bool:
        required_fields = [
            (self.ui_tiep_nhan.ho_ten, 'Họ tên bệnh nhân'),
            (self.ui_tiep_nhan.dia_chi, 'Địa chỉ'),
            (self.ui_tiep_nhan.cccd, 'Căn cước công dân'),
            # (self.ui_tiep_nhan.sdt, 'Số điện thoại'),
            (self.ui_tiep_nhan.cb_phong_kham, 'Phòng khám'),
        ]

        for field, name in required_fields:
            text = field.currentText().strip() if isinstance(field, QtWidgets.QComboBox) else field.text().strip()
            if not text:
                QMessageBox.warning(self, 'Thiếu dữ liệu', f'Vui lòng nhập {name}!')
                field.setFocus()
                return False

        sdt = self.ui_tiep_nhan.sdt.text().strip()
        if sdt and not self._is_valid_phone(sdt):
            QMessageBox.warning(self, 'Dữ liệu không hợp lệ', 'Số điện thoại phải có đúng 10 chữ số.')
            self.ui_tiep_nhan.sdt.setFocus()
            return False

        cccd = self.ui_tiep_nhan.cccd.text().strip()
        if cccd and not self._is_valid_cccd(cccd):
            QMessageBox.warning(self, 'Dữ liệu không hợp lệ', 'CCCD phải có từ 9 đến 12 chữ số.')
            self.ui_tiep_nhan.cccd.setFocus()
            return False

        bhyt = self.ui_tiep_nhan.so_bhyt.text().strip()
        if bhyt and not self._is_valid_bhyt(bhyt):
            QMessageBox.warning(self, 'Dữ liệu không hợp lệ', 'Số BHYT chỉ được chứa chữ và số, tối đa 15 ký tự.')
            self.ui_tiep_nhan.so_bhyt.setFocus()
            return False

        return True

    def handle_save_and_print(self):
        if not self.validate_required_fields():
            return

        data = self.collect_form_data()

        data['Tuoi'] = self.ui_tiep_nhan.tuoi.text().strip() or '0'
        luu_du_lieu_tiep_nhan(data)
        create_and_open_pdf_for_printing(data)
        self.load_history_table()
        if data.get('STT'):
            QMessageBox.information(self, 'Thông báo', f'Đã lưu tiếp nhận STT {data["STT"]}.')
        else:
            QMessageBox.information(self, 'Thông báo', 'Đã lưu tiếp nhận.')

    def collect_form_data(self):
        return {
            'STT': self._clean_numeric_string(self.ui_tiep_nhan.stt.text()),
            'MaYTe': self._clean_numeric_string(self.ui_tiep_nhan.ma_y_te.text(), expected_length=8),
            'HoTen': self.ui_tiep_nhan.ho_ten.text().strip(),
            'NamSinh': self.ui_tiep_nhan.nam_sinh.date().toString('yyyy'),
            'Tuoi': self.ui_tiep_nhan.tuoi.text().strip(),
            'GioiTinh': self.ui_tiep_nhan.gioi_tinh.currentText(),
            'DiaChi': self.ui_tiep_nhan.dia_chi.text().strip(),
            'CCCD': self._clean_numeric_string(self.ui_tiep_nhan.cccd.text()),
            'SoDienThoai': self._clean_numeric_string(self.ui_tiep_nhan.sdt.text(), expected_length=10),
            'DoiTuong': self.ui_tiep_nhan.doi_tuong.currentText().strip(),
            'SoBHYT': self._clean_numeric_string(self.ui_tiep_nhan.so_bhyt.text()),
            'BHYT_Tu': self.ui_tiep_nhan.bhyt_from.date().toString('dd/MM/yyyy'),
            'BHYT_Den': self.ui_tiep_nhan.bhyt_to.date().toString('dd/MM/yyyy'),
            'MaPhong': self.ui_tiep_nhan.cb_phong_kham.currentData() or self.ui_tiep_nhan.cb_phong_kham.currentText(),
            'PhongTiepNhan': self.ui_tiep_nhan.cb_phong_kham.currentText(),
            'NgayTiepNhan': self.ui_tiep_nhan.ngay_gio_tiep_nhan.dateTime().toString('yyyy-MM-dd HH:mm:ss'),
            'TenBacSi': self.ui_tiep_nhan.ten_bac_si.text().strip(),
            'TenBenhVien': 'BỆNH VIỆN NHÂN DÂN GIA ĐỊNH',
        }

    def reset_form(self):
        self.ui_tiep_nhan.ma_y_te.clear()
        self.ui_tiep_nhan.stt.clear()
        self.ui_tiep_nhan.ho_ten.clear()
        self.ui_tiep_nhan.dia_chi.clear()
        self.ui_tiep_nhan.tuoi.setText('0')
        self.ui_tiep_nhan.so_bhyt.clear()
        self.ui_tiep_nhan.sdt.clear()
        self.ui_tiep_nhan.gioi_tinh.setCurrentIndex(-1)

        self.ui_tiep_nhan.doi_tuong.setCurrentIndex(-1)
        self.ui_tiep_nhan.cb_phong_kham.setCurrentIndex(0)

        current_date = QDate.currentDate()
        self.ui_tiep_nhan.bhyt_from.setDate(current_date)
        self.ui_tiep_nhan.bhyt_to.setDate(current_date)
        self.ui_tiep_nhan.nam_sinh.setDate(current_date)
        self.ui_tiep_nhan.cccd.clear()
        
        self.ui_tiep_nhan.ten_bac_si.clear()
        self.update_ngay_gio_tiep_nhan_datetime_edit()
        self.ui_tiep_nhan.ma_y_te.setFocus()

    def setup_ngay_gio_tiep_nhan_realtime_clock(self):
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_ngay_gio_tiep_nhan_datetime_edit)
        self.timer.start(1000)
        self.update_ngay_gio_tiep_nhan_datetime_edit()

    def update_ngay_gio_tiep_nhan_datetime_edit(self):
        self.ui_tiep_nhan.ngay_gio_tiep_nhan.setDateTime(QDateTime.currentDateTime())

    def _on_search_triggered(self):
        self.current_page_index = 1
        self.load_history_table()

    def _on_refresh_history(self):
        self.ui_tiep_nhan.ma_y_te_search.clear()
        self.ui_tiep_nhan.ho_ten_search.clear()
        self.current_page_index = 1
        self.load_history_table()

    def _get_filtered_history_records(self):
        keyword_id = self.ui_tiep_nhan.ma_y_te_search.text().strip().lower()
        keyword_name = self.ui_tiep_nhan.ho_ten_search.text().strip().lower()
        all_rows = load_history_records()
        filtered_rows = []
        for row in all_rows:
            ma_y_te = str(row.get('MaYTe', '')).lower()
            ho_ten = str(row.get('HoTen', '')).lower()
            if keyword_id and keyword_id not in ma_y_te:
                continue
            if keyword_name and keyword_name not in ho_ten:
                continue
            filtered_rows.append(row)
        self.history_records = all_rows
        self.filtered_history_records = filtered_rows
        return filtered_rows

    def _clean_history_value(self, value):
        if value is None or (isinstance(value, float) and value != value):
            return ''
        text = str(value).strip()
        return '' if text.lower() == 'nan' else text

    def _clean_numeric_string(self, value, expected_length=0):
        """Hàm bổ trợ xử lý triệt để định dạng số bị mất số 0 đầu hoặc dính đuôi .0 từ Excel/Pandas"""
        if value is None:
            return ''
        text = str(value).strip()
        if text.endswith('.0'):
            text = text[:-2]
        if text.lower() == 'nan':
            return ''
        
        if text.isdigit():
            if expected_length > 0:
                text = text.zfill(expected_length)
            else:
                # Tự động bắt lỗi mất số 0 đầu của CMND (9 số) và CCCD (12 số)
                if len(text) == 11:
                    text = text.zfill(12)
                elif len(text) == 8:
                    text = text.zfill(9)
        return text

    def _parse_qdate_from_year(self, value):
        # Dùng _clean_numeric_string để tránh lỗi lỗi năm sinh biến thành '1995.0'
        text = self._clean_numeric_string(value)
        if text.isdigit():
            return QDate(int(text), 1, 1)
        try:
            parsed = QDate.fromString(text, 'dd/MM/yyyy')
            if parsed.isValid():
                return parsed
        except Exception:
            pass
        return QDate.currentDate()

    def _parse_qdatetime(self, value):
        text = self._clean_history_value(value)
        parsed = QDateTime.fromString(text, 'yyyy-MM-dd HH:mm:ss')
        if parsed.isValid():
            return parsed
        parsed = QDateTime.fromString(text, 'dd/MM/yyyy HH:mm:ss')
        if parsed.isValid():
            return parsed
        return QDateTime.currentDateTime()

    def load_history_table(self):
        rows = self._get_filtered_history_records()
        total_items = len(rows)
        if self.items_per_page < 1:
            self.items_per_page = 10
        self.total_pages = max(1, math.ceil(total_items / self.items_per_page))
        self.current_page_index = min(max(1, self.current_page_index), self.total_pages)

        self.ui_tiep_nhan.current_page.setText(str(self.current_page_index))
        self.ui_tiep_nhan.num_page.setText(str(self.total_pages))
        self.ui_tiep_nhan.btn_prev_page.setEnabled(self.current_page_index > 1)
        self.ui_tiep_nhan.btn_next_page.setEnabled(self.current_page_index < self.total_pages)

        self.ui_tiep_nhan.table.setRowCount(0)
        self.ui_tiep_nhan.table.setColumnCount(10)
        self.ui_tiep_nhan.table.setColumnWidth(9, 80)
        self.ui_tiep_nhan.table.setHorizontalHeaderLabels([
            'STT', 'Mã y tế', 'Họ tên', 'Tuổi', 'Giới tính',
            'Phòng', 'Ngày giờ', 'Đối tượng', 'Số BHYT', 'Thao tác'
        ])
        if total_items == 0:
            return

        start_idx = (self.current_page_index - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_rows = rows[start_idx:end_idx]

        for row_index, record in enumerate(page_rows):
            display_values = [
                self._clean_numeric_string(record.get('STT')),
                self._clean_numeric_string(record.get('MaYTe'), expected_length=8),
                self._clean_history_value(record.get('HoTen')),
                self._clean_history_value(record.get('Tuoi')),
                self._clean_history_value(record.get('GioiTinh')),
                self._clean_history_value(record.get('PhongTiepNhan')),
                self._clean_history_value(record.get('NgayTiepNhan')),
                self._clean_history_value(record.get('DoiTuong')),
                self._clean_numeric_string(record.get('SoBHYT')),
            ]
            self.ui_tiep_nhan.table.insertRow(row_index)
            for col, value in enumerate(display_values):
                item = QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, record)
                self.ui_tiep_nhan.table.setItem(row_index, col, item)

            delete_button = QPushButton('Xoá')
            delete_button.setProperty('record', record)
            delete_button.clicked.connect(lambda _, rec=record: self._delete_history_record(rec))
            self.ui_tiep_nhan.table.setCellWidget(row_index, 9, delete_button)

    def on_prev_page(self):
        if self.current_page_index > 1:
            self.current_page_index -= 1
            self.load_history_table()

    def on_next_page(self):
        if self.current_page_index < self.total_pages:
            self.current_page_index += 1
            self.load_history_table()

    def on_history_row_clicked(self, row, col):
        item = self.ui_tiep_nhan.table.item(row, 0)
        if not item:
            return
        record = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not record:
            return
        self.fill_form_from_history_record(record)

    def on_history_row_double_clicked(self, row, col):
        self.on_history_row_clicked(row, col)

    def _delete_history_record(self, record):
        if not record:
            return

        cccd = str(record.get('CCCD', '')).strip()
        reply = QMessageBox.question(
            self,
            'Xác nhận xoá',
            f'Bạn có muốn xoá bản ghi của {record.get("HoTen", "")} không?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            import pandas as pd
            from app.core.tiep_nhan_benh_nhan import LICH_SU_TIEP_NHAN_FILE_PATH
            df = pd.read_csv(LICH_SU_TIEP_NHAN_FILE_PATH, dtype=str)
            if 'CCCD' in df.columns and cccd:
                df = df[~df['CCCD'].astype(str).str.strip().eq(cccd)]
            else:
                df = df.iloc[:-1]
            df.to_csv(LICH_SU_TIEP_NHAN_FILE_PATH, index=False, na_rep='')
            self.load_history_table()
        except Exception as e:
            QMessageBox.warning(self, 'Lỗi xoá', str(e))

    def fill_form_from_history_record(self, record):
        self.ui_tiep_nhan.stt.setText(self._clean_numeric_string(record.get('STT')))
        self.ui_tiep_nhan.ma_y_te.setText(self._clean_numeric_string(record.get('MaYTe'), expected_length=8))
        self.ui_tiep_nhan.ho_ten.setText(self._clean_history_value(record.get('HoTen')))
        self.ui_tiep_nhan.tuoi.setText(self._clean_history_value(record.get('Tuoi')) or '0')

        gioi_tinh = self._clean_history_value(record.get('GioiTinh'))
        if gioi_tinh in [self.ui_tiep_nhan.gioi_tinh.itemText(i) for i in range(self.ui_tiep_nhan.gioi_tinh.count())]:
            self.ui_tiep_nhan.gioi_tinh.setCurrentText(gioi_tinh)
        else:
            self.ui_tiep_nhan.gioi_tinh.setCurrentIndex(-1)

        self.ui_tiep_nhan.nam_sinh.setDate(self._parse_qdate_from_year(record.get('NamSinh')))
        self.ui_tiep_nhan.dia_chi.setText(self._clean_history_value(record.get('DiaChi')))
        self.ui_tiep_nhan.sdt.setText(self._clean_numeric_string(record.get('SoDienThoai'), expected_length=10))

        doi_tuong = self._clean_history_value(record.get('DoiTuong'))
        doi_tuong_index = self.ui_tiep_nhan.doi_tuong.findText(doi_tuong)
        self.ui_tiep_nhan.doi_tuong.setCurrentIndex(doi_tuong_index if doi_tuong_index >= 0 else -1)

        self.ui_tiep_nhan.cccd.setText(self._clean_numeric_string(record.get('CCCD')))
        self.ui_tiep_nhan.so_bhyt.setText(self._clean_numeric_string(record.get('SoBHYT')))

        phong = self._clean_history_value(record.get('PhongTiepNhan'))
        phong_index = self.ui_tiep_nhan.cb_phong_kham.findText(phong)
        if phong_index >= 0:
            self.ui_tiep_nhan.cb_phong_kham.setCurrentIndex(phong_index)

        self.ui_tiep_nhan.ten_bac_si.setText(self._clean_history_value(record.get('TenBacSi')))

        bhyt_tu = self._clean_history_value(record.get('BHYT_Tu'))
        bhyt_den = self._clean_history_value(record.get('BHYT_Den'))
        if bhyt_tu:
            self.ui_tiep_nhan.bhyt_from.setDate(QDate.fromString(bhyt_tu, 'dd/MM/yyyy'))
        if bhyt_den:
            self.ui_tiep_nhan.bhyt_to.setDate(QDate.fromString(bhyt_den, 'dd/MM/yyyy'))

        ngay_tn = self._clean_history_value(record.get('NgayTiepNhan'))
        if ngay_tn:
            self.ui_tiep_nhan.ngay_gio_tiep_nhan.setDateTime(self._parse_qdatetime(ngay_tn))
        self.update_tuoi()

    def handle_export_excel(self):
        export_tiep_nhan_and_show_dialog(self)
    
    def parse_cccd_qr_data(self, qr_text):
        """Phân tích dữ liệu CCCD từ cổng COM và nạp lên biểu mẫu"""
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

            # Đổ dữ liệu lên UI
            if cccd_code:
                self.ui_tiep_nhan.cccd.setText(cccd_code)
            if ho_ten:
                self.ui_tiep_nhan.ho_ten.setText(ho_ten)
            if dia_chi:
                self.ui_tiep_nhan.dia_chi.setText(dia_chi)

            # Chuẩn hóa giới tính
            normalize_gioi_tinh = getattr(type(self), '_normalize_gioi_tinh', None)
            if callable(normalize_gioi_tinh):
                gioi_tinh_chuan = normalize_gioi_tinh(self, gioi_tinh)
            else:
                text_gt = str(gioi_tinh or '').strip().lower()
                mapping_gt = {'nam': 'Nam', 'nu': 'Nữ', 'nữ': 'Nữ', 'g': 'Nữ', 'm': 'Nam'}
                gioi_tinh_chuan = mapping_gt.get(text_gt, 'Nam')

            if gioi_tinh_chuan:
                self.ui_tiep_nhan.gioi_tinh.setCurrentText(gioi_tinh_chuan)

            # Phân tích ngày sinh
            date_parsed = self._parse_cccd_date(ngay_sinh_raw)

            # Chỉ set ngày sinh nếu đã phân tích được ngày hợp lệ
            if date_parsed.isValid():
                self.ui_tiep_nhan.nam_sinh.setDate(date_parsed)
                update_tuoi = self.__dict__.get('update_tuoi')
                if callable(update_tuoi):
                    update_tuoi()

        except Exception as e:
            QMessageBox.warning(
                self,
                "Lỗi xử lý dữ liệu",
                f"Đã xảy ra lỗi khi phân tách chuỗi CCCD: {str(e)}"
            )
        finally:
            QTimer.singleShot(1500, lambda: setattr(self, 'is_processing_scan', False))

    def _parse_cccd_date(self, date_str):
        """Hàm parse date từ mã QR CCCD"""
        date_str = str(date_str).strip()
        if len(date_str) == 8 and date_str.isdigit():
            day = int(date_str[0:2])
            month = int(date_str[2:4])
            year = int(date_str[4:8])
            # Kiểm tra tính hợp lệ của ngày trước khi trả về
            res_date = QDate(year, month, day)
            if res_date.isValid():
                return res_date
        
        for fmt in ('dd/MM/yyyy', 'dd-MM-yyyy'):
            parsed = QDate.fromString(date_str, fmt)
            if parsed.isValid():
                return parsed
        return QDate()
    
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

        # Nếu không tìm thấy cổng nào phù hợp, trả về cổng cuối cùng trong danh sách
        return available_ports[-1].portName()

    def setup_serial_scanner(self):
        """Khởi tạo và cấu hình cổng COM đọc dữ liệu từ máy quét"""
        # Nếu chưa có đối tượng serial thì mới tạo mới hoàn toàn
        if not hasattr(self, 'serial') or self.serial is None:
            self.serial = QSerialPort(self)
            self.serial.readyRead.connect(self.read_serial_data)

        # Nếu cổng đang mở, đóng lại trước khi tái cấu hình để tránh xung đột bận cổng
        if self.serial.isOpen():
            self.serial.close()

        # Tự động tìm cổng COM của máy quét Newland
        target_port = self.get_scanner_port_name()
        
        if not target_port:
            print("Không tìm thấy máy quét nào được cắm vào máy tính.")
            return

        self.serial.setPortName(target_port) # Gán tự động COM4, COM6...
        self.serial.setBaudRate(9600)
        
        if self.serial.open(QSerialPort.OpenModeFlag.ReadOnly):
            print(f"Đã kết nối máy quét thành công tại cổng {target_port} thành công tại Tab Tiếp nhận.")
        else:
            print(f"Cảnh báo cổng {target_port}  tại Tab Tiếp nhận: {self.serial.errorString()}. Vui lòng kiểm tra cắm dây máy quét.")

    def open_serial_port(self):
        """Mở lại cổng COM tại Tab Tiếp nhận"""

        # Tự động tìm cổng COM của máy quét Newland
        target_port = self.get_scanner_port_name()

        if hasattr(self, 'serial') and self.serial is not None:
            if not self.serial.isOpen():
                # ĐÃ SỬA THỤT LỀ LOGIC TẠI ĐÂY
                if self.serial.open(QSerialPort.OpenModeFlag.ReadOnly):
                    print(f"Đã mở lại cổng kết nối {target_port} tại Tab Tiếp nhận.")
                else:
                    print(f"Tab Tiếp nhận: Lỗi mở lại cổng ({self.serial.errorString()})")
        else:
            self.setup_serial_scanner()

    def close_serial_port(self):
        """Đóng cổng COM khi ẩn Tab Tiếp nhận"""
        if hasattr(self, 'serial') and self.serial is not None:
            if self.serial.isOpen():
                self.serial.close()
                print("Đã đóng cổng kết nối tại Tab Tiếp nhận.")

    def read_serial_data(self):
        """Đọc và tích lũy dữ liệu thô từ cổng COM, giải mã UTF-8 chuẩn xác"""
        if not hasattr(self, 'serial_buffer'):
            self.serial_buffer = b""

        # Đọc toàn bộ dữ liệu hiện có trong buffer của cổng COM
        self.serial_buffer += self.serial.readAll().data()

        try:
            text = self.serial_buffer.decode('utf-8', errors='ignore')
        except UnicodeDecodeError:
            return

        # Kết thúc dòng truyền (máy quét gửi \r hoặc \n)
        if '\r' in text or '\n' in text:
            clean_text = text.strip()
            if "|" in clean_text and len(clean_text.split("|")) >= 6:
                self.parse_cccd_qr_data(clean_text)
            self.serial_buffer = b"" # Reset bộ đệm cho lần quét kế tiếp