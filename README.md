# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/writeitai/ultimate-memory/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                                             |    Stmts |     Miss |   Branch |   BrPart |     Cover |   Missing |
|------------------------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | --------: | --------: |
| src/ultimate\_memory/\_\_init\_\_.py                                                             |        6 |        2 |        0 |        0 |     66.7% |     12-13 |
| src/ultimate\_memory/adapters/\_\_init\_\_.py                                                    |       10 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/codex\_writer.py                                                   |       82 |        3 |       20 |        3 |     94.1% |172, 203, 215 |
| src/ultimate\_memory/adapters/markitdown\_converter.py                                           |       24 |        2 |        0 |        0 |     91.7% |     40-41 |
| src/ultimate\_memory/adapters/openrouter.py                                                      |       61 |       23 |        4 |        0 |     61.5% |45-46, 56-84, 88-104, 108-114 |
| src/ultimate\_memory/adapters/selfhost/\_\_init\_\_.py                                           |       17 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/selfhost/forget.py                                                 |       43 |        1 |       10 |        1 |     96.2% |        19 |
| src/ultimate\_memory/adapters/selfhost/git.py                                                    |       98 |        6 |       32 |        8 |     89.2% |55, 75-\>127, 154, 184-185, 199-\>227, 263, 307, 331-\>329 |
| src/ultimate\_memory/adapters/selfhost/lance.py                                                  |      124 |       12 |       40 |       15 |     83.5% |46, 67, 131, 154, 156, 158-\>160, 180-\>185, 185-\>exit, 196, 278, 284, 286, 291, 299, 316 |
| src/ultimate\_memory/adapters/selfhost/mounts.py                                                 |       94 |        3 |       16 |        2 |     95.5% |150-\>173, 171-172, 239 |
| src/ultimate\_memory/adapters/selfhost/object\_store.py                                          |       60 |        2 |       26 |        2 |     95.3% |  102, 104 |
| src/ultimate\_memory/adapters/selfhost/projection.py                                             |       36 |        3 |       12 |        3 |     87.5% |52, 60, 78 |
| src/ultimate\_memory/adapters/selfhost/queue.py                                                  |       65 |        1 |       10 |        2 |     96.0% |111-\>118, 135 |
| src/ultimate\_memory/adapters/selfhost/telemetry.py                                              |       21 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/selfhost/watcher.py                                                |       31 |        1 |       10 |        1 |     95.1% |        39 |
| src/ultimate\_memory/adapters/testing/\_\_init\_\_.py                                            |        6 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/testing/cost\_meter.py                                             |        4 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/testing/model\_provider.py                                         |       33 |        1 |        4 |        1 |     94.6% |        48 |
| src/ultimate\_memory/adapters/testing/queue.py                                                   |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/testing/telemetry.py                                               |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/client.py                                                                   |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/\_\_init\_\_.py                                                        |       62 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/blockizer.py                                                           |       70 |        2 |       24 |        2 |     95.7% |  165, 178 |
| src/ultimate\_memory/core/chunker.py                                                             |       73 |        0 |       20 |        0 |    100.0% |           |
| src/ultimate\_memory/core/consumption\_skill.py                                                  |       55 |        1 |        6 |        1 |     96.7% |       258 |
| src/ultimate\_memory/core/conversion.py                                                          |       36 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/core/core\_manifest.py                                                      |       40 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/core/extension\_packs.py                                                    |       17 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/forget.py                                                              |        6 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/knowledge\_authored.py                                                 |      173 |       26 |       74 |       16 |     83.0% |48-\>59, 117-118, 142, 161, 168, 173-174, 183, 186, 194-197, 213, 217-218, 224, 234-235, 240, 247-249, 253, 255, 258, 264-\>266 |
| src/ultimate\_memory/core/knowledge\_compile.py                                                  |      106 |       11 |       52 |        7 |     86.1% |39, 44, 129, 131, 170-172, 184-186, 202 |
| src/ultimate\_memory/core/knowledge\_fact\_sheet.py                                              |       71 |        3 |       30 |        3 |     94.1% |37, 102, 150 |
| src/ultimate\_memory/core/knowledge\_hashing.py                                                  |       17 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/knowledge\_planner.py                                                  |       35 |        5 |       16 |        5 |     80.4% |33, 35, 37, 50, 52 |
| src/ultimate\_memory/core/knowledge\_writer.py                                                   |       71 |        1 |       30 |        1 |     98.0% |        24 |
| src/ultimate\_memory/core/ranking.py                                                             |       66 |        8 |       20 |        6 |     83.7% |60, 125, 127, 166, 178-179, 186, 197 |
| src/ultimate\_memory/core/recipe\_linter.py                                                      |       45 |        6 |       32 |        6 |     84.4% |99, 105, 116, 131, 137, 143 |
| src/ultimate\_memory/core/section\_snap.py                                                       |       63 |        3 |       26 |        3 |     93.3% |122, 177, 203 |
| src/ultimate\_memory/core/storage\_routing.py                                                    |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/\_\_init\_\_.py                                                        |       25 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/consumption.py                                                         |       43 |        2 |        8 |        2 |     92.2% |    76, 79 |
| src/ultimate\_memory/eval/contradiction.py                                                       |       45 |        1 |       10 |        1 |     96.4% |       111 |
| src/ultimate\_memory/eval/harness.py                                                             |       41 |        0 |        4 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/lifecycle.py                                                           |       57 |        2 |        8 |        2 |     93.8% |   71, 178 |
| src/ultimate\_memory/eval/operational\_scale.py                                                  |       15 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/resolution.py                                                          |       47 |        1 |       10 |        1 |     96.5% |       153 |
| src/ultimate\_memory/eval/retrieval\_spikes.py                                                   |       16 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/skeleton.py                                                            |       73 |        7 |       26 |        7 |     85.9% |96, 105, 124, 147, 181, 184, 215 |
| src/ultimate\_memory/llm/\_\_init\_\_.py                                                         |        0 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/\_\_init\_\_.py                                                       |      293 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/adjudication.py                                                       |       29 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/auth.py                                                               |       10 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/blocks.py                                                             |       16 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/chunks.py                                                             |       47 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/claims.py                                                             |       45 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/client.py                                                             |       44 |        4 |       16 |        1 |     85.0% |     94-97 |
| src/ultimate\_memory/model/clustering.py                                                         |       19 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/component\_version.py                                                 |       65 |        0 |        4 |        0 |    100.0% |           |
| src/ultimate\_memory/model/consumption.py                                                        |       29 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/conversion.py                                                         |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/deployment.py                                                         |       16 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/documents.py                                                          |       43 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/envelope.py                                                           |      151 |        0 |       10 |        0 |    100.0% |           |
| src/ultimate\_memory/model/evaluation.py                                                         |       27 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/forget.py                                                             |       63 |        0 |        6 |        0 |    100.0% |           |
| src/ultimate\_memory/model/git.py                                                                |        6 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/knowledge.py                                                          |      374 |       24 |       38 |       14 |     88.8% |232, 271, 356, 368, 387, 399, 429, 586, 603, 631-642, 654-656, 685, 700, 721, 759, 768 |
| src/ultimate\_memory/model/knowledge\_authored.py                                                |      135 |        4 |        8 |        3 |     95.1% |29, 101, 112, 192 |
| src/ultimate\_memory/model/knowledge\_planner.py                                                 |      213 |       15 |       32 |       11 |     88.6% |47, 106, 139, 145, 160, 189, 194, 196, 238, 275-277, 291, 312, 380 |
| src/ultimate\_memory/model/lifecycle.py                                                          |       15 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/model\_provider.py                                                    |       35 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/model/mounts.py                                                             |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/object\_store.py                                                      |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/operational\_scale.py                                                 |       25 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/model/operations.py                                                         |       46 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/processing.py                                                         |       90 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/queue.py                                                              |       47 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/model/recipes.py                                                            |       23 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/relations.py                                                          |       22 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/resolution.py                                                         |       30 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/retrieval\_spikes.py                                                  |       26 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/model/sections.py                                                           |       60 |        3 |       10 |        3 |     91.4% |90, 94, 100 |
| src/ultimate\_memory/model/telemetry.py                                                          |       10 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/\_\_init\_\_.py                                                       |       13 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/auth.py                                                               |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/connector.py                                                          |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/cost\_meter.py                                                        |        6 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/forget.py                                                             |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/git.py                                                                |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/model\_provider.py                                                    |       13 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/mounts.py                                                             |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/object\_store.py                                                      |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/p1\_index.py                                                          |       27 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/purge.py                                                              |       21 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/queue.py                                                              |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/telemetry.py                                                          |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/profiles/\_\_init\_\_.py                                                    |        0 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/profiles/selfhost\_forget.py                                                |       55 |       55 |        2 |        0 |      0.0% |     3-153 |
| src/ultimate\_memory/profiles/selfhost\_operations.py                                            |       44 |        5 |        4 |        1 |     87.5% |48, 62-64, 95 |
| src/ultimate\_memory/spine/\_\_init\_\_.py                                                       |       45 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/admission.py                                                          |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/backfill.py                                                           |       42 |        0 |        4 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/catalog\_contract.py                                                  |      136 |       19 |       60 |       20 |     80.1% |395, 414, 442, 455, 496, 509, 524, 546, 561, 572, 582, 592, 646-\>658, 680, 682, 684, 686, 688, 690, 739 |
| src/ultimate\_memory/spine/chunk\_catalog.py                                                     |       50 |        2 |       10 |        2 |     93.3% |   39, 143 |
| src/ultimate\_memory/spine/claim\_catalog.py                                                     |       62 |        4 |       14 |        5 |     88.2% |97-\>106, 113, 129, 149, 161 |
| src/ultimate\_memory/spine/clustering.py                                                         |      178 |        6 |       58 |        7 |     94.5% |131, 187, 256, 322-\>305, 483, 516, 521 |
| src/ultimate\_memory/spine/component\_versions.py                                                |       56 |        3 |       12 |        3 |     91.2% |102, 119, 187 |
| src/ultimate\_memory/spine/consumption.py                                                        |       20 |        1 |        2 |        1 |     90.9% |        32 |
| src/ultimate\_memory/spine/deployment\_bootstrap.py                                              |       88 |        0 |       16 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/document\_catalog.py                                                  |      103 |        2 |       14 |        2 |     96.6% |  138, 206 |
| src/ultimate\_memory/spine/entity\_registry.py                                                   |       50 |        2 |        4 |        2 |     92.6% |65-\>86, 126, 131 |
| src/ultimate\_memory/spine/extension\_packs.py                                                   |       48 |        2 |       20 |        2 |     94.1% |  110, 145 |
| src/ultimate\_memory/spine/fact\_catalog.py                                                      |      124 |       10 |       12 |        1 |     90.4% |122-169, 298-\>300 |
| src/ultimate\_memory/spine/forget.py                                                             |      198 |       54 |       46 |       13 |     66.0% |49, 63-73, 85-90, 99, 118-119, 141-147, 151-205, 209-213, 219-226, 250, 254, 264, 366-367, 390, 411, 437-450, 480, 508, 525, 584 |
| src/ultimate\_memory/spine/knowledge.py                                                          |     1280 |      123 |      472 |      102 |     86.5% |154, 169, 240, 250, 278, 284-\>exit, 297, 308, 320, 324, 378, 420, 454, 515-520, 544, 612-621, 636, 655, 683-\>679, 699, 752, 766, 878, 919, 949, 1040, 1074, 1094, 1178, 1229, 1265, 1274, 1329, 1349, 1380, 1433-1436, 1463, 1468, 1470, 1472, 1528, 1530, 1532, 1534, 1536, 1553, 1560, 1564, 1595, 1606, 1608-\>1626, 1665, 1781, 1810, 1825, 1832, 1857-1863, 1969-1972, 2081, 2105, 2128, 2169, 2176, 2178-2179, 2186, 2199, 2224-2237, 2298, 2332, 2350, 2360, 2387, 2389, 2393, 2402, 2427, 2455, 2584, 2595, 2599, 2616, 2619, 2691, 2722, 2739, 2767, 2791, 2797-\>2808, 2808-\>2819, 2844, 2860, 2946-\>2951, 2970-2974, 2979-2983, 3114, 3118-\>3131, 3131-\>3143, 3143-\>3150, 3186-3192, 3217-3223, 3264-\>3274, 3274-\>3287, 3402-3406, 3471-3480, 3590, 3609 |
| src/ultimate\_memory/spine/lifecycle.py                                                          |      164 |        8 |       22 |        3 |     93.0% |389-390, 420, 448-454 |
| src/ultimate\_memory/spine/migrations/\_\_init\_\_.py                                            |        0 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/\_helpers.py                                               |      123 |        9 |       72 |        5 |     91.8% |104-109, 130-132, 139-\>143, 145-\>147, 152 |
| src/ultimate\_memory/spine/migrations/env.py                                                     |       29 |        5 |        6 |        3 |     77.1% |13-\>16, 24, 29-37, 56 |
| src/ultimate\_memory/spine/migrations/versions/\_\_init\_\_.py                                   |        0 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p0\_02\_0001\_extensions\_enums.py                |       16 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p0\_02\_0002\_infrastructure\_registries.py       |       18 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p0\_02\_0003\_entities\_evaluation\_e0\_e1.py     |       13 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p0\_02\_0004\_claims\_facts\_evidence.py          |       13 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p0\_02\_0005\_projection\_knowledge\_retrieval.py |       13 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p0\_02\_0006\_partitions\_views.py                |       18 |        0 |        4 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p2\_06\_0007\_invalidated\_outcome.py             |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p3\_01\_0008\_document\_version\_target.py        |       15 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p3\_05\_0009\_reconcile\_stage.py                 |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p3\_07\_0010\_lifecycle\_eval\_suite.py           |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p4\_01\_0011\_survivor\_view\_rewrite.py          |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p6\_02\_0012\_knowledge\_compile\_recovery.py     |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p6\_04\_0013\_knowledge\_writer\_ledger.py        |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p6\_05\_0014\_knowledge\_planner\_runtime.py      |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p6\_06\_0015\_authored\_dispatch\_runtime.py      |       14 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p7\_02\_0016\_operational\_eval\_suite.py         |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/migrations/versions/p7\_05\_0017\_hard\_forget.py                     |       14 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/observation\_adjudication.py                                          |      159 |       21 |       34 |       11 |     82.4% |131, 229-248, 256-275, 327-345, 442-\>314, 476-493, 510, 518-528, 545, 683, 688 |
| src/ultimate\_memory/spine/operations.py                                                         |       76 |        1 |        4 |        1 |     97.5% |       149 |
| src/ultimate\_memory/spine/projection.py                                                         |      140 |       17 |       10 |        0 |     86.0% |49-50, 276-283, 289-292, 330-331, 340-341, 352-353 |
| src/ultimate\_memory/spine/recipes.py                                                            |       43 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/resolver.py                                                           |      179 |       12 |       48 |       11 |     89.9% |214, 216, 224-\>226, 232-236, 295, 305-306, 310, 391, 403, 626, 631 |
| src/ultimate\_memory/spine/review.py                                                             |      120 |        7 |       30 |        7 |     90.7% |118, 178, 248-\>259, 345-349, 396, 398, 649 |
| src/ultimate\_memory/spine/settings.py                                                           |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/supersession.py                                                       |       97 |        6 |       26 |        5 |     91.1% |103, 219, 235, 260-270, 318 |
| src/ultimate\_memory/spine/sync.py                                                               |       26 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/work\_ledger.py                                                       |      194 |        9 |       54 |       10 |     92.3% |70, 177, 241, 267, 271, 345, 356, 374, 415, 559-\>563 |
| src/ultimate\_memory/surfaces/\_\_init\_\_.py                                                    |       14 |        2 |        0 |        0 |     85.7% |   110-111 |
| src/ultimate\_memory/surfaces/cli.py                                                             |      250 |       49 |       42 |        8 |     79.1% |54-55, 59-60, 70-75, 102-107, 126-131, 136-138, 140-148, 158-160, 170-180, 198-199, 229-232, 239-240, 248-250, 265-267, 331-341 |
| src/ultimate\_memory/surfaces/consumption\_skill.py                                              |       42 |        2 |        8 |        1 |     94.0% |    35, 67 |
| src/ultimate\_memory/surfaces/graph\_queries.py                                                  |      202 |       14 |       52 |       10 |     90.6% |105-106, 223-224, 238, 242, 308, 312, 409-410, 429, 544-\>549, 566-\>568, 677, 684, 690 |
| src/ultimate\_memory/surfaces/http\_api.py                                                       |      131 |        8 |       20 |        3 |     91.4% |181, 257, 265, 272-284, 316-317 |
| src/ultimate\_memory/surfaces/mcp.py                                                             |       15 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/surfaces/query\_engine.py                                                   |      273 |        8 |       58 |        7 |     95.5% |102-103, 154, 389, 567, 642-\>644, 645, 905, 939 |
| src/ultimate\_memory/surfaces/recipe\_executor.py                                                |       64 |        3 |       24 |        3 |     93.2% |85, 106, 108 |
| src/ultimate\_memory/surfaces/recipe\_surface.py                                                 |       88 |       12 |       34 |        2 |     82.0% |62-68, 78-83, 169-\>171, 208 |
| src/ultimate\_memory/surfaces/remote\_mcp.py                                                     |       62 |       12 |       24 |        7 |     77.9% |57-58, 65, 71-72, 88, 98, 107, 113, 116, 121, 129 |
| src/ultimate\_memory/surfaces/sdk.py                                                             |      124 |       16 |       32 |        6 |     84.6% |69, 112, 138-144, 152, 160, 207, 209, 243, 303-304, 305-\>307, 310-311 |
| src/ultimate\_memory/workers/\_\_init\_\_.py                                                     |       76 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/workers/base.py                                                             |       99 |        1 |       16 |        1 |     98.3% |       109 |
| src/ultimate\_memory/workers/e0.py                                                               |      173 |        8 |       10 |        2 |     94.5% |290-294, 516, 531, 557-558, 565 |
| src/ultimate\_memory/workers/e1.py                                                               |      124 |        2 |       14 |        2 |     97.1% |  231, 422 |
| src/ultimate\_memory/workers/e2.py                                                               |      151 |        5 |       50 |        7 |     94.0% |116, 180, 368, 381, 419-\>417, 444-\>446, 522 |
| src/ultimate\_memory/workers/e3.py                                                               |      131 |        6 |       36 |        5 |     93.4% |245-248, 355, 380, 404, 417 |
| src/ultimate\_memory/workers/forget.py                                                           |      130 |       17 |       26 |        2 |     85.3% |118-123, 179, 191-197, 289-297 |
| src/ultimate\_memory/workers/knowledge\_authored.py                                              |       77 |        5 |       16 |        3 |     91.4% |55, 109, 117, 128-129 |
| src/ultimate\_memory/workers/knowledge\_driver.py                                                |      295 |       53 |       88 |       14 |     77.3% |166, 247-258, 290, 495-511, 515, 562-\>564, 591-611, 625, 629, 633, 641-647, 654-672, 696, 699-700, 702, 705-706, 708, 734 |
| src/ultimate\_memory/workers/knowledge\_fact\_sheet.py                                           |       41 |        2 |        2 |        1 |     93.0% |    31, 57 |
| src/ultimate\_memory/workers/knowledge\_planner.py                                               |      135 |       13 |       20 |        7 |     87.1% |73, 107, 175, 198, 206, 208, 213, 242-250, 273-274 |
| src/ultimate\_memory/workers/knowledge\_writer.py                                                |      156 |       12 |       22 |       11 |     87.1% |74, 94, 140, 174, 191, 196, 198, 297, 334, 340, 342, 363 |
| src/ultimate\_memory/workers/operations.py                                                       |       14 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/workers/p1.py                                                               |       80 |        2 |       12 |        2 |     95.7% |   89, 231 |
| src/ultimate\_memory/workers/p2.py                                                               |      191 |       11 |       48 |       12 |     90.4% |267-269, 281-\>298, 321-324, 325-\>329, 340, 417-\>446, 423, 430, 439, 458, 472, 507-\>511 |
| src/ultimate\_memory/workers/p2\_analytics.py                                                    |      104 |        3 |       16 |        1 |     96.7% |210, 229-230 |
| src/ultimate\_memory/workers/p3.py                                                               |      247 |        5 |       68 |        5 |     96.8% |122-127, 226-\>228, 333-\>335, 337-\>341, 564, 671 |
| src/ultimate\_memory/workers/reconcile.py                                                        |      143 |        7 |       36 |       10 |     90.5% |115, 211, 216, 250-\>242, 252, 286, 287-\>292, 296, 369-\>380, 482 |
| src/ultimate\_memory/workers/sync.py                                                             |       70 |        0 |       18 |        1 |     98.9% |  108-\>85 |
| **TOTAL**                                                                                        | **12302** |  **850** | **2570** |  **483** | **90.4%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/writeitai/ultimate-memory/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/writeitai/ultimate-memory/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/writeitai/ultimate-memory/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/writeitai/ultimate-memory/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fwriteitai%2Fultimate-memory%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/writeitai/ultimate-memory/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.