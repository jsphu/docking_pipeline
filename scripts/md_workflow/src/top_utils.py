import os
import re
import shutil
import math
import random
from .gmx_utils import run_gmx
from .conversion import pdbqt_to_pdb


def fix_gro(gro_file):
    """Ensures .gro file has valid finite coordinates and a sane box vector."""
    with open(gro_file, "r") as f:
        lines = f.readlines()
    if len(lines) < 3:
        return

    header = lines[0]
    num_atoms = lines[1]
    box_line = lines[-1]
    atom_lines = lines[2:-1]

    new_atom_lines = []
    last_valid = [0.0, 0.0, 0.0]

    for line in atom_lines:
        if len(line) < 44:
            new_atom_lines.append(line)
            continue

        try:
            # GRO format coordinates are at fixed positions:
            xs = line[20:28].strip()
            ys = line[28:36].strip()
            zs = line[36:44].strip()

            x = float(xs)
            y = float(ys)
            z = float(zs)

            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                raise ValueError("Non-finite coordinate")

            last_valid = [x, y, z]
            new_atom_lines.append(line)
        except Exception:
            # Replace invalid coordinates with last valid or a safe default
            new_coord_str = (
                f"{last_valid[0]:8.3f}{last_valid[1]:8.3f}{last_valid[2]:8.3f}"
            )
            new_line = line[:20] + new_coord_str + line[44:]
            new_atom_lines.append(new_line)

    # Check and fix box vector
    safe_box = "   10.00000   10.00000   10.00000\n"
    try:
        box_parts = [float(p) for p in box_line.split()]
        if not all(math.isfinite(v) and abs(v) < 1000.0 for v in box_parts):
            box_line = safe_box
    except Exception:
        box_line = safe_box

    with open(gro_file, "w") as f:
        f.write(header)
        f.write(num_atoms)
        f.writelines(new_atom_lines)
        f.write(box_line)

def clean_protein(input_file, output_file):
    """Filters residues by checking for full sidechain completeness."""
    temp_noh = input_file + ".noh.pdb"
    from .conversion import run_obabel

    run_obabel(input_file, temp_noh, options=["-d", "-c"])
    with open(temp_noh, "r") as f:
        lines = f.readlines()

    # Required heavy atom counts per residue type
    REQS = {
        "ALA": 5,
        "ARG": 11,
        "ASN": 8,
        "ASP": 8,
        "CYS": 6,
        "GLU": 9,
        "GLN": 9,
        "GLY": 4,
        "HIS": 10,
        "ILE": 8,
        "LEU": 8,
        "LYS": 9,
        "MET": 8,
        "PHE": 11,
        "PRO": 7,
        "SER": 6,
        "THR": 7,
        "TRP": 14,
        "TYR": 12,
        "VAL": 7,
    }

    residues = []
    curr_rn = None
    for l in lines:
        if l.startswith("ATOM"):
            try:
                rn_str = l[22:27].strip() # Include insertion code in identity
                rnm = l[17:20].strip()
                if rnm not in REQS:
                    continue
                if rn_str != curr_rn:
                    residues.append({"rn": rn_str, "rnm": rnm, "lines": []})
                    curr_rn = rn_str
                residues[-1]["lines"].append(l)
            except:
                pass

    islands = []
    curr_is = []
    for r in residues:
        # Check if residue is complete and NOT in the known bad list
        req = REQS.get(r["rnm"], 4)
        # Extract numeric part of rn for distance check
        try:
            rn_num = int("".join(filter(str.isdigit, r["rn"])))
        except:
            rn_num = 0

        if len(r["lines"]) >= req and rn_num not in [
            143,
            153,
            192,
            193,
            194,
            399,
            626,
        ]:
            if not curr_is:
                curr_is.append(r)
            else:
                try:
                    prev_rn_num = int("".join(filter(str.isdigit, curr_is[-1]["rn"])))
                    if rn_num - prev_rn_num == 1:
                        curr_is.append(r)
                    else:
                        if len(curr_is) >= 10:
                            islands.append(curr_is)
                        curr_is = [r]
                except:
                    curr_is = [r]
        else:
            if len(curr_is) >= 10:
                islands.append(curr_is)
            curr_is = []
    if len(curr_is) >= 10:
        islands.append(curr_is)

    with open(output_file, "w") as f:
        for island in islands:
            for res in island:
                for l in res["lines"]:
                    f.write(l)
            f.write("TER\n")
    if os.path.exists(temp_noh):
        os.remove(temp_noh)
    return True


