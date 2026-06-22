# src/app/ui/tab_tiep_nhan_benh_nhan.py
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton, QLineEdit, QDateEdit, QComboBox, \
    QCheckBox, QGridLayout, QApplication, QDateTimeEdit, QMessageBox
from PyQt6.QtCore import Qt, QDate, QObject, QEvent, QDateTime, QTimer, QRegularExpression

try:
    from app.core.tiep_nhan_benh_nhan import get_next_queue_number
except ImportError:
    def get_next_queue_number(data):
        print("LỖI: Không tìm thấy module 'get_next_queue_number'. Hàm được gọi với data:", data)

try:
    from app.core.tiep_nhan_benh_nhan import luu_du_lieu_tiep_nhan
except ImportError:
    def luu_du_lieu_tiep_nhan(data):
        print("LỖI: Không tìm thấy module 'luu_du_lieu_tiep_nhan'. Hàm được gọi với data:", data)

try:
    from app.core.tiep_nhan_benh_nhan import load_data_from_csv, populate_combobox, get_combobox_key
except ImportError:
    def load_data_from_csv(file_path):
        print("LỖI: Không tìm thấy module 'load_data_from_csv'. Hàm được gọi với filePath:", file_path)

    def populate_combobox():
        print("LỖI: Không tìm thấy module 'load_data_from_csv'.")

    def get_combobox_key():
        print("LỖI: Không tìm thấy module 'get_combobox_key'.")

try:
    from app.core.in_phieu_tiep_nhan import create_and_open_pdf_for_printing
except ImportError:
    def create_and_open_pdf_for_printing(data):
        print("LỖI: Không tìm thấy module 'create_and_open_pdf_for_printing'. Hàm đã được gọi với data:", data)

PHONG_KHAM_FILE_PATH ='data/tiep_nhan_benh_nhan/phong_kham.csv'
GIOI_TINH_FILE_PATH ='data/tiep_nhan_benh_nhan/gioi_tinh.csv'
NGHE_NGHIEP_FILE_PATH ='data/tiep_nhan_benh_nhan/nghe_nghiep.csv'
QUOC_TICH_FILE_PATH ='data/tiep_nhan_benh_nhan/quoc_tich.csv'
LY_DO_TIEP_NHAN_FILE_PATH ='data/tiep_nhan_benh_nhan/ly_do_tiep_nhan.csv'
NOI_DANG_KY_FILE_PATH = 'data/tiep_nhan_benh_nhan/noi_dang_ky.csv'
TUYEN_KHAM_BENH_FILE_PATH = 'data/tiep_nhan_benh_nhan/tuyen_kham_benh.csv'
KHU_VUC_FILE_PATH = 'data/tiep_nhan_benh_nhan/khu_vuc.csv'
DAN_TOC_FILE_PATH = 'data/tiep_nhan_benh_nhan/dan_toc.csv'
DOI_TUONG_FILE_PATH = 'data/tiep_nhan_benh_nhan/doi_tuong.csv'
HINH_THUC_DEN_FILE_PATH = 'data/tiep_nhan_benh_nhan/hinh_thuc_den.csv'

class ScrollEventFilter(QObject):
    def __init__(self, scroll_area, parent=None):
        super().__init__(parent)
        self.scroll_area = scroll_area

    def eventFilter(self, obj, event):
        # Nếu sự kiện là cuộn chuột (Wheel event)
        if event.type() == QEvent.Type.Wheel:
            # Chuyển hướng sự kiện tới Viewport của QScrollArea để cuộn
            QApplication.sendEvent(self.scroll_area.viewport(), event)
            return True  # Đánh dấu sự kiện đã được xử lý (chặn widget con hấp thụ)

        # Với các sự kiện khác, tiếp tục xử lý bình thường
        return super().eventFilter(obj, event)

