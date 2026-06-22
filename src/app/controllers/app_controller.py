from PyQt6 import QtWidgets, QtCore
from PyQt6.QtWidgets import QMessageBox
from PyQt6.uic.Compiler.qtproxies import QtGui

from app.controllers.dich_vu_controller import DangKyDichVuTabController
from app.controllers.tai_vu_controller import TaiVuTabController
# Import UI cha
from app.ui.MainWindow import Ui_mainWidget
# Import Controller con
from app.controllers.kham_benh_controller import KhamBenhTabController
from app.controllers.tiep_nhan_controller import TiepNhanTabController

from app.utils.constants import CLS_CODE


class AppController(QtWidgets.QWidget):
    """
    Controller chính của ứng dụng. Quản lý cửa sổ và các tab.
    """

    def __init__(self):
        super().__init__()

        self.ui_main = Ui_mainWidget()
        self.ui_main.setupUi(self)

        self.kham_benh_controller = KhamBenhTabController(
            tab_widget_container=self.ui_main.tab_kham_benh
        )

        self.dich_vu_controller = DangKyDichVuTabController(
            tab_widget_container=self.ui_main.tab_dkdv
        )

        self.tai_vu_controller = TaiVuTabController(
            tab_widget_container=self.ui_main.tab_tai_vu
        )

        self.tiep_nhan_controller = TiepNhanTabController(
            tab_widget_container=self.ui_main.tab_tiep_nhan
        )

        self._apply_tab_stylesheet()

        self.dich_vu_controller.dich_vu_completed.connect(self.handle_dich_vu_completed)
        self.kham_benh_controller.req_dang_ky_cls.connect(self.handle_f5_shortcut)
        self.tai_vu_controller.req_dang_ky_cls.connect(lambda : self.handle_f5_shortcut(mode='tai_vu'))
        self.kham_benh_controller.req_load_service_bill.connect(self.dich_vu_controller.load_data_from_service_bill)
        self.kham_benh_controller.req_reset_dich_vu.connect(self.dich_vu_controller.reset_all)

        self.ui_main.tabWidget.setCurrentIndex(0)
        self.showMaximized()


    def _apply_tab_stylesheet(self):
        stylesheet = """
            QTabBar::tab {
                background-color: #E0E0E0;
                color: black;
                padding: 8px;
                border: 1px solid #C4C4C3;
                border-bottom: none; 
            }
            QTabBar::tab:hover {
                background-color: #ADD8E6;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #0078D4;
                font-weight: bold;
            }
            
            QTabWidget {
                /* Đặt màu nền bằng mã hex (ví dụ: Light Blue) */
                background-color: #ADD8E6; 
            }
            
            QLabel {
                font-size:14px;
                font-family: Times;
            }
            
            QLineEdit, QComboBox,QDateEdit, QDateTimeEdit {
                /* Cài đặt Mặc định */
                background-color: white; /* Màu nền xanh nhạt (AliceBlue) */
                border: 2px solid #ccc; /* Viền xám nhạt */
                border-radius: 5px; /* Bo tròn góc */
                padding: 4px; /* Khoảng cách bên trong */
                font-size: 14px;
            }
            
            QLineEdit:hover, 
            QComboBox:hover {
                /* Khi con trỏ chuột di vào */
                border: 2px solid #a8a8a8; /* Viền sẫm hơn một chút */
            }
            
            QLineEdit:focus, 
            QComboBox:focus,
            QDateEdit:focus {
                /* Khi QLineEdit nhận focus (đang gõ) */
                border: 3px solid blue; /* Viền màu xanh lá đậm */
                background-color: white; /* Nền trắng để nổi bật */
            }
            
            QLineEdit:read-only, 
            QComboBox:read-only,
            QDateTimeEdit:read-only {
                /* Khi QLineEdit chỉ đọc (dùng setReadOnly(True)) */
                background-color: #f0f8ff; /* Nền xám để báo hiệu không thể chỉnh sửa */
                color: #555;
            }
        """
        self.ui_main.tabWidget.setStyleSheet(stylesheet)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Xử lý sự kiện nhấn phím toàn cục."""

        # Lấy index tab hiện tại
        current_index = self.ui_main.tabWidget.currentIndex()
        kham_benh_tab_index = 0
        dich_vu_tab_index = 1
        tai_vu_tab_index = 2
        tiep_nhan_tab_index = 3

        # Chỉ xử lý nếu đang ở Tab Khám Bệnh
        if current_index == kham_benh_tab_index:

            # --- F5: Chuyển sang Dịch vụ ---
            if event.key() == QtCore.Qt.Key.Key_F5:
                self.handle_f5_shortcut()
                event.accept()
                return

            # --- F6: Lưu và In toa thuốc ---
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier) and \
                    (event.key() == QtCore.Qt.Key.Key_P):
                self.kham_benh_controller.print_drug_bill()
                event.accept()
                return

            # --- F9: Kiểm tra thông tuyến BHYT ---
            if event.key() == QtCore.Qt.Key.Key_F3:
                self.kham_benh_controller.handle_btn_check_bhyt()
                event.accept()
                return

            # # --- F7: Reset màn hình ---
            # if event.key() == QtCore.Qt.Key.Key_F7:
            #     self.kham_benh_controller.reset_all()
            #     event.accept()
            #     return
            #
            # # --- F8: Xóa toa thuốc ---
            # if event.key() == QtCore.Qt.Key.Key_F8:
            #     self.kham_benh_controller.reset_prescription_table()
            #     event.accept()
            #     return

            # --- Shift + Enter: Thêm dòng thuốc ---
            # Kiểm tra: Phím Enter + Giữ Shift
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                    (event.key() == QtCore.Qt.Key.Key_Return or event.key() == QtCore.Qt.Key.Key_Enter):

                # Kiểm tra focus có đang nằm trong bảng thuốc hay không
                focus_widget = QtWidgets.QApplication.focusWidget()

                # Truy cập vào bảng thuốc qua ui_kham của controller
                ds_thuoc_table = self.kham_benh_controller.ui_kham.ds_thuoc

                # Nếu con trỏ đang nằm trong bảng thuốc -> Gọi hàm thêm dòng
                if focus_widget and ds_thuoc_table.isAncestorOf(focus_widget):
                    self.kham_benh_controller.finalize_drug_entry(0)
                    event.accept()
                    return

        if current_index == dich_vu_tab_index:
            # --- Ctrl+P: Lưu và In phiếu chỉ định ---
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier) and \
                    (event.key() == QtCore.Qt.Key.Key_P):
                self.dich_vu_controller.btn_in_phieu_handle()
                event.accept()
                return

        if current_index == tai_vu_tab_index:
            # --- F5: Chuyển sang Dịch vụ ---
            if event.key() == QtCore.Qt.Key.Key_F5:
                self.handle_f5_shortcut(mode='tai_vu')
                event.accept()
                return

            # --- Ctrl+P: Lưu và In phiếu chỉ định ---
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier) and \
                    (event.key() == QtCore.Qt.Key.Key_P):
                self.tai_vu_controller.handle_in_hoa_don()
                event.accept()
                return

        if current_index == tiep_nhan_tab_index:
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier) and \
                    (event.key() == QtCore.Qt.Key.Key_S):
                self.tiep_nhan_controller.handle_save_and_print()
                event.accept()
                return
        
        if current_index == tiep_nhan_tab_index:
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier) and \
                    (event.key() == QtCore.Qt.Key.Key_N):
                self.tiep_nhan_controller.reset_form()
                event.accept()
                return


        # Nếu không phải các phím trên, gọi xử lý mặc định
        super().keyPressEvent(event)
    


    def handle_f5_shortcut(self, mode='kham_benh'):
        """Xử lý chuyển đổi sang Đăng ký Dịch vụ khi nhấn F5."""
        hanh_chinh_data = None
        if mode == 'kham_benh':
            # 1. Thu thập dữ liệu hành chính
            hanh_chinh_data = self.kham_benh_controller.get_hanh_chinh_data()

            # 2. KIỂM TRA ĐIỀU KIỆN CHUYỂN SANG CẬN LÂM SÀNG
            if not self.kham_benh_controller.validate_patient_info():
                return

            cach_giai_quyet_code = hanh_chinh_data.get('MaGiaiQuyet')
            if cach_giai_quyet_code != CLS_CODE:
                QMessageBox.warning(self,
                                    "Thông báo",
                                    f"Chỉ chuyển màn hình khi Cách Giải Quyết là 'Cận Lâm Sàng'.")
                return
        elif mode == 'tai_vu':
            hanh_chinh_data = self.tai_vu_controller.get_hanh_chinh_data()

            if not self.tai_vu_controller.validate_patient_info():
                return
        else:
            pass

        # 3. Chuyển tab và truyền dữ liệu
        dich_vu_tab_index = 1

        if hanh_chinh_data is not None and self.ui_main.tabWidget.count() > dich_vu_tab_index:
            self.dich_vu_controller.load_thong_tin_benh_nhan(hanh_chinh_data)
            self.ui_main.tabWidget.setCurrentIndex(dich_vu_tab_index)
        else:
            QMessageBox.critical(self, "Lỗi", "Tab Đăng ký Dịch vụ không tồn tại.")

    @QtCore.pyqtSlot()
    def handle_dich_vu_completed(self):
        kham_benh_tab_index = 0

        # 2. Quay về Tab Khám bệnh (index 0)
        if self.ui_main.tabWidget.currentIndex() != kham_benh_tab_index:
            self.ui_main.tabWidget.setCurrentIndex(kham_benh_tab_index)

        self.kham_benh_controller.reset_all()