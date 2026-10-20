import io

from django.template import Context, Template
from django.template.loader import render_to_string
from pypdf import PdfReader, PdfWriter
from xhtml2pdf import pisa

BASE_CSS = """
@page { size: A4; margin: 2cm 2cm 2.2cm 2cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #1f2937; }
h1, h2, h3 { color: #0f3d5e; margin: 0 0 6pt 0; }
table { width: 100%; border-collapse: collapse; }
td, th { padding: 4pt 6pt; }
.muted { color: #6b7280; }
.right { text-align: right; }
.border td, .border th { border: 0.5pt solid #d1d5db; }
.header { border-bottom: 1.5pt solid #0f3d5e; margin-bottom: 14pt; padding-bottom: 6pt; }
"""


def html_to_pdf(html: str) -> bytes:
    out = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=out, encoding="utf-8")
    if result.err:
        raise RuntimeError("PDF generation failed")
    return out.getvalue()


def render_template_string(source: str, context: dict) -> str:
    return Template(source).render(Context(context))


def letter_pdf(body_html: str, context: dict) -> bytes:
    body = render_template_string(body_html, context)
    html = render_to_string("pdf/letter.html", {**context, "body": body, "css": BASE_CSS})
    return html_to_pdf(html)


def encrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=None, algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
