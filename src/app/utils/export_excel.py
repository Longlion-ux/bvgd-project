import os
import json
import pandas as pd
from datetime import datetime
from app.utils.get_file_path import get_file_path

from PyQt6.QtWidgets import QMessageBox

# Đường dẫn gốc chứa data json
DATA_DIR = get_file_path('data/collect')
EXPORT_DIR = get_file_path('data/exports')


def export_daily_report_to_excel(date_str):
    """
    Xuất dữ liệu ngày ra Excel.
    Cập nhật: Thêm đầy đủ Sinh hiệu (Mạch, Nhiệt, HA, SPO2...) và thông tin Hành chính.
    """
    day_dir = os.path.join(DATA_DIR, date_str)

    if not os.path.exists(day_dir):
        print(f"Không tìm thấy dữ liệu ngày {date_str}")
        return None

    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    # Khởi tạo danh sách
    list_drugs = []
    list_services = []
    list_invoices = []

    # Quét file JSON
    for filename in os.listdir(day_dir):
        if not filename.endswith('.json'):
            continue

        file_path = os.path.join(day_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Lỗi đọc file {filename}: {e}")
            continue

        # --- LẤY THÔNG TIN CHUNG (Meta Data) ---
        meta = data.get('meta_data', {})
        # Ép chuỗi để đảm bảo mã BN (nếu bằng số) không mất số 0
        user_id = str(meta.get('user_id', '')) 
        user_name = meta.get('user_name', '')

        bills = data.get('bills', {})

        # --- SHEET 1: CHI TIẾT KHÁM & THUỐC (DRUG BILLS) ---
        drug_bill = bills.get('drug_bill')
        if drug_bill and 'ToaThuoc' in drug_bill:
            vital_signs = {
                'Mạch (l/p)': drug_bill.get('Mach', ''),
                'Nhiệt độ (°C)': drug_bill.get('NhietDo', ''),
                'Huyết áp (mmHg)': drug_bill.get('HA', ''),
                'Nhịp thở (l/p)': drug_bill.get('NhipTho', ''),
                'Cân nặng (kg)': drug_bill.get('CanNang', ''),
                'Chiều cao (cm)': drug_bill.get('ChieuCao', ''),
                'SPO2 (%)': drug_bill.get('SPO2', ''),
                'Đường huyết': drug_bill.get('DuongHuyet', ''),
            }

            for drug in drug_bill['ToaThuoc']:
                row = {
                    'Mã BN': user_id,
                    'Tên Bệnh Nhân': user_name,
                    'Tuổi': drug_bill.get('Tuoi', ''),
                    'Giới Tính': drug_bill.get('GioiTinh', ''),
                    'Địa Chỉ': drug_bill.get('DiaChi', ''),
                    'BHYT': str(drug_bill.get('BHYT', '')),
                    'CCCD': str(drug_bill.get('CCCD', '')),

                    **vital_signs, 

                    'Chẩn Đoán': drug_bill.get('ChanDoan', ''),
                    'Bác Sĩ': drug_bill.get('TenBacSi', ''),

                    'Mã Thuốc': str(drug.get('MaThuoc', '')),
                    'Tên Thuốc': drug.get('TenThuoc', ''),
                    'Số Lượng': drug.get('SoLuong', 0),

                    'Sáng': drug.get('Sang', ''),
                    'Trưa': drug.get('Trua', ''),
                    'Chiều': drug.get('Chieu', ''),
                    'Tối': drug.get('Toi', '')
                }
                list_drugs.append(row)

        # --- SHEET 2: DỊCH VỤ (SERVICE BILLS) ---
        service_bill = bills.get('service_bill')
        if service_bill:
            for group_service in service_bill['DichVu']:
                for service in group_service['DSDichVu']:
                    row = {
                        'Mã y tế': str(service_bill.get('MaYTe', '')),
                        'Tên Bệnh Nhân': service_bill.get('HoTen', ''),
                        'Tuổi': service_bill.get('Tuoi', ''),
                        'Giới Tính': service_bill.get('GioiTinh', ''),

                        'Bác Sĩ CĐ': service_bill.get('BacSi', ''),
                        'Chẩn Đoán': service_bill.get('ChanDoan', ''),

                        'Tên nhóm dịch vụ': group_service.get('TenNhomDichVu', ''),
                        'Mã Dịch Vụ': str(service.get('MaDichVu', '')),
                        'Tên Dịch Vụ': service.get('TenDichVu', ''),
                        'Tên Loại giá': service.get('TenLoaiGia', ''),
                        'Nơi Thực Hiện': service.get('NoiThucHien', ''),
                        'Số Lượng': service.get('SoLuong', 1),
                        'Không hỗ trợ': service.get('KhongHoTro', 0),
                        'Không thu tiền': service.get('KhongThuTien', 0),
                    }
                    list_services.append(row)

        # --- SHEET 3: HÓA ĐƠN (INVOICES) ---
        invoice = bills.get('invoice')
        if invoice:
            row = {
                'Mã BN': user_id,
                'Tên Bệnh Nhân': user_name,
                'Người Thu': invoice.get('NguoiThuTien', ''),
                'Thời Gian': invoice.get('NgayTao', date_str),
                'Tổng Tiền': invoice.get('TongTienThanhToan', 0),
                'Hình Thức TT': invoice.get('HinhThucThanhToan', ''),
                'Đơn Vị': invoice.get('TenDonVi', ''),
                'MST': str(invoice.get('MST', ''))
            }
            list_invoices.append(row)

    # --- XUẤT FILE ---
    df_drugs = pd.DataFrame(list_drugs)
    df_services = pd.DataFrame(list_services)
    df_invoices = pd.DataFrame(list_invoices)

    if not df_drugs.empty:
        df_drugs.sort_values(by=['Tên Bệnh Nhân', 'Tên Thuốc'], inplace=True)
    if not df_services.empty:
        df_services.sort_values(by=['Tên Bệnh Nhân', 'Tên Dịch Vụ'], inplace=True)
    if not df_invoices.empty:
        df_invoices.sort_values(by=['Tên Bệnh Nhân'], inplace=True)

    timestamp = ''
    output_filename = f"BaoCao_Ngay_{date_str}_{timestamp}.xlsx"
    output_path = os.path.join(EXPORT_DIR, output_filename)

    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            if not df_drugs.empty:
                df_drugs.to_excel(writer, sheet_name='Chi Tiết Thuốc & Khám', index=False)
                _auto_adjust_column_width(writer, df_drugs, 'Chi Tiết Thuốc & Khám')
            else:
                pd.DataFrame({'Info': ['Không có dữ liệu']}).to_excel(writer, sheet_name='Chi Tiết Thuốc & Khám', index=False)

            if not df_services.empty:
                df_services.to_excel(writer, sheet_name='Chi Tiết Dịch Vụ', index=False)
                _auto_adjust_column_width(writer, df_services, 'Chi Tiết Dịch Vụ')
            else:
                pd.DataFrame({'Info': ['Không có dữ liệu']}).to_excel(writer, sheet_name='Chi Tiết Dịch Vụ', index=False)

            if not df_invoices.empty:
                df_invoices.to_excel(writer, sheet_name='Tổng Hợp Doanh Thu', index=False)
                _auto_adjust_column_width(writer, df_invoices, 'Tổng Hợp Doanh Thu')
            else:
                pd.DataFrame({'Info': ['Không có dữ liệu']}).to_excel(writer, sheet_name='Tổng Hợp Doanh Thu', index=False)

        print(f"Xuất file thành công: {output_path}")
        return output_path

    except Exception as e:
        print(f"Lỗi khi ghi file Excel: {e}")
        return None


def _auto_adjust_column_width(writer, df, sheet_name):
    """Căn chỉnh độ rộng cột thông minh"""
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        sample_values = df[col].astype(str).head(50)
        max_len = max(
            sample_values.map(len).max() if not sample_values.empty else 0,
            len(str(col))
        ) + 3

        if max_len > 40: max_len = 40
        if max_len < 8: max_len = 8

        worksheet.column_dimensions[chr(65 + i)].width = max_len

def export_tiep_nhan_to_excel(date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    source_path = get_file_path('data/lich_su_tiep_nhan.csv')
    export_dir = get_file_path('data/exports')
    export_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(source_path):
        return None

    # Quan trọng: Thêm dtype=str để Pandas hiểu toàn bộ file là chuỗi, tránh mất số 0
    df = pd.read_csv(source_path, dtype=str)
    df = df.fillna('')
    
    # Dọn dẹp cột 'Phong' thừa trước khi xuất
    if 'Phong' in df.columns:
        df = df.drop(columns=['Phong'])

    if 'MaYTe' in df.columns:
        df['MaYTe'] = df['MaYTe'].astype(str).str.replace(r'\.0$', '', regex=True)
    elif 'Mã y tế' in df.columns: 
        df['Mã y tế'] = df['Mã y tế'].astype(str).str.replace(r'\.0$', '', regex=True)

    if not df.empty and 'NgayTiepNhan' in df.columns:
        df = df[df['NgayTiepNhan'].astype(str).str.startswith(date_str, na=False)]
        
    if 'STT' in df.columns:
        df['STT'] = df['STT'].astype(str)
        
    if 'SoBHYT' in df.columns:
        df['SoBHYT'] = df['SoBHYT'].astype(str).str.replace('.0', '', regex=False)

    output_path = export_dir / f'tiep_nhan_{date_str}.xlsx'
    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Tiếp Nhan', index=False)
            _auto_adjust_column_width(writer, df, 'Tiếp Nhan') if not df.empty else None
        return str(output_path)
    except Exception as e:
        print(f'Lỗi xuất Excel tiếp nhận: {e}')
        return None


def export_excel():
    today = datetime.now().strftime("%Y-%m-%d")
    export_daily_report_to_excel(today)


def export_tiep_nhan_and_show_dialog(parent_widget, date_str=None):
    """
    Đã sửa: Bổ sung popup giống hệt hàm `export_and_show_dialog` để có nút mở file
    """
    file_path = export_tiep_nhan_to_excel(date_str)
    
    if file_path and os.path.exists(file_path):
        msg = QMessageBox(parent_widget)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Xuất dữ liệu thành công")
        msg.setText(f"File Excel đã được lưu tại:\n{file_path}")

        btn_open = msg.addButton("Mở File Ngay", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Đóng", QMessageBox.ButtonRole.RejectRole)

        msg.exec()

        if msg.clickedButton() == btn_open:
            try:
                os.startfile(file_path)  # Chỉ chạy trên Windows
            except Exception as e:
                QMessageBox.warning(parent_widget, "Lỗi", f"Không thể mở file: {e}")
        return file_path
        
    QMessageBox.warning(parent_widget, 'Thông báo', 'Không có dữ liệu để xuất.')
    return None

def export_and_show_dialog(parent_widget, date_str=None):
    """
    Hàm wrapper: Vừa xuất Excel, vừa hiển thị thông báo, vừa mở file.
    Giúp code trong Controller ngắn gọn hơn.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    file_path = export_daily_report_to_excel(date_str)

    if file_path and os.path.exists(file_path):
        msg = QMessageBox(parent_widget)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Xuất dữ liệu thành công")
        msg.setText(f"File Excel đã được lưu tại:\n{file_path}")

        btn_open = msg.addButton("Mở File Ngay", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Đóng", QMessageBox.ButtonRole.RejectRole)

        msg.exec()

        if msg.clickedButton() == btn_open:
            try:
                os.startfile(file_path) 
            except Exception as e:
                QMessageBox.warning(parent_widget, "Lỗi", f"Không thể mở file: {e}")
    else:
        QMessageBox.warning(parent_widget, "Thông báo", "Không có dữ liệu để xuất hoặc xảy ra lỗi ghi file.")

if __name__ == '__main__':
    export_excel()