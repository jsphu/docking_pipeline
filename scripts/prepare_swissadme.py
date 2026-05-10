import pandas as pd
from rdkit import Chem
import argparse
import os


def clean_and_fix_smiles(smiles):
    try:
        # Initial parse
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return None

        # Fix the "radical" issue common in some explicit SMILES exports
        for atom in mol.GetAtoms():
            atom.SetNumRadicalElectrons(0)
            atom.SetNoImplicit(False)

        # Re-sanitize to update valency and implicit hydrogens
        Chem.SanitizeMol(mol)

        # Canonicalize
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception as e:
        # print(f"Error processing SMILES: {e}")
        return None


def prepare_for_swissadme(input_csv, output_smi):
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    df = pd.read_csv(input_csv)
    print(f"Processing and fixing {len(df)} ligands...")

    os.makedirs(os.path.dirname(output_smi), exist_ok=True)

    count = 0
    with open(output_smi, "w") as f:
        for _, row in df.iterrows():
            smiles = row["SMILES"]
            name = row["ligand:number"]

            # name shouldn't include ':' colons
            name = name.replace(":", "_")

            clean = clean_and_fix_smiles(smiles)
            if clean:
                # SwissADME works best with TAB or SPACE separated SMILES Name
                f.write(f"{clean} {name}\n")
                count += 1
            else:
                print(f"Warning: Could not fix SMILES for {name}")

    print(f"Successfully wrote {count} fixed ligands to {output_smi}")
    print("These SMILES are now standard organic structures (no radical issues).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/filtered_ligands.csv")
    parser.add_argument("--output", default="data/filtered_ligands.smi")
    args = parser.parse_args()
    prepare_for_swissadme(args.input, args.output)
