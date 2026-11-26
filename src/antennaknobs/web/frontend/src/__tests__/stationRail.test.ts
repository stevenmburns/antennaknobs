// The station rail's chain <-> JSON serialisation (src/lib/stationRail.ts):
// the page holds rails as JSON-shaped data and posts them back, so a chain
// must survive the trip unchanged, write one text however its keys were
// ordered, and refuse a malformed chain with a reason before it is posted.
import { describe, expect, it } from "vitest";
import {
  CHAIN_VERSION,
  chainFromData,
  chainFromJson,
  chainToJson,
  sameChain,
  StationChainError,
  withoutItem,
  type StationChain,
} from "../lib/stationRail";

// Invented values, in the shapes the server writes (a frozen chain carries
// its instance and node names).
const CHAIN: StationChain = {
  version: CHAIN_VERSION,
  rig: "shack",
  items: [
    { kind: "t_tuner", c1_pF: 90, c2_pF: 400, l_uH: 3.3, ql: 150, name: "tuner" },
    { kind: "shorted_stub", freq_mhz: 14.2, length_wl: 0.1, cable: "RG-8X", name: "stub" },
    { kind: "cable", cable: "openwire-600", length_m: 12.5, node: "li" },
  ],
};

describe("chain JSON", () => {
  it("round-trips a chain unchanged", () => {
    const back = chainFromJson(chainToJson(CHAIN));
    expect(back).toEqual(CHAIN);
    expect(chainToJson(back)).toBe(chainToJson(CHAIN));
  });

  it("writes one text whatever order the keys arrived in", () => {
    const shuffled = JSON.parse(
      JSON.stringify({
        items: CHAIN.items.map((it) =>
          Object.fromEntries(Object.entries(it).reverse()),
        ),
        rig: CHAIN.rig,
        version: CHAIN.version,
      }),
    ) as unknown;
    expect(chainToJson(chainFromData(shuffled))).toBe(chainToJson(CHAIN));
    expect(sameChain(chainFromData(shuffled), CHAIN)).toBe(true);
  });

  it("puts the kind first and sorts the rest", () => {
    const text = chainToJson(CHAIN);
    expect(text.startsWith('{"version":1,"rig":"shack","items":[{"kind":"t_tuner","c1_pF":90')).toBe(
      true,
    );
  });

  it("drops null values and fills a missing version and rig", () => {
    const c = chainFromData({ items: [{ kind: "balun", n: 1, qlmag: null }] });
    expect(c).toEqual({ version: 1, rig: "rig", items: [{ kind: "balun", n: 1 }] });
  });

  it.each([
    ["[]", "a chain is an object"],
    ["{", "not JSON"],
    ['{"version": 2, "items": []}', "chain version 2"],
    ['{"rig": "1x"}', "not an identifier"],
    ['{"items": {}}', "items are a list"],
    ['{"items": [{"n": 1}]}', "names its kind"],
    ['{"items": [{"kind": "cable", "length_m": [1]}]}', "number or text"],
    ['{"items": [{"kind": "balun", "name": "a b"}]}', "not an identifier"],
    ['{"design": "x", "items": []}', 'no field "design"'],
  ])("refuses %s", (text, why) => {
    expect(() => chainFromJson(text)).toThrow(StationChainError);
    expect(() => chainFromJson(text)).toThrow(why);
  });

  it("removes one item and leaves the rest", () => {
    const c = withoutItem(CHAIN, 1);
    expect(c.items.map((it) => it.kind)).toEqual(["t_tuner", "cable"]);
    expect(CHAIN.items).toHaveLength(3);
  });
});
