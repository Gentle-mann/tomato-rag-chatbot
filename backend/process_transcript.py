"""Script to process a YouTube video transcript PDF and load into Qdrant."""

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

# Timestamp regex — matches "0:00", "1:05", "12:34", "1:23:45" etc.
TIMESTAMP_RE = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s*$")

# Section heading regex — matches "## Section title"
SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$")


def detect_section(text):
    """Detect section from transcript text content.

    Patterns are ordered from most specific to least specific.
    """
    text_lower = text.lower()
    # Ordered list — more specific patterns first
    patterns = [
        (r"(variet|品種)", "Varieties"),
        (r"(prun|剪定|整枝|芽かき|脇芽|摘芯)", "Pruning"),
        (r"(裂果|割れ)", "Fruit Cracking"),
        (r"(光合成|日射)", "Photosynthesis"),
        (r"(着果|受粉)", "Fruiting"),
        (r"(seedling|育苗)", "Seedling Care"),
        (r"(seed|播種|種まき)", "Seeding"),
        (r"(transplant|定植|植え付け)", "Transplanting"),
        (r"(fertiliz|肥料|施肥|追肥|元肥)", "Fertilization"),
        (r"(water|irrigation|灌水|水やり)", "Irrigation"),
        (r"(disease|病気|病害)", "Disease Management"),
        (r"(pest|害虫)", "Pest Control"),
        (r"(harvest|収穫)", "Harvesting"),
        (r"(temperature|温度|気温|高温|低温)", "Temperature"),
        (r"(生育|成長|生長)", "Growth"),
    ]

    for pattern, section in patterns:
        if re.search(pattern, text_lower):
            return section
    return "General"


