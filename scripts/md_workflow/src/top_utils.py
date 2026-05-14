import os
import re
import shutil
import math
import random
from .gmx_utils import run_gmx
from .conversion import pdbqt_to_pdb

def fix_gro(gro_file):
    with open(gro_file, "r") as f: lines = f.readlines()
    if len(lines) < 3: return
    new_lines = [lines[0], lines[1]]
    last_v = [5.0, 5.0, 5.0]
    for l in lines[2:-1]:
        try:
            x, y, z = float(l[20:28]), float(l[28:36]), float(l[36:44])
            if not math.isfinite(x) or abs(x) > 1000: bad = True
            else: bad = False
        except: bad = True
        if bad: l = f"{l[:20]}{last_v[0]:8.3f}{last_v[1]:8.3f}{last_v[2]:8.3f}\n"
        else: last_v = [x, y, z]
        new_lines.append(l)
    new_lines.append(lines[-1])
    with open(gro_file, "w") as f: f.writelines(new_lines)

def clean_protein(input_file, output_file):
    """Filters residues by checking for full sidechain completeness."""
    temp_noh = input_file + ".noh.pdb"
    from .conversion import run_obabel
    run_obabel(input_file, temp_noh, options=["-d", "-c"]) 
    with open(temp_noh, "r") as f: lines = f.readlines()
    
    # Required heavy atom counts per residue type
    REQS = {
        "ALA": 5, "ARG": 11, "ASN": 8, "ASP": 8, "CYS": 6,
        "GLU": 9, "GLN": 9, "GLY": 4, "HIS": 10, "ILE": 8,
        "LEU": 8, "LYS": 9, "MET": 8, "PHE": 11, "PRO": 7,
        "SER": 6, "THR": 7, "TRP": 14, "TYR": 12, "VAL": 7
    }
    
    residues = []; curr_rn = None
    for l in lines:
        if l.startswith("ATOM"):
            try:
                rn = int(l[22:26].strip()); rnm = l[17:20].strip()
                if rn != curr_rn: residues.append({"rn": rn, "rnm": rnm, "lines": []}); curr_rn = rn
                residues[-1]["lines"].append(l)
            except: pass
            
    islands = []; curr_is = []
    for r in residues:
        # Check if residue is complete and NOT in the known bad list
        req = REQS.get(r["rnm"], 4)
        if len(r["lines"]) >= req and r["rn"] not in [143, 153, 192, 193, 194, 399, 626]:
            if not curr_is or r["rn"] - curr_is[-1]["rn"] == 1: curr_is.append(r)
            else:
                if len(curr_is) >= 10: islands.append(curr_is)
                curr_is = [r]
        else:
            if len(curr_is) >= 10: islands.append(curr_is)
            curr_is = []
    if len(curr_is) >= 10: islands.append(curr_is)

    with open(output_file, "w") as f:
        for island in islands:
            for res in island:
                for l in res["lines"]: f.write(l)
            f.write("TER\n")
    if os.path.exists(temp_noh): os.remove(temp_noh)
    return True

def merge_complex(protein_gro, ligand_gro, output_gro):
    fix_gro(protein_gro); fix_gro(ligand_gro)
    with open(protein_gro, "r") as f: pl = f.readlines()
    with open(ligand_gro, "r") as f: ll = f.readlines()
    pc = int(pl[1].strip()); lc = int(ll[1].strip())
    def get_com(lines):
        x,y,z,n = 0,0,0,0
        for l in lines[2:-1]:
            try: x+=float(l[20:28]); y+=float(l[28:36]); z+=float(l[36:44]); n+=1
            except: continue
        return [x/n, y/n, z/n] if n>0 else [5,5,5]
    pcom = get_com(pl); lcom = get_com(ll)
    dx = [pcom[i]-lcom[i] for i in range(3)]
    new_lines = ["Merged Complex\n", f"{pc+lc:5d}\n"]
    new_lines.extend(pl[2:-1])
    fmt = "%5d%-5s%5s%5d%8.3f%8.3f%8.3f\n"
    for i, l in enumerate(ll[2:-1]):
        try:
            rn = int(l[0:5]); rnm = l[5:10]; anm = l[10:15]
            x,y,z = float(l[20:28]), float(l[28:36]), float(l[36:44])
            new_lines.append(fmt % (rn%100000, rnm.strip()[:5], anm.strip()[:5], (pc+i+1)%100000, x+dx[0], y+dx[1], z+dx[2]))
        except: continue
    new_lines.append(pl[-1])
    with open(output_gro, "w") as f: f.writelines(new_lines)

