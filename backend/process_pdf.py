"""Script to process all PDF manuals and load into Qdrant vector database."""

import argparse
import re
import sys
import uuid
from pathlib import Path

import fitz  # PyMuPDF

from ingest_utils import (
    ensure_collection,
    delete_source,
    embed_and_upsert,
    register_in_postgres,
    clear_response_cache,
    chunk_text,
)

# Vegetable sidebar list that appears on odd pages of the PDF.
# This is an index/navigation element, not content, so we strip it.
VEGETABLE_SIDEBAR_ITEMS = [
    "キュウリ", "メロン", "スイカ", "小玉", "カボチャ", "ズッキーニ",
    "トマト", "ミニ", "ナス", "ベイナス", "シシトウ", "ピーマン",
    "パプリカ", "オクラ", "イチゴ", "スイート", "コーン", "エダマメ",
    "サヤエン", "ドウ", "サヤイン", "ゲン", "ソラマメ", "キャベツ",
    "ハクサイ", "ブロッコ", "リー", "カリフラ", "ワー", "レタス",
    "リーフレ", "タス", "ホウレン", "ソウ", "シュンギ", "ク",
    "チンゲン", "サイ", "コマツナ", "ナバナ類", "ミズナ", "アスパラ",
    "ガス", "ネギ", "タマネギ", "ニラ", "ニンニク", "モロヘイヤ",
    "食用ギク", "ミョウガ", "セリ", "切ミツバ", "ダイコン", "カブ",
    "ニンジン", "ゴボウ", "ジャガイモ", "サツマイモ", "サトイモ",
    "ナガイモ", "ツクネイモ", "山ウド", "クサソテツ", "（コゴミ）",
    "モミジガサ", "（シドケ）", "ミヤマイラクサ", "（アイコ）",
    "イヌドウナ", "（ホンナ）", "フキ", "ジュンサイ", "タラノメ",
    "ギョウジャ",
]


def clean_text(text):
    """Clean extracted PDF text by removing sidebar noise and normalizing."""
    lines = text.split("\n")
    cleaned_lines = []
    skip_sidebar = True  # Start by checking for sidebar

    for line in lines:
        stripped = line.strip()
        # Skip vegetable sidebar lines (short lines matching known items)
        if skip_sidebar and (stripped in VEGETABLE_SIDEBAR_ITEMS or stripped == ""):
            continue
        else:
            skip_sidebar = False

        # Remove standalone page numbers (e.g. "107", "108 トマト")
        if re.match(r"^\d{2,3}\s*$", stripped):
            continue
        if re.match(r"^\d{2,3}\s+トマト$", stripped):
            continue
        # Remove bare "トマト" line that follows page number in sidebar pages
        if stripped == "トマト" and not cleaned_lines:
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def table_to_text(table_data):
    """Convert a table (list of lists) to readable text."""
    rows = []
    for row in table_data:
        cells = [str(cell).strip() if cell else "" for cell in row]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def detect_section(text):
    """Detect section from text content.

    Patterns are ordered from most specific to least specific to avoid
    false positives (e.g. 耐病性 in a varieties table triggering
    'Disease Management').
    """
    text_lower = text.lower()
    # Ordered list — more specific patterns first
    patterns = [
        (r"(variet|品種|桃太郎)", "Varieties"),
        (r"(prun|剪定|整枝|芽かき|脇芽|摘芯)", "Pruning"),
        (r"(seedling|育苗)", "Seedling Care"),
        (r"(seed|播種|種まき)", "Seeding"),
        (r"(transplant|定植|植え付け)", "Transplanting"),
        (r"(fertiliz|肥料|施肥|追肥|元肥)", "Fertilization"),
        (r"(water|irrigation|灌水|水やり)", "Irrigation"),
        (r"(disease|病気|病害)", "Disease Management"),
        (r"(pest|害虫)", "Pest Control"),
        (r"(harvest|収穫)", "Harvesting"),
        (r"(temperature|温度|気温)", "Temperature"),
    ]

    for pattern, section in patterns:
        if re.search(pattern, text_lower):
            return section
    return "General"


def is_table_noise(chunk):
    """Detect garbled table-layout chunks (mostly single-character lines)."""
    lines = [line.strip() for line in chunk.split("\n") if line.strip()]
    if not lines:
        return True
    short_lines = sum(1 for line in lines if len(line) <= 3)
    sentences = chunk.count("。")
    return short_lines > len(lines) * 0.5 and sentences < 2


