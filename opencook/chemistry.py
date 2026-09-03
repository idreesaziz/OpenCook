from __future__ import annotations

import hashlib
from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import Descriptors, Draw, rdMolDescriptors

from .domain import Molecule


class MoleculeError(ValueError):
    pass


@lru_cache(maxsize=262_144)
def canonical_identity(value: str) -> tuple[str, str]:
    """Return the stable database identity without computing costly descriptors."""
    mol = _parse(value)
    smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    return hashlib.sha256(smiles.encode()).hexdigest()[:20], smiles


def _parse(value: str, fmt: str = "auto") -> Chem.Mol:
    value = value.strip()
    if not value:
        raise MoleculeError("Molecular structure is empty")
    mol = None
    if fmt in ("auto", "smiles"):
        mol = Chem.MolFromSmiles(value)
    if mol is None and fmt in ("auto", "inchi") and value.startswith("InChI="):
        mol = Chem.MolFromInchi(value)
    if mol is None and fmt in ("mol", "sdf"):
        mol = Chem.MolFromMolBlock(value, sanitize=True, removeHs=False)
    if mol is None:
        raise MoleculeError("Invalid or unsupported molecular structure")
    Chem.SanitizeMol(mol)
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    return mol


@lru_cache(maxsize=16_384)
def normalize(value: str, fmt: str = "auto") -> Molecule:
    mol = _parse(value, fmt)
    smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    normalized = Chem.MolFromSmiles(smiles)
    assert normalized is not None
    inchi = Chem.MolToInchi(normalized)
    inchikey = Chem.InchiToInchiKey(inchi)
    return Molecule(
        id=hashlib.sha256(smiles.encode()).hexdigest()[:20],
        smiles=smiles,
        inchi=inchi,
        inchikey=inchikey,
        formula=rdMolDescriptors.CalcMolFormula(normalized),
        molecular_weight=round(Descriptors.MolWt(normalized), 4),
        formal_charge=Chem.GetFormalCharge(normalized),
        heavy_atoms=normalized.GetNumHeavyAtoms(),
        rings=rdMolDescriptors.CalcNumRings(normalized),
        stereocenters=len(Chem.FindMolChiralCenters(normalized, includeUnassigned=True)),
    )


@lru_cache(maxsize=4096)
def depict_svg(smiles: str, width: int = 260, height: int = 180) -> str:
    mol = Chem.MolFromSmiles(normalize(smiles).smiles)
    assert mol is not None
    drawer = Draw.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = True
    opts.setBackgroundColour((0.137, 0.149, 0.122, 1.0))
    opts.setAtomPalette(
        {
            1: (0.86, 0.84, 0.77),
            6: (0.93, 0.91, 0.84),
            7: (0.49, 0.61, 0.50),
            8: (0.73, 0.35, 0.24),
            9: (0.49, 0.61, 0.50),
            15: (0.76, 0.56, 0.40),
            16: (0.76, 0.65, 0.37),
            17: (0.49, 0.61, 0.50),
            35: (0.62, 0.37, 0.27),
            53: (0.55, 0.42, 0.61),
        }
    )
    opts.addStereoAnnotation = True
    Draw.rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()
