/** A chain's name as a small coloured badge: AH, Jumbo, Lidl. */
export function ChainBadge({ chain }: { chain: string }) {
  return <span className={`chain chain-${chain.toLowerCase()}`}>{chain}</span>;
}
