# Retrieval Evaluation

A reproducible retrieval-quality benchmark for the Tomato RAG pipeline. It exercises the
same stack the app serves with — **BGE-M3 dense + sparse embeddings, Qdrant RRF fusion,
and a cross-encoder reranker** — and measures how often the chunk containing the answer is
actually retrieved.

## Method

- **Corpus:** the English-translated Aomori tomato manual plus five English regional tomato
  PDFs (FAO IPM, AVRDC, Nepal AFACI / NARC / DOA) as distractors, character-chunked like
  production. ~700 chunks total, so retrieval competes against a realistic, noisy index.
- **Questions:** 29 paraphrased, natural-language questions that deliberately do *not* reuse
  the answer's wording (no lexical gimme).
- **Gold / metric:** each question carries a distinctive verbatim answer phrase present in the
  manual's answer chunk. A **hit** = a retrieved chunk contains that phrase. We report
  `Hit@1/3/5` and `MRR` for hybrid retrieval alone and after the cross-encoder rerank, to
  isolate the reranker's contribution.

## Run

```bash
# from repo root, with the backend venv active
python evals/retrieval_eval.py
```

Writes `evals/results.json` and prints a summary. First run downloads the BGE-M3 (~2.3 GB)
and reranker weights.

## Latest result (2026-07, 29 questions over 696 chunks)

| stage | Hit@1 | Hit@3 | Hit@5 | MRR |
|-------|-------|-------|-------|-----|
| Hybrid (BGE-M3 + RRF) | 58.6% | 79.3% | 86.2% | 0.699 |
| + Cross-encoder rerank | **72.4%** | 86.2% | **93.1%** | **0.810** |

Reranking adds **+13.8 pts** on top-1 accuracy. 2 of 29 questions miss after rerank, which is
expected on a noisy multi-source corpus and confirms the benchmark isn't trivially saturated.
