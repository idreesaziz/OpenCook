import type { Reaction, RouteNode } from "./types";

function MoleculeCard({ node, onSelect }: { node: RouteNode; onSelect: (value: RouteNode) => void }) {
  const state = node.in_stock ? "stock" : node.reaction ? "intermediate" : "unresolved";
  return <button className={`compound-card ${state}`} onClick={() => onSelect(node)}>
    <span className="compound-depiction"><img src={`/api/v1/molecules/depict-image?smiles=${encodeURIComponent(node.molecule)}`} alt={`Structure of ${node.display_name ?? node.molecule}`} /></span>
    <span className="compound-copy"><strong>{node.display_name ?? "Unnamed compound"}</strong><code>{node.molecule}</code><small>{state}</small></span>
  </button>;
}

function ReactionBar({ reaction, onSelect }: { reaction: Reaction; onSelect: (value: Reaction) => void }) {
  const inferred = reaction.evidence === "computational_proposal";
  return <button className={`reaction-bar ${inferred ? "computational" : ""}`} onClick={() => onSelect(reaction)}><span>{reaction.id}</span><b>{reaction.evidence.replaceAll("_", " ")}</b><small>{Math.round(reaction.confidence * 100)}% {inferred ? "model confidence" : "confidence"}</small></button>;
}

function Branch({ node, onSelect, target = false }: { node: RouteNode; onSelect: (value: RouteNode | Reaction) => void; target?: boolean }) {
  return <div className={`route-branch ${target ? "target-branch" : ""}`}>
    {node.reaction ? <><div className={`precursor-row ${node.precursors.length > 1 ? "joined" : ""}`}>{node.precursors.map((precursor, index) => <Branch key={`${precursor.molecule}-${index}`} node={precursor} onSelect={onSelect} />)}</div><div className="synthesis-line" aria-hidden="true" /><ReactionBar reaction={node.reaction} onSelect={onSelect} /><div className="synthesis-arrow" aria-hidden="true">↓</div></> : null}
    <MoleculeCard node={node} onSelect={onSelect} />
  </div>;
}

export function SynthesisGraph({ root, onSelect }: { root: RouteNode; onSelect: (value: RouteNode | Reaction) => void }) {
  return <section className="route-diagram" aria-label="Synthesis route"><div className="direction-label"><span>STARTING MATERIALS</span><i /><span>TARGET</span></div><div className="route-scroll"><Branch node={root} onSelect={onSelect} target /></div></section>;
}
