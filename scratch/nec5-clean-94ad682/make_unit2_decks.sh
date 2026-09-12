#!/usr/bin/env bash
# The unit-2 headline set: the eight corpus decks the clean room named, plus the
# three 6mYagi spellings that decompose where its 42 s actually goes.
#
# The three spellings, and the care the FR one needs:
#   as-shipped  FR 0 41 0 0 50 0.1   +  RP 0 361 361 ...   (130,321 points x 41 f)
#   RP-to-XQ    the same 41 frequencies, SOLVE ONLY
#   one-FR      ONE frequency, full pattern -- field 3 (NFRQ) -> 1 and field 7
#               (DELFRQ) -> 0, KEEPING field 6 (FMHZ = 50). Zeroing field 6
#               instead writes a 0 MHz deck, which runs and means nothing.
set -u
T="$HOME/nec5-timing"
SRC="$T/nec5"
OUT="$T/decks-unit2"
rm -rf "$OUT"; mkdir -p "$OUT"

copy() {  # <relpath> <name>
  cp "$SRC/$1" "$OUT/$2.nec"
}
copy "opennec/6mYagi-Onec.nec"                                              "6mYagi-Onec"
copy "sokyrad/unsorted/15m_20m_jumper_half_square.nec"                      "15m_20m_jumper_half_square"
copy "sokyrad/unsorted/fan_dipole_80_40_20_10_6m_20m_height_voltage_balun.nec" "fan_dipole_80_40_20_10_6m"
copy "g1ojs/Trapped/TRAPx2_V.nec"                                           "TRAPx2_V"
copy "antenna-modeling/gbhoyt.nec"                                          "gbhoyt"
copy "antenna-modeling/2m-sat-yagi/2m-sat-candidate2-thick-crossed-wide.nec" "2m-sat-candidate2"
copy "antenna-modeling/yagitools/ON6MU.nec"                                 "ON6MU"
copy "w8io/LP144-35-MAXFB.nec"                                              "LP144-35-MAXFB"

# the two derived 6mYagi spellings
sed 's/^RP .*/XQ/' "$SRC/opennec/6mYagi-Onec.nec" > "$OUT/6mYagi-RPtoXQ.nec"
awk '$1=="FR" {$3="1"; $7="0"; print; next} {print}' \
    "$SRC/opennec/6mYagi-Onec.nec" > "$OUT/6mYagi-oneFR.nec"

echo "decks:"
for f in "$OUT"/*.nec; do
  printf "  %-30s %5s segs   %s\n" "$(basename "$f" .nec)" \
    "$(awk '$1=="GW"{s+=$3} END{print s+0}' "$f")" \
    "$(grep -hE '^(FR|RP|NE|NH|XQ)' "$f" | tr '\n' ';')"
done
