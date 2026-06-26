from datetime import datetime
import os
import sys

from reportlab.lib.pagesizes import A4
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
    """Tạo phiếu tiếp nhận trên giấy A4 portrait, đặt nội dung nhỏ ở góc trái trên để in phù hợp với máy in."""
    try:
        pdf_path = _build_pdf_path(data)

        width, height = A4
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.setTitle('Phiếu tiếp nhận')

        # Khu vực nội dung nhỏ ở góc trái trên giấy A4
        margin_left = 8 * mm
        margin_top = 8 * mm
        content_width = 95 * mm
        content_height = 118 * mm
        content_x = margin_left
        content_y = height - margin_top - content_height

        qr_size = 24 * mm
        qr_x = content_x + content_width - qr_size - 3 * mm
        qr_y = content_y + content_height - qr_size - 2 * mm

        c.setFont(VIET_FONT_BOLD, 10)
        c.drawString(content_x + 2 * mm, content_y + content_height - 6 * mm, _safe_text(data.get('TenBenhVien', 'BỆNH VIỆN')))
        c.drawString(content_x + 2 * mm, content_y + content_height - 11 * mm, _safe_text(data.get('PhongTiepNhan', data.get('Phong', 'PHÒNG KHÁM'))))

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

        stt_text = _safe_text(data.get('STT'))
        if stt_text:
            c.setFont(VIET_FONT_BOLD, 16)
            c.drawString(content_x + 2 * mm, content_y + content_height - 22 * mm, f"{stt_text}")

        if qr_path and os.path.exists(qr_path):
            c.drawImage(ImageReader(qr_path), qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto')

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
                fontSize=7.5,
                leading=9,
                alignment=1,
            )
            qr_text_p = Paragraph("<br/>".join(qr_labels), qr_text_style)
            qr_box_width = qr_size + 4 * mm
            _, ql_h = qr_text_p.wrap(qr_box_width, 18 * mm)
            qr_text_p.drawOn(c, qr_x + (qr_size / 2) - (qr_box_width / 2), qr_y - ql_h - 0 * mm)

        name_y = content_y + content_height - 40 * mm
        c.setFont(VIET_FONT_BOLD, 9.5)
        c.drawString(content_x + 2 * mm, name_y, _safe_text(data.get('HoTen')))
        c.drawString(content_x + 64 * mm, name_y, _safe_text(data.get('NamSinh')))
        c.drawString(content_x + 80 * mm, name_y, _safe_text(data.get('GioiTinh')))

        bhyt_y = name_y - 5.5 * mm
        c.setFont(VIET_FONT, 9.5)
        label = 'Mã số thẻ BHYT: '
        bhyt_value = _safe_text(data.get('SoBHYT'))
        c.drawString(content_x + 2 * mm, bhyt_y, label)
        c.setFont(VIET_FONT_BOLD, 9.5)
        c.drawString(content_x + 2 * mm + stringWidth(label, VIET_FONT, 9.5), bhyt_y, bhyt_value)

        address_y = bhyt_y - 2.2 * mm
        address_value = _safe_text(data.get('DiaChi'))
        address_style = ParagraphStyle(
            name='AddressStyle',
            fontName=VIET_FONT,
            fontSize=9.5,
        )
        address_paragraph = Paragraph(f"Địa chỉ: <b>{address_value}</b>", address_style)
        address_width = content_width - 4 * mm
        _, address_h = address_paragraph.wrap(address_width, 20 * mm)
        address_paragraph.drawOn(c, content_x + 2 * mm, address_y - address_h + 1)

        bh_from_label = 'BH Từ ngày: '
        bh_to_label = 'BH Đến ngày: '
        bh_from_value = _safe_text(data.get('BHYT_Tu') or data.get('BHYTFrom') or data.get('BHYT_TuNgay'))
        bh_to_value = _safe_text(data.get('BHYT_Den') or data.get('BHYTTo') or data.get('BHYT_DenNgay'))

        date_y = address_y - address_h - 3 * mm
        c.setFont(VIET_FONT_BOLD, 9.5)
        c.drawString(content_x + 2 * mm, date_y, bh_from_label)
        c.drawString(content_x + 2 * mm + stringWidth(bh_from_label, VIET_FONT_BOLD, 9.5), date_y, bh_from_value)
        c.drawString(content_x + 50 * mm, date_y, bh_to_label)
        c.drawString(content_x + 50 * mm + stringWidth(bh_to_label, VIET_FONT_BOLD, 9.5), date_y, bh_to_value)

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