class TabTiepNhanBenhNhan(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        self.scroll_filter = ScrollEventFilter(scroll_area)

        self.container_widget = QWidget()
        # **Tạo QGridLayout cho nội dung**
        self.content_layout = QGridLayout(self.container_widget)

        # ----------------------------------------------------
        # Áp dụng Style Sheets cho container
        self.container_widget.setStyleSheet("""
            QLineEdit, QDateEdit, QComboBox, QDateTimeEdit {
                font-family: Arial;
                font-size: 12pt; 
                color: #333333;
                min-height: 30px; 
                padding: 3px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            /* 💥 STYLE HIGHLIGHT KHI ĐƯỢC FOCUS 💥 */
            QLineEdit:focus, 
            QDateEdit:focus, 
            QComboBox:focus, 
            QDateTimeEdit:focus {
                border: 2px solid #0078D7; /* Đổi viền dày và màu xanh nổi bật */
                background-color: #F0F8FF; /* Đổi màu nền nhẹ */
                padding: 2px; /* Điều chỉnh padding do viền dày hơn */
            }
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                padding-left: 5px;
            }
            /* Đặt QLineEdit rộng hơn */
            QLineEdit {
                min-width: 300px;
            }
            
            QPushButton {
                /* Trạng thái mặc định */
                background-color: #0078D7;      /* Màu nền xanh dương */
                color: white;                   /* Màu chữ trắng */
                border: 2px solid #005A9E;      /* Viền dày 2px */
                border-radius: 8px;             /* Bo góc */
                padding: 10px 20px;             /* Khoảng đệm bên trong */
                font-size: 14pt;                /* Cỡ chữ lớn hơn */
                font-weight: bold;
            }
        
            QPushButton:hover {
                /* Trạng thái khi di chuột qua */
                background-color: #005A9E;      /* Màu nền đậm hơn một chút */
                border: 2px solid #004070;
            }
        
            QPushButton:pressed {
                /* Trạng thái khi nhấn giữ chuột */
                background-color: #003366;      /* Màu nền rất đậm (hiệu ứng nhấn xuống) */
                border: 2px solid #00254D;
            }
        
            QPushButton:disabled {
                /* Trạng thái khi nút bị vô hiệu hóa */
                background-color: #A0A0A0;      /* Màu nền xám */
                color: #E0E0E0;                 /* Màu chữ xám nhạt */
                border: none;
            }
            
            /* Style cho trường bị lỗi */
            .error {
                border: 2px solid red; /* Viền đỏ nổi bật */
                background-color: #FFF0F0; /* Nền đỏ nhạt */
            }
        """)
        # ----------------------------------------------------

        # Danh sách các trường nhập liệu
        # Sử dụng QGridLayout với 2 cột: Cột 0 (Nhãn) và Cột 1 (Trường nhập liệu)
        # Danh sách các trường và loại widget phù hợp
        # Quyết định thứ tự cac trường nhập liệu từ trên xuống dưới
        self.data_widgets = {
            "Mã y tế": QLineEdit(),
            "Phòng khám": QComboBox(),
            "Số tiếp nhận": QLineEdit(),
            "Họ tên": QLineEdit(),
            "Giới tính": QComboBox(),
            "Ngày sinh": QDateEdit(calendarPopup=True),
            "Nghề nghiệp": QComboBox(),
            "Số điện thoại": QLineEdit(),
            "Lý do tiếp nhận": QComboBox(),
            "Đối tượng": QComboBox(),
            "Hình thức đến": QComboBox(),
            "ĐT chi tiết": QLineEdit(),
            "Nơi giới thiệu": QLineEdit(),
            "Chẩn đoán NG": QLineEdit(),
            "Người liên hệ": QLineEdit(),
            "Tiếp nhận lúc": QDateTimeEdit(calendarPopup=True),
            "Địa chỉ liên hệ": QLineEdit(),
            "Quốc tịch": QComboBox(),
            "CCCD/Số định danh": QLineEdit(),
            "Dân tộc": QComboBox(),
            "Ngày cấp": QDateEdit(calendarPopup=True),
            "Nơi cấp": QLineEdit(),
            "Mã số thuế": QLineEdit(),
            "Tên công ty": QLineEdit(),
            "Mã Đơn vị quan hệ ngân sách": QLineEdit(),
            "Hộ chiếu": QLineEdit(),
            "Tên cha": QLineEdit(),
            "Tên mẹ": QLineEdit(),
            "Số nhà": QLineEdit(),
            "Tỉnh/Thành": QComboBox(),
            "Quận/Huyện": QComboBox(),
            "Phường/Xã": QComboBox(),
            "Ngày cấp BHYT": QDateEdit(calendarPopup=True),
            "Tên vợ chồng": QLineEdit(),
            "Ghi chú": QLineEdit(),
            "Số BHYT (tick)": QCheckBox("Có Số BHYT?"),
            "BH 10 (tick)": QCheckBox("Có BH 10?"),
            "BHYT Từ ngày": QDateEdit(calendarPopup=True),
            "BHYT Đến ngày": QDateEdit(calendarPopup=True),
            "Nơi đăng ký": QComboBox(),
            "Tuyến KB": QComboBox(),
            "Khu vực": QComboBox(),
            "BHYT 5 năm?": QCheckBox("BHYT 5 năm?"),
        }

        # Thiết lập các giá trị mặc định/ban đầu
        # 0. Chọn phòng khám
        self._setup_combobox_from_csv(
            field_name="Phòng khám",
            file_path=PHONG_KHAM_FILE_PATH,
            display_col='TenPhong',
            key_col='MaPhong'
        )

        # 1. Giới tính
        self._setup_combobox_from_csv(
            field_name="Giới tính",
            file_path=GIOI_TINH_FILE_PATH,
            display_col='TenGioiTinh',
            key_col='MaGioiTinh'
        )

        # 2. Nghề nghiệp
        self._setup_combobox_from_csv(
            field_name="Nghề nghiệp",
            file_path=NGHE_NGHIEP_FILE_PATH,
            display_col='TenNgheNghiep',
            key_col='MaNgheNghiep'
        )

        # 3. Ngày sinh (Giữ nguyên hoặc thay đổi cho mục đích demo)
        self.data_widgets["Ngày sinh"].setDate(QDate(2000, 1, 1))

        # 4. Lý do tiếp nhận
        self._setup_combobox_from_csv(
            field_name="Lý do tiếp nhận",
            file_path=LY_DO_TIEP_NHAN_FILE_PATH,
            display_col='TenLyDo',
            key_col='MaLyDo'
        )

        # 5. Đối tượng (Thường là đối tượng bảo hiểm, dịch vụ)
        self._setup_combobox_from_csv(
            field_name="Đối tượng",
            file_path=DOI_TUONG_FILE_PATH,
            display_col='TenDT',
            key_col='MaDT',
        )

        # 6. Hình thức đến
        self._setup_combobox_from_csv(
            field_name="Hình thức đến",
            file_path=HINH_THUC_DEN_FILE_PATH,
            display_col='TenHTDen',
            key_col='MaHTDen',
        )

        # 7. Quốc tịch (Tạo danh sách các quốc tịch phổ biến/liên quan)
        self._setup_combobox_from_csv(
            field_name="Quốc tịch",
            file_path=QUOC_TICH_FILE_PATH,
            display_col='TenQuocGia',
            key_col='MaQuocGia',
            default_key='VN'
        )

        # 8. Dân tộc
        self._setup_combobox_from_csv(
            field_name="Dân tộc",
            file_path=DAN_TOC_FILE_PATH,
            display_col='TenDanToc',
            key_col='MaDanToc',
            default_key='DT01'
        )

        # 9. Tỉnh/Thành
        self.data_widgets["Tỉnh/Thành"].addItems(
            ["Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng", "Cần Thơ", "Hải Phòng", "Tỉnh khác"])

        # 10. Quận/Huyện
        self.data_widgets["Quận/Huyện"].addItems(["Quận 1", "Quận Ba Đình", "Huyện Củ Chi", "Huyện Thanh Trì", "Khác"])

        # 11. Phường/Xã (Thông tin chi tiết phụ thuộc vào Quận/Huyện đã chọn, nhưng tạo giả để demo)
        self.data_widgets["Phường/Xã"].addItems(["Phường Bến Nghé", "Phường Đồng Tâm", "Xã Tân Thông Hội", "Khác"])

        # 12. Nơi đăng ký (Địa điểm đăng ký khám chữa bệnh ban đầu hoặc tạm trú)
        self._setup_combobox_from_csv(
            field_name="Nơi đăng ký",
            file_path=NOI_DANG_KY_FILE_PATH,
            display_col='TenBV',
            key_col='MaBV'
        )

        # 13. Tuyến KB (Tuyến Khám Bệnh - thường liên quan đến BHYT)
        self._setup_combobox_from_csv(
            field_name="Tuyến KB",
            file_path=TUYEN_KHAM_BENH_FILE_PATH,
            display_col='TenTuyen',
            key_col='MaTuyen'
        )

        # 14. Khu vực (Thường là khu vực ưu tiên, vùng khó khăn, v.v.)
        self._setup_combobox_from_csv(
            field_name="Khu vực",
            file_path=KHU_VUC_FILE_PATH,
            display_col='TenKV',
            key_col='MaKV'
        )

        self.data_widgets["Tiếp nhận lúc"].setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.data_widgets["Tiếp nhận lúc"].setDateTime(QDateTime.currentDateTime())
        self.data_widgets["Tiếp nhận lúc"].setReadOnly(True)

        self.tiep_nhan_luc_widget = self.data_widgets["Tiếp nhận lúc"]

        # Khởi tạo các widget BHYT đặc biệt
        self.cb_so_bhyt = QCheckBox("Có Số BHYT?")
        self.cb_bh_10 = QCheckBox("Có BH 10?")
        self.de_bhyt_tu = QDateEdit(calendarPopup=True)
        self.de_bhyt_den = QDateEdit(calendarPopup=True)
        self.cb_bhyt_5nam = QCheckBox("BHYT 5 năm?")
        self.noi_dang_ky = QComboBox()
        self.tuyen_kb = QComboBox()
        self.khu_vuc = QComboBox()

        # 3. Đặt các widget vào layout theo HÀNG và CỘT
        current_row = 1  # Bắt đầu từ hàng 1, sau tiêu đề

        list_items = list(self.data_widgets.items())

        for label_text, widget in list_items:
            label = QLabel(f"{label_text}:")

            # CÀI ĐẶT BỘ LỌC SỰ KIỆN CHO WIDGET
            if isinstance(widget, (QLineEdit, QDateEdit, QComboBox, QDateTimeEdit)):
                widget.installEventFilter(self.scroll_filter)

            # Cột 0 là Nhãn
            self.content_layout.addWidget(label, current_row, 0)
            # Cột 1 là Trường nhập liệu
            self.content_layout.addWidget(widget, current_row, 1)
            current_row += 1

        # 5. Nút bấm (kéo dài qua 2 cột)
        nut_mau = QPushButton("Tạo phiếu tiếp nhận")
        self.content_layout.addWidget(nut_mau, current_row, 0, 1, 2)  # Kéo dài qua 2 cột
        nut_mau.clicked.connect(self.handle_action_button_click)

        # Thiết lập khoảng cách giữa các cột
        self.content_layout.setColumnStretch(1, 1)  # Cột nhập liệu (cột 1) sẽ co giãn
        self.content_layout.setSpacing(10)  # Khoảng cách giữa các widget là 10px

        # 6. Đặt container vào khu vực cuộn
        scroll_area.setWidget(self.container_widget)

        # 7. Layout cuối cùng
        final_layout = QVBoxLayout(self)
        final_layout.addWidget(scroll_area)

        # 8. THIẾT LẬP QTIMER ĐỂ CẬP NHẬT THỜI GIAN LIÊN TỤC
        self.timer = QTimer(self)
        # Kết nối tín hiệu timeout của timer với hàm cập nhật
        self.timer.timeout.connect(self.update_system_time)
        # Kích hoạt timer chạy mỗi 1000 miligiây (1 giây)
        self.timer.start(1000)

        # Lấy widget Số điện thoại
        sdt_widget = self.data_widgets["Số điện thoại"]

        # Tạo biểu thức chính quy: \d{10} : Yêu cầu chính xác 10 chữ số (0-9).
        sdt_regex = QRegularExpression(r"^\d{10}$")

        # Tạo Validator
        sdt_validator = QRegularExpressionValidator(sdt_regex, sdt_widget)

        # Áp dụng Validator cho widget
        sdt_widget.setValidator(sdt_validator)

        # (Tùy chọn) Giới hạn độ dài tối đa (để người dùng không nhập quá 10)
        sdt_widget.setMaxLength(10)


    def update_system_time(self):
        """Cập nhật giá trị QDateTimeEdit với thời gian hiện tại của hệ thống."""
        self.tiep_nhan_luc_widget.setDateTime(QDateTime.currentDateTime())

    def _setup_combobox_from_csv(self, field_name, file_path, display_col, key_col, default_key=None):
        """
        :param field_name: Tên của trường (key) trong self.data_widgets.
        :param file_path: Đường dẫn đến file CSV.
        :param display_col: Tên cột hiển thị.
        :param key_col: Tên cột giá trị khóa (key value).
        :param default_key: (TÙY CHỌN) Giá trị khóa (key value) để đặt làm mặc định.
        """
        # 1. Tải dữ liệu
        data_frame = load_data_from_csv(file_path)

        # 2. Lấy widget tương ứng
        combobox = self.data_widgets.get(field_name)

        if combobox is None:
            print(f"LỖI: Không tìm thấy widget cho trường '{field_name}'.")
            return

        if not data_frame.empty:
            # 3. Điền dữ liệu vào ComboBox
            populate_combobox(combobox, data_frame, display_col, key_col)

            # 4. >>> LOGIC THIẾT LẬP GIÁ TRỊ MẶC ĐỊNH DỰA TRÊN KEY <<<
            if default_key is not None:
                index = combobox.findData(str(default_key))
                if index >= 0:
                    combobox.setCurrentIndex(index)
                    return  # Thoát khỏi hàm nếu đã tìm thấy và đặt mặc định

            # Nếu không có key mặc định hoặc không tìm thấy key: chọn mục đầu tiên
            combobox.setCurrentIndex(0)

        else:
            print(f"CẢNH BÁO: Dữ liệu CSV cho '{field_name}' rỗng hoặc bị lỗi.")

    def is_valid_form(self) -> bool:
        """Kiểm tra các trường bắt buộc không được để trống và áp dụng Style Sheet lỗi."""

        # Danh sách tên các trường BẮT BUỘC (Dựa trên key trong self.data_widgets)
        REQUIRED_FIELDS = [
            "Mã y tế", "Họ tên", "Ngày sinh", "Giới tính",
            "Số điện thoại", "Lý do tiếp nhận", "Quốc tịch", "Dân tộc",
            "CCCD/Số định danh"
            # Thêm các trường * bắt buộc khác vào đây
        ]

        is_valid = True

        # Lặp qua tất cả các widget để kiểm tra
        for field_name, widget in self.data_widgets.items():
            # Xóa style lỗi cũ trước khi kiểm tra lại
            widget.setProperty('class', None)
            widget.style().polish(widget)

            if field_name not in REQUIRED_FIELDS:
                continue

            # Kiểm tra giá trị
            value = None
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, QComboBox):
                # Kiểm tra cả giá trị key, tránh trường hợp item đầu tiên là '---chọn---'
                value = get_combobox_key(widget)
                if value is None or value == "":
                    # Nếu ComboBox có nội dung nhưng giá trị key rỗng
                    value = None
                else:
                    # Nếu đã chọn một key hợp lệ, value có giá trị
                    value = "valid"
            elif isinstance(widget, QDateEdit) or isinstance(widget, QDateTimeEdit):
                # Kiểm tra giá trị hợp lệ, thường là kiểm tra ngày không phải null/mặc định
                # Nếu không có giới hạn, ta coi như luôn hợp lệ
                value = widget.dateTime().toString() if widget.dateTime().isValid() else None

            # Nếu giá trị là rỗng (None hoặc chuỗi rỗng)
            if not value:
                # 1. Đặt thuộc tính 'class' thành 'error'
                widget.setProperty('class', 'error')

                # 2. Yêu cầu widget cập nhật style (cần thiết cho setProperty)
                widget.style().polish(widget)

                is_valid = False

        return is_valid

    def handle_action_button_click(self):
        """Thu thập dữ liệu từ tất cả các trường và gọi hàm in."""

        # 1. GỌI HÀM VALIDATION
        if not self.is_valid_form():
            QMessageBox.warning(self, "Lỗi Nhập liệu", "Vui lòng điền đầy đủ các trường bắt buộc!")
            return

        collected_data = {}

        # 1. Thu thập dữ liệu từ tất cả các widget
        for key, widget in self.data_widgets.items():
            if isinstance(widget, QLineEdit):
                value = widget.text()
            elif isinstance(widget, QDateEdit):
                value = widget.date().toString("dd/MM/yyyy")
            elif isinstance(widget, QDateTimeEdit):
                # Sử dụng định dạng có giây để truyền đi
                value = widget.dateTime().toString("dd/MM/yyyy HH:mm:ss")
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked() # Trả về True/False
            else:
                value = None

            # Lưu dữ liệu vào dictionary bằng key đã chuẩn hóa
            collected_data[key.replace("*", "").strip()] = value

        # 2. Gọi hàm và lưu dữ liệu vào file csv
        luu_du_lieu_tiep_nhan(collected_data)

        # Lấy mã phòng khám
        ma_phong_kham = get_combobox_key(self.data_widgets.get('Phòng khám'))

        # Gọi hàm lấy mã tiếp theo và cập nhật STT
        next_stt = get_next_queue_number(ma_phong_kham)

        # 3. Chuẩn bị dữ liệu cho hàm in (Định dạng lại key theo yêu cầu của hàm in)
        # Đây là bước ánh xạ dữ liệu thu thập được (collected_data) sang
        # định dạng key mà hàm create_and_open_pdf_for_printing yêu cầu.

        data_for_printing = {
            'clinic_name': 'BỆNH VIỆN ABC',
            'room_info': collected_data.get('Phòng khám'),
            'queue_number': next_stt,
            'code': collected_data.get('Mã y tế', 'CODE'),
            'patient_name': collected_data.get('Họ tên', 'N/A'),
            'patient_dob': collected_data.get('Ngày sinh', 'N/A'),
            'schedule_time': collected_data.get('Tiếp nhận lúc', 'N/A'),
            'print_time': QDateTime.currentDateTime().toString("dd/MM/yyyy HH:mm:ss"),
            'payment_method': 'BHYT' if collected_data.get('Số BHYT (tick)') else 'Thu Phí',
        }

        # 4. Gọi hàm in với dữ liệu đã chuẩn bị
        create_and_open_pdf_for_printing(data_for_printing)