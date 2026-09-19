# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                 |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/antennaknobs/\_\_init\_\_.py                                     |       23 |        2 |     91% |   115-116 |
| src/antennaknobs/\_\_main\_\_.py                                     |        0 |        0 |    100% |           |
| src/antennaknobs/builder.py                                          |      320 |        1 |     99% |       371 |
| src/antennaknobs/catenary.py                                         |      354 |       16 |     95% |293, 333, 547-550, 555-556, 558, 572-574, 601, 698, 706, 818 |
| src/antennaknobs/cell.py                                             |       70 |        1 |     99% |        88 |
| src/antennaknobs/cli.py                                              |      713 |       42 |     94% |71, 77, 269, 288, 334, 349, 374-375, 608-609, 705, 710, 1117, 1266-1270, 1363, 1373, 1375, 1460, 1496, 1531-1538, 1545, 1585, 1589-1599, 1680, 1834, 1911, 1990-1991, 2021-2022 |
| src/antennaknobs/core.py                                             |       16 |        2 |     88% |     12-13 |
| src/antennaknobs/density.py                                          |       11 |        0 |    100% |           |
| src/antennaknobs/design\_data.py                                     |       29 |        1 |     97% |        43 |
| src/antennaknobs/design\_screen.py                                   |       95 |        2 |     98% |  239, 325 |
| src/antennaknobs/design\_trust.py                                    |      103 |        7 |     93% |154, 182-184, 222-224 |
| src/antennaknobs/designs/\_\_init\_\_.py                             |        0 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/\_\_init\_\_.py                      |        0 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtie1x2\_bl.py                     |       36 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtie4x4.py                         |       25 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtie16x1.py                        |       25 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtiearray1x2.py                    |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtiearray2x4.py                    |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/bowtiearray.py                       |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray.py                  |       10 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_1x4.py             |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_1x4\_grouped.py    |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_2x2.py             |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/delta\_looparray\_network.py         |       28 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/folded\_invveearray.py               |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/hentenna\_array.py                   |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/hourglass\_array.py                  |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/invveearray.py                       |        8 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/lumped\_coupled\_pair.py             |       13 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/moxonarray.py                        |        7 |        0 |    100% |           |
| src/antennaknobs/designs/arrays/yagiarray.py                         |        7 |        0 |    100% |           |
| src/antennaknobs/designs/beams/\_\_init\_\_.py                       |        0 |        0 |    100% |           |
| src/antennaknobs/designs/beams/hb9cv.py                              |       27 |        0 |    100% |           |
| src/antennaknobs/designs/beams/hexbeam.py                            |       43 |        0 |    100% |           |
| src/antennaknobs/designs/beams/moxon.py                              |       34 |        0 |    100% |           |
| src/antennaknobs/designs/beams/moxon\_turnstile.py                   |       32 |        0 |    100% |           |
| src/antennaknobs/designs/beams/owa\_yagi.py                          |       27 |        0 |    100% |           |
| src/antennaknobs/designs/beams/owa\_yagi\_6el.py                     |       28 |        0 |    100% |           |
| src/antennaknobs/designs/beams/phased\_driver\_yagi.py               |       36 |        0 |    100% |           |
| src/antennaknobs/designs/beams/yagi.py                               |       32 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/\_\_init\_\_.py                   |        0 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/discone.py                        |       26 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/g5rv.py                           |       20 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/lpda.py                           |       44 |        0 |    100% |           |
| src/antennaknobs/designs/broadband/t2fd.py                           |       22 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/\_\_init\_\_.py                     |        0 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/dipole\_turnstile.py                |       13 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/folded\_invvee.py                   |       23 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/folded\_invvee\_balun.py            |       10 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/invvee.py                           |       24 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/invvee\_apex.py                     |       15 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/invvee\_catenary.py                 |       64 |        1 |     98% |       400 |
| src/antennaknobs/designs/dipoles/invvee\_coax\_station.py            |        9 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/koch\_dipole.py                     |       37 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/ocf\_dipole.py                      |       18 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/pota\_invvee.py                     |        5 |        0 |    100% |           |
| src/antennaknobs/designs/dipoles/short\_dipole\_loaded.py            |       11 |        0 |    100% |           |
| src/antennaknobs/designs/loops/\_\_init\_\_.py                       |        0 |        0 |    100% |           |
| src/antennaknobs/designs/loops/bisquare.py                           |       19 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop.py                        |       25 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_flyby.py                 |       34 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_reflected.py             |       27 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_slanted.py               |       32 |        0 |    100% |           |
| src/antennaknobs/designs/loops/delta\_loop\_topdown.py               |       26 |        0 |    100% |           |
| src/antennaknobs/designs/loops/diamond\_loop.py                      |       26 |        0 |    100% |           |
| src/antennaknobs/designs/loops/diamond\_loop\_turnstile.py           |       32 |        0 |    100% |           |
| src/antennaknobs/designs/loops/horizontal\_loop.py                   |       19 |        0 |    100% |           |
| src/antennaknobs/designs/loops/horizontal\_loop\_drone.py            |       19 |        0 |    100% |           |
| src/antennaknobs/designs/loops/inv\_delta\_loop.py                   |       25 |        0 |    100% |           |
| src/antennaknobs/designs/loops/quad.py                               |       29 |        0 |    100% |           |
| src/antennaknobs/designs/loops/skyloop\_lmatch.py                    |       10 |        0 |    100% |           |
| src/antennaknobs/designs/loops/triangular\_skyloop.py                |       21 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/\_\_init\_\_.py                   |        0 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/fandipole.py                      |       57 |        1 |     98% |       124 |
| src/antennaknobs/designs/multiband/hexbeam\_5band.py                 |       99 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/trap\_dipole.py                   |       28 |        0 |    100% |           |
| src/antennaknobs/designs/multiband/trap\_fan\_dipole.py              |       77 |        3 |     96% |247, 308, 314 |
| src/antennaknobs/designs/multiband/twoband\_fan\_dipole.py           |       72 |       12 |     83% |   234-246 |
| src/antennaknobs/designs/specialty/\_\_init\_\_.py                   |        0 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/bowtie.py                         |       17 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/buried\_dipole.py                 |       10 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/continuous\_helix.py              |       37 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/faceted\_helix.py                 |       37 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hentenna.py                       |       33 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hentenna\_slant.py                |       43 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hourglass.py                      |       33 |        0 |    100% |           |
| src/antennaknobs/designs/specialty/hourglass\_slant.py               |       37 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/\_\_init\_\_.py                   |        0 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/bobtail.py                        |       15 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/bruce.py                          |       35 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/buried\_radial\_vertical.py       |       56 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/challenger.py                     |       25 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/dominator.py                      |       23 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/elevated\_buried\_counterpoise.py |       26 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/elt\_whip.py                      |      115 |        2 |     98% |   328-329 |
| src/antennaknobs/designs/verticals/four\_square.py                   |       26 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/half\_square.py                   |       20 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/inverted\_l.py                    |       25 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/inverted\_l\_tmatch.py            |       10 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/jpole.py                          |       16 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/phased\_verticals.py              |       22 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/pota\_performer.py                |       30 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/raised\_vertical.py               |       22 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/rectangle.py                      |       24 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/right\_angle\_delta.py            |       25 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/stub\_matched\_vertical.py        |       12 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/tri\_moxon.py                     |       41 |        0 |    100% |           |
| src/antennaknobs/designs/verticals/vertical.py                       |       19 |        0 |    100% |           |
| src/antennaknobs/designs/wire/\_\_init\_\_.py                        |        0 |        0 |    100% |           |
| src/antennaknobs/designs/wire/doublet\_balanced\_tuner.py            |       16 |        0 |    100% |           |
| src/antennaknobs/designs/wire/doublet\_ladder\_tuner.py              |       15 |        0 |    100% |           |
| src/antennaknobs/designs/wire/edz.py                                 |       20 |        0 |    100% |           |
| src/antennaknobs/designs/wire/efhw\_sloper.py                        |       24 |        0 |    100% |           |
| src/antennaknobs/designs/wire/expanded\_lazy\_h.py                   |       25 |        0 |    100% |           |
| src/antennaknobs/designs/wire/lazy\_h.py                             |       21 |        0 |    100% |           |
| src/antennaknobs/designs/wire/longwire.py                            |       16 |        0 |    100% |           |
| src/antennaknobs/designs/wire/rhombic.py                             |       23 |        0 |    100% |           |
| src/antennaknobs/designs/wire/sterba.py                              |       54 |        0 |    100% |           |
| src/antennaknobs/designs/wire/sterba\_bl.py                          |       74 |        0 |    100% |           |
| src/antennaknobs/designs/wire/sterba\_tl.py                          |       60 |        0 |    100% |           |
| src/antennaknobs/designs/wire/terminated\_longwire.py                |       19 |        0 |    100% |           |
| src/antennaknobs/designs/wire/vbeam.py                               |       19 |        0 |    100% |           |
| src/antennaknobs/designs/wire/w8jk.py                                |       22 |        0 |    100% |           |
| src/antennaknobs/designs/wire/zepp.py                                |       15 |        0 |    100% |           |
| src/antennaknobs/drone.py                                            |      131 |        4 |     97% |208, 249-250, 261 |
| src/antennaknobs/engine.py                                           |      285 |        7 |     98% |109, 365, 367, 588, 636, 758, 764 |
| src/antennaknobs/engine\_capture.py                                  |       27 |        3 |     89% |     60-62 |
| src/antennaknobs/engines/\_\_init\_\_.py                             |        8 |        2 |     75% |       3-4 |
| src/antennaknobs/engines/\_external.py                               |       12 |        0 |    100% |           |
| src/antennaknobs/engines/\_nec\_wire.py                              |       34 |        0 |    100% |           |
| src/antennaknobs/engines/momwire.py                                  |      850 |       30 |     96% |160, 350-356, 559, 563, 565, 816, 1251, 1619, 1625-1630, 1826, 1877, 2145, 2369-2385 |
| src/antennaknobs/engines/nec2.py                                     |      360 |       21 |     94% |188, 201, 256, 259, 270-273, 502, 531, 538, 552-553, 569, 574, 589, 602, 708, 731, 744, 787 |
| src/antennaknobs/engines/nec5.py                                     |      680 |      149 |     78% |168-169, 228, 241-242, 362, 393, 460, 501, 519, 528, 534, 539, 546, 573, 620, 649, 651, 653, 679, 702, 705, 735, 738, 740-743, 777-786, 790-798, 808-815, 829-848, 884, 1146, 1280-1283, 1286, 1313, 1320, 1334-1335, 1351, 1356, 1363-1385, 1402-1403, 1416, 1423, 1431-1451, 1512-1542, 1549-1550, 1560-1573 |
| src/antennaknobs/engines/pynec.py                                    |      495 |       42 |     92% |9-10, 79-81, 174, 423-428, 544, 560, 591, 606, 616, 647, 654, 688, 780, 790, 796, 810, 934-935, 1132, 1155-1184 |
| src/antennaknobs/far\_field.py                                       |      184 |        2 |     99% |    92, 96 |
| src/antennaknobs/ferrite.py                                          |      116 |        5 |     96% |289, 292, 300-301, 355 |
| src/antennaknobs/file\_designs.py                                    |       87 |        2 |     98% |  184, 212 |
| src/antennaknobs/fit.py                                              |      221 |       14 |     94% |247, 265, 277-278, 304, 314, 346, 350-352, 387, 402, 412-413 |
| src/antennaknobs/geometry.py                                         |      234 |        6 |     97% |116, 138-139, 143, 174, 219 |
| src/antennaknobs/in\_medium.py                                       |       59 |        0 |    100% |           |
| src/antennaknobs/measured.py                                         |       61 |        0 |    100% |           |
| src/antennaknobs/module.py                                           |       87 |        4 |     95% |89, 94, 164, 195 |
| src/antennaknobs/nec5\_export.py                                     |       17 |        0 |    100% |           |
| src/antennaknobs/nec\_export.py                                      |      108 |        4 |     96% |146, 245, 264, 284 |
| src/antennaknobs/nec\_import.py                                      |     1809 |       81 |     96% |190-191, 593, 679, 809, 916, 995, 1100, 1191, 1300, 1541, 1548, 1750, 1769, 1779, 1920, 1936, 1986, 1992, 2000, 2024, 2033, 2056, 2071, 2075, 2158, 2181-2191, 2213-2229, 2354, 2356, 2358, 2376, 2378, 2380, 2385, 2391-2392, 2411, 2485, 2508, 2545, 2777, 2786, 2791, 2822, 2841, 2866, 2915, 3003-3006, 3008, 3261, 3557-3563, 3645, 3848, 4057 |
| src/antennaknobs/network.py                                          |      116 |        4 |     97% |159, 358, 364, 378 |
| src/antennaknobs/network\_reduce.py                                  |        3 |        0 |    100% |           |
| src/antennaknobs/opt.py                                              |       90 |       14 |     84% |54-55, 57-60, 65-66, 72-76, 153 |
| src/antennaknobs/plane.py                                            |       74 |        5 |     93% |59, 92, 158, 161-162 |
| src/antennaknobs/schematic.py                                        |      734 |       85 |     88% |199, 330, 366, 386, 398-404, 426, 523, 536, 616, 663-664, 714, 745, 749, 868-869, 889, 902, 1149, 1156, 1258-1260, 1271-1272, 1289, 1332, 1346-1364, 1369-1376, 1389-1392, 1500-1515, 1536-1544, 1552, 1713, 1719, 1732, 1747, 1775-1776, 1780, 1783 |
| src/antennaknobs/serialize.py                                        |       83 |        6 |     93% |32-34, 54, 91, 103 |
| src/antennaknobs/settings\_file.py                                   |       41 |        2 |     95% |     69-70 |
| src/antennaknobs/sim.py                                              |        2 |        0 |    100% |           |
| src/antennaknobs/simnec\_export.py                                   |      248 |       27 |     89% |191, 369, 404, 410, 434, 442, 447, 457, 503, 510, 512-527, 534, 538, 580, 592, 632, 832-835, 855 |
| src/antennaknobs/simnec\_import.py                                   |      296 |       21 |     93% |155-156, 213, 277, 303, 322, 359-360, 380, 425, 456, 459-460, 572-573, 577-578, 633-634, 637-638 |
| src/antennaknobs/smith\_chart.py                                     |       44 |        0 |    100% |           |
| src/antennaknobs/station.py                                          |       68 |        3 |     96% |235-236, 313 |
| src/antennaknobs/sweep.py                                            |      376 |       60 |     84% |213-224, 466, 469-524, 605, 755-756, 765-767, 790-791, 801, 809-856 |
| src/antennaknobs/terrain.py                                          |      139 |        9 |     94% |54, 56, 58, 77, 120, 157-159, 299 |
| src/antennaknobs/terrain\_utd.py                                     |      316 |        5 |     98% |118-119, 138, 189, 230 |
| src/antennaknobs/touchstone.py                                       |      150 |        5 |     97% |184, 213, 292, 304, 309 |
| src/antennaknobs/transform.py                                        |       42 |        1 |     98% |        62 |
| src/antennaknobs/user\_designs.py                                    |       75 |        4 |     95% |42, 52, 117, 144 |
| src/antennaknobs/vna.py                                              |      112 |       17 |     85% |83, 96-105, 108, 112, 115, 129-134, 260 |
| src/antennaknobs/web/\_\_init\_\_.py                                 |        0 |        0 |    100% |           |
| src/antennaknobs/web/adapter.py                                      |     1593 |      123 |     92% |86-88, 269, 742, 1010, 1052, 1055, 1084, 1087, 1284, 1540, 1636-1637, 1671, 1675, 1726, 1729, 1734-1737, 1740, 1750, 1755, 1919, 1929, 1943, 1945, 1947, 1980, 1990-1991, 2377, 2521, 2523, 2529-2533, 2537, 2683-2688, 2941, 2977, 2980, 2983, 2995, 2998, 3016, 3070-3071, 3159-3161, 3169, 3173-3174, 3234-3235, 3245-3247, 3306, 3310, 3337, 3340, 3343, 3364, 3367, 3370-3380, 3418, 3501-3502, 3533-3534, 3559-3560, 3844-3845, 3848-3849, 3949, 3956, 3980-3981, 4043-4044, 4083, 4664-4686, 4773, 4871, 5084, 5106-5108, 5111, 5116-5117 |
| src/antennaknobs/web/cost.py                                         |       43 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_\_init\_\_.py                        |       20 |        1 |     95% |        59 |
| src/antennaknobs/web/examples/\_base.py                              |      110 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_feedline.py                          |       29 |        2 |     93% |     73-74 |
| src/antennaknobs/web/lane.py                                         |      123 |        5 |     96% |133, 151, 154-156 |
| src/antennaknobs/web/nec2\_backend.py                                |       30 |       20 |     33% |39-43, 47-51, 58-61, 67-72 |
| src/antennaknobs/web/nec5\_backend.py                                |       30 |       16 |     47% |41, 45-49, 56-59, 65-70 |
| src/antennaknobs/web/optimize.py                                     |      413 |       57 |     86% |121, 129, 135, 144, 149, 153, 182, 191, 244, 250, 257, 263, 269-270, 277, 283, 304-314, 318-322, 333, 338, 342, 348, 350-351, 354-371, 518, 534, 812-813 |
| src/antennaknobs/web/progress\_stream.py                             |      120 |        1 |     99% |       243 |
| src/antennaknobs/web/pynec\_backend.py                               |       93 |       38 |     59% |20-22, 74-92, 119, 130-133, 179-186, 198-208, 215-220 |
| src/antennaknobs/web/server.py                                       |     1289 |       97 |     92% |114-116, 201-205, 308-309, 311, 369-370, 445, 940-942, 1061, 1116, 1219-1222, 1779-1782, 1830, 1850-1852, 1903, 1914, 1940, 1953-1956, 1968-1980, 1987, 2012, 2039-2053, 2102-2104, 2152, 2166, 2195-2196, 2221-2222, 2254, 2334-2341, 2370, 2439, 2454, 2488-2489, 2492, 2527, 2537-2540, 2565, 2568-2574, 2628, 2656, 2659-2660, 2746, 2764-2767, 2783, 2943, 2957, 3350, 3467, 3509, 3511, 3515-3516, 3529, 3540, 3544, 3613-3614 |
| src/antennaknobs/web/settings.py                                     |      325 |       28 |     91% |182, 196-197, 211-212, 215, 223, 238, 247, 259, 263, 274, 281-282, 291-292, 317-318, 351, 377, 389, 447-448, 627-628, 635-637 |
| src/antennaknobs/web/tracker.py                                      |      254 |       30 |     88% |207, 213, 256, 272-273, 302-303, 306, 317-319, 326-327, 333, 415, 438-442, 445-454, 481 |
| src/antennaknobs/web/user\_designs.py                                |       64 |        6 |     91% |60-61, 92-93, 98-99 |
| src/antennaknobs/wire\_catalog.py                                    |      183 |        0 |    100% |           |
| **TOTAL**                                                            | **18083** | **1161** | **94%** |           |


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