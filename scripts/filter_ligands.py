import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, rdmolops
import tomllib
import argparse
import os
import time
import sys
import gzip
from concurrent.futures import ProcessPoolExecutor
from functools import partial

# Global variable to store compiled rules in worker processes
_WORKER_TESTS = {}


def compile_rules(rules_data):
    """Compile rule expressions into callable tests."""
    tests = {}
    for k, expr in rules_data.items():
        if not expr:
            tests[k] = lambda x: True
            continue
        if isinstance(expr, list):
            expr = " and ".join(f"({e})" for e in expr)
        try:
            code = compile(expr, "<string>", "eval")

            def test_func(x, c=code):
                return bool(eval(c, {"__builtins__": {}}, {"x": x}))

            tests[k] = test_func
        except Exception as e:
            print(f"Warning: Could not parse rule '{expr}': {e}")
            tests[k] = lambda x: True
    return tests


def init_worker(rules_toml_path):
    """Initialize worker process by loading and compiling rules once."""
    global _WORKER_TESTS
    try:
        with open(rules_toml_path, "rb") as f:
            rules_data = tomllib.load(f)
        _WORKER_TESTS = compile_rules(rules_data)
    except Exception as e:
        print(f"Worker initialization failed: {e}")
        _WORKER_TESTS = {}


def process_single_ligand(row_tuple, has_scores, score_cols, verbose=False):
    """Worker function to process one ligand using global _WORKER_TESTS."""
    idx, row = row_tuple
    ligand_id = row["ligand:number"]
    smiles = row["SMILES"]
    mol = Chem.MolFromSmiles(smiles)

    if mol is None:
        return None, (ligand_id, "Invalid SMILES") if verbose else None

    # Sanitization and cleaning
    for atom in mol.GetAtoms():
        atom.SetNumRadicalElectrons(0)
        atom.SetNoImplicit(False)
    try:
        mol = Chem.RemoveHs(mol)
        Chem.SanitizeMol(mol)
        smiles = Chem.MolToSmiles(mol, canonical=True)
    except:
        return None, (ligand_id, "Sanitization failed") if verbose else None

    # Property calculations
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    psa = Descriptors.TPSA(mol)
    charge = rdmolops.GetFormalCharge(mol)
    heavy_atoms = mol.GetNumHeavyAtoms()

    # Rule evaluation using global tests
    pass_mw = _WORKER_TESTS.get("mw", lambda x: True)(mw)
    pass_logp = _WORKER_TESTS.get("logp", lambda x: True)(logp)
    pass_hbd = _WORKER_TESTS.get("hbd", lambda x: True)(hbd)
    pass_hba = _WORKER_TESTS.get("hba", lambda x: True)(hba)
    pass_psa = _WORKER_TESTS.get("psa", lambda x: True)(psa)
    pass_charge = _WORKER_TESTS.get("charge", lambda x: True)(charge)

    # Efficiency evaluation
    efficiencies = {}
    pass_efficiency = True

    if has_scores:
        for col in score_cols:
            score = row.get(col)
            if pd.isna(score):
                continue
            efficiency = abs(score) / heavy_atoms
            efficiencies[f"{col}_efficiency"] = efficiency
            if not _WORKER_TESTS.get("vs", lambda x: True)(efficiency):
                pass_efficiency = False
        if not efficiencies:
            pass_efficiency = False

    rejection = None
    if verbose and not all(
        [pass_mw, pass_logp, pass_hbd, pass_hba, pass_psa, pass_charge, pass_efficiency]
    ):
        reasons = []
        if not pass_mw:
            reasons.append(f"MW={mw:.1f}")
        if not pass_logp:
            reasons.append(f"LogP={logp:.1f}")
        if not pass_hbd:
            reasons.append(f"HBD={hbd}")
        if not pass_hba:
            reasons.append(f"HBA={hba}")
        if not pass_psa:
            reasons.append(f"TPSA={psa:.1f}")
        if not pass_charge:
            reasons.append(f"Charge={charge}")
        if has_scores and not pass_efficiency:
            reasons.append("Efficiency")
        rejection = (ligand_id, ", ".join(reasons))

    if all(
        [pass_mw, pass_logp, pass_hbd, pass_hba, pass_psa, pass_charge, pass_efficiency]
    ):
        row_dict = row.to_dict()
        row_dict.update(
            {
                "MW": mw,
                "LogP": logp,
                "HBD": hbd,
                "HBA": hba,
                "TPSA": psa,
                "Charge": charge,
                "HeavyAtoms": heavy_atoms,
                "SMILES": smiles,
            }
        )
        row_dict.update(efficiencies)
        return row_dict, None

    return None, rejection