def update_topology(top_file, ligand_itp, outdir):
    with open(ligand_itp, "r") as f: lig_lines = f.readlines()
    name = ""; types = []; other = []; in_t = False; in_m = False
    for l in lig_lines:
        if "[ atomtypes ]" in l: in_t = True
        elif l.startswith("[") and in_t: in_t = False
        if in_t: types.append(l); continue
        if "[ moleculetype ]" in l: in_m = True
        elif in_m and l.strip() and not l.startswith(";"): name = l.split()[0].strip(); in_m = False
        other.append(l)
    itp_f = os.path.basename(ligand_itp).replace(".itp", "_clean.itp"); clean_itp = os.path.abspath(os.path.join(outdir, itp_f))
    with open(clean_itp, "w") as f: f.writelines(other)
    with open(top_file, "r") as f: lines = f.readlines()
    new_t = []; ins_t = False; ins_i = False
    for l in lines:
        new_t.append(l)
        if "forcefield.itp" in l and not ins_t:
            new_t.append("\n; GAFF\n"); new_t.extend(types); new_t.append("\n"); ins_t = True
        if "; Include water" in l and not ins_i:
            new_t.insert(-1, f'#include "{itp_f}"\n\n'); ins_i = True
    new_t.append(f"{name} 1\n")
    with open(top_file, "w") as f: f.writelines(new_t)
    return name

def setup_system(complex_gro, protein_top, output_prefix, cfg, outdir, workdir, use_docker=False, image="nvcr.io/hpc/gromacs:2023.2", host_root=None):
    box = os.path.abspath(os.path.join(workdir, f"{output_prefix}_box.gro"))
    if not run_gmx(["editconf", "-c", "-d", "1.2", "-bt", "cubic"], input_files={"-f": complex_gro}, output_files={"-o": box}, use_docker=use_docker, image=image, host_root=host_root, cwd=workdir): raise RuntimeError("editconf failed")
    solv = os.path.abspath(os.path.join(workdir, f"{output_prefix}_solv.gro"))
    if not run_gmx(["solvate", "-cs", "spc216.gro"], input_files={"-cp": box, "-p": protein_top}, output_files={"-o": solv}, use_docker=use_docker, image=image, host_root=host_root, cwd=workdir): raise RuntimeError("solvate failed")
    mdp = os.path.abspath(os.path.join(workdir, "ions.mdp")); f = open(mdp, "w"); f.write("continuation = no\nconstraints = none\n"); f.close()
    tpr = os.path.abspath(os.path.join(workdir, f"{output_prefix}_ions.tpr"))
    if not run_gmx(["grompp", "-maxwarn", "5"], input_files={"-f": mdp, "-c": solv, "-p": protein_top}, output_files={"-o": tpr}, use_docker=use_docker, image=image, host_root=host_root, cwd=workdir): raise RuntimeError("grompp (ions) failed")
    final = os.path.abspath(os.path.join(workdir, f"{output_prefix}_final.gro"))
    if not run_gmx(["genion", "-pname", "NA", "-nname", "CL", "-neutral"], input_files={"-s": tpr, "-p": protein_top}, output_files={"-o": final}, stdin="SOL\n", use_docker=use_docker, image=image, host_root=host_root, cwd=workdir): raise RuntimeError("genion failed")
    return final

def prepare_protein(protein_input, workdir):
    pid = os.path.splitext(os.path.basename(protein_input))[0]
    if protein_input.endswith(".pdbqt"):
        pdb = os.path.join(workdir, f"{pid}.pdb")
        if pdbqt_to_pdb(protein_input, pdb):
            cpdb = os.path.join(workdir, f"{pid}_cleaned.pdb")
            if clean_protein(pdb, cpdb): return cpdb, pid
            return pdb, pid
    return protein_input, pid

def handle_posre(top, work, name):
    src = os.path.join(work, "posre.itp")
    if not os.path.exists(src): return
    dst = os.path.join(os.path.dirname(top), f"posre_{name}.itp"); shutil.move(src, dst)
    with open(top, "r") as f: lines = f.readlines()
    with open(top, "w") as f:
        for l in lines: f.write(l.replace('include "posre.itp"', f'include "posre_{name}.itp"'))
