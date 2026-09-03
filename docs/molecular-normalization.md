# Molecular normalization

OpenCook parses SMILES and InChI with RDKit, sanitizes valence/aromaticity, assigns stereochemistry, and emits canonical isomeric SMILES, Standard InChI/InChIKey, formula, mass, charge, and complexity descriptors.

Stereoisomers are not collapsed. Isotopes and formal charges remain encoded. Disconnected structures are accepted but retained as disconnected canonical structures; OpenCook does not silently strip salts or choose a largest fragment. Tautomers are not canonicalized across tautomeric forms. Mixtures with unknown composition are unsupported. These conservative policies avoid inventing identity equivalences and can later be replaced by an explicitly versioned normalization profile.

