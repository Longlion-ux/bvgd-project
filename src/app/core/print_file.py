import win32api
import win32print
import os


def print_file_win32(file_path):
    if not os.path.exists(file_path):
        print(f"Lỗi: Không tìm thấy tệp tại đường dẫn: {file_path}")
        return False

    try:
        default_printer = win32print.GetDefaultPrinter()
        abs_path = os.path.abspath(file_path)

        win32api.ShellExecute(
            0,
            "printto",  # 'printto' sẽ gửi tệp trực tiếp đến máy in
            abs_path,
            f'"{default_printer}"',
            ".",
            0  # 0: SW_HIDE - Cố gắng ẩn cửa sổ ứng dụng in
        )

        return True

    except Exception as e:
        print(f"Lỗi khi in bằng win32api: {e}")
        return False


if __name__ == "__main__":
    # Đường dẫn tệp của bạn
    path = r'C:\Users\hoduc\PycharmProjects\BVGD_Project\src\data\in_phieu_toa_thuoc\DonThuoc_123_15_12_2025__13_58_18.pdf'
    print_file_win32(path)