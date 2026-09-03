const elements: Record<string, [string, string]> = {
  O: ["8", "Oxygen"],
  P: ["15", "Phosphorus"],
  N: ["7", "Nitrogen"],
  C: ["6", "Carbon"],
  K: ["19", "Potassium"],
};

function Tile({ letter, open = false }: { letter: string; open?: boolean }) {
  const element = elements[letter];
  return (
    <span className={`tile ${open ? "open" : ""}`}>
      {element ? <small>{element[0]}</small> : null}
      <strong>{letter}</strong>
      {element ? <span>{element[1]}</span> : null}
    </span>
  );
}

export function Brand() {
  return (
    <div className="brand" aria-label="OpenCook">
      <div className="tiles" aria-hidden="true">
        <Tile letter="O" /><Tile letter="P" /><Tile letter="E" open /><Tile letter="N" />
        <Tile letter="C" /><Tile letter="O" /><Tile letter="O" /><Tile letter="K" />
      </div>
      <div className="wordmark">open <b>·</b> cook</div>
    </div>
  );
}