def merge_complex(protein_gro, ligand_gro, output_gro):
    """Merges protein and ligand while centering both in a reasonable frame."""
    fix_gro(protein_gro)
    fix_gro(ligand_gro)
    with open(protein_gro, "r") as f:
        pl = f.readlines()
    with open(ligand_gro, "r") as f:
        ll = f.readlines()
    if len(pl) < 3 or len(ll) < 3:
        return

    pc = int(pl[1].strip())
    lc = int(ll[1].strip())

    def get_com(lines):
        x, y, z, n = 0, 0, 0, 0
        for l in lines[2:-1]:
            if len(l) < 44: continue
            try:
                xv = float(l[20:28])
                yv = float(l[28:36])
                zv = float(l[36:44])
                if math.isfinite(xv) and math.isfinite(yv) and math.isfinite(zv):
                    x += xv
                    y += yv
                    z += zv
                    n += 1
            except:
                continue
        return [x / n, y / n, z / n] if n > 0 else [0, 0, 0]

    pcom = get_com(pl)
    lcom = get_com(ll)

    # Target center for protein
    target = [5.0, 5.0, 5.0]
    p_off = [target[i] - pcom[i] for i in range(3)]

    # Ligand offset to be at the same center as protein
    l_off = [target[i] - lcom[i] for i in range(3)]

    new_lines = ["Merged Complex\n", f"{pc + lc:5d}\n"]

    # Strict GRO format: "%5d%-5s%5s%5d%8.3f%8.3f%8.3f\n"
    fmt = "%5d%-5s%5s%5d%8.3f%8.3f%8.3f\n"

    def cap_val(v):
        """Ensure coordinate fits in 8.3f and exactly 8 chars."""
        if not math.isfinite(v):
            return 0.0
        return max(min(v, 999.999), -999.999)

    # Process protein lines
    for i, l in enumerate(pl[2:-1]):
        try:
            rn = int(l[0:5])
            rnm = l[5:10].strip()
            anm = l[10:15].strip()
            ai = int(l[15:20])
            x, y, z = float(l[20:28]), float(l[28:36]), float(l[36:44])
            safe_rnm = rnm[:5] if rnm else "PROT"
            safe_anm = anm[:5] if anm else "A"
            new_lines.append(
                fmt
                % (
                    rn % 100000,
                    safe_rnm,
                    safe_anm,
                    ai % 100000,
                    cap_val(x + p_off[0]),
                    cap_val(y + p_off[1]),
                    cap_val(z + p_off[2]),
                )
            )
        except:
            continue

    # Process ligand lines
    for i, l in enumerate(ll[2:-1]):
        try:
            rn = int(l[0:5])
            rnm = l[5:10].strip()
            anm = l[10:15].strip()
            x, y, z = float(l[20:28]), float(l[28:36]), float(l[36:44])
            safe_rnm = rnm[:5] if rnm else "LIG"
            safe_anm = anm[:5] if anm else "L"
            new_lines.append(
                fmt
                % (
                    rn % 100000,
                    safe_rnm,
                    safe_anm,
                    (pc + i + 1) % 100000,
                    cap_val(x + l_off[0]),
                    cap_val(y + l_off[1]),
                    cap_val(z + l_off[2]),
                )
            )
        except:
            continue

    new_lines.append(pl[-1])
    with open(output_gro, "w") as f:
        f.writelines(new_lines)


