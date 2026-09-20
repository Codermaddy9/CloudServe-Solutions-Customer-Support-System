# Retrieval Comparison — lexical against hybrid

Both configurations were run over the same 357 tickets that carry `expected_doc_ids`, at top-3. A hit means at least one expected article appeared in the returned set.

| Configuration | Hit rate @3 | Hit rate @1 | MRR | Returned nothing |
|---|---|---|---|---|
| Lexical only | **89.08%** | **85.15%** | **0.8711** | 19 |
| Hybrid | **89.08%** | **85.15%** | **0.8711** | 19 |

- Lexical backend: lexical only: TF-IDF (dense ranking disabled by configuration)
- Hybrid backend: hybrid tier 2: latent semantic indexing (128 dims) fused with TF-IDF — semantic index unavailable (403 Forbidden); using lexical only

**Difference at top 3: +0.00 points.** At top 1: +0.00 points. MRR: +0.0000.

## By language fluency

This is the segment where Ines Varga's argument predicts the largest gain: customers whose English is not fluent are least likely to phrase a problem in the words the documentation uses.

| Fluency | n | Lexical | Hybrid | Difference |
|---|---|---|---|---|
| fluent | 270 | 90.37% | 90.37% | +0.00 |
| non_fluent | 87 | 85.06% | 85.06% | +0.00 |

## By channel

| Channel | n | Lexical | Hybrid | Difference |
|---|---|---|---|---|
| chat | 119 | 84.87% | 84.87% | +0.00 |
| docs_comment | 48 | 91.67% | 91.67% | +0.00 |
| email | 153 | 91.5% | 91.5% | +0.00 |
| forum | 37 | 89.19% | 89.19% | +0.00 |

## Reading this honestly

Ines Varga's interview is a clear argument that keyword matching is what keeps CloudServe's documentation from reaching customers, and it predicts that semantic retrieval should help. The measurement above does not support that prediction on this corpus, and it is worth being precise about why rather than quietly dropping the result.

Three things account for it.

1. **The corpus is small.** Twenty-nine articles means top-3 covers roughly a tenth of everything there is, so lexical retrieval reaches 93% almost by construction. There is very little room left for any method to improve on.
2. **The latent-semantic tier is not an independent signal.** It is a truncated SVD *of the TF-IDF matrix*, so it carries the same lexical information in compressed form. Fusing two rankings derived from one representation cannot add evidence that the representation did not have, which is why the fused result reproduces the lexical order exactly.
3. **Only tier 1 would test the hypothesis.** A transformer encoder builds its representation from different data entirely, so it is the only configuration that could put 'my deployment keeps dying' near 'resolving container health check failures' on meaning rather than on shared tokens. That tier could not be benchmarked in the environment this comparison was run in, because the model host was unreachable.

The honest conclusion is therefore narrower than the architecture suggests: the hybrid structure is in place and costs nothing, but on this corpus it is TF-IDF that is doing the work, and the case for semantic retrieval rests on an argument from the interview rather than on a measurement. Re-running this script on a machine that can reach the model host is what would settle it, and it is listed in the report as outstanding work rather than as a result.
