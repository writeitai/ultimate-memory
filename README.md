# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/writeitai/ultimate-memory/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                                             |    Stmts |     Miss |   Branch |   BrPart |     Cover |   Missing |
|------------------------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | --------: | --------: |
| src/ultimate\_memory/\_\_init\_\_.py                                                             |        6 |        2 |        0 |        0 |     66.7% |     12-13 |
| src/ultimate\_memory/adapters/\_\_init\_\_.py                                                    |        6 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/markitdown\_converter.py                                           |       24 |        2 |        0 |        0 |     91.7% |     40-41 |
| src/ultimate\_memory/adapters/openrouter.py                                                      |       41 |       18 |        2 |        0 |     53.5% |39-40, 50-69, 75-85, 89-95 |
| src/ultimate\_memory/adapters/selfhost/\_\_init\_\_.py                                           |       10 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/selfhost/lance.py                                                  |       64 |        6 |       20 |        7 |     84.5% |29, 97, 115, 117, 119-\>121, 166, 174 |
| src/ultimate\_memory/adapters/selfhost/mounts.py                                                 |       12 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/selfhost/object\_store.py                                          |       23 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/selfhost/queue.py                                                  |       65 |        1 |       10 |        2 |     96.0% |111-\>118, 135 |
| src/ultimate\_memory/adapters/selfhost/watcher.py                                                |       31 |        1 |       10 |        1 |     95.1% |        39 |
| src/ultimate\_memory/adapters/testing/\_\_init\_\_.py                                            |        4 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/adapters/testing/model\_provider.py                                         |       27 |        1 |        4 |        1 |     93.5% |        44 |
| src/ultimate\_memory/adapters/testing/queue.py                                                   |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/\_\_init\_\_.py                                                        |       28 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/blockizer.py                                                           |       70 |        2 |       24 |        2 |     95.7% |  165, 178 |
| src/ultimate\_memory/core/chunker.py                                                             |       73 |        1 |       20 |        1 |     97.8% |       180 |
| src/ultimate\_memory/core/conversion.py                                                          |       36 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/core/core\_manifest.py                                                      |       40 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/core/extension\_packs.py                                                    |       17 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/core/section\_snap.py                                                       |       63 |        3 |       26 |        3 |     93.3% |122, 177, 203 |
| src/ultimate\_memory/eval/\_\_init\_\_.py                                                        |       14 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/contradiction.py                                                       |       45 |        1 |       10 |        1 |     96.4% |       111 |
| src/ultimate\_memory/eval/harness.py                                                             |       41 |        0 |        4 |        0 |    100.0% |           |
| src/ultimate\_memory/eval/resolution.py                                                          |       47 |        1 |       10 |        1 |     96.5% |       153 |
| src/ultimate\_memory/eval/skeleton.py                                                            |       73 |        7 |       26 |        7 |     85.9% |96, 105, 124, 147, 181, 184, 215 |
| src/ultimate\_memory/llm/\_\_init\_\_.py                                                         |        0 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/\_\_init\_\_.py                                                       |      128 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/adjudication.py                                                       |       29 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/auth.py                                                               |       10 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/blocks.py                                                             |       16 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/chunks.py                                                             |       45 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/claims.py                                                             |       45 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/clustering.py                                                         |       19 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/component\_version.py                                                 |       64 |        0 |        4 |        0 |    100.0% |           |
| src/ultimate\_memory/model/conversion.py                                                         |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/deployment.py                                                         |       16 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/documents.py                                                          |       43 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/envelope.py                                                           |       44 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/evaluation.py                                                         |       19 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/git.py                                                                |        6 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/model\_provider.py                                                    |       22 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/model/mounts.py                                                             |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/object\_store.py                                                      |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/processing.py                                                         |       59 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/queue.py                                                              |       44 |        0 |        2 |        0 |    100.0% |           |
| src/ultimate\_memory/model/relations.py                                                          |       20 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/resolution.py                                                         |       30 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/model/sections.py                                                           |       60 |        3 |       10 |        3 |     91.4% |90, 94, 100 |
| src/ultimate\_memory/model/telemetry.py                                                          |       10 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/\_\_init\_\_.py                                                       |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/auth.py                                                               |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/connector.py                                                          |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/git.py                                                                |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/model\_provider.py                                                    |       12 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/mounts.py                                                             |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/object\_store.py                                                      |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/p1\_index.py                                                          |       23 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/queue.py                                                              |        8 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/ports/telemetry.py                                                          |        7 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/profiles/\_\_init\_\_.py                                                    |        0 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/\_\_init\_\_.py                                                       |       26 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/catalog\_contract.py                                                  |      136 |       19 |       60 |       20 |     80.1% |381, 400, 428, 441, 481, 494, 509, 531, 546, 557, 567, 577, 631-\>643, 665, 667, 669, 671, 673, 675, 724 |
| src/ultimate\_memory/spine/chunk\_catalog.py                                                     |       44 |        2 |       10 |        2 |     92.6% |   38, 100 |
| src/ultimate\_memory/spine/claim\_catalog.py                                                     |       50 |        4 |       12 |        4 |     87.1% |51, 67, 87, 99 |
| src/ultimate\_memory/spine/clustering.py                                                         |      178 |        6 |       58 |        7 |     94.5% |131, 187, 256, 322-\>305, 483, 516, 521 |
| src/ultimate\_memory/spine/component\_versions.py                                                |       56 |        3 |       12 |        3 |     91.2% |102, 119, 187 |
| src/ultimate\_memory/spine/deployment\_bootstrap.py                                              |       88 |        0 |       16 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/document\_catalog.py                                                  |      103 |        2 |       14 |        2 |     96.6% |  134, 202 |
| src/ultimate\_memory/spine/entity\_registry.py                                                   |       45 |        0 |        2 |        1 |     97.9% |   65-\>86 |
| src/ultimate\_memory/spine/extension\_packs.py                                                   |       48 |        2 |       20 |        2 |     94.1% |  110, 145 |
| src/ultimate\_memory/spine/fact\_catalog.py                                                      |      124 |       10 |       12 |        1 |     90.4% |122-169, 298-\>300 |
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
| src/ultimate\_memory/spine/observation\_adjudication.py                                          |      122 |        9 |       24 |        7 |     89.0% |158, 221-239, 320-\>211, 347, 371-375, 504, 509 |
| src/ultimate\_memory/spine/resolver.py                                                           |      171 |       10 |       42 |        9 |     91.1% |203, 205, 213-\>215, 221-225, 278, 288-289, 293, 580, 585 |
| src/ultimate\_memory/spine/review.py                                                             |      114 |        7 |       30 |        7 |     90.3% |104, 164, 234-\>245, 306-310, 357, 359, 585 |
| src/ultimate\_memory/spine/settings.py                                                           |        9 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/supersession.py                                                       |       90 |        4 |       22 |        3 |     93.8% |97, 236-246, 294 |
| src/ultimate\_memory/spine/sync.py                                                               |       26 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/spine/work\_ledger.py                                                       |      110 |        4 |       26 |        5 |     93.4% |111, 137, 141, 211, 311-\>315 |
| src/ultimate\_memory/surfaces/\_\_init\_\_.py                                                    |        4 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/surfaces/cli.py                                                             |       52 |        7 |        8 |        2 |     85.0% |33-34, 96-106 |
| src/ultimate\_memory/surfaces/http\_api.py                                                       |       26 |        1 |        0 |        0 |     96.2% |        47 |
| src/ultimate\_memory/surfaces/query\_engine.py                                                   |       96 |        3 |        8 |        3 |     94.2% |264, 328, 356 |
| src/ultimate\_memory/workers/\_\_init\_\_.py                                                     |       32 |        0 |        0 |        0 |    100.0% |           |
| src/ultimate\_memory/workers/base.py                                                             |       63 |        1 |        8 |        1 |     97.2% |        73 |
| src/ultimate\_memory/workers/e0.py                                                               |      156 |        7 |       10 |        2 |     94.6% |213-217, 439, 476-477, 484 |
| src/ultimate\_memory/workers/e1.py                                                               |      103 |        1 |        8 |        1 |     98.2% |       335 |
| src/ultimate\_memory/workers/e2.py                                                               |      136 |        6 |       44 |        7 |     92.8% |115, 314, 327, 353-354, 365-\>363, 390-\>392, 468 |
| src/ultimate\_memory/workers/e3.py                                                               |      118 |        6 |       32 |        5 |     92.7% |121, 203-206, 297, 322, 340 |
| src/ultimate\_memory/workers/p1.py                                                               |       75 |        2 |       12 |        2 |     95.4% |   88, 222 |
| src/ultimate\_memory/workers/sync.py                                                             |       68 |        0 |       18 |        1 |     98.8% |  106-\>83 |
| **TOTAL**                                                                                        | **4456** |  **179** |  **782** |  **134** | **93.9%** |           |


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