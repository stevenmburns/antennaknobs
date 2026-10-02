// What the two slot families, solver (A, B, C, ...) and ground (X, Y, Z,
// ...), share about a variable count of slots (AK#1801): the + appends the
// next id of the family's sequence, and a slot past the stock set can be
// removed. Only the LAST slot can: slots run without gaps, as the settings
// file reads them ([slots.D] needs a slot C, [grounds.U] a slot Z), and
// removing one from the middle would leave a gap or rename the slots after
// it under every chart, pin and kept study that names them.

/** A slot family: its ids in order, how many of them the stock set holds,
 *  and the words its sentences use ("solver", "ground"). */
export type SlotFamily = {
  ids: readonly string[];
  stock: number;
  noun: string;
};

/** The next slot's id, or null when the family is full. */
export function nextSlotId(family: SlotFamily, have: readonly string[]): string | null {
  return family.ids.find((id) => !have.includes(id)) ?? null;
}

/** Why slot `id` cannot be removed, or null when it can. */
export function slotRemovalRefusal(
  family: SlotFamily,
  have: readonly string[],
  id: string,
): string | null {
  const i = family.ids.indexOf(id);
  if (i < 0 || !have.includes(id)) return `there is no ${family.noun} slot ${id}`;
  if (i < family.stock) {
    const stock = family.ids.slice(0, family.stock).join(", ");
    return `${stock} are the stock ${family.noun} slots, which stay`;
  }
  const last = family.ids.filter((x) => have.includes(x)).at(-1);
  if (last !== id) {
    return `remove slot ${last} first: ${family.noun} slots run without gaps`;
  }
  return null;
}

/** The id that becomes active when slot `removed` goes: the one before it. */
export function slotBefore(family: SlotFamily, removed: string): string {
  const i = family.ids.indexOf(removed);
  return family.ids[Math.max(i - 1, 0)];
}
