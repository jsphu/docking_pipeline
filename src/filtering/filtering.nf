
process COLLECT_RESULTS {
    container 'ghcr.io/jsphu/docking_pipeline/filtering:latest'
    publishDir "${params.outdir}/summary", mode: 'copy'

    input:
    path "docking_results/*"

    output:
    path "docking_scores.csv", emit: csv

    script:
    """
    # Create a metadata-like file for the script to parse
    # The script expects lines like: Receptor:path/lig_1_out(Model-1) -9.0
    for f in docking_results/*.pdbqt; do
        # Extract score from Vina output (usually the first REMARK VINA RESULT)
        score=\$(grep "REMARK VINA RESULT:" \$f | head -n 1 | awk '{print \$4}')
        # Dummy receptor and path for the script's regex
        name=\$(basename \$f .pdbqt)
        echo "RECEPTOR:PATH/\${name}(Model-1) \${score}" >> metadata.txt
    done

    # Note: The original script needs some adjustments to handle this metadata.txt
    # or we can write a simpler collector here.
    # For now, let's use a simpler version since the original is very specific to 5TBM/6NJS
    python -c "
import pandas as pd
import glob
import os
import re

results = []
for f in glob.glob('docking_results/*.pdbqt'):
    name = os.path.basename(f).replace('result_', '').replace('.pdbqt', '')
    with open(f, 'r') as fh:
        for line in fh:
            if 'REMARK VINA RESULT:' in line:
                score = float(line.split()[3])
                results.append({'ligand:number': name, 'score': score})
                break
df = pd.DataFrame(results)
df.to_csv('docking_scores.csv', index=False)
    "
    """
}

process EXTRACT_SMILES {
    container 'ghcr.io/jsphu/docking_pipeline/filtering:latest'
    
    input:
    path "prepped_ligands/*"

    output:
    path "all_smiles.csv", emit: csv

    script:
    """
    python -c "
import pandas as pd
import glob
import os
from rdkit import Chem

def extract_smiles_from_pdbqt(f):
    try:
        with open(f, 'r') as fh:
            lines = fh.readlines()
        
        # Clean PDBQT for RDKit (handle A, NA, OA types)
        pdb_lines = []
        for line in lines:
            if line.startswith('ATOM'):
                parts = line.split()
                element = parts[-1]
                mapping = {'A': 'C', 'NA': 'N', 'OA': 'O', 'SA': 'S', 'HD': 'H'}
                element = mapping.get(element, element)
                # Position element in 77-78
                new_line = line[:76] + element.rjust(2) + line[78:]
                pdb_lines.append(new_line)
            elif line.startswith(('REMARK', 'TER', 'END', 'MODEL', 'ENDMDL')):
                pdb_lines.append(line)

        # Process only the first model to avoid overlapping valence errors
        first_model = []
        in_model = False
        for l in pdb_lines:
            if l.startswith('MODEL'):
                if in_model: break
                in_model = True
            if in_model: first_model.append(l)
            if l.startswith('ENDMDL'): break
        if not first_model: first_model = pdb_lines

        mol = Chem.MolFromPDBBlock('\n'.join(first_model), removeHs=True, proximityBonding=True)
        if mol:
            # Fix radicals and re-perceive aromaticity/valency
            for atom in mol.GetAtoms():
                atom.SetNumRadicalElectrons(0)
                atom.SetNoImplicit(False)
            Chem.SanitizeMol(mol)
            return Chem.MolToSmiles(mol, canonical=True)
    except:
        pass
    return None

data = []
for f in glob.glob('prepped_ligands/*.pdbqt'):
    name = os.path.basename(f).replace('.pdbqt', '')
    smiles = extract_smiles_from_pdbqt(f)
    if smiles:
        data.append({'ligand:number': name.upper(), 'SMILES': smiles})

df = pd.DataFrame(data)
df.to_csv('all_smiles.csv', index=False)
    "
    """
}

process FILTER_LIGANDS {
    container 'ghcr.io/jsphu/docking_pipeline/filtering:latest'
    publishDir "${params.outdir}/filtering", mode: 'copy'

    input:
    path smiles_csv
    path scores_csv
    path rules_toml

    output:
    path "filtered_ligands.csv", emit: csv

    script:
    """
    python ${baseDir}/scripts/filter_ligands.py \
        --smiles ${smiles_csv} \
        --scores ${scores_csv} \
        --rules ${rules_toml} \
        --output filtered_ligands.csv
    """
}

process PAINS_FILTER {
    container 'ghcr.io/jsphu/docking_pipeline/filtering:latest'
    publishDir "${params.outdir}/filtering", mode: 'copy'

    input:
    path filtered_csv

    output:
    path "filtered_ligands_pains_free.csv", emit: csv

    script:
    """
    python ${baseDir}/scripts/pains_filter.py \
        --input ${filtered_csv} \
        --output filtered_ligands_pains_free.csv
    """
}

process BOILED_EGG {
    container 'ghcr.io/jsphu/docking_pipeline/filtering:latest'
    publishDir "${params.outdir}/filtering", mode: 'copy'

    input:
    path pains_free_csv

    output:
    path "*_BOILED_Egg.csv", emit: csv
    path "*_BOILED_Egg.pdf", emit: pdf

    script:
    """
    python ${baseDir}/scripts/pyBOILEDegg.py \
        --prefix "leads" \
        --input-type "csv" \
        --infile ${pains_free_csv}
    """
}