def extract_transcript(pdf_path):
    """Extract text from a transcript PDF, preserving timestamps and sections.

    Returns a list of segments, each with:
        text (str): The spoken text (timestamps stripped).
        timestamp (str): The nearest preceding timestamp (e.g. "1:05").
        section (str): The current ## section heading, or None.
        page (int): PDF page number.
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    segments = []           # list of {text, timestamp, section, page}
    current_timestamp = "0:00"
    current_section = None
    current_text_lines = []
    current_page = 1

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        lines = text.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for timestamp
            ts_match = TIMESTAMP_RE.match(stripped)
            if ts_match:
                # Flush accumulated text as a segment
                if current_text_lines:
                    segments.append({
                        "text": " ".join(current_text_lines),
                        "timestamp": current_timestamp,
                        "section": current_section,
                        "page": current_page,
                    })
                    current_text_lines = []
                current_timestamp = ts_match.group(1)
                current_page = page_num
                continue

            # Check for section heading
            sec_match = SECTION_HEADING_RE.match(stripped)
            if sec_match:
                # Flush accumulated text before new section
                if current_text_lines:
                    segments.append({
                        "text": " ".join(current_text_lines),
                        "timestamp": current_timestamp,
                        "section": current_section,
                        "page": current_page,
                    })
                    current_text_lines = []
                current_section = sec_match.group(1)
                continue

            # Regular text line
            current_text_lines.append(stripped)

    # Flush remaining text
    if current_text_lines:
        segments.append({
            "text": " ".join(current_text_lines),
            "timestamp": current_timestamp,
            "section": current_section,
            "page": current_page,
        })

    doc.close()
    return segments, total_pages


def segments_to_chunks(segments):
    """Merge small consecutive segments and chunk the result.

    We first concatenate segments into section-level blocks, then apply
    character-based chunking. Each chunk inherits the timestamp of its
    first contributing segment.
    """
    if not segments:
        return []

    # Group segments into blocks by section heading
    blocks = []
    current_block_text = ""
    current_block_ts = segments[0]["timestamp"]
    current_block_section = segments[0]["section"]
    current_block_page = segments[0]["page"]
    ts_map = []  # [(char_offset, timestamp)] for timestamp assignment

    for seg in segments:
        # Start a new block on section change
        if seg["section"] != current_block_section and current_block_text:
            blocks.append({
                "text": current_block_text.strip(),
                "timestamp": current_block_ts,
                "section": current_block_section or "General",
                "page": current_block_page,
                "ts_map": list(ts_map),
            })
            current_block_text = ""
            current_block_ts = seg["timestamp"]
            current_block_section = seg["section"]
            current_block_page = seg["page"]
            ts_map = []

        # Record timestamp offset for this segment's start
        ts_map.append((len(current_block_text), seg["timestamp"]))
        current_block_text += seg["text"] + " "

    # Flush last block
    if current_block_text.strip():
        blocks.append({
            "text": current_block_text.strip(),
            "timestamp": current_block_ts,
            "section": current_block_section or "General",
            "page": current_block_page,
            "ts_map": list(ts_map),
        })

    # Chunk each block
    all_chunks = []
    for block in blocks:
        text_chunks = chunk_text(block["text"])
        char_offset = 0

        for idx, chunk in enumerate(text_chunks):
            if len(chunk) < 30:
                char_offset += len(chunk)
                continue

            # Find the nearest preceding timestamp for this chunk
            chunk_ts = block["timestamp"]
            for offset, ts in block["ts_map"]:
                if offset <= char_offset:
                    chunk_ts = ts
                else:
                    break

            section = block["section"]
            # Fallback to keyword detection if section is generic
            if section == "General":
                section = detect_section(chunk)

            all_chunks.append({
                "id": str(uuid.uuid4()),
                "text": chunk,
                "page": block["page"],
                "section": section,
                "timestamp": chunk_ts,
            })

            char_offset += len(chunk)

    return all_chunks


def main():
    parser = argparse.ArgumentParser(description="Process video transcript for Qdrant ingestion")
    parser.add_argument(
        "--region", default="global",
        choices=["global", "japan", "nepal", "vietnam", "indonesia"],
        help="Region tag for this transcript (default: global)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Tomato RAG Chatbot - Transcript Processing")
    print(f"Region: {args.region}")
    print("=" * 60)

    # Find transcript PDF
    print("\n[1/5] Loading transcript PDF...")
    transcript_dir = Path(__file__).parent.parent / "data" / "transcripts"

    if not transcript_dir.exists():
        print(f"ERROR: Directory not found: {transcript_dir}")
        print("       Create data/transcripts/ and place transcript PDFs there.")
        sys.exit(1)

    pdf_files = list(transcript_dir.glob("*.pdf"))
    if not pdf_files:
        print("ERROR: No PDF files found in data/transcripts/")
        sys.exit(1)

    pdf_path = pdf_files[0]
    print(f"      Found: {pdf_path.name}")

    # Extract segments
    print("\n[2/5] Extracting transcript segments...")
    segments, total_pages = extract_transcript(pdf_path)
    print(f"      Pages: {total_pages}")
    print(f"      Segments extracted: {len(segments)}")

    if not segments:
        print("ERROR: No text segments found in transcript")
        sys.exit(1)

    # Chunk segments
    print("\n[3/5] Chunking content...")
    all_chunks = segments_to_chunks(segments)
    print(f"      Created {len(all_chunks)} chunks")

    # Ensure collection exists
    print("\n[4/5] Preparing Qdrant collection...")
    ensure_collection()

    # Delete existing vectors for this source, then upsert
    delete_source(pdf_path.name)

    print("\n[5/5] Generating embeddings and uploading to Qdrant...")
    embed_and_upsert(all_chunks, source_type="transcript", source_name=pdf_path.name, region=args.region)

    # Register document in PostgreSQL
    print("\nRegistering document in database...")
    register_in_postgres(pdf_path.name, str(pdf_path), total_pages, len(all_chunks), region=args.region)

    # Clear stale cached responses
    print("\nClearing response cache...")
    clear_response_cache()

    print(f"\n{'=' * 60}")
    print("Processing Complete!")
    print(f"{'=' * 60}")
    print(f"  Transcript: {pdf_path.name}")
    print(f"  Pages: {total_pages}")
    print(f"  Segments: {len(segments)}")
    print(f"  Chunks created: {len(all_chunks)}")
    print(f"\nYou can now start the chatbot!")


if __name__ == "__main__":
    main()