def ocr_page(page):
    """OCR a page using PyMuPDF's Tesseract integration."""
    tp = page.get_textpage_ocr(language="jpn", dpi=300, full=True)
    return page.get_text("text", textpage=tp)


def process_single_pdf(pdf_path):
    """Process a single PDF file and return (pages_content, all_chunks).

    Args:
        pdf_path: Path object to the PDF file.

    Returns:
        Tuple of (pages_content list, all_chunks list).
    """
    print(f"\n--- Processing: {pdf_path.name} ---")

    # Extract text from PDF
    doc = fitz.open(str(pdf_path))
    print(f"    Pages: {len(doc)}")

    pages_content = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")

        # If page has no usable text but has images, try OCR
        images = page.get_images()
        if len(text.strip()) < 20 and len(images) > 0:
            try:
                text = ocr_page(page)
                if text.strip():
                    print(f"    Page {page_num}: OCR extracted {len(text)} chars")
            except Exception as e:
                print(f"    Page {page_num}: OCR failed ({e})")

        text = clean_text(text)

        # Extract tables
        table_text = ""
        try:
            tables = page.find_tables()
            for table in tables:
                data = table.extract()
                if data:
                    table_text += "\n" + table_to_text(data)
        except Exception:
            pass

        combined = text
        if table_text.strip():
            combined += "\n\n" + table_text.strip()

        if combined.strip():
            pages_content.append({
                "page": page_num,
                "text": combined.strip()
            })

    doc.close()
    print(f"    Extracted text from {len(pages_content)} pages")

    # Chunk the content
    all_chunks = []
    for page_data in pages_content:
        page_chunks = chunk_text(page_data["text"])
        for idx, chunk in enumerate(page_chunks):
            if len(chunk) > 50 and not is_table_noise(chunk):
                all_chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": chunk,
                    "page": page_data["page"],
                    "section": detect_section(chunk),
                    "timestamp": None,
                    "chunk_index": idx,
                })

    print(f"    Created {len(all_chunks)} chunks")
    return pages_content, all_chunks


def main():
    parser = argparse.ArgumentParser(description="Process PDF manuals for Qdrant ingestion")
    parser.add_argument(
        "--region", default="global",
        choices=["global", "japan", "nepal", "vietnam", "indonesia", "philippines"],
        help="Region tag for these documents (default: global)",
    )
    parser.add_argument(
        "--file", default=None,
        help="Process a single specific PDF file instead of all PDFs in data/pdfs/",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Tomato RAG Chatbot - PDF Processing (Multi-PDF)")
    print(f"Region: {args.region}")
    print("=" * 60)

    # Find PDFs
    print("\n[1/4] Scanning for PDF files...")
    pdf_dir = Path(__file__).parent.parent / "data" / "pdfs"
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = pdf_dir / target
        if not target.exists():
            print(f"ERROR: File not found: {target}")
            sys.exit(1)
        pdf_files = [target]
    else:
        pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        print("ERROR: No PDF files found in data/pdfs/")
        sys.exit(1)

    print(f"      Found {len(pdf_files)} PDF(s):")
    for pdf_path in pdf_files:
        print(f"        - {pdf_path.name}")

    # Ensure collection exists (non-destructive)
    print("\n[2/4] Preparing Qdrant collection...")
    ensure_collection()

    # Process each PDF
    print("\n[3/4] Processing PDFs...")
    summary = []
    for pdf_path in pdf_files:
        pages_content, all_chunks = process_single_pdf(pdf_path)

        if not all_chunks:
            print(f"    WARNING: No valid chunks from {pdf_path.name}, skipping")
            continue

        # Delete existing vectors for this source, then upsert
        delete_source(pdf_path.name)
        embed_and_upsert(all_chunks, source_type="manual", source_name=pdf_path.name, region=args.region)

        # Register document in PostgreSQL
        register_in_postgres(pdf_path.name, str(pdf_path), len(pages_content), len(all_chunks), region=args.region)

        summary.append({
            "name": pdf_path.name,
            "pages": len(pages_content),
            "chunks": len(all_chunks),
        })

    # Clear stale cached responses (once after all PDFs)
    print("\n[4/4] Clearing response cache...")
    clear_response_cache()

    print(f"\n{'=' * 60}")
    print("Processing Complete!")
    print(f"{'=' * 60}")
    total_chunks = 0
    for item in summary:
        print(f"  {item['name']}: {item['pages']} pages, {item['chunks']} chunks")
        total_chunks += item["chunks"]
    print(f"\n  Total: {len(summary)} PDF(s), {total_chunks} chunks")
    print(f"\nYou can now start the chatbot!")


if __name__ == "__main__":
    main()
