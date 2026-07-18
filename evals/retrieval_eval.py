"""
Retrieval-quality evaluation harness for the Tomato RAG pipeline.

Exercises the same retrieval stack the app uses in production:
  - BGE-M3 (BAAI/bge-m3) dense (1024-d) + sparse lexical weights via FlagEmbedding
  - Qdrant named vectors with RRF fusion (run in-memory here, mirroring the prod config)
  - cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 reranker (retrieve top-10, rerank to top-5)

Corpus: the English-translated Aomori tomato manual PLUS five English regional tomato PDFs
(FAO IPM, AVRDC, Nepal AFACI/NARC/DOA) as distractors, chunked like prod (character windows).
This makes retrieval compete against a realistic, noisy multi-source index (~700 chunks).

Metric: each gold question carries a distinctive verbatim answer phrase that appears in the
manual's answer chunk. A "hit" = a retrieved chunk contains that phrase. We report Hit@1/3/5
and MRR for hybrid retrieval alone and after the cross-encoder rerank, isolating the reranker's
contribution.

Run (from repo root, with the backend venv active):
    python evals/retrieval_eval.py

Latest result (2026-07, 29 questions over 696 chunks):
    HYBRID    hit@1 58.6  hit@3 79.3  hit@5 86.2  MRR 0.699
    RERANKED  hit@1 72.4  hit@3 86.2  hit@5 93.1  MRR 0.810
    (reranking adds +13.8 pts on top-1 accuracy; 2/29 misses)
"""
import json
import re
import time
from pathlib import Path

import fitz  # PyMuPDF

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "data/translated/tomato_manual_en.md"
PDF_DIR = REPO / "data/pdfs"
DISTRACTORS = [
    "southasia_fao_tomato_ipm.pdf",
    "southasia_avrdc_tomato_practices.pdf",
    "nepal_afaci_vegetable_pests.pdf",
    "nepal_narc_tomato_diseases.pdf",
    "nepal_doa_tomato_book.pdf",
]
OUT = Path(__file__).resolve().parent / "results.json"

# Paraphrased question -> distinctive verbatim answer phrase (from the Aomori manual).
GOLD = [
    ("Once seedlings are set out in the field, what daytime and nighttime temperatures should I aim for?", "25-26°C"),
    ("How warm should the facility be right after I sow the seeds, to get them to sprout?", "28-30°C"),
    ("What acidity should the soil be at when choosing a field for planting?", "5.5-6.5"),
    ("When thinning, how many fruit should stay on the earliest clusters?", "3 fruits for 1st"),
    ("How much nitrogen goes into the base fertilizer for a standard plot?", "12-15kg of nitrogen"),
    ("How do I tell that a young plant's stem is the right length to graft?", "reaches around 10mm"),
    ("Why can the bottom of the fruit still rot even when there is plenty of lime in the ground?", "absorption can be inhibited by excess nitrogen"),
    ("What is physically going wrong inside a puffy, under-filled tomato?", "cavities between the pericarp and placenta"),
    ("What kind of blemishes does the gray fungus leave on the fruit skin?", "ghost spots on fruit surfaces"),
    ("What time of day is best for picking so the fruit stays in good shape?", "cool morning hours"),
    ("What are the different ways the skin can split as the fruit ripens?", "concentric cracks"),
    ("How does the cucumber mosaic virus spread between plants?", "transmitted by aphids"),
    ("How small do the holes in the screening need to be so the pollinating bees stay inside?", "mesh size of 4mm"),
    ("How do the leaves look when the plant is short on magnesium?", "Interveinal areas of middle and lower leaves"),
    ("What happens to the very top of the plant when the growing tip fails?", "tip suddenly becomes narrow"),
    ("How big should a young plant be before I move it into the field?", "30-35 cm in height"),
    ("How closely together should I space the plants?", "6-7 plants per tsubo"),
    ("How much water does each plant need on a hot, clear midsummer day?", "1-1.5 L per plant"),
    ("What resistance was bred into the Natsumi variety that the plain Momotaro 8 lacks?", "cf9 factor"),
    ("What is the highest temperature at which pollen can still form normally?", "below 32.5°C"),
    ("What makes the tops of the fruit stay green and hard instead of coloring?", "excessive nitrogen during fruit enlargement"),
    ("When in the season is thrips damage at its worst here?", "mid to late July"),
    ("How deep do I need to work the soil so the roots have enough room?", "minimum depth of 50cm"),
    ("What does the mold look like on the underside of an infected leaf?", "gray-brown velvety mold"),
    ("How fast can the water-mold blight kill a whole plant?", "as if scalded with hot water"),
    ("What is an obvious sign that stems are rotting from bacteria?", "emit a foul odor"),
    ("What electrical-conductivity target should the nursery soil be mixed to?", "EC of 0.7-0.8"),
    ("How much should I dial back the base fertilizer when the plants are grafted?", "reduced by 10-20%"),
    ("How big should the fruit be when I go in to thin them?", "OK sign"),
]


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def chunk_md(text, window=600, overlap=150):
    lines = text.split("\n")
    blocks, cur, title = [], [], "Preamble"

    def flush():
        if cur:
            body = "\n".join(cur).strip()
            if len(re.sub(r"\s", "", body)) >= 15:
                blocks.append((title, body))

    for ln in lines:
        if re.match(r"^#{2,4}\s", ln):
            flush()
            cur = [ln]
            title = re.sub(r"^#{2,4}\s", "", ln).strip()
        else:
            cur.append(ln)
    flush()

    out = []
    for _title, body in blocks:
        if len(body) <= window:
            out.append(("manual", body))
        else:
            i = 0
            while i < len(body):
                out.append(("manual", body[i:i + window]))
                i += window - overlap
    return out


