from __future__ import annotations


def flatten_report(value, prefix="", depth=0):
    lines = []
    if depth > 5:
        return ["{}: ...".format(prefix or "value")]
    if isinstance(value, dict):
        for key, item in value.items():
            label = "{} / {}".format(prefix, key) if prefix else str(key)
            if isinstance(item, (dict, list)):
                lines.extend(flatten_report(item, label, depth + 1))
            else:
                lines.append("{}: {}".format(label, item))
    elif isinstance(value, list):
        for index, item in enumerate(value[:40]):
            label = "{} [{}]".format(prefix, index)
            if isinstance(item, (dict, list)):
                lines.extend(flatten_report(item, label, depth + 1))
            else:
                lines.append("{}: {}".format(label, item))
    else:
        lines.append("{}: {}".format(prefix or "value", value))
    return lines


def pdf_escape(value):
    return str(value).replace("\\", "/").replace("(", "[").replace(")", "]").encode("latin-1", "replace").decode("latin-1")[:118]


def render_report_pdf(report):
    """Render a dependency-free PDF while preserving the existing wire format."""
    title = "DRIVEFORT AI V3 {} REPORT".format(str(report.get("level", "executive")).upper())
    lines = [title, "Generated: {}".format(report.get("generated_at", "")), ""]
    lines.extend(flatten_report(report))
    wrapped = []
    for line in lines[:360]:
        text = pdf_escape(line)
        while len(text) > 100:
            wrapped.append(text[:100])
            text = "  " + text[100:]
        wrapped.append(text)
    pages = [wrapped[index:index + 44] for index in range(0, max(1, len(wrapped)), 44)] or [[title]]

    font_id = 3
    page_ids = []
    objects = {}
    next_id = 4
    for page_number, page_lines in enumerate(pages, 1):
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        text_ops = ["BT", "/F1 15 Tf", "52 794 Td", "({}) Tj".format(pdf_escape(title)), "ET"]
        y = 770
        for line in page_lines:
            text_ops.extend(["BT", "/F1 9 Tf", "52 {} Td".format(y), "({}) Tj".format(pdf_escape(line)), "ET"])
            y -= 15
        text_ops.extend(["BT", "/F1 8 Tf", "510 28 Td", "(Page {} of {}) Tj".format(page_number, len(pages)), "ET"])
        stream = "\n".join(text_ops).encode("latin-1")
        objects[page_id] = "{} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 {} 0 R >> >> /Contents {} 0 R >> endobj\n".format(page_id, font_id, content_id).encode("latin-1")
        objects[content_id] = b"%d 0 obj << /Length %d >> stream\n" % (content_id, len(stream)) + stream + b"\nendstream endobj\n"

    kids = " ".join("{} 0 R".format(page_id) for page_id in page_ids)
    objects[1] = b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    objects[2] = "2 0 obj << /Type /Pages /Kids [{}] /Count {} >> endobj\n".format(kids, len(page_ids)).encode("latin-1")
    objects[font_id] = b"3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (max(objects) + 1)
    for object_id in range(1, max(objects) + 1):
        offsets[object_id] = len(pdf)
        pdf.extend(objects[object_id])
    xref = len(pdf)
    pdf.extend("xref\n0 {}\n0000000000 65535 f \n".format(len(offsets)).encode("latin-1"))
    for object_id in range(1, len(offsets)):
        pdf.extend("{:010d} 00000 n \n".format(offsets[object_id]).encode("latin-1"))
    pdf.extend("trailer << /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(len(offsets), xref).encode("latin-1"))
    return bytes(pdf)