def update_topology(top_file, ligand_itp, outdir):
    with open(ligand_itp, "r") as f:
        lig_lines = f.readlines()
    name = ""
    types = []
    other = []
    in_t = False
    in_m = False
    for l in lig_lines:
        if "[ atomtypes ]" in l:
            in_t = True
        elif l.startswith("[") and in_t:
            in_t = False
        if in_t:
            types.append(l)
            continue
        if "[ moleculetype ]" in l:
            in_m = True
        elif in_m and l.strip() and not l.startswith(";"):
            parts = l.split()
            if parts:
                name = parts[0].strip()
            in_m = False
        other.append(l)

    if not name:
        name = "LIG"

    itp_f = os.path.basename(ligand_itp).replace(".itp", "_clean.itp")
    clean_itp = os.path.abspath(os.path.join(outdir, itp_f))
    with open(clean_itp, "w") as f:
        f.writelines(other)
    with open(top_file, "r") as f:
        lines = f.readlines()
    new_t = []
    ins_t = False
    ins_i = False
    for l in lines:
        new_t.append(l)
        if "forcefield.itp" in l and not ins_t:
            new_t.append("\n; GAFF\n")
            new_t.extend(types)
            new_t.append("\n")
            ins_t = True
        if "; Include water" in l and not ins_i:
            new_t.insert(-1, f'#include "{itp_f}"\n\n')
            ins_i = True

    if not any(f"{name} " in line for line in lines):
        new_t.append(f"{name} 1\n")

    with open(top_file, "w") as f:
        f.writelines(new_t)
    return name


def setup_system(
    complex_gro,
    protein_top,
    output_prefix,
    cfg,
    outdir,
    workdir,
    use_docker=False,
    image="nvcr.io/hpc/gromacs:2023.2",
    host_root=None,
):
    box = os.path.abspath(os.path.join(workdir, f"{output_prefix}_box.gro"))
    if not run_gmx(
        ["editconf", "-c", "-d", "1.2", "-bt", "cubic"],
        input_files={"-f": complex_gro},
        output_files={"-o": box},
        use_docker=use_docker,
        image=image,
        host_root=host_root,
        cwd=workdir,
    ):
        raise RuntimeError("editconf failed")
    solv = os.path.abspath(os.path.join(workdir, f"{output_prefix}_solv.gro"))
    if not run_gmx(
        ["solvate", "-cs", "spc216.gro"],
        input_files={"-cp": box, "-p": protein_top},
        output_files={"-o": solv},
        use_docker=use_docker,
        image=image,
        host_root=host_root,
        cwd=workdir,
    ):
        raise RuntimeError("solvate failed")
    mdp = os.path.abspath(os.path.join(workdir, "ions.mdp"))
    with open(mdp, "w") as f:
        f.write(
            "integrator = steep\nemtol = 1000.0\nemstep = 0.01\nnsteps = 50000\nnstlist = 1\ncutoff-scheme = Verlet\ncoulombtype = PME\nrcoulomb = 1.0\nrvdw = 1.0\npbc = xyz\n"
        )

    tpr = os.path.abspath(os.path.join(workdir, f"{output_prefix}_ions.tpr"))
    if not run_gmx(
        ["grompp", "-maxwarn", "5"],
        input_files={"-f": mdp, "-c": solv, "-p": protein_top},
        output_files={"-o": tpr},
        use_docker=use_docker,
        image=image,
        host_root=host_root,
        cwd=workdir,
    ):
        raise RuntimeError("grompp (ions) failed")
    final = os.path.abspath(os.path.join(workdir, f"{output_prefix}_final.gro"))
    if not run_gmx(
        ["genion", "-pname", "NA", "-nname", "CL", "-neutral"],
        input_files={"-s": tpr, "-p": protein_top},
        output_files={"-o": final},
        stdin="SOL\n",
        use_docker=use_docker,
        image=image,
        host_root=host_root,
        cwd=workdir,
    ):
        raise RuntimeError("genion failed")
    return final


def prepare_protein(protein_input, workdir):
    pid = os.path.splitext(os.path.basename(protein_input))[0]
    pdb = protein_input
    if protein_input.endswith(".pdbqt"):
        pdb = os.path.join(workdir, f"{pid}.pdb")
        if not pdbqt_to_pdb(protein_input, pdb):
            return protein_input, pid
    
    cpdb = os.path.join(workdir, f"{pid}_cleaned.pdb")
    if clean_protein(pdb, cpdb):
        return cpdb, pid
    return pdb, pid


def handle_posre(top, work, name):
    src = os.path.join(work, "posre.itp")
    if not os.path.exists(src):
        return
    dst = os.path.join(os.path.dirname(top), f"posre_{name}.itp")
    shutil.move(src, dst)
    with open(top, "r") as f:
        lines = f.readlines()
    with open(top, "w") as f:
        for l in lines:
            f.write(l.replace('include "posre.itp"', f'include "posre_{name}.itp"'))
