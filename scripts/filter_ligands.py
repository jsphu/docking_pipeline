import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, rdmolops
import tomllib
import argparse
import os


def parse_rules(toml_path):
    with open(toml_path, "rb") as f:
        rules_data = tomllib.load(f)

    def create_test(expr):
        if not expr:
            return lambda x: True

        if isinstance(expr, list):
            # If multiple rules are provided as a list, they all must pass (AND logic)
            expr = " and ".join(f"({e})" for e in expr)

        try:
            # Pre-compile the expression for efficiency during the main loop
            code = compile(expr, "<string>", "eval")
            # Evaluate using restricted globals/locals for safety
            return lambda x: bool(eval(code, {"__builtins__": {}}, {"x": x}))
        except Exception as e:
            print(f"Warning: Could not parse or evaluate rule '{expr}': {e}")
            return lambda x: True

    return {k: create_test(v) for k, v in rules_data.items()}


def main():
    parser = argparse.ArgumentParser(
        description="Filter ligands based on rules and docking scores."
    )
    parser.add_argument(
        "--smiles",
        default="data/sorted_smiles.csv",
        help="Path to sorted SMILES CSV",
    )
    parser.add_argument(
        "--scores",
        default="data/sorted_file.csv",
        help="Path to sorted docking scores CSV",
    )
    parser.add_argument(
        "--rules",
        default="scripts/rules.toml",
        help="Path to toml file of rules",
    )
    parser.add_argument(
        "--output", default="scripts/filtered_ligands.csv", help="Output CSV path"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print details for each ligand"
    )

    args = parser.parse_args()

    if not os.path.exists(args.smiles) or not os.path.exists(args.scores):
        print("Error: SMILES or scores file not found.")
        return

    smiles_df = pd.read_csv(args.smiles)
    scores_df = pd.read_csv(args.scores)

    # Merge data on 'ligand:number'
    df = pd.merge(smiles_df, scores_df, on="ligand:number")

    # Parse rules once
    tests = parse_rules(args.rules)

    filtered_data = []

    print(f"Starting filtering of {len(df)} ligands...")

    for idx, row in df.iterrows():
        ligand_id = row["ligand:number"]
        smiles = row["SMILES"]
        mol = Chem.MolFromSmiles(smiles)

        if mol is None:
            if args.verbose:
                print(f"Skipping {ligand_id}: Invalid SMILES")
            continue

        # Fix the "radical" issue common in some explicit SMILES exports
        for atom in mol.GetAtoms():
            atom.SetNumRadicalElectrons(0)
            atom.SetNoImplicit(False)
        try:
            Chem.SanitizeMol(mol)
        except:
            if args.verbose:
                print(f"Skipping {ligand_id}: Sanitization failed")
            continue

        # Property calculations
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        psa = Descriptors.TPSA(mol)
        charge = rdmolops.GetFormalCharge(mol)
        heavy_atoms = mol.GetNumHeavyAtoms()

        # Rule evaluation
        pass_mw = tests.get("mw", lambda x: True)(mw)
        pass_logp = tests.get("logp", lambda x: True)(logp)
        pass_hbd = tests.get("hbd", lambda x: True)(hbd)
        pass_hba = tests.get("hba", lambda x: True)(hba)
        pass_psa = tests.get("psa", lambda x: True)(psa)
        pass_charge = tests.get("charge", lambda x: True)(charge)

        # Vina Score / Non-Hydrogen Atom Count >= 0.3
        # We check efficiency for all available receptor scores
        score_cols = [col for col in scores_df.columns if col != "ligand:number"]
        efficiencies = {}
        pass_efficiency = True

        for col in score_cols:
            score = row[col]
            if pd.isna(score):
                continue
            efficiency = abs(score) / heavy_atoms
            efficiencies[f"{col}_efficiency"] = efficiency
            if not tests.get("vs", lambda x: True)(efficiency):
                pass_efficiency = False

        if not efficiencies:
            pass_efficiency = False

        # Check if all criteria are met
        if all(
            [
                pass_mw,
                pass_logp,
                pass_hbd,
                pass_hba,
                pass_psa,
                pass_charge,
                pass_efficiency,
            ]
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
                }
            )
            row_dict.update(efficiencies)
            filtered_data.append(row_dict)
        elif args.verbose:
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
                reasons.append(f"PSA={psa:.1f}")
            if not pass_charge:
                reasons.append(f"Charge={charge}")
            if not pass_efficiency:
                le_val = min(efficiencies.values()) if efficiencies else 0
                reasons.append(f"LE={le_val:.2f}")
            print(f"Rejected {ligand_id}: {', '.join(reasons)}")

    filtered_df = pd.DataFrame(filtered_data)
    filtered_df.to_csv(args.output, index=False)

    print("-" * 30)
    print(f"Filtering complete.")
    print(f"Total ligands: {len(df)}")
    print(f"Filtered ligands: {len(filtered_df)}")
    print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    main()
