from datetime import datetime
import os
import sys

from reportlab.lib.pagesizes import A7, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle

from app.core.print_file import print_file_win32
from app.utils.create_qr_code import generate_medical_qr_code
from app.utils.get_file_path import get_file_path

VIET_FONT = 'TimesNewRomanVN'
VIET_FONT_BOLD = 'TimesNewRomanVNBold'
VIET_FONT_ITALIC = 'TimesNewRomanVNItalic'

try:
    pdfmetrics.registerFont(TTFont(VIET_FONT, 'C:/Windows/Fonts/times.ttf'))
    pdfmetrics.registerFont(TTFont(VIET_FONT_BOLD, 'C:/Windows/Fonts/timesbd.ttf'))
    pdfmetrics.registerFont(TTFont(VIET_FONT_ITALIC, 'C:/Windows/Fonts/timesi.ttf'))
except Exception:
    VIET_FONT = 'Times-Roman'
    VIET_FONT_BOLD = 'Times-Bold'
    VIET_FONT_ITALIC = 'Times-Italic'


def _safe_text(value):
    return '' if value is None else str(value).strip()


def _build_pdf_path(data):
    output_dir = get_file_path('data/tiep_nhan_benh_nhan')
    output_dir.mkdir(parents=True, exist_ok=True)
    ma_y_te = _safe_text(data.get('MaYTe'))
    stt = _safe_text(data.get('STT'))
    safe_time = datetime.now().strftime('%H%M%S')
    parts = ['phieu_tiep_nhan']
    if ma_y_te:
        parts.append(ma_y_te)
    if stt:
        parts.append(stt)
    parts.append(safe_time)
    return output_dir / ('_'.join(parts) + '.pdf')


