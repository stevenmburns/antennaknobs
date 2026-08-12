# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                              |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------ | -------: | -------: | ------: | --------: |
| src/antennaknobs/\_\_init\_\_.py                                  |       23 |        2 |     91% |   115-116 |
| src/antennaknobs/\_\_main\_\_.py                                  |        0 |        0 |    100% |           |
| src/antennaknobs/builder.py                                       |      302 |        1 |     99% |       299 |
| src/antennaknobs/catenary.py                                      |      354 |       16 |     95% |293, 333, 547-550, 555-556, 558, 572-574, 601, 698, 706, 818 |
| src/antennaknobs/cell.py                                          |       70 |        1 |     99% |        88 |
| src/antennaknobs/cli.py                                           |      526 |       35 |     93% |46, 193, 212, 258, 273, 298-299, 613, 755-759, 852, 862, 864, 949, 985, 1020-1027, 1034, 1065-1075, 1159, 1232, 1311-1312, 1341-1342 |
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
| src/antennaknobs/designs/dipoles/invvee\_catenary.py              |       63 |        1 |     98% |       399 |
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
| src/antennaknobs/engines/\_\_init\_\_.py                          |        7 |        2 |     71% |       3-4 |
| src/antennaknobs/engines/momwire.py                               |      503 |       20 |     96% |56, 105, 434, 450, 857, 1161, 1221-1237 |
| src/antennaknobs/engines/nec5.py                                  |      388 |      107 |     72% |74, 137, 159, 209, 217, 219, 235, 249, 290, 350, 450-451, 454-455, 482-485, 488, 515, 522, 536-537, 553, 558, 565-587, 604-605, 618, 625, 633-653, 699-715, 722-723, 733-743, 746-772 |
| src/antennaknobs/engines/pynec.py                                 |      455 |       30 |     93% |63-65, 295-300, 405, 425, 454, 462, 472, 481, 503, 510, 544, 575, 614, 624, 630, 644, 762-763, 943, 968, 972-983, 985, 990 |
| src/antennaknobs/far\_field.py                                    |      184 |        2 |     99% |    92, 96 |
| src/antennaknobs/ferrite.py                                       |      116 |        5 |     96% |287, 290, 298-299, 353 |
| src/antennaknobs/file\_designs.py                                 |       67 |        2 |     97% |  119, 142 |
| src/antennaknobs/fit.py                                           |      221 |       14 |     94% |247, 265, 277-278, 304, 314, 346, 350-352, 387, 402, 412-413 |
| src/antennaknobs/geometry.py                                      |      185 |        6 |     97% |80, 102-103, 107, 126, 152 |
| src/antennaknobs/measured.py                                      |       61 |        0 |    100% |           |
| src/antennaknobs/module.py                                        |       82 |        4 |     95% |84, 89, 146, 182 |
| src/antennaknobs/nec\_export.py                                   |       57 |        3 |     95% |60, 107, 113 |
| src/antennaknobs/nec\_import.py                                   |     1026 |       47 |     95% |291-292, 296, 299, 337, 436, 561, 568, 602, 656, 675, 685, 823, 839, 889, 895, 903, 927, 936, 959, 974, 978, 1167, 1169, 1171, 1189, 1191, 1193, 1198, 1204-1205, 1224, 1298, 1321, 1336, 1407, 1458-1459, 1462, 1465, 1562, 1586, 1600-1601, 1760, 1888, 2005 |
| src/antennaknobs/nec\_portal.py                                   |     1266 |       18 |     99% |595, 599, 631, 648, 827, 1050, 1060-1061, 1141, 1182, 1640, 1745, 1857-1858, 2117, 2205, 2808, 3078 |
| src/antennaknobs/network.py                                       |      454 |       13 |     97% |599, 1034, 1125, 1301, 1325, 1331, 1419, 1426, 1450, 1452, 1540, 1546, 1560 |
| src/antennaknobs/network\_reduce.py                               |      456 |       15 |     97% |615, 685, 705, 771-772, 779, 787-792, 807, 1208, 1286, 1426 |
| src/antennaknobs/opt.py                                           |       90 |       14 |     84% |54-55, 57-60, 65-66, 72-76, 151 |
| src/antennaknobs/plane.py                                         |       74 |        5 |     93% |59, 92, 158, 161-162 |
| src/antennaknobs/schematic.py                                     |      734 |       85 |     88% |198, 329, 365, 385, 397-403, 425, 522, 535, 615, 662-663, 713, 744, 748, 867-868, 888, 901, 1148, 1155, 1257-1259, 1270-1271, 1288, 1331, 1345-1363, 1368-1375, 1388-1391, 1499-1514, 1535-1543, 1551, 1712, 1718, 1731, 1746, 1774-1775, 1779, 1782 |
| src/antennaknobs/serialize.py                                     |       83 |        6 |     93% |32-34, 54, 91, 103 |
| src/antennaknobs/sim.py                                           |        5 |        2 |     60% |       3-4 |
| src/antennaknobs/simnec\_export.py                                |      241 |       34 |     86% |171, 333, 368, 374, 398, 406, 411, 421, 467, 474, 476-491, 498, 502, 544, 556, 584-591, 787-790, 810 |
| src/antennaknobs/simnec\_import.py                                |      289 |       21 |     93% |155-156, 213, 277, 303, 322, 359-360, 380, 425, 456, 459-460, 531-532, 536-537, 592-593, 596-597 |
| src/antennaknobs/smith\_chart.py                                  |       44 |        0 |    100% |           |
| src/antennaknobs/station.py                                       |       68 |        3 |     96% |234-235, 312 |
| src/antennaknobs/sweep.py                                         |      190 |        7 |     96% |   213-224 |
| src/antennaknobs/terrain.py                                       |      137 |        9 |     93% |53, 55, 57, 76, 97, 134-136, 276 |
| src/antennaknobs/touchstone.py                                    |      150 |        5 |     97% |188, 217, 296, 308, 313 |
| src/antennaknobs/transform.py                                     |       42 |        1 |     98% |        62 |
| src/antennaknobs/user\_designs.py                                 |       67 |        5 |     93% |35, 45, 77, 99, 104 |
| src/antennaknobs/vna.py                                           |      112 |       17 |     85% |83, 96-105, 108, 112, 115, 129-134, 260 |
| src/antennaknobs/web/\_\_init\_\_.py                              |        0 |        0 |    100% |           |
| src/antennaknobs/web/adapter.py                                   |     1135 |      154 |     86% |78-80, 357, 369, 371, 375, 506, 602-603, 637, 641, 649, 692, 695, 700-703, 706, 716, 721, 885, 895, 909, 911, 913, 916, 936, 946, 956-957, 1188, 1326-1334, 1338-1342, 1346, 1492-1497, 1627, 1660, 1663, 1666, 1678, 1681, 1696, 1715-1716, 1742-1743, 1797, 1825, 1829, 1842-1861, 1863, 1892, 1962-1963, 1994-1995, 2020-2021, 2072-2073, 2123-2124, 2127-2128, 2167, 2650-2652, 2668-2739, 2744-2766, 2798, 3019, 3041-3043, 3046, 3051-3052 |
| src/antennaknobs/web/cost.py                                      |       43 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_\_init\_\_.py                     |       11 |        1 |     91% |        24 |
| src/antennaknobs/web/examples/\_base.py                           |       97 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_feedline.py                       |       29 |        2 |     93% |     73-74 |
| src/antennaknobs/web/lane.py                                      |      123 |        5 |     96% |128, 146, 149-151 |
| src/antennaknobs/web/nec5\_backend.py                             |       29 |       16 |     45% |33, 37-41, 48-51, 57-62 |
| src/antennaknobs/web/optimize.py                                  |       72 |        0 |    100% |           |
| src/antennaknobs/web/progress\_stream.py                          |      120 |        1 |     99% |       243 |
| src/antennaknobs/web/pynec\_backend.py                            |       92 |       38 |     59% |20-22, 73-91, 118, 129-132, 178-185, 197-207, 214-219 |
| src/antennaknobs/web/server.py                                    |     1056 |       97 |     91% |74-76, 144-148, 279-280, 347, 653-655, 766, 821, 924-927, 1235, 1290, 1346, 1364-1366, 1426, 1452, 1465-1468, 1480-1492, 1499, 1524, 1551-1565, 1614-1616, 1664, 1678, 1707-1708, 1733-1734, 1766, 1846-1853, 1865-1878, 1900, 1903-1909, 1963, 1991, 1994-1995, 2071, 2089-2092, 2108, 2268, 2278, 2579, 2675, 2710, 2712, 2716-2717, 2730, 2741, 2745, 2797-2798, 2821-2829 |
| src/antennaknobs/web/user\_designs.py                             |       62 |        6 |     90% |59-60, 91-92, 97-98 |
| **TOTAL**                                                         | **15049** |  **915** | **94%** |           |


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