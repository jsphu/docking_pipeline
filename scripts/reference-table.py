import os
import re
import pandas as pd
import argparse
from openbabel import pybel

parser = argparse.ArgumentParser(description="generate reference table of ligands")

parser.add_argument("INPUT", help="Input docking results path")

parser.add_argument("--output", "-o", help="CSV output path, defaults to stdout")

args = parser.parse_args()

base_dir = args.INPUT

results = []

# Regular expression to match your ligand files, e.g., lig_00001_out.pdbqt
file_pattern = re.compile(r"lig_(?P<num>\d+)_out\.pdbqt")

for root, dirs, files in os.walk(base_dir):
    for filename in files:
        match = file_pattern.match(filename)
        if match:
            lig_num = match.group("num")
            file_path = os.path.join(root, filename)

            # Extract the path name (e.g., Anticancer-Library-61538)
            # Adjust the split logic based on your exact folder depth
            path_parts = root.split(os.sep)
            path_name = (
                path_parts[-1] if path_parts[-1] != "results" else path_parts[-2]
            )

            try:
                # Read the PDBQT file (taking the first model/frame)
                mol = next(pybel.readfile("pdbqt", file_path))

                # Convert to SMILES (canonical, stripped of coordinates)
                smiles = mol.write("can").strip().split()[0]

                results.append(
                    {
                        "path-name": path_name.upper(),
                        "ligand-number": lig_num,
                        "SMILES": smiles,
                    }
                )
            except Exception as e:
                print(f"Could not convert {filename}: {e}")

# Create the reference table
smiles_df = pd.DataFrame(results)

if args.output:
    smiles_df.to_csv(args.output, index=False)
else:
    print(smiles_df.to_string(index=False))
