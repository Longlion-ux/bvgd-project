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

from app.core.in_phieu_tiep_nhan import _build_pdf_path
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


def create_and_open_pdf_for_printing(data):
    """Tạo phiếu tiếp nhận A7 có QR và in ra máy in mặc định."""
    try:
        pdf_path = _build_pdf_path(data)

        width, height = landscape(A7)
        c = canvas.Canvas(str(pdf_path), pagesize=landscape(A7))
        c.setTitle('Phiếu tiếp nhận')

        margin_left = 4 * mm
        margin_right = 4 * mm
        qr_size = 19 * mm                    # Tăng nhẹ kích thước QR
        qr_x = width - margin_right - qr_size - 2*mm
        qr_y = height - 29 * mm              # Điều chỉnh vị trí QR lên cao hơn

        center_x = width / 2

        # === Header ===
        c.setFont(VIET_FONT_BOLD, 13)
        c.drawCentredString(center_x, height - 6 * mm, _safe_text(data.get('TenBenhVien', 'BỆNH VIỆN')))
        c.drawCentredString(center_x, height - 13 * mm, _safe_text(data.get('PhongTiepNhan', data.get('Phong', 'PHÒNG KHÁM'))))

        # === STT ===
        stt_text = _safe_text(data.get('STT'))
        if stt_text:
            c.setFont(VIET_FONT_BOLD, 20)
            c.drawString(margin_left, height - 27 * mm, stt_text)

        # === QR Code + Mã Y Tế + Đối Tượng ===
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

        if qr_path and os.path.exists(qr_path):
            c.drawImage(ImageReader(qr_path), qr_x, qr_y, width=qr_size, height=qr_size,
                       preserveAspectRatio=True, mask='auto')

        # Mã Y Tế (trên Đối Tượng, bên phải)
        code_text = _safe_text(data.get('MaYTe'))
        if code_text:
            c.setFont(VIET_FONT, 13)
            c.drawRightString(width - margin_right, qr_y - 5 * mm, code_text)

        # Đối Tượng - Chia 2 cột đều, căn giữa
        doi_tuong_text = _safe_text(data.get('DoiTuong'))
        if doi_tuong_text:
            c.setFont(VIET_FONT_BOLD, 13)
            # Căn giữa trong vùng bên phải
            right_area_center = qr_x + (width - qr_x - margin_right) / 2
            c.drawCentredString(right_area_center, qr_y - 13 * mm, doi_tuong_text)

        # === Thông tin bệnh nhân: Họ tên - Năm sinh - Giới tính (dùng tab + wrap) ===
        name_y = height - 38 * mm
        ho_ten = _safe_text(data.get('HoTen'))
        nam_sinh = _safe_text(data.get('NamSinh'))
        gioi_tinh = _safe_text(data.get('GioiTinh'))

        c.setFont(VIET_FONT_BOLD, 13)
        c.drawString(margin_left, name_y, ho_ten)

        # Năm sinh và Giới tính căn phải + giữa
        c.setFont(VIET_FONT, 13)
        if nam_sinh:
            c.drawCentredString(center_x, name_y, nam_sinh)
        if gioi_tinh:
            c.drawRightString(width - margin_right, name_y, gioi_tinh)

        # Nếu tên quá dài sẽ wrap xuống dòng
        if stringWidth(ho_ten, VIET_FONT_BOLD, 13) > (width * 0.55):
            c.setFont(VIET_FONT_BOLD, 13)
            c.drawString(margin_left, name_y - 6*mm, ho_ten)

        # === Mã số thẻ BHYT ===
        bhyt_y = height - 49 * mm
        label = 'Mã số thẻ BHYT: '
        bhyt_value = _safe_text(data.get('SoBHYT'))

        c.setFont(VIET_FONT, 13)
        c.drawString(margin_left, bhyt_y, label)
        c.setFont(VIET_FONT_BOLD, 13)
        c.drawString(margin_left + stringWidth(label, VIET_FONT, 13), bhyt_y, bhyt_value)

        # === Địa chỉ ===
        address_y = height - 56 * mm
        address_style = ParagraphStyle(
            name='AddressStyle',
            fontName=VIET_FONT,
            fontSize=13,
            leading=15,
            alignment=0,  # left
        )
        address_value = _safe_text(data.get('DiaChi'))
        address_paragraph = Paragraph(f"Địa chỉ: <b>{address_value}</b>", address_style)
        address_width = width - margin_left - margin_right
        w, h = address_paragraph.wrap(address_width, 40 * mm)
        address_paragraph.drawOn(c, margin_left, address_y - h + 2)

        # === BH Từ ngày - Đến ngày ===
        date_y = height - 67 * mm
        bh_from_label = 'BH Từ ngày: '
        bh_to_label = 'BH Đến ngày: '
        bh_from_value = _safe_text(data.get('BHYT_Tu') or data.get('BHYTFrom') or data.get('BHYT_TuNgay'))
        bh_to_value = _safe_text(data.get('BHYT_Den') or data.get('BHYTTo') or data.get('BHYT_DenNgay'))

        c.setFont(VIET_FONT, 13)
        c.drawString(margin_left, date_y, bh_from_label)
        c.setFont(VIET_FONT_BOLD, 13)
        c.drawString(margin_left + stringWidth(bh_from_label, VIET_FONT, 13), date_y, bh_from_value)

        right_x = width / 2 + 6 * mm
        c.setFont(VIET_FONT, 13)
        c.drawString(right_x, date_y, bh_to_label)
        c.setFont(VIET_FONT_BOLD, 13)
        c.drawString(right_x + stringWidth(bh_to_label, VIET_FONT, 13), date_y, bh_to_value)

        c.showPage()
        c.save()

        # In file
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