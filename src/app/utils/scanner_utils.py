import re
import unicodedata
from typing import Optional

from PyQt6.QtWidgets import QWidget


PROTECTED_FIELD_NAMES = {
    "ma_y_te",
    "stt",
    "so_bhyt",
    "ma_dich_vu",
    "ma_thuoc",
}


def normalize_scanned_text(text: str) -> str:
    """Chuẩn hóa text nhận từ máy quét, bỏ ký tự thừa và xử lý unicode."""
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", str(text))
    normalized = re.sub(r'([Aa])([âăêôơưấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡợứừửữựÂĂÊÔƠƯẤẦẨẪẬẮẰẲẴẶẾỀỂỄỆỐỒỔỖỘỚỜỞỠỢỨỪỬỮỰ])', r'\2', normalized)
    normalized = normalized.replace("\ufeff", "")
    normalized = normalized.replace("\u200b", "")
    normalized = normalized.replace("\r", " ").replace("\n", " ")
    normalized = re.sub(r"[\x00-\x1f\x7f]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def parse_scanned_data(raw_text: str) -> dict:
    """Parse chuỗi dữ liệu quét từ CCCD/QR sang dict các field chuẩn."""
    cleaned = normalize_scanned_text(raw_text)
    if not cleaned:
        return {}

    parts = [part.strip() for part in cleaned.split("|")]
    if not parts:
        return {}

    result = {
        "cccd": "",
        "ma_y_te": "",
        "ho_ten": "",
        "gioi_tinh": "",
        "ngay_sinh": "",
        "dia_chi": "",
        "ma_dt": "",
        "bhyt": "",
        "tuoi": "",
        "tien": "",
        "bill_type": "",
        "ds_string": "",
        "raw": cleaned,
    }

    # Hỗ trợ định dạng key:value phổ biến trong QR đơn thuốc / phiếu chỉ định
    if any(":" in part for part in parts):
        data_parts = {}
        for part in parts:
            if ":" in part:
                key, value = part.split(":", 1)
                data_parts[key.strip()] = value.strip()
        if data_parts:
            result["ma_y_te"] = data_parts.get("MaYTe", "")
            result["ho_ten"] = data_parts.get("Ten", "") or data_parts.get("HoTen", "")
            result["gioi_tinh"] = data_parts.get("GT", "")
            result["dia_chi"] = data_parts.get("DC", "")
            result["ma_dt"] = data_parts.get("MaDT", "")
            result["bhyt"] = data_parts.get("BHYT", "")
            result["tuoi"] = data_parts.get("Tuoi", "")
            result["tien"] = data_parts.get("Tien", "")
            result["bill_type"] = (data_parts.get("Loai", "") or "").upper()
            result["ds_string"] = data_parts.get("DS", "")
            result["cccd"] = data_parts.get("CCCD", "")
            return result

    # Hỗ trợ định dạng đơn giản: DON_THUOC|... hoặc PHIEU_CHI_DINH|...
    if parts and parts[0].upper() in {"DON_THUOC", "THUOC"}:
        result["bill_type"] = "THUOC"
        if len(parts) > 2:
            result["ho_ten"] = parts[2]
        return result

    if parts and parts[0].upper() in {"PHIEU_CHI_DINH", "DICH_VU"}:
        result["bill_type"] = "DICH_VU"
        if len(parts) > 2:
            result["ho_ten"] = parts[2]
        return result

    if len(parts) < 5:
        return result

    ngay_sinh_raw = ""
    date_index = -1
    for index, part in enumerate(parts):
        if len(part) == 8 and part.isdigit():
            ngay_sinh_raw = part
            date_index = index
            break

    if len(parts) >= 5 and parts[0].isdigit() and len(parts[0]) >= 9:
        result["cccd"] = parts[0]
        result["ho_ten"] = parts[2] if len(parts) > 2 else ""
        result["gioi_tinh"] = parts[3] if len(parts) > 3 else ""
        result["dia_chi"] = parts[5] if len(parts) > 5 else ""
        if date_index == -1:
            ngay_sinh_raw = parts[4] if len(parts) > 4 else ""
    else:
        if date_index != -1:
            result["ho_ten"] = parts[date_index - 1] if date_index - 1 >= 0 else ""
            result["gioi_tinh"] = parts[date_index + 1] if date_index + 1 < len(parts) else ""
            result["dia_chi"] = parts[date_index + 2] if date_index + 2 < len(parts) else ""
        else:
            result["ho_ten"] = parts[2] if len(parts) > 2 else ""
            result["gioi_tinh"] = parts[3] if len(parts) > 3 else ""
            result["dia_chi"] = parts[5] if len(parts) > 5 else ""

    result["ngay_sinh"] = ngay_sinh_raw
    return result


def should_skip_scanner_input(widget: Optional[QWidget]) -> bool:
    """Kiểm tra xem có nên bỏ qua việc nhập dữ liệu từ scanner vào widget đang focus hay không."""
    if widget is None:
        return False

    object_name = (widget.objectName() or "").strip().lower()
    return object_name in PROTECTED_FIELD_NAMES
