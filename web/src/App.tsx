import { useCallback, useEffect, useState } from "react";
import { Brand } from "./Brand";
import { SynthesisGraph } from "./Graph";
import { MoleculeEditor } from "./MoleculeEditor";
import type { Health, Reaction, RouteNode, SearchResult } from "./types";

const example = "CC(=O)OCCO";

function ProgressGauge({ label, value, maximum, detail }: { label: string; value: number; maximum: number; detail: string }) {
  const percent = maximum > 0 ? Math.min(100, (value / maximum) * 100) : 0;
  return <div className="progress-gauge">
    <div><span>{label}</span><code>{detail}</code></div>
    <div className="gauge-track"><i style={{ width: `${percent}%` }} /></div>
  </div>;
}

function stockLeaves(root: RouteNode): RouteNode[] {
  const leaves = new Map<string, RouteNode>();
  const visit = (node: RouteNode) => {
    if (node.in_stock) leaves.set(node.molecule, node);
    node.precursors.forEach(visit);
  };
  visit(root);
  return [...leaves.values()];
}
function unresolvedLeaves(root: RouteNode): RouteNode[] {
  const leaves = new Map<string, RouteNode>();
  const visit = (node: RouteNode) => {
    if (!node.in_stock && !node.reaction) leaves.set(node.molecule, node);
    node.precursors.forEach(visit);
  };
  visit(root);
  return [...leaves.values()];
}
export function App() {
  const [input, setInput] = useState(example),
    [job, setJob] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false),
    [route, setRoute] = useState(0);
  const [selected, setSelected] = useState<RouteNode | Reaction | null>(null),
    [error, setError] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [searchStartedAt, setSearchStartedAt] = useState(0);
  const [liveNow, setLiveNow] = useState(0);
  useEffect(() => {
    void fetch("/api/v1/health")
      .then((response) => response.json())
      .then(setHealth);
  }, []);
  const run = async () => {
    const startedAt = Date.now();
    setSearchStartedAt(startedAt);
    setLiveNow(startedAt);
    setBusy(true);
    setError("");
    setJob(null);
    try {
      const response = await fetch("/api/v1/searches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ structure: input, routes: 5 }),
      });
      if (!response.ok) throw new Error((await response.json()).detail);
      const created = await response.json();
      setJob({
        id: created.id,
        status: "queued",
        target: {
          smiles: input,
          formula: "",
          molecular_weight: 0,
          inchikey: "",
        },
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search failed");
      setBusy(false);
    }
  };
  useEffect(() => {
    if (!busy) return;
    const clock = setInterval(() => setLiveNow(Date.now()), 200);
    return () => clearInterval(clock);
  }, [busy]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = setInterval(async () => {
      const next = await fetch(`/api/v1/searches/${job.id}`).then((response) =>
        response.json(),
      );
      setJob(next);
      if (["completed", "failed", "canceled"].includes(next.status))
        setBusy(false);
    }, 250);
    return () => clearInterval(timer);
  }, [job]);
  const cancel = async () => {
    if (!job) return;
    await fetch(`/api/v1/searches/${job.id}`, { method: "DELETE" });
  };
  const select = useCallback(
      (value: RouteNode | Reaction) => setSelected(value),
      [],
    ),
    routes = job?.routes ?? [];
  const activeRoot = routes[route]?.root;
  return (
    <>
      <header>
        <Brand />
        <nav>
          search <span>/</span> settings
        </nav>
      </header>
      <main>
        {health?.corpus_mode === "fixture_only" ? (
          <div className="corpus-warning">
            <b>DEMO CORPUS</b>
            <span>
              Only {health.database.reaction} fixture reactions are indexed.
              Most molecules cannot be solved until ORD data is imported.
            </span>
            <code>opencook data import-ord DATASET.parquet</code>
          </div>
        ) : null}
        {!job ? (
          <section className="entry">
            <p className="eyebrow">LOCAL RETROSYNTHESIS</p>
            <h1>OpenCook</h1>
            <p className="subtitle">
              An open-source search engine for chemical synthesis.
            </p>
            <MoleculeEditor value={input} onChange={setInput} />
            <button className="primary" onClick={run} disabled={busy}>
              Find synthesis <span>-&gt;</span>
            </button>
            {error ? <p className="error">{error}</p> : null}
          </section>
        ) : null}
        {job ? (
          <section className="results">
            <div className="target-head">
              <div className="target-identity">
                <div className="target-structure">
                  <img
                    src={`/api/v1/molecules/depict-image?smiles=${encodeURIComponent(job.target.smiles)}`}
                    alt="Target molecular structure"
                  />
                </div>
                <div className="target-copy">
                  <p className="eyebrow">TARGET</p>
                  <h1>
                    {activeRoot?.display_name ??
                      job.target.formula ??
                      "Normalizing..."}
                  </h1>
                  {activeRoot?.display_name ? (
                    <strong>{job.target.formula}</strong>
                  ) : null}
                  <code>{job.target.smiles}</code>
                  {job.target.molecular_weight > 0 ? (
                    <p>
                      MW {job.target.molecular_weight.toFixed(2)} /{" "}
                      {job.target.inchikey}
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="summary">
                <b>{job.status}</b>
                {job.stats ? (
                  <>
                    <span>
                      <strong>{job.stats.complete_routes}</strong> complete /{" "}
                      <strong>{routes.filter((item) => !item.complete).length}</strong> partial
                    </span>
                    <span>
                      <strong>{job.stats.reactions_examined}</strong> reactions
                      examined
                    </span>
                    <small>
                      {job.stats.elapsed_seconds.toFixed(3)} seconds
                    </small>
                    <small>termination: {job.stats.termination}</small>
                    {job.stats.model_calls > 0 ? (
                      <small>
                        model: {job.stats.model_calls} calls / {job.stats.model_reactions_generated} proposals
                      </small>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>
            {busy ? (
              <div className="progress">
                <div className="retro-signal" aria-hidden="true">
                  <span /><span /><span /><span /><span />
                </div>
                <div className="progress-copy">
                  <div className="trace-label"><span>RETRO // TRACE</span><em>LIVE</em></div>
                  <b>&gt; {job.progress?.stage ?? "Starting search"}</b>
                  <code>{job.progress?.current_molecule}</code>
                  <div className="progress-grid">
                    <ProgressGauge label="TIME BUDGET" value={(liveNow - searchStartedAt) / 1000} maximum={job.configuration?.timeout_seconds ?? 180} detail={`${((liveNow - searchStartedAt) / 1000).toFixed(1)} / ${job.configuration?.timeout_seconds ?? 180}s`} />
                    <ProgressGauge label="GRAPH EXPANSIONS" value={job.progress?.molecules_expanded ?? 0} maximum={job.configuration?.max_expansions ?? 10000} detail={`${job.progress?.molecules_expanded ?? 0} / ${job.configuration?.max_expansions ?? 10000}`} />
                    <ProgressGauge label="SEARCH DEPTH" value={job.progress?.deepest_complete_route ?? job.progress?.current_depth ?? 0} maximum={job.configuration?.max_depth ?? 8} detail={`${job.progress?.deepest_complete_route ?? job.progress?.current_depth ?? 0} / ${job.configuration?.max_depth ?? 8}`} />
                    <ProgressGauge label="ROUTE RECOVERY" value={job.progress?.complete_routes_discovered ?? 0} maximum={job.configuration?.routes ?? 5} detail={`${job.progress?.complete_routes_discovered ?? 0} / ${job.configuration?.routes ?? 5}`} />
                    <ProgressGauge label="MODEL FALLBACK" value={job.progress?.model_calls ?? 0} maximum={job.configuration?.max_model_calls ?? 25} detail={`${job.progress?.model_calls ?? 0} calls · ${job.progress?.model_reactions_generated ?? 0} proposals`} />
                    <ProgressGauge label="FRONTIER LOAD" value={job.progress?.frontier_size ?? 0} maximum={Math.max(job.progress?.molecules_discovered ?? 1, 1)} detail={`${job.progress?.frontier_size ?? 0} queued`} />
                  </div>
                  <div className="progress-metrics">
                    <span>depth <strong>{job.progress?.current_depth ?? 0}</strong></span>
                    <span>expanded <strong>{job.progress?.molecules_expanded ?? 0}</strong></span>
                    <span>reactions <strong>{job.progress?.unique_reactions_examined ?? 0}</strong></span>
                    <span>frontier <strong>{job.progress?.frontier_size ?? 0}</strong></span>
                    <span>routes <strong>{job.progress?.complete_routes_discovered ?? 0}</strong></span>
                    <span>deepest <strong>{job.progress?.deepest_complete_route ?? 0}</strong></span>
                    <span>model calls <strong>{job.progress?.model_calls ?? 0}</strong></span>
                    <span>proposals <strong>{job.progress?.model_reactions_generated ?? 0}</strong></span>
                    <span>{(job.progress?.elapsed_seconds ?? 0).toFixed(1)} s</span>
                  </div>
                  <div className="assembly-feed">
                    <div className="trace-label"><span>GRAPH ASSEMBLY // ACCEPTED DISCONNECTIONS</span></div>
                    {(job.progress?.recent_reactions ?? []).length ? job.progress?.recent_reactions.map((reaction) => (
                      <div className="assembly-line" key={`${reaction.id}-${reaction.depth}`}>
                        <em>{reaction.evidence === "computational_proposal" ? "MODEL" : "ORD"}</em>
                        <code>{reaction.reactants.join(" + ")} → {reaction.product}</code>
                        <small>d{reaction.depth} / {reaction.id}</small>
                      </div>
                    )) : <div className="assembly-empty">Awaiting first indexed transformation...</div>}
                  </div>
                </div>
                <button className="cancel-search" onClick={cancel}>[ CANCEL SEARCH ]</button>
              </div>
            ) : null}
            {job.status === "failed" ? (
              <p className="error search-error">
                Search failed: {job.error ?? "Unknown backend error"}
              </p>
            ) : null}
            {job.message ? <p className="notice">{job.message}</p> : null}
            {routes.length ? (
              <>
                <div className="route-tabs">
                  {routes.map((item, index) => (
                    <button
                      className={index === route ? "active" : ""}
                      onClick={() => setRoute(index)}
                      key={item.signature}
                    >
                      Route {index + 1}
                      <small>
                        {item.complete ? "complete" : `${item.metrics.unresolved_leaves} unresolved`}
                        {" / "}{item.metrics.transformations} steps
                      </small>
                    </button>
                  ))}
                </div>
                <section className="materials">
                  <p className="eyebrow">
                    {routes[route].complete ? "REQUIRED STARTING MATERIALS" : "KNOWN AND UNRESOLVED MATERIALS"}
                  </p>
                  <div>
                    {stockLeaves(routes[route].root).map((item) => (
                      <button
                        key={item.molecule}
                        onClick={() => setSelected(item)}
                      >
                        <b>{item.display_name ?? item.molecule}</b>
                        <code>{item.molecule}</code>
                        <span>
                          {item.name_record
                            ? `${item.name_record.source} ${item.name_record.source_id}`
                            : "No database name found"}
                        </span>
                      </button>
                    ))}
                    {unresolvedLeaves(routes[route].root).map((item) => (
                      <button className="unresolved-material" key={item.molecule} onClick={() => setSelected(item)}>
                        <b>{item.display_name ?? item.molecule}</b>
                        <code>{item.molecule}</code>
                        <span>Unresolved — no complete indexed path to selected stock</span>
                      </button>
                    ))}
                  </div>
                </section>
                <SynthesisGraph root={routes[route].root} onSelect={select} />
              </>
            ) : null}
          </section>
        ) : null}
      </main>
      {selected ? (
        <aside>
          <button className="close" onClick={() => setSelected(null)}>
            x
          </button>
          {"evidence" in selected ? (
            <>
              <p className="eyebrow">REACTION EVIDENCE</p>
              <h2>{selected.id}</h2>
              <dl>
                <dt>Classification</dt>
                <dd>{selected.evidence.replaceAll("_", " ")}</dd>
                <dt>Confidence</dt>
                <dd>{selected.confidence}</dd>
                <dt>Validation</dt>
                <dd>{selected.validation}</dd>
              </dl>
              <h3>Provenance</h3>
              {selected.provenance.map((item) => (
                <div className="provenance" key={item.record_id}>
                  <b>{item.dataset}</b>
                  <span>
                    {item.record_id} / v{item.dataset_version}
                  </span>
                  <span>{item.source}</span>
                  <span>License: {item.license}</span>
                </div>
              ))}
            </>
          ) : (
            <>
              <p className="eyebrow">MOLECULE</p>
              <h2>
                {selected.in_stock ? "Starting material" : "Intermediate"}
              </h2>
              <code>{selected.molecule}</code>
              {selected.display_name ? <h3>{selected.display_name}</h3> : null}
              {selected.name_record ? (
                <>
                  <p className="source-label">Chemical-name provenance</p>
                  <dl>
                    <dt>Database</dt>
                    <dd>{selected.name_record.source}</dd>
                    <dt>Record</dt>
                    <dd>{selected.name_record.source_id}</dd>
                    <dt>Match</dt>
                    <dd>
                      {selected.name_record.match_type.replaceAll("_", " ")}
                    </dd>
                    {selected.name_record.systematic_name ? (
                      <>
                        <dt>Systematic name</dt>
                        <dd>{selected.name_record.systematic_name}</dd>
                      </>
                    ) : null}
                  </dl>
                  <p className="source-warning">
                    The name is external identifier metadata, not reaction
                    evidence or a statement of purity.
                  </p>
                </>
              ) : null}
            </>
          )}
        </aside>
      ) : null}
    </>
  );
}
