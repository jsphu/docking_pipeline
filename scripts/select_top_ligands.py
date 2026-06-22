#!/usr/bin/env python
import argparse
import os
import shutil
import pandas as pd

def normalize_name(name):
    if not isinstance(name, str):
        return ""
    return name.upper().strip().replace("-", "_").replace(" ", "_")

def main():
    parser = argparse.ArgumentParser(description="Select top docked ligands after filtering for MD simulation.")
    parser.add_argument("--filtered-csv", help="Filtered CSV (e.g. from BOILED Egg)")
    parser.add_argument("--scores-csv", required=True, help="Original docking scores CSV")
    parser.add_argument("--docked-dir", required=True, help="Directory containing all docked .pdbqt files")
    parser.add_argument("--output-dir", default=".", help="Directory to save selected .pdbqt files")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of ligands to select")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # 1. Load scores
    print(f"Loading docking scores from {args.scores_csv}")
    scores_df = pd.read_csv(args.scores_csv)
    
    # Standardize columns
    scores_df.columns = [c.strip().lower() for c in scores_df.columns]
    
    # We expect 'ligand:number' and 'score'
    id_col = None
    for col in ['ligand:number', 'name', 'ligand']:
        if col in scores_df.columns:
            id_col = col
            break
            
    score_col = None
    for col in ['score', 'vina_score', 'docking_score']:
        if col in scores_df.columns:
            score_col = col
            break
            
    if not id_col or not score_col:
        # Fallback to first two columns
        id_col = scores_df.columns[0]
        score_col = scores_df.columns[1]
        print(f"Using fallback columns: ID='{id_col}', Score='{score_col}'")
    else:
        print(f"Using columns: ID='{id_col}', Score='{score_col}'")

    scores_df['norm_name'] = scores_df[id_col].apply(normalize_name)

    # 2. Filter if filtered-csv is provided
    if args.filtered_csv and os.path.exists(args.filtered_csv) and os.path.getsize(args.filtered_csv) > 0:
        print(f"Filtering using subset from {args.filtered_csv}")
        filtered_df = pd.read_csv(args.filtered_csv)
        filtered_df.columns = [c.strip().lower() for c in filtered_df.columns]
        
        filt_id_col = None
        for col in ['name', 'ligand:number', 'ligand']:
            if col in filtered_df.columns:
                filt_id_col = col
                break
        if not filt_id_col:
            filt_id_col = filtered_df.columns[0]
            
        filtered_names = set(filtered_df[filt_id_col].apply(normalize_name))
        scores_df = scores_df[scores_df['norm_name'].isin(filtered_names)]
        print(f"Filtered down to {len(scores_df)} ligands passing filters")
    else:
        if args.filtered_csv:
            print(f"Warning: Filtered CSV '{args.filtered_csv}' was not found or is empty. Selecting from raw scores.")

    # 3. Sort by score (lower is better) and limit
    scores_df = scores_df.sort_values(by=score_col, ascending=True)
    top_df = scores_df.head(args.limit)
    print(f"Selected top {len(top_df)} ligands:")
    for idx, row in top_df.iterrows():
        print(f" - {row[id_col]}: {row[score_col]}")

    # 4. Map back to PDBQT files
    # Find all pdbqt files in docked-dir
    docked_files = [f for f in os.listdir(args.docked_dir) if f.endswith('.pdbqt')]
    file_map = {}
    for f in docked_files:
        # PDBQT files are usually named result_<id>.pdbqt
        base = os.path.splitext(f)[0]
        name_clean = base.replace("result_", "").replace("_out", "")
        file_map[normalize_name(name_clean)] = f

    copied_count = 0
    selected_csv_data = []
    
    for idx, row in top_df.iterrows():
        norm_n = row['norm_name']
        orig_name = row[id_col]
        score_val = row[score_col]
        
        # Try direct normalize match, or match containing it
        mapped_file = file_map.get(norm_n)
        if not mapped_file:
            # Try partial matching if names were modified
            for f_norm, f_orig in file_map.items():
                if norm_n in f_norm or f_norm in norm_n:
                    mapped_file = f_orig
                    break

        if mapped_file:
            src_path = os.path.join(args.docked_dir, mapped_file)
            # Standardize destination name to selected_<ligand_name>.pdbqt
            dest_name = f"selected_{orig_name}.pdbqt"
            dest_path = os.path.join(args.output_dir, dest_name)
            shutil.copy2(src_path, dest_path)
            print(f"Copied {mapped_file} -> {dest_name}")
            copied_count += 1
            selected_csv_data.append({
                "ligand:number": orig_name,
                "score": score_val,
                "file": dest_name
            })
        else:
            print(f"Warning: Could not find docked file for ligand {orig_name} ({norm_n})")

    # Save metadata for these selected ligands
    selected_csv_df = pd.DataFrame(selected_csv_data)
    selected_csv_df.to_csv(os.path.join(args.output_dir, "selected_ligands.csv"), index=False)
    print(f"Successfully copied {copied_count} files to {args.output_dir}")

if __name__ == "__main__":
    main()
