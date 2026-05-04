import pandas as pd
import re
import argparse

parser = argparse.ArgumentParser(description="generate docking-scores-table")

parser.add_argument("INPUT", help="Input metadata path")

parser.add_argument("--output", "-o", help="CSV output path, defaults to stdout")

args = parser.parse_args()

file_path = args.INPUT

data = []
# Regex to capture: Receptor, Path, Ligand ID, Model #, and Score
pattern = re.compile(
    r"(?P<receptor>[^:]+):(?P<path>.*?)(?:/results)?/lig_(?P<ligand>\d+)_out\(Model-(?P<model>\d+)\)\s+(?P<score>-?\d+\.\d+)"
)

try:
    with open(file_path, "r") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                data.append(
                    {
                        "path-name": match.group("path").strip("/").upper(),
                        "ligand-number": match.group("ligand"),
                        "model_idx": int(match.group("model")),
                        "receptor": match.group("receptor"),
                        "score": float(match.group("score")),
                    }
                )

    df = pd.DataFrame(data)

    # Create the column names (e.g., "5TBM-model-1")
    df["col_name"] = df["receptor"] + "-model-" + df["model_idx"].astype(str)

    # Pivot: Index by path and ligand, columns are the receptor-model pairs
    pivot_df = df.pivot(
        index=["path-name", "ligand-number"], columns="col_name", values="score"
    ).reset_index()

    # To keep the columns in a logical order (model-1 pairs, then model-2 pairs...)
    # We find all unique model numbers and sort them
    unique_models = sorted(df["model_idx"].unique())
    receptors = ["5TBM", "6NJS"]

    ordered_cols = ["path-name", "ligand-number"]
    for m in unique_models:
        for r in receptors:
            col = f"{r}-model-{m}"
            if col in pivot_df.columns:
                ordered_cols.append(col)

    # Reorganize the dataframe with the sorted columns
    final_df = pivot_df[ordered_cols]

    # FILTERING:
    # Here we filter for ligands where the TOP model (Model 1)
    # for BOTH receptors is -8.0 or better.
    mask = (final_df["5TBM-model-1"] <= -8.0) & (final_df["6NJS-model-1"] <= -8.0)
    filtered_df = final_df[mask]

    print("--- Widened Data View (Showing Top Leads) ---")
    if filtered_df.empty:
        print("No ligands met the -8.0 threshold for both receptors in Model 1.")
        print("\nShowing first few rows of the unfiltered table instead:")
        print(final_df.head(10).to_string(index=False))
    else:
        if args.output:
            filtered_df.to_csv(args.output, index=False)
        else:
            print(filtered_df.to_string(index=False))

except FileNotFoundError:
    print("File not found. Please check the 'file_path' variable.")
