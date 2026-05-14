import os
import logging
from rdkit import Chem
from rdkit.Chem import AllChem
from .conversion import pdbqt_to_smiles, run_obabel

logger = logging.getLogger(__name__)


def clean_molecule(smiles, add_hs=True, generate_3d=True, minimize=True):
    """
    Cleans and prepares a molecule using RDKit for MD simulations.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string: {smiles}")

    if add_hs:
        mol = Chem.AddHs(mol)

    if generate_3d:
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        res = AllChem.EmbedMolecule(mol, params)
        if res != 0:
            AllChem.EmbedMolecule(mol, randomSeed=42)

        if minimize:
            try:
                AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94")
            except Exception as e:
                logger.warning(f"Warning: MMFF minimization failed: {e}")

    return mol


def prepare_ligand(ligand_name, smiles, output_dir, run_command_func):
    """
    Prepares ligand topology using RDKit for 3D prep and acpype for GMX topology.
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        mol = clean_molecule(smiles)
    except Exception as e:
        logger.error(f"Error cleaning molecule {ligand_name}: {e}")
        return None, None

    pdb_file = os.path.join(output_dir, f"{ligand_name}_rdkit.pdb")
    Chem.MolToPDBFile(mol, pdb_file)

    if not run_command_func(
        [
            "acpype",
            "-i",
            pdb_file,
            "-c",
            "bcc",
            "-n",
            "0",
            "-a",
            "gaff2",
            "-b",
            ligand_name,
        ],
        cwd=output_dir,
    ):
        return None, None

    acpype_out_dir = os.path.join(output_dir, f"{ligand_name}.acpype")
    itp_file = os.path.abspath(os.path.join(acpype_out_dir, f"{ligand_name}_GMX.itp"))
    gro_file = os.path.abspath(os.path.join(acpype_out_dir, f"{ligand_name}_GMX.gro"))

    if os.path.exists(itp_file) and os.path.exists(gro_file):
        return itp_file, gro_file
    return None, None


def extract_first_model_pdbqt(pdbqt_file, output_file):
    """Manually extracts the first model from a PDBQT file."""
    with open(pdbqt_file, "r") as f:
        lines = f.readlines()

    model_lines = []
    has_model_tag = False
    for line in lines:
        if line.startswith("MODEL 1"):
            has_model_tag = True
            continue
        if has_model_tag and (line.startswith("ENDMDL") or line.startswith("MODEL 2")):
            break
        if not has_model_tag:
            if line.startswith("MODEL 2"):
                break
            if any(
                line.startswith(prefix)
                for prefix in [
                    "ATOM",
                    "HETATM",
                    "ROOT",
                    "ENDROOT",
                    "BRANCH",
                    "ENDBRANCH",
                ]
            ):
                model_lines.append(line)
        else:
            model_lines.append(line)

    if not model_lines:
        model_lines = lines

    with open(output_file, "w") as f:
        f.writelines(model_lines)


def prepare_ligand_from_pose(ligand_file, output_dir, run_command_func):
    """
    Prepares ligand topology while strictly preserving the 3D coordinates (pose).
    Uses a template-based approach to fix bond orders and hydrogens.
    """
    os.makedirs(output_dir, exist_ok=True)
    ligand_name = os.path.splitext(os.path.basename(ligand_file))[0]

    # 1. Get SMILES for correct bond orders
    # We use pdbqt_to_smiles and then clean it of radicals []
    raw_smiles = pdbqt_to_smiles(ligand_file, workdir=output_dir)
    if not raw_smiles:
        logger.error(f"Error: Could not get SMILES from {ligand_file}")
        return None, None

    # Clean SMILES (remove brackets used for radicals in obabel output)
    clean_smi = raw_smiles.replace("[", "").replace("]", "")
    template = Chem.MolFromSmiles(clean_smi)
    if not template:
        # Try without cleaning if RDKit can handle it
        template = Chem.MolFromSmiles(raw_smiles)

    if not template:
        logger.error(f"Error: RDKit failed to parse SMILES for {ligand_name}")
        return None, None

    # 2. Extract first model as PDB (heavy only)
    model1_pdbqt = os.path.join(output_dir, f"{ligand_name}_model1.pdbqt")
    extract_first_model_pdbqt(ligand_file, model1_pdbqt)

    heavy_pdb = os.path.join(output_dir, f"{ligand_name}_heavy.pdb")
    if not run_obabel(model1_pdbqt, heavy_pdb):
        return None, None

    try:
        # 3. Load heavy coordinates without automatic bonding
        pose_mol = Chem.MolFromPDBFile(heavy_pdb, proximityBonding=False)
        if not pose_mol:
            raise RuntimeError("RDKit failed to read heavy PDB")

        # 4. Assign Bond Orders from Template
        # This is the magic step that fixes everything
        fixed_mol = AllChem.AssignBondOrdersFromTemplate(template, pose_mol)

        # 5. Add Hydrogens while preserving coordinates
        fixed_mol = Chem.AddHs(fixed_mol, addCoords=True)

        # 6. Final verification
        total_electrons = sum([a.GetAtomicNum() for a in fixed_mol.GetAtoms()])
        if total_electrons % 2 != 0:
            logger.warning(
                f"Warning: {ligand_name} still has an odd number of electrons ({total_electrons})."
            )

        # 7. Write to PDB for acpype
        final_input = os.path.join(output_dir, f"{ligand_name}_fixed.pdb")
        Chem.MolToPDBFile(fixed_mol, final_input)

    except Exception as e:
        logger.error(
            f"Error during template-based prep for {ligand_name}: {e}. Falling back to standard conversion."
        )
        final_input = os.path.join(output_dir, f"{ligand_name}_pose.pdb")
        run_obabel(model1_pdbqt, final_input, options=["-h"])

    # Run acpype
    if not run_command_func(
        [
            "acpype",
            "-i",
            final_input,
            "-c",
            "bcc",
            "-n",
            "0",
            "-a",
            "gaff2",
            "-b",
            ligand_name,
        ],
        cwd=output_dir,
    ):
        return None, None

    acpype_out_dir = os.path.join(output_dir, f"{ligand_name}.acpype")
    itp_file = os.path.abspath(os.path.join(acpype_out_dir, f"{ligand_name}_GMX.itp"))
    gro_file = os.path.abspath(os.path.join(acpype_out_dir, f"{ligand_name}_GMX.gro"))

    if os.path.exists(itp_file) and os.path.exists(gro_file):
        return itp_file, gro_file
    return None, None


def prepare_ligand_from_file(ligand_file, output_dir, run_command_func):
    """
    Handles ligand preparation. If it's a coordinate-based file (PDBQT/MOL2),
    it preserves the pose.
    """
    return prepare_ligand_from_pose(ligand_file, output_dir, run_command_func)
