import pandas as pd
import os
from datetime import datetime

from PyQt6.QtWidgets import QComboBox

from app.utils.get_file_path import get_file_path

STT_THEO_PHONG_FILE_PATH = get_file_path('data/tiep_nhan_benh_nhan/stt_theo_ngay.csv')
LICH_SU_TIEP_NHAN_FILE_PATH = get_file_path('data/lich_su_tiep_nhan.csv')

def load_data_from_csv(file_path):
    """
    Đọc dữ liệu từ file CSV.
    LƯU Ý: Hàm này chỉ đọc một file (không phải nhiều sheet như Excel).
    """
    try:
        # Giả sử file CSV sử dụng dấu phẩy (,) làm delimiter và có header
        df = pd.read_csv(file_path)
        return df
    except Exception as e:
        print(f"LỖI: Không thể đọc file CSV '{file_path}'. {e}")
        return pd.DataFrame()  # Trả về DataFrame rỗng nếu có lỗi


def populate_combobox(combobox: QComboBox, data_frame: pd.DataFrame, display_col, key_col):
    """
    Điền dữ liệu vào QComboBox từ DataFrame.
    display_col và key_col phải là tên cột (header) trong CSV.
    """
    combobox.clear()
    for index, row in data_frame.iterrows():
        # Đảm bảo chuyển đổi sang chuỗi
        display_value = str(row[display_col])
        key_value = str(row[key_col])

        # Thêm giá trị hiển thị và lưu giá trị khóa (key value)
        combobox.addItem(display_value)
        combobox.setItemData(combobox.count() - 1, key_value)


def get_combobox_key(combobox: QComboBox):
    """Lấy giá trị khóa (key value) của mục hiện tại."""
    return combobox.currentData()


def load_history_records():
    if not os.path.exists(LICH_SU_TIEP_NHAN_FILE_PATH) or os.path.getsize(LICH_SU_TIEP_NHAN_FILE_PATH) == 0:
        return []
    try:
        return pd.read_csv(LICH_SU_TIEP_NHAN_FILE_PATH).to_dict('records')
    except Exception:
        return []

def luu_du_lieu_tiep_nhan(data: dict):
    """
    Lưu toàn bộ dữ liệu tiếp nhận từ biểu mẫu vào file CSV.
    Nếu bản ghi đã tồn tại theo CCCD thì cập nhật thay vì tạo bản ghi mới.
    """
    data = dict(data)
    data['timestamp_luu'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Chuẩn hóa STT
    stt_val = str(data.get('STT', '')).strip()
    data['STT'] = stt_val
    
    # 2. Chuẩn hóa Số điện thoại
    if 'SDT' in data:
        data['SDT'] = str(data.get('SDT', '')).strip()
        
    # 3. Chuẩn hóa Căn cước công dân
    if 'CCCD' in data:
        data['CCCD'] = str(data.get('CCCD', '')).strip()

    # 4. Chuẩn hóa Số BHYT
    data['SoBHYT'] = str(data.get('SoBHYT', '')).strip().replace('.0', '')
    
    data['PhongTiepNhan'] = data.get('PhongTiepNhan')
    data['TenBenhVien'] = data.get('TenBenhVien') or 'BỆNH VIỆN NHÂN DÂN GIA ĐỊNH'

    # Dọn dẹp các trường dữ liệu rỗng hoặc lỗi NaN
    for key, value in list(data.items()):
        if pd.isna(value) or value is None:
            data[key] = ''
        else:
            # Ép toàn bộ value của dict về dạng chuỗi trước khi chuyển thành DataFrame
            data[key] = str(value).strip()

    df_moi = pd.DataFrame([data])

    # 3. Kiểm tra và Lưu file
    if os.path.exists(LICH_SU_TIEP_NHAN_FILE_PATH):
        try:
            df_hien_tai = pd.read_csv(LICH_SU_TIEP_NHAN_FILE_PATH, dtype=str)

            if 'Phong' in df_hien_tai.columns:
                df_hien_tai = df_hien_tai.drop(columns=['Phong'])
            if 'Phong' in df_moi.columns:
                df_moi = df_moi.drop(columns=['Phong'])

            if 'MaYTe' in df_hien_tai.columns:
                df_hien_tai['MaYTe'] = df_hien_tai['MaYTe'].astype(str).str.replace(r'\.0$', '', regex=True)
            if 'Mã y tế' in df_hien_tai.columns:
                df_hien_tai['Mã y tế'] = df_hien_tai['Mã y tế'].astype(str).str.replace(r'\.0$', '', regex=True)

            cccd_value = str(data.get('CCCD', '')).strip()
            if cccd_value:
                existing_mask = df_hien_tai['CCCD'].fillna('').astype(str).str.strip() == cccd_value
                if existing_mask.any():
                    index_to_update = df_hien_tai.index[existing_mask][0]
                    for col in df_moi.columns:
                        if col in df_hien_tai.columns:
                            df_hien_tai.at[index_to_update, col] = data.get(col, '')
                    df_hien_tai = df_hien_tai.fillna('')
                    df_hien_tai.to_csv(LICH_SU_TIEP_NHAN_FILE_PATH, index=False, na_rep='')
                    print(f"SUCCESS: Đã cập nhật bản ghi có CCCD {cccd_value} tại {LICH_SU_TIEP_NHAN_FILE_PATH}.")
                    return

            df_ket_hop = pd.concat([df_hien_tai, df_moi], ignore_index=True)
            df_ket_hop = df_ket_hop.fillna('')
            df_ket_hop.to_csv(LICH_SU_TIEP_NHAN_FILE_PATH, index=False, na_rep='')
            print(f"SUCCESS: Đã thêm dữ liệu mới vào {LICH_SU_TIEP_NHAN_FILE_PATH}.")
        except Exception as e:
            print(f"LỖI LƯU: Không thể đọc/ghi vào file {LICH_SU_TIEP_NHAN_FILE_PATH}. {e}")

    else:
        try:
            os.makedirs(os.path.dirname(str(LICH_SU_TIEP_NHAN_FILE_PATH)), exist_ok=True)

            if 'Phong' in df_moi.columns:
                df_moi = df_moi.drop(columns=['Phong'])

            df_moi = df_moi.fillna('')
            df_moi.to_csv(LICH_SU_TIEP_NHAN_FILE_PATH, index=False, na_rep='')
            print(f"SUCCESS: Đã tạo và lưu dữ liệu đầu tiên vào {LICH_SU_TIEP_NHAN_FILE_PATH}.")
        except Exception as e:
            print(f"LỖI LƯU: Không thể tạo file lịch sử. {e}")