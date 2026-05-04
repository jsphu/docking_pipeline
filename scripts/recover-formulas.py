import os
from pathlib import Path
from collections import Counter


def get_molecule_fingerprint(pdbqt_path):
    """Counts atom types to create a molecular formula fingerprint."""
    atoms = []
    try:
        with open(pdbqt_path, "r") as f:
            for line in f:
                if line.startswith(("ATOM", "HETATM")):
                    # PDBQT atom type is typically the last column
                    atom_type = line.split()[-1]
                    atoms.append(atom_type)
        # Returns a sorted tuple like (('C', 10), ('H', 12)) which is hashable
        return tuple(sorted(Counter(atoms).items()))
    except Exception:
        return None


def restore_ligands(oops_dir, ref_root, target_code):
    oops_path = Path(oops_dir)
    ref_path = Path(ref_root)

    # 1. Index the 'oops' ligands by their fingerprint
    print(f"Indexing ligands in {oops_dir}...")
    oops_map = {}
    for f in oops_path.glob("*.pdbqt"):
        fingerprint = get_molecule_fingerprint(f)
        if fingerprint:
            if fingerprint not in oops_map:
                oops_map[fingerprint] = []
            oops_map[fingerprint].append(f)

    # 2. Scan reference directory and move matches
    print(f"Scanning reference directory: {ref_root}...")
    matches_found = 0

    # Using rglob to find all pdbqt files in the reference results
    for ref_file in ref_path.rglob("*.pdbqt"):
        ref_fingerprint = get_molecule_fingerprint(ref_file)

        if ref_fingerprint in oops_map and oops_map[ref_fingerprint]:
            source_file = oops_map[ref_fingerprint].pop(0)

            # 1. Generate target path
            target_dir_str = str(ref_file.parent).replace("6NJS", target_code)
            target_path = Path(target_dir_str)

            try:
                # 2. Ensure the destination folder exists
                target_path.mkdir(parents=True, exist_ok=True)

                # 3. Define full target file path
                destination = target_path / source_file.name

                print(f"Moving: {source_file.name} -> {destination}")

                # UNCOMMENT BELOW ONLY AFTER DRY RUN
                source_file.rename(destination)

                matches_found += 1
            except Exception as e:
                print(f"Error moving {source_file.name}: {e}")

    print(f"\nTask complete. Matches found and moved: {matches_found}")
    print(f"Files remaining in oops: {sum(len(v) for v in oops_map.values())}")


# Run the script
# Adjust these paths to your actual folder names
restore_ligands(oops_dir=".", ref_root="../results-6NJS", target_code="5TBM")
