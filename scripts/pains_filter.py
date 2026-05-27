import pandas as pd
from rdkit import Chem
from rdkit.Chem import FilterCatalog
import argparse
import os


def apply_pains_filter(input_csv, output_csv):
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    df = pd.read_csv(input_csv)
    print(f"Applying PAINS filter to {len(df)} ligands...")

    # Initialize PAINS filter
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    catalog = FilterCatalog.FilterCatalog(params)

    pains_free_data = []
    pains_count = 0

    for _, row in df.iterrows():
        smiles = row["SMILES"]
        mol = Chem.MolFromSmiles(smiles)

        if mol:
            # Fix radicals and re-sanitize before checking for PAINS
            for atom in mol.GetAtoms():
                atom.SetNumRadicalElectrons(0)
                atom.SetNoImplicit(False)
            try:
                Chem.SanitizeMol(mol)
            except:
                pass
            
            # Check for PAINS matches
            if catalog.HasMatch(mol):
                pains_count += 1
                # print(f"PAINS Match found: {row['ligand:number']}")
            else:
                pains_free_data.append(row.to_dict())
        else:
            print(f"Invalid SMILES: {row['ligand:number']}")

    pains_free_df = pd.DataFrame(pains_free_data)
    pains_free_df.to_csv(output_csv, index=False)

    print("-" * 30)
    print(f"PAINS filtering complete.")
    print(f"Initial leads: {len(df)}")
    print(f"PAINS matches removed: {pains_count}")
    print(f"Final clean leads: {len(pains_free_df)}")
    print(f"Clean leads saved to: {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/filtered_ligands.csv")
    parser.add_argument("--output", default="data/filtered_ligands_clean.csv")
    args = parser.parse_args()
    apply_pains_filter(args.input, args.output)
