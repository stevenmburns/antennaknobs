# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                 |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/antennaknobs/\_\_init\_\_.py                                     |       23 |        2 |     91% |   115-116 |
| src/antennaknobs/\_\_main\_\_.py                                     |        0 |        0 |    100% |           |
| src/antennaknobs/builder.py                                          |      321 |        1 |     99% |       380 |
| src/antennaknobs/catenary.py                                         |      354 |       16 |     95% |293, 333, 547-550, 555-556, 558, 572-574, 601, 698, 706, 818 |
| src/antennaknobs/cell.py                                             |       70 |        1 |     99% |        88 |
| src/antennaknobs/cli.py                                              |      715 |       42 |     94% |71, 77, 269, 288, 334, 349, 379-380, 618-619, 715, 720, 1129, 1278-1282, 1375, 1385, 1387, 1472, 1508, 1543-1550, 1557, 1597, 1601-1611, 1692, 1846, 1923, 2002-2003, 2033-2034 |
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
| src/antennaknobs/engine.py                                           |      319 |        7 |     98% |109, 436, 438, 677, 756, 880, 886 |
| src/antennaknobs/engine\_capture.py                                  |       27 |        3 |     89% |     60-62 |
| src/antennaknobs/engines/\_\_init\_\_.py                             |        8 |        2 |     75% |       3-4 |
| src/antennaknobs/engines/\_external.py                               |       12 |        0 |    100% |           |
| src/antennaknobs/engines/\_nec\_wire.py                              |       34 |        0 |    100% |           |
| src/antennaknobs/engines/momwire.py                                  |      849 |       30 |     96% |166, 356-362, 565, 569, 571, 822, 1284, 1666, 1672-1677, 1888, 1939, 2217, 2442-2458 |
| src/antennaknobs/engines/nec2.py                                     |      396 |       22 |     94% |139, 152, 154, 243, 256, 311, 314, 325-328, 605, 612, 626-627, 643, 648, 664, 773, 820, 833, 885 |
| src/antennaknobs/engines/nec5.py                                     |      742 |      103 |     86% |170-171, 230, 243-244, 365-367, 457, 488, 555, 596, 614, 623, 629, 634, 641, 668, 715, 804, 925, 1200, 1339-1342, 1345, 1372, 1379, 1393-1394, 1410, 1415, 1429-1448, 1465-1466, 1479, 1510-1520, 1586-1616, 1625, 1637-1650, 1667-1677 |
| src/antennaknobs/engines/pynec.py                                    |      526 |       43 |     92% |9-10, 79-81, 174, 444-449, 565, 581, 612, 627, 637, 668, 675, 718, 810, 820, 826, 840, 964-965, 1163, 1186-1215, 1326 |
| src/antennaknobs/far\_field.py                                       |      184 |        2 |     99% |    92, 96 |
| src/antennaknobs/ferrite.py                                          |      116 |        5 |     96% |289, 292, 300-301, 355 |
| src/antennaknobs/file\_designs.py                                    |       94 |        5 |     95% |197, 199-201, 229 |
| src/antennaknobs/fit.py                                              |      221 |       14 |     94% |247, 265, 277-278, 304, 314, 346, 350-352, 387, 402, 412-413 |
| src/antennaknobs/geometry.py                                         |      234 |        6 |     97% |116, 138-139, 143, 174, 219 |
| src/antennaknobs/in\_medium.py                                       |       59 |        0 |    100% |           |
| src/antennaknobs/measured.py                                         |       61 |        0 |    100% |           |
| src/antennaknobs/module.py                                           |       87 |        4 |     95% |89, 94, 164, 195 |
| src/antennaknobs/nec5\_export.py                                     |       17 |        0 |    100% |           |
| src/antennaknobs/nec\_export.py                                      |      127 |        4 |     97% |185, 298, 317, 337 |
| src/antennaknobs/nec\_import.py                                      |     1998 |      103 |     95% |220-221, 330, 335, 732, 810-811, 815, 818, 951, 1058, 1137, 1210, 1283, 1383, 1469, 1487-1488, 1563, 1687, 1941-1942, 1969, 1976, 2180, 2199, 2209, 2350, 2366, 2416, 2422, 2430, 2454, 2463, 2486, 2501, 2505, 2588, 2611-2621, 2643-2659, 2784, 2786, 2788, 2806, 2808, 2810, 2815, 2821-2822, 2841, 2915, 2938, 2975, 3207, 3216, 3221, 3252, 3271, 3296, 3345, 3440-3443, 3445, 3752-3754, 3782-3784, 3800, 4029-4035, 4043-4049, 4123-4129, 4211, 4419, 4642 |
| src/antennaknobs/network.py                                          |      116 |        4 |     97% |159, 358, 364, 378 |
| src/antennaknobs/network\_reduce.py                                  |        3 |        0 |    100% |           |
| src/antennaknobs/opt.py                                              |       90 |       14 |     84% |54-55, 57-60, 65-66, 72-76, 153 |
| src/antennaknobs/plane.py                                            |       74 |        5 |     93% |59, 92, 158, 161-162 |
| src/antennaknobs/schematic.py                                        |      734 |       85 |     88% |199, 330, 366, 386, 398-404, 426, 523, 536, 616, 663-664, 714, 745, 749, 868-869, 889, 902, 1149, 1156, 1258-1260, 1271-1272, 1289, 1332, 1346-1364, 1369-1376, 1389-1392, 1500-1515, 1536-1544, 1552, 1713, 1719, 1732, 1747, 1775-1776, 1780, 1783 |
| src/antennaknobs/serialize.py                                        |       83 |        6 |     93% |32-34, 54, 91, 103 |
| src/antennaknobs/settings\_file.py                                   |       52 |        2 |     96% |     77-78 |
| src/antennaknobs/sim.py                                              |        2 |        0 |    100% |           |
| src/antennaknobs/simnec\_export.py                                   |      251 |       27 |     89% |195, 373, 408, 414, 438, 446, 451, 461, 507, 514, 516-531, 538, 542, 584, 596, 636, 837-840, 860 |
| src/antennaknobs/simnec\_import.py                                   |      308 |       19 |     94% |227, 292, 318, 337, 367-368, 427, 480, 508, 511-512, 624-625, 629-630, 674-675, 678-679 |
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
| src/antennaknobs/web/adapter.py                                      |     1621 |      110 |     93% |86-88, 270, 743, 1011, 1053, 1056, 1085, 1088, 1285, 1541, 1637-1638, 1672, 1676, 1727, 1730, 1735-1738, 1741, 1751, 1756, 1920, 1930, 1944, 1946, 1948, 1981, 1991-1992, 2378, 2531, 2533, 2543, 2546-2548, 2698-2703, 2963, 2999, 3002, 3005, 3017, 3020, 3038, 3092-3093, 3210-3212, 3220, 3224-3225, 3286-3287, 3297-3299, 3358, 3362, 3389, 3392, 3395, 3416, 3419, 3422-3432, 3470, 3553-3554, 3585-3586, 3611-3612, 3896-3897, 3900-3901, 4001, 4008, 4032-4033, 4095-4096, 4135, 4748-4761, 4848, 4946, 5159, 5181-5183, 5186, 5191-5192 |
| src/antennaknobs/web/cost.py                                         |       43 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_\_init\_\_.py                        |       20 |        1 |     95% |        59 |
| src/antennaknobs/web/examples/\_base.py                              |      110 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_feedline.py                          |       29 |        2 |     93% |     73-74 |
| src/antennaknobs/web/lane.py                                         |      123 |        5 |     96% |133, 151, 154-156 |
| src/antennaknobs/web/nec2\_backend.py                                |       30 |       20 |     33% |39-43, 47-51, 58-61, 67-72 |
| src/antennaknobs/web/nec5\_backend.py                                |       30 |       16 |     47% |41, 45-49, 56-59, 65-70 |
| src/antennaknobs/web/optimize.py                                     |      413 |       57 |     86% |121, 129, 135, 144, 149, 153, 182, 191, 244, 250, 257, 263, 269-270, 277, 283, 304-314, 318-322, 333, 338, 342, 348, 350-351, 354-371, 518, 534, 812-813 |
| src/antennaknobs/web/progress\_stream.py                             |      120 |        1 |     99% |       243 |
| src/antennaknobs/web/pynec\_backend.py                               |       95 |       38 |     60% |20-22, 75-93, 120, 131-134, 199-206, 218-228, 235-240 |
| src/antennaknobs/web/server.py                                       |     1293 |       97 |     92% |114-116, 201-205, 308-309, 311, 369-370, 445, 946-948, 1067, 1122, 1225-1228, 1799-1802, 1850, 1870-1872, 1923, 1934, 1960, 1973-1976, 1988-2000, 2007, 2032, 2059-2073, 2122-2124, 2172, 2186, 2215-2216, 2241-2242, 2274, 2352-2359, 2388, 2457, 2472, 2506-2507, 2510, 2545, 2555-2558, 2583, 2586-2592, 2646, 2674, 2677-2678, 2764, 2782-2785, 2801, 2961, 2975, 3368, 3485, 3527, 3529, 3533-3534, 3547, 3558, 3562, 3631-3632 |
| src/antennaknobs/web/settings.py                                     |      325 |       28 |     91% |182, 196-197, 211-212, 215, 223, 238, 247, 259, 263, 274, 281-282, 291-292, 317-318, 351, 377, 389, 447-448, 627-628, 635-637 |
| src/antennaknobs/web/tracker.py                                      |      254 |       30 |     88% |207, 213, 256, 272-273, 302-303, 306, 317-319, 326-327, 333, 415, 438-442, 445-454, 481 |
| src/antennaknobs/web/user\_designs.py                                |       68 |        6 |     91% |60-61, 92-93, 98-99 |
| src/antennaknobs/wire\_catalog.py                                    |      188 |        0 |    100% |           |
| **TOTAL**                                                            | **18532** | **1127** | **94%** |           |


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