"""Original structured office-file authoring and bounded local PDF operations."""
import io
import math
import re
import secrets
from pathlib import Path
from xml.sax.saxutils import escape

from spark_maintenance import atomic_write
from spark_productivity import WorkbenchError, text, identity

MIMES = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
         "pdf": "application/pdf"}


class Office:
    def __init__(self, productivity):
        self.store = productivity

    def _folder(self, project):
        self.store.skills._file(project)
        folder = self.store.root / project / "artifacts"
        if any(p.is_symlink() for p in (self.store.root, folder.parent, folder)):
            raise WorkbenchError("Linked artifact storage is not allowed.")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def save(self, project, title, extension, blob):
        if extension not in MIMES or not isinstance(blob, bytes) or not 0 < len(blob) <= 10000000:
            raise WorkbenchError("Invalid artifact or output exceeds 10 MB.")
        title = text(title, 100)
        item_id = secrets.token_hex(12)
        filename = (re.sub(r"[^\w -]", "", title).strip()[:70] or "Spark document")+"."+extension
        item = {"id": item_id, "title": title, "extension": extension, "name": filename, "bytes": len(blob)}
        path = self._folder(project) / (item_id+"."+extension)
        with self.store.lock, self.store._db(project) as db:
            # Check quotas before writing; failed metadata saves remove the orphan.
            try:
                self.store._put(db, "artifact", item)
                atomic_write(path, blob)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        return item

    def list(self, project):
        with self.store.lock, self.store._db(project) as db:
            return self.store._all(db, "artifact")

    def download(self, project, item_id):
        with self.store.lock, self.store._db(project) as db:
            item = self.store._get(db, "artifact", item_id)
        if item["extension"] not in MIMES:
            raise WorkbenchError("Invalid stored artifact format.")
        path = self._folder(project) / (identity(item_id)+"."+item["extension"])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 10000000:
            raise WorkbenchError("Artifact is unavailable or exceeds its limit.")
        return {"name": item["name"], "mime": MIMES[item["extension"]], "data": path.read_bytes()}

    @staticmethod
    def _sections(spec):
        if not isinstance(spec, dict) or set(spec)-{"title", "sections"} or "sections" not in spec:
            raise WorkbenchError("Document requires title and sections.")
        title = text(spec.get("title"), 100)
        sections = spec["sections"]
        if not isinstance(sections, list) or not 1 <= len(sections) <= 40:
            raise WorkbenchError("Use 1–40 document sections or slides.")
        clean = []
        for item in sections:
            if not isinstance(item, dict) or set(item)-{"heading", "text", "bullets", "notes"}:
                raise WorkbenchError("Invalid document section.")
            heading = text(item.get("heading", "Section"), 160)
            body, notes, bullets = item.get("text", ""), item.get("notes", ""), item.get("bullets", [])
            if (not isinstance(body, str) or len(body) > 8000 or not isinstance(notes, str) or len(notes) > 4000
                    or not isinstance(bullets, list) or len(bullets) > 20):
                raise WorkbenchError("Document section exceeds its size limit.")
            clean.append({"heading": heading, "text": body, "notes": notes, "bullets": [text(b, 500) for b in bullets]})
        return title, clean

    def create(self, project, extension, spec):
        if extension not in MIMES:
            raise WorkbenchError("Choose docx, xlsx, pptx or pdf.")
        stream = io.BytesIO()
        if extension == "xlsx":
            title = self._spreadsheet(spec, stream)
        else:
            title, sections = self._sections(spec)
            if extension == "docx":
                from docx import Document
                doc = Document()
                doc.add_heading(title, 0)
                for section in sections:
                    doc.add_heading(section["heading"], 1)
                    if section["text"]: doc.add_paragraph(section["text"])
                    for bullet in section["bullets"]: doc.add_paragraph(bullet, style="List Bullet")
                doc.save(stream)
            elif extension == "pptx":
                from pptx import Presentation
                deck = Presentation()
                slide = deck.slides.add_slide(deck.slide_layouts[0])
                slide.shapes.title.text = title
                for section in sections:
                    slide = deck.slides.add_slide(deck.slide_layouts[1])
                    slide.shapes.title.text = section["heading"]
                    frame = slide.placeholders[1].text_frame
                    frame.clear()
                    lines = ([section["text"]] if section["text"] else [])+section["bullets"]
                    for index, line in enumerate(lines):
                        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                        paragraph.text = line
                    slide.notes_slide.notes_text_frame.text = section["notes"]
                deck.save(stream)
            else:
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet
                styles = getSampleStyleSheet()
                story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 12)]
                for section in sections:
                    story.append(Paragraph(escape(section["heading"]), styles["Heading2"]))
                    for line in section["text"].splitlines()+["• "+b for b in section["bullets"]]:
                        story.append(Paragraph(escape(line), styles["BodyText"]))
                    story.append(Spacer(1, 8))
                SimpleDocTemplate(stream, title=title).build(story)
        return self.save(project, title, extension, stream.getvalue())

    @staticmethod
    def _spreadsheet(spec, stream):
        from openpyxl import Workbook
        from openpyxl.chart import BarChart, Reference
        from openpyxl.styles import Font, PatternFill
        if not isinstance(spec, dict) or set(spec) != {"title", "sheets"}:
            raise WorkbenchError("Spreadsheet requires title and sheets.")
        title = text(spec["title"], 100)
        sheets = spec["sheets"]
        if not isinstance(sheets, list) or not 1 <= len(sheets) <= 10:
            raise WorkbenchError("Use 1–10 worksheets.")
        book = Workbook()
        book.remove(book.active)
        names = set()
        for sheet in sheets:
            if not isinstance(sheet, dict) or set(sheet)-{"name", "rows", "chart"}:
                raise WorkbenchError("Invalid worksheet.")
            name = text(sheet.get("name"), 31)
            if re.search(r"[\\/*?:\[\]]", name) or name.casefold() in names:
                raise WorkbenchError("Worksheet names must be valid and unique.")
            names.add(name.casefold())
            rows = sheet.get("rows")
            if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
                raise WorkbenchError("Use 1–1000 rows per worksheet.")
            tab = book.create_sheet(name)
            for index, row in enumerate(rows, 1):
                if not isinstance(row, list) or not 1 <= len(row) <= 30:
                    raise WorkbenchError("Use 1–30 cells per row.")
                for column, value in enumerate(row, 1):
                    cell = tab.cell(index, column)
                    if isinstance(value, dict) and set(value) == {"formula"}:
                        formula = value["formula"]
                        if not isinstance(formula, str) or not re.fullmatch(r"=(?:SUM|AVERAGE|MIN|MAX|COUNT)\([A-Z]{1,2}[1-9][0-9]{0,3}:[A-Z]{1,2}[1-9][0-9]{0,3}\)", formula):
                            raise WorkbenchError("Only explicit local SUM/AVERAGE/MIN/MAX/COUNT range formulas are supported.")
                        cell.value = formula
                    elif value is None or type(value) in (bool, int, float):
                        if isinstance(value, (int, float)) and (abs(value) > 1e15 or not math.isfinite(value)):
                            raise WorkbenchError("Spreadsheet number is outside its finite range.")
                        cell.value = value
                    elif isinstance(value, str) and len(value) <= 4000:
                        cell.value, cell.data_type = value, "s"
                    else: raise WorkbenchError("Invalid spreadsheet cell value.")
            for cell in tab[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="164E63")
            tab.freeze_panes = "A2"
            if sheet.get("chart") is True and len(rows) > 1 and tab.max_column > 1:
                chart = BarChart()
                chart.add_data(Reference(tab, min_col=2, max_col=tab.max_column, min_row=1, max_row=len(rows)), titles_from_data=True)
                chart.set_categories(Reference(tab, min_col=1, min_row=2, max_row=len(rows)))
                tab.add_chart(chart, "D2")
        book.save(stream)
        return title

    def import_pdf(self, project, name, data):
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        if not isinstance(data, bytes) or not 0 < len(data) <= 2000000 or not data.startswith(b"%PDF-"):
            raise WorkbenchError("Select a PDF of at most 2 MB.")
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 200:
                raise WorkbenchError("PDF must be unencrypted and contain 1–200 pages.")
        except PdfReadError:
            raise WorkbenchError("Selected PDF is malformed or unreadable.") from None
        return self.save(project, Path(text(name, 100)).stem, "pdf", data)

    def pdf(self, project, item_ids, pages, operation):
        from pypdf import PdfReader, PdfWriter
        if not isinstance(item_ids, list) or not 1 <= len(item_ids) <= 10:
            raise WorkbenchError("Select 1–10 PDF artifact IDs.")
        if operation not in ("merge", "extract", "text"):
            raise WorkbenchError("Choose merge, extract or text.")
        if operation != "merge" and len(item_ids) != 1:
            raise WorkbenchError("Page extraction uses one source PDF.")
        if not isinstance(pages, list) or len(pages) > 200 or any(type(p) is not int or p < 1 for p in pages):
            raise WorkbenchError("Page numbers must be positive integers, up to 200 pages.")
        writer, extracted, total = PdfWriter(), [], 0
        for item_id in item_ids:
            artifact = self.download(project, item_id)
            if artifact["mime"] != MIMES["pdf"]:
                raise WorkbenchError("Selected artifact is not a PDF.")
            reader = PdfReader(io.BytesIO(artifact["data"]))
            chosen = list(range(1, len(reader.pages)+1)) if not pages or operation == "merge" else pages
            if any(p > len(reader.pages) for p in chosen) or total+len(chosen) > 200:
                raise WorkbenchError("Invalid page range or output exceeds 200 pages.")
            total += len(chosen)
            for number in chosen:
                page = reader.pages[number-1]
                if operation == "text": extracted.append((page.extract_text() or "")[:20000])
                else: writer.add_page(page)
        if operation == "text": return {"text": "\n\n".join(extracted)[:100000], "pages": total}
        stream = io.BytesIO()
        writer.write(stream)
        return self.save(project, "Merged PDF" if operation == "merge" else "Extracted pages", "pdf", stream.getvalue())