def create_and_open_pdf_for_printing(data):
    """Tạo phiếu tiếp nhận A7 có QR và in ra máy in mặc định."""
    try:
        pdf_path = _build_pdf_path(data)

        width, height = landscape(A7)
        c = canvas.Canvas(str(pdf_path), pagesize=landscape(A7))
        c.setTitle('Phiếu tiếp nhận')

        margin_left = 4 * mm
        margin_right = 4 * mm
        qr_size = 16 * mm
        
        # Đặt mã QR ở góc phải bên trên sát lề
        qr_x = width - margin_right - qr_size
        qr_y = height - 4 * mm - qr_size
        
        # Căn giữa tiêu đề bệnh viện ở vùng trống bên trái mã QR
        header_center_x = (qr_x + margin_left) / 2

        c.setFont(VIET_FONT_BOLD, 10)
        c.drawCentredString(header_center_x, height - 6 * mm, _safe_text(data.get('TenBenhVien', 'BỆNH VIỆN')))
        c.drawCentredString(header_center_x, height - 11 * mm, _safe_text(data.get('PhongTiepNhan', data.get('Phong', 'PHÒNG KHÁM'))))

        # Sinh mã QR
        qr_path = generate_medical_qr_code(
            ma_y_te=data.get('MaYTe', ''),
            so_bhyt=data.get('SoBHYT', ''),
            doi_tuong=data.get('DoiTuong', ''),
            ho_ten=data.get('HoTen', ''),
            tuoi=str(data.get('Tuoi', '')),
            gioi_tinh=data.get('GioiTinh', ''),
            dia_chi=data.get('DiaChi', ''),
            so_dien_thoai=data.get('SoDienThoai', ''),
            so_tien='0',
            bill_type='TIEP_NHAN',
            items=[]
        )

        # Vẽ Số thứ tự (STT) ở phía bên trái vùng trên
        stt_text = _safe_text(data.get('STT'))
        if stt_text:
            c.setFont(VIET_FONT_BOLD, 18)
            c.drawString(margin_left, height - 19 * mm, f"{stt_text}")

        # Vẽ hình ảnh QR Code
        if qr_path and os.path.exists(qr_path):
            c.drawImage(ImageReader(qr_path), qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto')
        
        # Tạo Paragraph bọc chữ căn giữa và tự động xuống hàng cho Mã y tế & Đối tượng dưới mã QR
        code_text = _safe_text(data.get('MaYTe'))
        doi_tuong_text = _safe_text(data.get('DoiTuong'))
        qr_labels = []
        if code_text:
            qr_labels.append(code_text)
        if doi_tuong_text:
            qr_labels.append(f"({doi_tuong_text})")
            
        if qr_labels:
            qr_text_style = ParagraphStyle(
                name='QRTextStyle',
                fontName=VIET_FONT_BOLD,
                fontSize=8,
                leading=10,
                alignment=1,  # Căn giữa hoàn toàn (Center alignment)
            )
            qr_text_p = Paragraph("<br/>".join(qr_labels), qr_text_style)
            qr_box_width = qr_size + 8 * mm  # Tăng chiều rộng hộp text một chút để căn giữa cân xứng dưới QR
            ql_w, ql_h = qr_text_p.wrap(qr_box_width, 20 * mm)
            qr_text_p.drawOn(c, qr_x + (qr_size / 2) - (qr_box_width / 2), qr_y - ql_h - 1 * mm)

        # --- Khu vực thông tin bệnh nhân ---
        # Dòng 1: Họ tên - Năm sinh - Giới tính
        name_y = height - 35.5 * mm
        c.setFont(VIET_FONT_BOLD, 10)
        c.drawString(margin_left, name_y, _safe_text(data.get('HoTen')))
        c.drawString(margin_left + 185, name_y, _safe_text(data.get('NamSinh')))
        c.drawString(margin_left + 250, name_y, _safe_text(data.get('GioiTinh')))

        # Dòng 2: Mã số thẻ BHYT
        bhyt_y = name_y - 5.5 * mm
        c.setFont(VIET_FONT, 10)
        label = 'Mã số thẻ BHYT: '
        bhyt_value = _safe_text(data.get('SoBHYT'))
        c.drawString(margin_left, bhyt_y, label)
        c.setFont(VIET_FONT_BOLD, 10)
        c.drawString(margin_left + stringWidth(label, VIET_FONT, 10), bhyt_y, bhyt_value)

        # Dòng 3: Địa chỉ (Xử lý co giãn tự động và text wrap)
        address_y = bhyt_y - 5.5 * mm
        address_value = _safe_text(data.get('DiaChi'))

        address_style = ParagraphStyle(
            name='AddressStyle',
            fontName=VIET_FONT,
            fontSize= 10,
        )
        address_paragraph = Paragraph(f"Địa chỉ: <b>{address_value}</b>", address_style)
        address_width = width - margin_left - margin_right
        address_w, address_h = address_paragraph.wrap(address_width, 30 * mm)
        address_paragraph.drawOn(c, margin_left, address_y - address_h + 2)

        # Dòng 4: Thời hạn bảo hiểm y tế
        bh_from_label = 'BH Từ ngày: '
        bh_to_label = 'BH Đến ngày: '
        bh_from_value = _safe_text(data.get('BHYT_Tu') or data.get('BHYTFrom') or data.get('BHYT_TuNgay'))
        bh_to_value = _safe_text(data.get('BHYT_Den') or data.get('BHYTTo') or data.get('BHYT_DenNgay'))
        
        # Tọa độ Y động tính dựa trên điểm kết thúc của khối Địa chỉ
        date_y = address_y - address_h - 2.5 * mm
        
        # In đậm toàn bộ thông tin BH Từ ngày
        c.setFont(VIET_FONT_BOLD, 10)
        c.drawString(margin_left, date_y, bh_from_label)
        c.drawString(margin_left + stringWidth(bh_from_label, VIET_FONT_BOLD, 10), date_y, bh_from_value)
        
        # In đậm toàn bộ thông tin BH Đến ngày
        right_x = width / 2 + 2 * mm
        c.drawString(right_x, date_y, bh_to_label)
        c.drawString(right_x + stringWidth(bh_to_label, VIET_FONT_BOLD, 10), date_y, bh_to_value)

        c.showPage()
        c.save()

        # Tiến trình đẩy lệnh in / preview tự động
        printed = print_file_win32(str(pdf_path))
        if not printed:
            if sys.platform == 'win32':
                try:
                    os.startfile(str(pdf_path))
                except Exception:
                    pass
            elif sys.platform == 'darwin':
                os.system(f'open "{pdf_path}"')
            else:
                os.system(f'xdg-open "{pdf_path}"')
        return str(pdf_path)
    except Exception as e:
        print(f'Lỗi tạo phiếu tiếp nhận: {e}')
        return None