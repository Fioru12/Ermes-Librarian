# Measured, not claimed

> Moved here from the README so the front page stays short. Nothing was removed: every number, every table and
> the list of things that do not work are below, unchanged. The embedding-model comparison of 16 October 2026 is
> in [RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md).

Every number below was produced by a command in this repository, and every
command can be re-run by anyone who clones it. The unflattering results are
here too — they are the reason several features are switched off.

**Retrieval quality** — 52 questions over a demo corpus: 16 direct, 20
paraphrased, 16 with no answer in the corpus (several of them lexical traps
that share words with a real passage). Recall@3 for the first two, correct
refusals for the third. Left: the 16-passage demo corpus. Right: the same
corpus with 388 unrelated passages of real prose around it
(`python evaluation/scale_check.py --sizes 0,97`, add `--semantic` /
`--verify`):

| | Shipped default | Semantic search | Evidence verification | Semantic + verification |
|---|---|---|---|---|
| Direct | 1.000 / 0.938 | 1.000 / 1.000 | 1.000 / 0.938 | 1.000 / 0.625 |
| Paraphrased | 0.450 / 0.250 | **0.900 / 0.500** | 0.350 / 0.200 | 0.350 / 0.050 |
| Correct refusals | 0.375 / 0.062 | 0.000 / 0.000 | **1.000 / 1.000** | 1.000 / 1.000 |

Until 25 September 2026 this table read "1.000" for refusals. That number
came from **three** questions, so one error was worth 33 points; on sixteen
the shipped default refuses correctly 6 times, and with a large archive
around it once. Evidence verification (a local model checks each cited
passage) is the only configuration that keeps refusals at 16/16 at both
sizes without losing direct questions. Semantic + verification refuses just
as well, but on the large archive it also rejects correct passages, so its
perfect refusal score is partly refusing everything. Verification uses
`qwen3.5:4b`; the semantic + verification run hit 3 model errors out of
several hundred calls.

**Same corpus, RAGAS definitions** (`python evaluation/ragas_report.py`), so the
numbers can sit next to other projects' — shipped default, k=3:

| context_precision | context_recall | MRR | abstention precision | false abstention |
|---|---|---|---|---|
| 0.653 | 0.694 | 0.653 | 0.375 | 0.167 |

Direct questions: precision 0.938 / recall 1.000 (one question finds its citation at rank 2, not 1). Paraphrased: 0.425 / 0.450. Faithfulness and answer relevancy are *not* reported: in the default evidence-only mode there is no generated answer to judge, and reporting them would require a generator plus a judge model — a different measurement, kept separate rather than decorated in.

**Speed on an office-sized archive** (`python evaluation/archive_scale.py`):

| Passages | Indexing | Typical search | Worst-case search |
|---|---|---|---|
| 10.000 | 15,1 s | 1,9 ms | 58 ms |
| 50.000 | 79,6 s | **4,6 ms** | **308 ms** |

The worst case was 3,2 s at 50.000 passages until 25 September 2026: every
row matching a common word was scored in Python. Candidates are now capped by
the database's own full-text rank (`bm25()` / `ts_rank`) — ten times faster,
and the retrieval-quality numbers above are unchanged.

### What does not work, stated here rather than discovered later

- **Without a model, the shipped default does not reliably say "I don't
  know".** 6 correct refusals out of 16 on the demo corpus, 1 out of 16 with a
  large archive around it: any single shared term is enough to be cited as
  evidence. Evidence verification brings it to 16/16 at both sizes, but needs
  a model running, so it is off by default. For libraries beyond a demo
  corpus, run the [verified profile](#verified-profile-ollama-required), which
  makes the model a declared requirement.
- **The neural reranker is disabled**, because measuring it showed it makes
  every configuration worse — the previously shipped default was the worst of
  the five.
- **Paraphrases are the weak spot of every configuration that refuses
  correctly** (0.200–0.450). Semantic search finds twice as many but never
  refuses; with verification on top, the 4B verifier rejects correct passages
  too. A stronger verifier model is the next thing to measure.
- **Semantic search is disabled**, because it doubles paraphrase recall and
  destroys abstention. Four score-based signals were measured looking for a
  cutoff that keeps both; none separates the two populations, and the analysis
  is written up rather than glossed over.
- **The corpus is synthetic.** These numbers are honest for it and prove
  nothing about yours. `evaluation/scale_check.py` is the starting point for
  measuring on real documents.

The full analysis, including three attempted fixes that were measured and
rejected, is in [docs/RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md).
What the system defends against, and what it does not, is in
[docs/THREAT_MODEL.md](THREAT_MODEL.md). How to install, back up and
operate it is in [docs/RUNBOOK.md](RUNBOOK.md).

## Why abstention is the hard part

The number that degrades with corpus size is abstention, and it is the
product's central claim. `evaluation/scale_check.py` isolates that single
variable — same 52 questions, same expected answers, only the amount of
surrounding text changes, using real prose from this repository as noise
(frozen in `evaluation/noise_corpus.json`, without the documents that discuss
the evaluation itself).

Direct questions hold up as the archive grows; abstention falls from 6/16 to
1/16 as soon as the library contains other text. The cause is not statistical: a
question about a colleague working *sempre da casa senza mai* venire in sede
matched an unrelated technical paragraph on *sempre*, *senza* and *mai* alone —
three words that carry no meaning — because any single shared term is enough to
be returned as evidence. A question about the *codice etico* matched a sentence
about source code, which is a genuine ambiguity rather than a bug.

Three fixes were tried and measured: a lexical-coverage floor, term-rarity
(IDF) weighting, and a wider stopword list. None restores abstention; the
weighting was kept anyway because it improves ranking at scale, the other two
were dropped. Evidence verification is the only mechanism that works, and its
advantage grows with the corpus. All of it, including the numbers for the
rejected attempts, is in
[docs/RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md).
