#!/usr/bin/env python3
import sys
import os

def main():
    if len(sys.argv) < 3:
        print("non-Protein")
        sys.exit(0)

    tpr = sys.argv[1]
    complex_name = sys.argv[2]
    
    # Run make_ndx to generate temporary index file to inspect group names
    os.system(f"echo 'q' | gmx make_ndx -f {tpr} -o {complex_name}_tmp.ndx >/dev/null 2>&1")

    groups = []
    ndx_file = f"{complex_name}_tmp.ndx"
    if os.path.exists(ndx_file):
        with open(ndx_file, "r") as f:
            for line in f:
                if line.startswith("["):
                    groups.append(line.strip("[] \n"))
        try:
            os.remove(ndx_file)
        except:
            pass

    # Look for common ligand identifiers
    lig_group = "non-Protein"
    for g in groups:
        if g.upper() in ["LIG", "UNK"]:
            lig_group = g
            print(lig_group)
            sys.exit(0)

    # Standard GROMACS groups to filter out
    standard = [
        "System", "Protein", "Protein-H", "C-alpha", "Backbone", "MainChain",
        "MainChain+Cb", "MainChain+H", "SideChain", "SideChain-H", "Prot-Masses",
        "non-Protein", "Water", "SOL", "non-Water", "Ion", "NA", "CL", "Water_and_Ions"
    ]

    # Find the first non-standard group (which is the ligand)
    for g in groups:
        if g not in standard:
            lig_group = g
            break

    print(lig_group)

if __name__ == "__main__":
    main()
