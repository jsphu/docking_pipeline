import pandas as pd
import argparse
import tomllib
import os

# Mapping from rules.toml keys to CSV column names
KEY_MAP = {
    "mw": "MW",
    "logp": "LogP",
    "hbd": "HBD",
    "hba": "HBA",
    "psa": "TPSA",
    "charge": "Charge",
}


def format_rule(key, value):
    name = KEY_MAP.get(key, key.upper())
    if isinstance(value, list):
        return f"{name}: {' and '.join(value)}"
    return f"{name}: {value}"


def generate_report(input_csv, rules_path, limit=10):
    if not os.path.exists(input_csv):
        print(f"Error: Input CSV '{input_csv}' not found.")
        return

    df = pd.read_csv(input_csv)

    if df.empty:
        print("No candidates found in the input CSV.")
        return

    # Dynamically find efficiency columns (e.g., '6NJS_efficiency')
    efficiency_cols = [col for col in df.columns if col.endswith("_efficiency")]

    if not efficiency_cols:
        print("Warning: No efficiency columns found (ending with '_efficiency').")
        df["Avg_Efficiency"] = 0
    else:
        df["Avg_Efficiency"] = df[efficiency_cols].mean(axis=1)

    # Sort by average efficiency
    sorted_df = df.sort_values(by="Avg_Efficiency", ascending=False)
    
    # Apply limit if applicable
    if limit is not None:
        display_df = sorted_df.head(limit)
        title_limit = f"TOP {limit} "
    else:
        display_df = sorted_df
        title_limit = "ALL "

    # Load rules for display and to determine columns to show
    rules_data = {}
    criteria_str = "No rules found"
    if os.path.exists(rules_path):
        with open(rules_path, "rb") as f:
            rules_data = tomllib.load(f)
            criteria_str = " | ".join(
                [format_rule(k, v) for k, v in rules_data.items()]
            )

    # Determine which property columns to show based on rules and availability
    prop_cols = []
    for k in rules_data.keys():
        csv_col = KEY_MAP.get(k)
        if csv_col and csv_col in df.columns:
            prop_cols.append(csv_col)

    # Build the header
    header_parts = [f"{'Ligand ID':<45}", f"{'Avg LE':<8}"]
    for col in prop_cols:
        header_parts.append(f"{col:<6}")

    header = " | ".join(header_parts)

    print(f"\n{'=' * len(header)}")
    print(f"{(title_limit + 'LIGAND CANDIDATES'):^{len(header)}}")
    print(f"{'(Ranked by Combined Efficiency)':^{len(header)}}")
    print(f"{'=' * len(header)}\n")

    print(header)
    print("-" * len(header))

    for _, row in display_df.iterrows():
        row_parts = [
            f"{row['ligand:number']:<45}",
            f"{row['Avg_Efficiency']:<8.3f}",
        ]
        for col in prop_cols:
            val = row[col]
            if isinstance(val, (int, float)):
                if col == "Charge":
                    row_parts.append(f"{int(val):<6d}")
                else:
                    row_parts.append(f"{val:<6.1f}")
            else:
                row_parts.append(f"{str(val):<6}")
        print(" | ".join(row_parts))

    print(f"\n{'=' * len(header)}")
    print(f"Total Filtered Candidates: {len(df)}")
    print(f"Criteria: {criteria_str}")
    print(f"{'=' * len(header)}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a summary report for filtered ligands."
    )
    parser.add_argument(
        "--csv",
        default="scripts/filtered_ligands.csv",
        help="Path to filtered ligands CSV",
    )
    parser.add_argument(
        "--rules", default="scripts/rules.toml", help="Path to rules TOML file"
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Number of top candidates to display (default: 10)"
    )
    parser.add_argument(
        "--no-limit", action="store_true", help="Display all candidates (overrides --limit)"
    )
    args = parser.parse_args()
    
    final_limit = None if args.no_limit else args.limit
    generate_report(args.csv, args.rules, final_limit)
