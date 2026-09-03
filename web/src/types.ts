export type Molecule = {
  smiles: string;
  formula: string;
  molecular_weight: number;
  inchikey: string;
};
export type Provenance = {
  dataset: string;
  dataset_version: string;
  record_id: string;
  source: string;
  license: string;
  doi?: string;
};
export type Reaction = {
  id: string;
  evidence: string;
  confidence: number;
  validation: string;
  provenance: Provenance[];
  yield_percent?: number;
};
export type RouteNode = {
  molecule: string;
  in_stock: boolean;
  display_name: string | null;
  common_sources: string[];
  name_record?: {
    preferred_name: string;
    systematic_name: string | null;
    source: string;
    source_id: string;
    match_type: string;
    retrieved_at: string;
  };
  reaction: Reaction | null;
  precursors: RouteNode[];
};
export type Route = {
  root: RouteNode;
  signature: string;
  complete: boolean;
  metrics: {
    transformations: number;
    longest_linear_sequence: number;
    stock_leaves: number;
    average_confidence: number;
    total_score: number;
    unresolved_leaves: number;
  };
};
export type SearchResult = {
  id: string;
  status: string;
  target: Molecule;
  routes?: Route[];
  stats?: {
    elapsed_seconds: number;
    molecules_discovered: number;
    reactions_examined: number;
    molecules_expanded: number;
    frontier_size: number;
    complete_routes: number;
    termination: string;
    model_calls: number;
    model_reactions_generated: number;
    model_failures: number;
  };
  progress?: {
    stage: string;
    current_molecule: string | null;
    current_depth: number;
    elapsed_seconds: number;
    molecules_discovered: number;
    molecules_expanded: number;
    unique_reactions_examined: number;
    frontier_size: number;
    complete_routes_discovered: number;
    deepest_complete_route: number;
    model_calls: number;
    model_reactions_generated: number;
    model_failures: number;
  };
  message?: string;
  error?: string;
};
export type Health = {
  status: string;
  database: { molecule: number; reaction: number };
  corpus_mode: "fixture_only" | "imported";
  stock_version: string;
  stock_molecules: number;
  model_provider: string;
  model_version: string;
};
