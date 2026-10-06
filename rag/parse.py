"""Parse guideline PDFs into per-page text, keeping page numbers for citation.

Run:  python -m rag.parse    (prints a summary of every PDF in docs/guidelines/)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from copilot.config import GUIDELINES_DIR


@dataclass
class Page:
    file: str  # the PDF's filename, used as the citation's document id
    page: int  # 1-indexed, matching what a human would see in a PDF viewer
    text: str


def load_pdf(path: Path) -> list[Page]:
    reader = PdfReader(str(path))
    pages = []
    for i, pdf_page in enumerate(reader.pages, start=1):
        text = (pdf_page.extract_text() or "").strip()
        if text:
            pages.append(Page(file=path.name, page=i, text=text))
    return pages


def load_all(guidelines_dir: Path = GUIDELINES_DIR) -> list[Page]:
    pages: list[Page] = []
    for pdf_path in sorted(guidelines_dir.glob("*.pdf")):
        pages.extend(load_pdf(pdf_path))
    return pages


if __name__ == "__main__":
    pages = load_all()
    by_file: dict[str, int] = {}
    for p in pages:
        by_file[p.file] = by_file.get(p.file, 0) + 1
    for file, n in by_file.items():
        chars = sum(len(p.text) for p in pages if p.file == file)
        print(f"{file}: {n} pages with text, {chars} characters")
    print(f"total: {len(pages)} pages across {len(by_file)} documents")
