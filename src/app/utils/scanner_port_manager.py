from PyQt6.QtCore import QObject, QTimer


class ScannerPortManager(QObject):
    """Quản lý kết nối scanner theo tab đang active để tránh xung đột cổng COM."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controllers = {}
        self._active_tab = None

    def register_controller(self, tab_name: str, controller) -> None:
        self._controllers[tab_name] = controller

    def activate_tab(self, tab_name: str) -> None:
        if self._active_tab == tab_name:
            return

        previous_tab = self._active_tab
        self._active_tab = tab_name

        if previous_tab and previous_tab in self._controllers:
            previous_controller = self._controllers[previous_tab]
            if hasattr(previous_controller, 'close_serial_port'):
                previous_controller.close_serial_port()

        current_controller = self._controllers.get(tab_name)
        if current_controller is None:
            return

        if hasattr(current_controller, 'open_serial_port'):
            QTimer.singleShot(150, current_controller.open_serial_port)
