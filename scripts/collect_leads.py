import pandas as pd
import os
import argparse
import shutil


def collect_best_leads(args):
    input_csv, output_dir, delim, column_name = (
        args.input,
        args.output,
        args.column_delim,
        args.column_name,
    )
    results_prefix, receptors = args.results_prefix, args.receptors
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    df = pd.read_csv(input_csv)
    print(f"Collecting PDBQT files for {len(df)} ligands...")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    count = 0

    for _, row in df.iterrows():
        ligand_id = row[column_name]  # Format LIBRARY:NUMBER
        library, number = ligand_id.split(delim)
        library = library.replace("_", "-")

        for receptor in receptors:
            lib_dir = os.path.join(f"{results_prefix}{receptor}", library)
            if not os.path.exists(lib_dir):
                continue

            results_directory = os.path.join(lib_dir, "results")
            if os.path.exists(results_directory):
                lib_dir = results_directory
            # Search recursively for the file with flexible padding
            import re

            pattern = re.compile(rf"lig_0*{number}_out\.pdbqt")

            for root, dirs, files in os.walk(lib_dir):
                for f in files:
                    if pattern.fullmatch(f):
                        source_path = os.path.join(root, f)
                        dest_name = f"{receptor}_{library}_{number}.pdbqt"
                        shutil.copy2(source_path, os.path.join(output_dir, dest_name))
                        count += 1
                        print(f"    #{count:<6} Found: {dest_name}")
                        break  # Found for this receptor

    print(f"Successfully collected PDBQT files for {count} ligands into {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/filtered_ligands.csv")
    parser.add_argument("--output", default="data/best_leads_pdbqt")
    parser.add_argument("--column-delim", default=":")
    parser.add_argument("--column-name", default="ligand:number")
    parser.add_argument("--results-prefix", default="results-")
    parser.add_argument("--receptors", nargs="+", default=["5TBM", "6NJS"])
    args = parser.parse_args()
    # We use the filtered ligands CSV
    collect_best_leads(args)
