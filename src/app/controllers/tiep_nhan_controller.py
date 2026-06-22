import re
import math

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QKeySequence, QRegularExpressionValidator, QShortcut
from PyQt6.QtCore import QRegularExpression, QDate, QDateTime, QEvent, QTimer
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from app.styles.styles import ADD_BTN_STYLE, TUOI_STYLE, COMPLETER_THUOC_STYLE

from app.core.tiep_nhan_benh_nhan import luu_du_lieu_tiep_nhan, load_history_records
from app.core.in_phieu_tiep_nhan import create_and_open_pdf_for_printing

from app.services.BenhNhanService import get_benh_nhan_by_id
from app.services.DoiTuongService import get_list_doi_tuong
from app.services.PhongBanService import get_list_phong_ban

from app.ui.TabTiepNhan import Ui_formTiepNhan
from app.utils.export_excel import export_tiep_nhan_and_show_dialog
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
        tuoi = str(calculate_age(nam_sinh.toString('dd/MM/yyyy')))
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

    def on_prev_page(self):
        if self.current_page_index > 1:
            self.current_page_index -= 1
            self.load_history_table()

    def on_next_page(self):
        if self.current_page_index < self.total_pages:
            self.current_page_index += 1
            self.load_history_table()

    def on_history_row_double_clicked(self, row, col):
        item = self.ui_tiep_nhan.table.item(row, 0)
        if not item:
            return
        record = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not record:
            return
        self.fill_form_from_history_record(record)

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