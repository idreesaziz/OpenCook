import { useRef } from 'react';
import type { Ketcher } from 'ketcher-core';
import { Editor } from 'ketcher-react';
import { StandaloneStructServiceProvider } from 'ketcher-standalone';
import 'ketcher-react/dist/index.css';

const provider = new StandaloneStructServiceProvider();

export function MoleculeEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const api = useRef<Ketcher | null>(null);
  const load = async () => { if (api.current && value) await api.current.setMolecule(value); };
  const clear = async () => { if (api.current) await api.current.setMolecule(''); onChange(''); };
  const useDrawing = async () => { if (api.current) onChange(await api.current.getSmiles()); };
  return <div className="editor">
    <div className="editor-head">MOLECULAR STRUCTURE <span>DRAW / SMILES / MOLFILE</span></div>
    <div className="ketcher"><Editor staticResourcesUrl="/" structServiceProvider={provider} errorHandler={() => undefined} onInit={ketcher => { api.current = ketcher; if (value) void ketcher.setMolecule(value); }} /></div>
    <div className="smiles-row"><label htmlFor="structure">SMILES / InChI</label><input id="structure" value={value} onChange={e => onChange(e.target.value)} /></div>
    <div className="editor-tools"><button onClick={clear}>Clear</button><button onClick={load}>Load text in editor</button><button onClick={useDrawing}>Use drawing</button></div>
  </div>;
}
