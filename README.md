# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                              |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------ | -------: | -------: | ------: | --------: |
| src/antennaknobs/\_\_init\_\_.py                                  |       22 |        2 |     91% |   113-114 |
| src/antennaknobs/\_\_main\_\_.py                                  |        0 |        0 |    100% |           |
| src/antennaknobs/builder.py                                       |      302 |        1 |     99% |       299 |
| src/antennaknobs/cell.py                                          |       70 |        1 |     99% |        88 |
| src/antennaknobs/cli.py                                           |      505 |       50 |     90% |182, 201, 239, 251, 276-277, 526, 660-673, 765, 775, 777, 859, 893, 927-932, 939, 970-980, 1049-1063, 1127, 1206-1207 |
| src/antennaknobs/core.py                                          |       16 |        2 |     88% |     12-13 |
| src/antennaknobs/design\_data.py                                  |       29 |        1 |     97% |        43 |
| src/antennaknobs/design\_screen.py                                |       95 |        2 |     98% |  239, 325 |
| src/antennaknobs/design\_trust.py                                 |      103 |        7 |     93% |154, 182-184, 222-224 |
| src/antennaknobs/designs/\_\_init\_\_.py                          |        0 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/\_\_init\_\_.py                   |        0 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtie1x2\_bl.py                  |       35 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtie4x4.py                      |       25 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtie16x1.py                     |       25 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtiearray1x2.py                 |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtiearray2x4.py                 |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtiearray.py                    |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray.py               |       10 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_1x4.py          |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_1x4\_grouped.py |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_2x2.py          |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_network.py      |       28 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/folded\_invveearray.py            |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/hentenna\_array.py                |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/hourglass\_array.py               |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/invveearray.py                    |        8 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/lumped\_coupled\_pair.py          |       13 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/moxonarray.py                     |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/yagiarray.py                      |        7 |        0 |    100% |           |
| src/antennaknobs/designs/beams/\_\_init\_\_.py                    |        0 |        0 |    100% |           |
| src/antennaknobs/designs/beams/hb9cv.py                           |       27 |        0 |    100% |           |
| src/antennaknobs/designs/beams/hexbeam.py                         |       42 |        0 |    100% |           |
| src/antennaknobs/designs/beams/moxon.py                           |       33 |        0 |    100% |           |
| src/antennaknobs/designs/beams/moxon\_turnstile.py                |       32 |        0 |    100% |           |
| src/antennaknobs/designs/beams/owa\_yagi.py                       |       27 |        0 |    100% |           |
| src/antennaknobs/designs/beams/owa\_yagi\_6el.py                  |       28 |        0 |    100% |           |
| src/antennaknobs/designs/beams/phased\_driver\_yagi.py            |       36 |        0 |    100% |           |
| src/antennaknobs/designs/beams/yagi.py                            |       32 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/discone.py                     |       26 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/g5rv.py                        |       20 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/lpda.py                        |       44 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/t2fd.py                        |       22 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/dipole\_turnstile.py             |       13 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/folded\_invvee.py                |       23 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/folded\_invvee\_balun.py         |       10 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/invvee.py                        |       24 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/invvee\_coax\_station.py         |        9 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/koch\_dipole.py                  |       36 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/ocf\_dipole.py                   |       18 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/pota\_invvee.py                  |        5 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/short\_dipole\_loaded.py         |       11 |        0 |    100% |           |
| src/antennaknobs/designs/loops/\_\_init\_\_.py                    |        0 |        0 |    100% |           |
| src/antennaknobs/designs/loops/bisquare.py                        |       19 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop.py                     |       25 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_flyby.py              |       34 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_reflected.py          |       27 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_slanted.py            |       32 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_topdown.py            |       26 |        0 |    100% |           |
| src/antennaknobs/designs/loops/diamond\_loop.py                   |       26 |        0 |    100% |           |
| src/antennaknobs/designs/loops/diamond\_loop\_turnstile.py        |       32 |        0 |    100% |           |
| src/antennaknobs/designs/loops/horizontal\_loop.py                |       19 |        0 |    100% |           |
| src/antennaknobs/designs/loops/horizontal\_loop\_drone.py         |       19 |        0 |    100% |           |
| src/antennaknobs/designs/loops/inv\_delta\_loop.py                |       25 |        0 |    100% |           |
| src/antennaknobs/designs/loops/quad.py                            |       29 |        0 |    100% |           |
| src/antennaknobs/designs/loops/skyloop\_lmatch.py                 |       10 |        0 |    100% |           |
| src/antennaknobs/designs/loops/triangular\_skyloop.py             |       21 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/fandipole.py                   |       57 |        1 |     98% |       124 |
| src/antennaknobs/designs/multiband/hexbeam\_5band.py              |       92 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/trap\_dipole.py                |       28 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/trap\_fan\_dipole.py           |       77 |        3 |     96% |247, 308, 314 |
| src/antennaknobs/designs/multiband/twoband\_fan\_dipole.py        |       72 |       12 |     83% |   234-246 |
| src/antennaknobs/designs/specialty/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/bowtie.py                      |       17 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/continuous\_helix.py           |       37 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/faceted\_helix.py              |       37 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hentenna.py                    |       32 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hentenna\_slant.py             |       42 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hourglass.py                   |       32 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hourglass\_slant.py            |       36 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/bobtail.py                     |       15 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/bruce.py                       |       34 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/challenger.py                  |       25 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/dominator.py                   |       23 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/elt\_whip.py                   |      114 |        2 |     98% |   325-326 |
| src/antennaknobs/designs/verticals/four\_square.py                |       26 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/half\_square.py                |       20 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/inverted\_l.py                 |       25 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/inverted\_l\_tmatch.py         |       10 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/jpole.py                       |       16 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/phased\_verticals.py           |       22 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/pota\_performer.py             |       30 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/raised\_vertical.py            |       22 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/rectangle.py                   |       24 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/right\_angle\_delta.py         |       25 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/stub\_matched\_vertical.py     |       12 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/tri\_moxon.py                  |       41 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/vertical.py                    |       19 |        0 |    100% |           |
| src/antennaknobs/designs/wire/\_\_init\_\_.py                     |        0 |        0 |    100% |           |
| src/antennaknobs/designs/wire/doublet\_balanced\_tuner.py         |       16 |        0 |    100% |           |
| src/antennaknobs/designs/wire/doublet\_ladder\_tuner.py           |       15 |        0 |    100% |           |
| src/antennaknobs/designs/wire/edz.py                              |       20 |        0 |    100% |           |
| src/antennaknobs/designs/wire/efhw\_sloper.py                     |       24 |        0 |    100% |           |
| src/antennaknobs/designs/wire/expanded\_lazy\_h.py                |       25 |        0 |    100% |           |
| src/antennaknobs/designs/wire/lazy\_h.py                          |       21 |        0 |    100% |           |
| src/antennaknobs/designs/wire/longwire.py                         |       16 |        0 |    100% |           |
| src/antennaknobs/designs/wire/rhombic.py                          |       23 |        0 |    100% |           |
| src/antennaknobs/designs/wire/sterba.py                           |       54 |        0 |    100% |           |
| src/antennaknobs/designs/wire/sterba\_bl.py                       |       74 |        0 |    100% |           |
| src/antennaknobs/designs/wire/sterba\_tl.py                       |       60 |        0 |    100% |           |
| src/antennaknobs/designs/wire/terminated\_longwire.py             |       19 |        0 |    100% |           |
| src/antennaknobs/designs/wire/vbeam.py                            |       19 |        0 |    100% |           |
| src/antennaknobs/designs/wire/w8jk.py                             |       22 |        0 |    100% |           |
| src/antennaknobs/designs/wire/zepp.py                             |       15 |        0 |    100% |           |
| src/antennaknobs/drone.py                                         |      131 |        4 |     97% |208, 249-250, 261 |
| src/antennaknobs/engine.py                                        |       46 |        3 |     93% |69, 120, 126 |
| src/antennaknobs/engines/\_\_init\_\_.py                          |        6 |        2 |     67% |       3-4 |
| src/antennaknobs/engines/momwire.py                               |      486 |       20 |     96% |56, 105, 375, 391, 767, 1070, 1130-1146 |
| src/antennaknobs/engines/pynec.py                                 |      455 |       30 |     93% |63-65, 295-300, 405, 425, 454, 462, 472, 481, 503, 510, 544, 575, 614, 624, 630, 644, 762-763, 943, 968, 972-983, 985, 990 |
| src/antennaknobs/far\_field.py                                    |      184 |        2 |     99% |    92, 96 |
| src/antennaknobs/ferrite.py                                       |      116 |        5 |     96% |287, 290, 298-299, 353 |
| src/antennaknobs/fit.py                                           |      221 |       14 |     94% |247, 265, 277-278, 304, 314, 346, 350-352, 387, 402, 412-413 |
| src/antennaknobs/geometry.py                                      |      185 |        6 |     97% |80, 102-103, 107, 126, 152 |
| src/antennaknobs/measured.py                                      |       61 |        0 |    100% |           |
| src/antennaknobs/module.py                                        |       82 |        4 |     95% |84, 89, 146, 182 |
| src/antennaknobs/nec\_export.py                                   |       57 |       12 |     79% |60, 105-115 |
| src/antennaknobs/nec\_import.py                                   |      937 |       48 |     95% |290-291, 295, 298, 336, 435, 560, 567, 601, 655, 674, 684, 822, 838, 888, 894, 902, 926, 935, 958, 973, 977, 1031, 1049, 1051, 1053, 1071, 1073, 1075, 1080, 1086-1087, 1106, 1180, 1203, 1218, 1289, 1340-1341, 1344, 1347, 1443, 1467, 1481-1482, 1641, 1723, 1835 |
| src/antennaknobs/network.py                                       |      454 |       13 |     97% |599, 1029, 1120, 1296, 1320, 1326, 1414, 1421, 1445, 1447, 1535, 1541, 1555 |
| src/antennaknobs/network\_reduce.py                               |      398 |       15 |     96% |440, 506, 526, 587-591, 593, 613-615, 622, 968, 1027, 1144 |
| src/antennaknobs/opt.py                                           |       90 |       14 |     84% |54-55, 57-60, 65-66, 72-76, 148 |
| src/antennaknobs/plane.py                                         |       74 |        5 |     93% |59, 92, 158, 161-162 |
| src/antennaknobs/schematic.py                                     |      607 |      116 |     81% |190, 265, 288, 308, 320-326, 348, 445, 458, 533, 579-580, 608, 639, 643, 739, 752, 945, 952, 1013-1022, 1073-1074, 1078, 1088-1126, 1131-1149, 1154-1161, 1174-1177, 1255, 1285-1300, 1321-1329, 1337, 1381-1388, 1424-1425, 1429, 1432 |
| src/antennaknobs/serialize.py                                     |       83 |        6 |     93% |32-34, 54, 91, 103 |
| src/antennaknobs/sim.py                                           |        5 |        2 |     60% |       3-4 |
| src/antennaknobs/simnec\_export.py                                |       94 |       13 |     86% |98, 129-132, 337-340, 350-352, 358 |
| src/antennaknobs/smith\_chart.py                                  |       44 |        0 |    100% |           |
| src/antennaknobs/station.py                                       |       76 |        3 |     96% |235-236, 313 |
| src/antennaknobs/sweep.py                                         |      190 |        7 |     96% |   213-224 |
| src/antennaknobs/terrain.py                                       |      137 |        9 |     93% |53, 55, 57, 76, 97, 134-136, 276 |
| src/antennaknobs/touchstone.py                                    |      132 |        5 |     96% |99, 111, 168, 180, 185 |
| src/antennaknobs/transform.py                                     |       42 |        1 |     98% |        62 |
| src/antennaknobs/user\_designs.py                                 |       67 |        5 |     93% |35, 45, 77, 99, 104 |
| src/antennaknobs/vna.py                                           |      112 |       17 |     85% |83, 96-105, 108, 112, 115, 129-134, 260 |
| src/antennaknobs/web/\_\_init\_\_.py                              |        0 |        0 |    100% |           |
| src/antennaknobs/web/adapter.py                                   |     1007 |       91 |     91% |77-79, 336, 348, 350, 354, 361, 476, 572-573, 607, 611, 619, 662, 665, 670-673, 676, 686, 691, 855, 865, 879, 881, 883, 886, 906, 916, 926-927, 1158, 1427, 1460, 1463, 1466, 1478, 1481, 1496, 1515-1516, 1542-1543, 1597, 1625, 1629, 1642-1661, 1663, 1692, 1762-1763, 1794-1795, 1820-1821, 1872-1873, 1923-1924, 1927-1928, 1967, 2442-2444, 2474, 2693, 2715-2717, 2720, 2725-2726 |
| src/antennaknobs/web/cost.py                                      |       43 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_\_init\_\_.py                     |       11 |        1 |     91% |        24 |
| src/antennaknobs/web/examples/\_base.py                           |       95 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_feedline.py                       |       29 |        2 |     93% |     73-74 |
| src/antennaknobs/web/lane.py                                      |      123 |        5 |     96% |114, 132, 135-137 |
| src/antennaknobs/web/optimize.py                                  |       54 |        1 |     98% |        54 |
| src/antennaknobs/web/pynec\_backend.py                            |       92 |       38 |     59% |20-22, 73-91, 118, 129-132, 178-185, 197-207, 214-219 |
| src/antennaknobs/web/server.py                                    |      890 |       97 |     89% |71-73, 141-145, 276-277, 344, 590-592, 597, 689, 744, 847-850, 1027, 1110, 1128-1130, 1193, 1201-1204, 1223-1235, 1238, 1263, 1278-1291, 1339-1341, 1389, 1403, 1432-1433, 1457-1458, 1490, 1570-1577, 1589-1602, 1624, 1627-1633, 1687, 1715, 1718-1719, 1752-1753, 1784, 1802-1805, 1821, 1854, 1857, 1865, 1892-1893, 2129, 2215, 2242, 2244, 2248-2249, 2262, 2273, 2277, 2329-2330, 2349 |
| src/antennaknobs/web/user\_designs.py                             |       62 |        6 |     90% |59-60, 91-92, 97-98 |
| **TOTAL**                                                         | **11688** |  **706** | **94%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/stevenmburns/antennaknobs/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/stevenmburns/antennaknobs/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fstevenmburns%2Fantennaknobs%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.