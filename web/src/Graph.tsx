import type { Reaction, RouteNode } from "./types";

type SelectHandler = (value: RouteNode | Reaction) => void;

function MoleculeLabel({ node, onSelect }: { node: RouteNode; onSelect: SelectHandler }) {
  const state = node.in_stock
    ? "stock"
    : node.reaction
      ? "intermediate"
      : "unresolved";
  const label = node.display_name ?? "Unnamed compound";

  return (
    <button
      className={`compound-label ${state}`}
      onClick={() => onSelect(node)}
      title={node.display_name ?? node.molecule}
    >
      <span className="compound-depiction">
        <img
          src={`/api/v1/molecules/depict-image?smiles=${encodeURIComponent(node.molecule)}`}
          alt={`Structure of ${node.display_name ?? node.molecule}`}
        />
      </span>
      <strong className="compound-name">{label}</strong>
      <code className="compound-smiles">{node.molecule}</code>
      <small className="compound-state">{state}</small>
    </button>
  );
}

function ReactionLabel({ reaction, onSelect }: { reaction: Reaction; onSelect: SelectHandler }) {
  const inferred = reaction.evidence === "computational_proposal";
  return (
    <button
      className={`reaction-bar ${inferred ? "computational" : ""}`}
      onClick={() => onSelect(reaction)}
      title={reaction.id}
    >
      <span>{reaction.id}</span>
      <b>{reaction.evidence.replaceAll("_", " ")}</b>
      <small>
        {Math.round(reaction.confidence * 100)}% {inferred ? "model confidence" : "confidence"}
      </small>
    </button>
  );
}

function Branch({
  node,
  onSelect,
  target = false,
}: {
  node: RouteNode;
  onSelect: SelectHandler;
  target?: boolean;
}) {
  return (
    <div className={`route-branch ${target ? "target-branch" : ""}`}>
      {node.reaction ? (
        <>
          <div className={`precursor-row ${node.precursors.length > 1 ? "joined" : ""}`}>
            {node.precursors.map((precursor, index) => (
              <Branch
                key={`${precursor.molecule}-${index}`}
                node={precursor}
                onSelect={onSelect}
              />
            ))}
          </div>
          <div className="synthesis-line" aria-hidden="true" />
          <ReactionLabel reaction={node.reaction} onSelect={onSelect} />
          <div className="synthesis-arrow" aria-hidden="true" />
        </>
      ) : null}
      <MoleculeLabel node={node} onSelect={onSelect} />
    </div>
  );
}

export function SynthesisGraph({ root, onSelect }: { root: RouteNode; onSelect: SelectHandler }) {
  return (
    <section className="route-diagram" aria-label="Synthesis route">
      <div className="direction-label">
        <span>STARTING MATERIALS</span>
        <i />
        <span>TARGET</span>
      </div>
      <div className="route-scroll">
        <Branch node={root} onSelect={onSelect} target />
      </div>
    </section>
  );
}