def count_lines(filename):
    """Estimate total ligands by counting lines in files."""
    count = 0
    try:
        opener = gzip.open if filename.endswith(".gz") else open
        mode = "rt" if filename.endswith(".gz") else "r"
        with opener(filename, mode) as f:
            for _ in f:
                count += 1
        return count - 1  # Subtract header
    except:
        return 0


def format_time(seconds):
    if seconds is None or seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:.0f}h {m:.0f}m"
    return f"{m:.0f}m {s:.0f}s"


def main():
    parser = argparse.ArgumentParser(
        description="Filter ligands based on rules and docking scores (Parallel with Progress)."
    )
    parser.add_argument(
        "--smiles", nargs="+", required=True, help="Path to SMILES CSV/SMI file(s)"
    )
    parser.add_argument(
        "--scores", default=None, help="Path to docking scores CSV (optional)"
    )
    parser.add_argument("--rules", required=True, help="Path to toml file of rules")
    parser.add_argument(
        "--output", default="filtered_ligands.csv", help="Output CSV path"
    )
    parser.add_argument("--smi-output", default=None, help="Output SMI path (optional)")
    parser.add_argument(
        "--chunk-size", type=int, default=5000, help="Processing chunk size"
    )
    parser.add_argument(
        "--cpus", type=int, default=os.cpu_count(), help="Number of CPUs to use"
    )
    parser.add_argument(
        "--compress", action="store_true", help="Compress output files using gzip"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print details for each ligand"
    )

    args = parser.parse_args()

    if not os.path.exists(args.rules):
        print(f"Error: Rules file {args.rules} not found.")
        return

    final_output_csv = args.output
    if args.compress and not final_output_csv.endswith(".gz"):
        final_output_csv += ".gz"
    compression = "gzip" if final_output_csv.endswith(".gz") else None

    # Load scores
    has_scores = False
    scores_df = None
    score_cols = []
    if args.scores and os.path.exists(args.scores):
        scores_df = pd.read_csv(args.scores)
        scores_df.columns = [c.strip() for c in scores_df.columns]
        if "ligand:number" in scores_df.columns:
            scores_df.set_index("ligand:number", inplace=True)
            score_cols = [c for c in scores_df.columns]
            has_scores = True

    # Count total ligands for progress estimation
    print("Estimating total library size...")
    total_to_process = sum(count_lines(f) for f in args.smiles)
    print(f"Total ligands to process: {total_to_process}")

    work_dir = "work_filter_ligands"
    os.makedirs(work_dir, exist_ok=True)

    part_files_csv = []
    part_files_smi = []
    part_idx = 0
    total_processed = 0
    total_filtered = 0
    start_time = time.time()

    print(
        f"Starting parallel filtering with {args.cpus} CPUs (chunk_size={args.chunk_size})..."
    )

    with ProcessPoolExecutor(
        max_workers=args.cpus, initializer=init_worker, initargs=(args.rules,)
    ) as executor:
        worker_func = partial(
            process_single_ligand,
            has_scores=has_scores,
            score_cols=score_cols,
            verbose=args.verbose,
        )

        for input_file in args.smiles:
            if not os.path.exists(input_file):
                continue

            if input_file.endswith(".csv") or input_file.endswith(".csv.gz"):
                reader = pd.read_csv(input_file, chunksize=args.chunk_size)
            else:
                reader = pd.read_csv(
                    input_file,
                    sep=None,
                    engine="python",
                    names=["SMILES", "ligand:number"],
                    chunksize=args.chunk_size,
                )

            for chunk in reader:
                if (
                    "SMILES" not in chunk.columns
                    or "ligand:number" not in chunk.columns
                ):
                    if len(chunk.columns) >= 2:
                        chunk.columns = ["SMILES", "ligand:number"] + list(
                            chunk.columns[2:]
                        )
                    else:
                        continue

                if has_scores:
                    chunk = chunk.join(scores_df, on="ligand:number", how="inner")
                    if chunk.empty:
                        continue

                # Parallel execution
                results_raw = list(executor.map(worker_func, chunk.iterrows()))

                filtered_data = []
                for res, rej in results_raw:
                    if res:
                        filtered_data.append(res)
                    if args.verbose and rej:
                        print(f"  Rejected {rej[0]}: {rej[1]}")

                if filtered_data:
                    filtered_df = pd.DataFrame(filtered_data)
                    total_filtered += len(filtered_df)
                    csv_part = os.path.join(work_dir, f"part_{part_idx}.csv")
                    filtered_df.to_csv(csv_part, index=False)
                    part_files_csv.append(csv_part)
                    if args.smi_output:
                        smi_part = os.path.join(work_dir, f"part_{part_idx}.smi")
                        filtered_df[["SMILES", "ligand:number"]].to_csv(
                            smi_part, sep=" ", index=False, header=False
                        )
                        part_files_smi.append(smi_part)
                    part_idx += 1

                total_processed += len(chunk)

                # Progress reporting
                elapsed = time.time() - start_time
                rate = total_processed / elapsed if elapsed > 0 else 0

                # Handle cases where total was underestimated or header was counted
                display_total = max(total_to_process, total_processed)
                pct = (
                    (total_processed / display_total * 100) if display_total > 0 else 0
                )
                eta = (display_total - total_processed) / rate if rate > 0 else 0

                sys.stdout.write(
                    f"\rProgress: {total_processed}/{display_total} ({pct:.1f}%) | Rate: {rate:.0f} lig/s | Elapsed: {format_time(elapsed)} | ETA: {format_time(eta)}   "
                )
                sys.stdout.flush()

    print("\n" + "-" * 30)
    # Ensure output directory exists
    out_dir = os.path.dirname(final_output_csv)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Merge
    if part_files_csv:
        first = True
        for part in part_files_csv:
            pd.read_csv(part).to_csv(
                final_output_csv,
                mode="a",
                index=False,
                header=first,
                compression=compression,
            )
            first = False
            os.remove(part)
    else:
        cols = (
            ["SMILES", "ligand:number"]
            + (score_cols if has_scores else [])
            + ["MW", "LogP", "HBD", "HBA", "TPSA", "Charge", "HeavyAtoms"]
        )
        pd.DataFrame(columns=cols).to_csv(
            final_output_csv, index=False, compression=compression
        )
    if args.smi_output:
        final_output_smi = args.smi_output
        if args.compress and not final_output_smi.endswith(".gz"):
            final_output_smi += ".gz"

        os.makedirs(
            os.path.dirname(final_output_smi)
            if os.path.dirname(final_output_smi)
            else ".",
            exist_ok=True,
        )
        if part_files_smi:
            open_func = gzip.open if final_output_smi.endswith(".gz") else open
            mode = "wt" if final_output_smi.endswith(".gz") else "w"
            with open_func(final_output_smi, mode) as f_out:
                for part in part_files_smi:
                    with open(part, "r") as f_in:
                        f_out.write(f_in.read())
                    os.remove(part)
        else:
            with (
                gzip.open(final_output_smi, "wb")
                if final_output_smi.endswith(".gz")
                else open(final_output_smi, "w")
            ) as f:
                pass

        try:
            os.rmdir(work_dir)
        except:
            pass

        print(
            f"Parallel filtering complete.\nTotal Processed: {total_processed}\nKept: {total_filtered}\nResults: {final_output_csv}"
        )


if __name__ == "__main__":
    main()
