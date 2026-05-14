import subprocess
import logging
import os

logger = logging.getLogger(__name__)


def run_obabel(input_file, output_file, options=None):
    """Utility to run obabel for format conversion."""
    cmd = ["obabel", input_file, "-O", output_file]
    if options:
        cmd.extend(options)

    logger.info(f"Converting: {input_file} -> {output_file}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Obabel Error: {result.stderr}")
        return False
    return True


def pdbqt_to_smiles(pdbqt_file, workdir=None):
    """Converts PDBQT to SMILES string."""
    out_dir = workdir or os.path.dirname(pdbqt_file)
    temp_smi = os.path.join(out_dir, os.path.basename(pdbqt_file) + ".smi")
    if run_obabel(pdbqt_file, temp_smi):
        with open(temp_smi, "r") as f:
            line = f.readline()
            smiles = line.split()[0]
        if os.path.exists(temp_smi):
            os.remove(temp_smi)
        return smiles
    return None


def pdbqt_to_pdb(pdbqt_file, pdb_file):
    """Converts PDBQT to PDB."""
    return run_obabel(pdbqt_file, pdb_file)
