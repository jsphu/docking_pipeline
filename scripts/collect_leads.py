import pandas as pd
import os
import argparse
import shutil


def collect_best_leads(input_csv, output_dir, delim=":"):
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    df = pd.read_csv(input_csv)
    print(f"Collecting PDBQT files for {len(df)} ligands...")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    receptors = ["5TBM", "6NJS"]
    count = 0

    for _, row in df.iterrows():
        ligand_id = row["ligand:number"]  # Format LIBRARY:NUMBER
        library, number = ligand_id.split(delim)

        found_any = False
        for receptor in receptors:
            lib_dir = os.path.join(f"results-{receptor}", library)
            if not os.path.exists(lib_dir):
                continue

            # Search recursively for the file with flexible padding
            import re

            pattern = re.compile(rf"lig_0*{number}_out\.pdbqt")

            for root, dirs, files in os.walk(lib_dir):
                for f in files:
                    if pattern.fullmatch(f):
                        source_path = os.path.join(root, f)
                        dest_name = f"{receptor}_{library}_{number}.pdbqt"
                        shutil.copy2(source_path, os.path.join(output_dir, dest_name))
                        found_any = True
                        break  # Found for this receptor
                if found_any:
                    break

        if found_any:
            count += 1

    print(f"Successfully collected PDBQT files for {count} ligands into {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/filtered_ligands.csv")
    parser.add_argument("--output", default="data/best_leads_pdbqt")
    parser.add_argument("--delim", default=":")
    args = parser.parse_args()
    # We use the filtered ligands CSV
    collect_best_leads(args.input, args.output, args.delim)
