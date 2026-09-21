# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/stevenmburns/antennaknobs/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                 |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/antennaknobs/\_\_init\_\_.py                                     |       23 |        2 |     91% |   115-116 |
| src/antennaknobs/\_\_main\_\_.py                                     |        0 |        0 |    100% |           |
| src/antennaknobs/builder.py                                          |      321 |        1 |     99% |       380 |
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
| src/antennaknobs/engine.py                                           |      319 |        7 |     98% |109, 436, 438, 677, 756, 880, 886 |
| src/antennaknobs/engine\_capture.py                                  |       27 |        3 |     89% |     60-62 |
| src/antennaknobs/engines/\_\_init\_\_.py                             |        8 |        2 |     75% |       3-4 |
| src/antennaknobs/engines/\_external.py                               |       12 |        0 |    100% |           |
| src/antennaknobs/engines/\_nec\_wire.py                              |       34 |        0 |    100% |           |
| src/antennaknobs/engines/momwire.py                                  |      849 |       30 |     96% |163, 353-359, 562, 566, 568, 819, 1274, 1656, 1662-1667, 1878, 1929, 2205, 2429-2445 |
| src/antennaknobs/engines/nec2.py                                     |      363 |       21 |     94% |188, 201, 256, 259, 270-273, 502, 531, 538, 552-553, 569, 574, 589, 602, 708, 731, 744, 795 |
| src/antennaknobs/engines/nec5.py                                     |      737 |      103 |     86% |170-171, 230, 243-244, 365-367, 456, 487, 554, 595, 613, 622, 628, 633, 640, 667, 714, 803, 919, 1184, 1323-1326, 1329, 1356, 1363, 1377-1378, 1394, 1399, 1413-1432, 1449-1450, 1463, 1494-1504, 1570-1600, 1609, 1621-1634, 1651-1661 |
| src/antennaknobs/engines/pynec.py                                    |      518 |       43 |     92% |9-10, 79-81, 174, 431-436, 552, 568, 599, 614, 624, 655, 662, 696, 788, 798, 804, 818, 942-943, 1141, 1164-1193, 1304 |
| src/antennaknobs/far\_field.py                                       |      184 |        2 |     99% |    92, 96 |
| src/antennaknobs/ferrite.py                                          |      116 |        5 |     96% |289, 292, 300-301, 355 |
| src/antennaknobs/file\_designs.py                                    |       88 |        2 |     98% |  194, 222 |
| src/antennaknobs/fit.py                                              |      221 |       14 |     94% |247, 265, 277-278, 304, 314, 346, 350-352, 387, 402, 412-413 |
| src/antennaknobs/geometry.py                                         |      234 |        6 |     97% |116, 138-139, 143, 174, 219 |
| src/antennaknobs/in\_medium.py                                       |       59 |        0 |    100% |           |
| src/antennaknobs/measured.py                                         |       61 |        0 |    100% |           |
| src/antennaknobs/module.py                                           |       87 |        4 |     95% |89, 94, 164, 195 |
| src/antennaknobs/nec5\_export.py                                     |       17 |        0 |    100% |           |
| src/antennaknobs/nec\_export.py                                      |      122 |        4 |     97% |172, 271, 290, 310 |
| src/antennaknobs/nec\_import.py                                      |     1951 |      101 |     95% |220-221, 678, 756-757, 761, 764, 897, 1004, 1083, 1156, 1229, 1329, 1415, 1433-1434, 1509, 1633, 1887-1888, 1915, 1922, 2126, 2145, 2155, 2296, 2312, 2362, 2368, 2376, 2400, 2409, 2432, 2447, 2451, 2534, 2557-2567, 2589-2605, 2730, 2732, 2734, 2752, 2754, 2756, 2761, 2767-2768, 2787, 2861, 2884, 2921, 3153, 3162, 3167, 3198, 3217, 3242, 3291, 3386-3389, 3391, 3677-3679, 3707-3709, 3725, 3954-3960, 3968-3974, 4048-4054, 4136, 4339, 4548 |
| src/antennaknobs/network.py                                          |      116 |        4 |     97% |159, 358, 364, 378 |
| src/antennaknobs/network\_reduce.py                                  |        3 |        0 |    100% |           |
| src/antennaknobs/opt.py                                              |       90 |       14 |     84% |54-55, 57-60, 65-66, 72-76, 153 |
| src/antennaknobs/plane.py                                            |       74 |        5 |     93% |59, 92, 158, 161-162 |
| src/antennaknobs/schematic.py                                        |      734 |       85 |     88% |199, 330, 366, 386, 398-404, 426, 523, 536, 616, 663-664, 714, 745, 749, 868-869, 889, 902, 1149, 1156, 1258-1260, 1271-1272, 1289, 1332, 1346-1364, 1369-1376, 1389-1392, 1500-1515, 1536-1544, 1552, 1713, 1719, 1732, 1747, 1775-1776, 1780, 1783 |
| src/antennaknobs/serialize.py                                        |       83 |        6 |     93% |32-34, 54, 91, 103 |
| src/antennaknobs/settings\_file.py                                   |       52 |        2 |     96% |     77-78 |
| src/antennaknobs/sim.py                                              |        2 |        0 |    100% |           |
| src/antennaknobs/simnec\_export.py                                   |      248 |       27 |     89% |191, 369, 404, 410, 434, 442, 447, 457, 503, 510, 512-527, 534, 538, 580, 592, 632, 832-835, 855 |
| src/antennaknobs/simnec\_import.py                                   |      283 |       21 |     93% |137-138, 195, 259, 285, 304, 334-335, 356, 401, 429, 432-433, 545-546, 550-551, 595-596, 599-600 |
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
| src/antennaknobs/web/adapter.py                                      |     1606 |      111 |     93% |86-88, 270, 743, 1011, 1053, 1056, 1085, 1088, 1285, 1541, 1637-1638, 1672, 1676, 1727, 1730, 1735-1738, 1741, 1751, 1756, 1920, 1930, 1944, 1946, 1948, 1981, 1991-1992, 2378, 2522, 2524, 2530-2534, 2684-2689, 2942, 2978, 2981, 2984, 2996, 2999, 3017, 3071-3072, 3187-3189, 3197, 3201-3202, 3263-3264, 3274-3276, 3335, 3339, 3366, 3369, 3372, 3393, 3396, 3399-3409, 3447, 3530-3531, 3562-3563, 3588-3589, 3873-3874, 3877-3878, 3978, 3985, 4009-4010, 4072-4073, 4112, 4724-4737, 4824, 4922, 5135, 5157-5159, 5162, 5167-5168 |
| src/antennaknobs/web/cost.py                                         |       43 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_\_init\_\_.py                        |       20 |        1 |     95% |        59 |
| src/antennaknobs/web/examples/\_base.py                              |      110 |        0 |    100% |           |
| src/antennaknobs/web/examples/\_feedline.py                          |       29 |        2 |     93% |     73-74 |
| src/antennaknobs/web/lane.py                                         |      123 |        5 |     96% |133, 151, 154-156 |
| src/antennaknobs/web/nec2\_backend.py                                |       30 |       20 |     33% |39-43, 47-51, 58-61, 67-72 |
| src/antennaknobs/web/nec5\_backend.py                                |       30 |       16 |     47% |41, 45-49, 56-59, 65-70 |
| src/antennaknobs/web/optimize.py                                     |      413 |       57 |     86% |121, 129, 135, 144, 149, 153, 182, 191, 244, 250, 257, 263, 269-270, 277, 283, 304-314, 318-322, 333, 338, 342, 348, 350-351, 354-371, 518, 534, 812-813 |
| src/antennaknobs/web/progress\_stream.py                             |      120 |        1 |     99% |       243 |
| src/antennaknobs/web/pynec\_backend.py                               |       95 |       38 |     60% |20-22, 75-93, 120, 131-134, 183-190, 202-212, 219-224 |
| src/antennaknobs/web/server.py                                       |     1293 |       97 |     92% |114-116, 201-205, 308-309, 311, 369-370, 445, 946-948, 1067, 1122, 1225-1228, 1799-1802, 1850, 1870-1872, 1923, 1934, 1960, 1973-1976, 1988-2000, 2007, 2032, 2059-2073, 2122-2124, 2172, 2186, 2215-2216, 2241-2242, 2274, 2352-2359, 2388, 2457, 2472, 2506-2507, 2510, 2545, 2555-2558, 2583, 2586-2592, 2646, 2674, 2677-2678, 2764, 2782-2785, 2801, 2961, 2975, 3368, 3485, 3527, 3529, 3533-3534, 3547, 3558, 3562, 3631-3632 |
| src/antennaknobs/web/settings.py                                     |      325 |       28 |     91% |182, 196-197, 211-212, 215, 223, 238, 247, 259, 263, 274, 281-282, 291-292, 317-318, 351, 377, 389, 447-448, 627-628, 635-637 |
| src/antennaknobs/web/tracker.py                                      |      254 |       30 |     88% |207, 213, 256, 272-273, 302-303, 306, 317-319, 326-327, 333, 415, 438-442, 445-454, 481 |
| src/antennaknobs/web/user\_designs.py                                |       68 |        6 |     91% |60-61, 92-93, 98-99 |
| src/antennaknobs/wire\_catalog.py                                    |      188 |        0 |    100% |           |
| **TOTAL**                                                            | **18383** | **1124** | **94%** |           |


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