def chunk_pdf(path, window=500, overlap=100, max_chunks=200):
    try:
        doc = fitz.open(path)
    except Exception:
        return []
    text = "\n".join(p.get_text() for p in doc)
    text = re.sub(r"\s+\n", "\n", text)
    out, i, name = [], 0, Path(path).stem
    while i < len(text) and len(out) < max_chunks:
        c = text[i:i + window]
        if len(re.sub(r"\s", "", c)) >= 40:
            out.append((name, c))
        i += window - overlap
    return out


def main():
    t0 = time.time()
    from FlagEmbedding import BGEM3FlagModel
    from sentence_transformers import CrossEncoder
    from qdrant_client import QdrantClient, models

    print("loading models...", flush=True)
    emb = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
    ce = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")

    chunks = chunk_md(MANUAL.read_text(encoding="utf-8"))
    n_manual = len(chunks)
    for d in DISTRACTORS:
        chunks += chunk_pdf(str(PDF_DIR / d))
    print(f"corpus: {len(chunks)} chunks ({n_manual} manual + {len(chunks) - n_manual} distractor)", flush=True)

    texts = [c[1] for c in chunks]
    enc = emb.encode(texts, batch_size=16, max_length=1024, return_dense=True, return_sparse=True)
    dense, sparse = enc["dense_vecs"], enc["lexical_weights"]

    client = QdrantClient(":memory:")
    client.create_collection(
        "t",
        vectors_config={"dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )
    pts = []
    for i, (src, body) in enumerate(chunks):
        lw = sparse[i]
        pts.append(models.PointStruct(
            id=i,
            vector={
                "dense": dense[i].tolist(),
                "sparse": models.SparseVector(
                    indices=[int(k) for k in lw.keys()],
                    values=[float(v) for v in lw.values()],
                ),
            },
            payload={"src": src, "text": body},
        ))
    for j in range(0, len(pts), 256):
        client.upsert("t", pts[j:j + 256])

    def retrieve(q, limit=10):
        qe = emb.encode([q], return_dense=True, return_sparse=True)
        dv = qe["dense_vecs"][0]
        qlw = qe["lexical_weights"][0]
        sv = models.SparseVector(indices=[int(k) for k in qlw.keys()], values=[float(v) for v in qlw.values()])
        r = client.query_points(
            "t",
            prefetch=[
                models.Prefetch(query=dv.tolist(), using="dense", limit=20),
                models.Prefetch(query=sv, using="sparse", limit=20),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [p.payload for p in r.points]

    def rank(cands, phrase):
        p = norm(phrase)
        for i, c in enumerate(cands):
            if p in norm(c["text"]):
                return i + 1
        return 0

    hyb = {"h1": 0, "h3": 0, "h5": 0, "mrr": 0.0}
    rrk = {"h1": 0, "h3": 0, "h5": 0, "mrr": 0.0}
    rows = []
    for q, phrase in GOLD:
        cands = retrieve(q, 10)
        rh = rank(cands[:5], phrase)
        scores = ce.predict([(q, c["text"]) for c in cands])
        reranked = [c for c, _ in sorted(zip(cands, scores), key=lambda x: -x[1])]
        rr = rank(reranked[:5], phrase)
        for r, d in ((rh, hyb), (rr, rrk)):
            if r == 1:
                d["h1"] += 1
            if r and r <= 3:
                d["h3"] += 1
            if r and r <= 5:
                d["h5"] += 1
            if r:
                d["mrr"] += 1.0 / r
        rows.append({"q": q, "phrase": phrase, "hybrid_rank": rh, "rerank_rank": rr})

    n = len(GOLD)
    pct = lambda x: round(100 * x / n, 1)
    summary = {
        "n_questions": n,
        "n_chunks": len(chunks),
        "n_manual": n_manual,
        "n_distractor": len(chunks) - n_manual,
        "hybrid": {"hit@1": pct(hyb["h1"]), "hit@3": pct(hyb["h3"]), "hit@5": pct(hyb["h5"]), "mrr": round(hyb["mrr"] / n, 3)},
        "reranked": {"hit@1": pct(rrk["h1"]), "hit@3": pct(rrk["h3"]), "hit@5": pct(rrk["h5"]), "mrr": round(rrk["mrr"] / n, 3)},
        "elapsed_s": round(time.time() - t0, 1),
        "rows": rows,
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2), flush=True)
    print("misses (after rerank):", [r["q"] for r in rows if r["rerank_rank"] == 0], flush=True)


if __name__ == "__main__":
    main()
