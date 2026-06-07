import pandas as pd
import glob
import os
import argparse
from rdkit import Chem
import tarfile
import zipfile
import io

def extract_smiles_from_content(content):
    try:
        # Clean PDBQT for RDKit
        pdb_lines = []
        for line in content.splitlines():
            if line.startswith('ATOM'):
                parts = line.split()
                element = parts[-1]
                mapping = {'A': 'C', 'NA': 'N', 'OA': 'O', 'SA': 'S', 'HD': 'H'}
                element = mapping.get(element, element)
                new_line = line[:76] + element.rjust(2) + line[78:]
                pdb_lines.append(new_line)
            elif line.startswith(('REMARK', 'TER', 'END', 'MODEL', 'ENDMDL')):
                pdb_lines.append(line)

        # Process first model
        first_model = []
        in_model = False
        for l in pdb_lines:
            if l.startswith('MODEL'):
                if in_model: break
                in_model = True
            if in_model: first_model.append(l)
            if l.startswith('ENDMDL'): break
        if not first_model: first_model = pdb_lines

        mol = Chem.MolFromPDBBlock('\n'.join(first_model), removeHs=True, proximityBonding=True)
        if mol:
            for atom in mol.GetAtoms():
                atom.SetNumRadicalElectrons(0)
                atom.SetNoImplicit(False)
            Chem.SanitizeMol(mol)
            return Chem.MolToSmiles(mol, canonical=True)
    except:
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Extract SMILES from PDBQT files or archives into a single CSV.")
    parser.add_argument("--input", nargs='+', required=True, help="Input PDBQT files, directories, or archives (.tar.gz, .zip)")
    parser.add_argument("--output", default="all_smiles.csv", help="Output CSV path")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Batch size for writing")
    parser.add_argument("--compress", action="store_true", help="Compress output CSV using gzip")
    args = parser.parse_args()

    output_path = args.output
    if args.compress and not output_path.endswith('.gz'):
        output_path += '.gz'

    data = []
    total_found = 0
    first = True
    compression = 'gzip' if output_path.endswith('.gz') else None
    
    for item in args.input:
        if not os.path.exists(item):
            files_glob = glob.glob(item)
            if not files_glob:
                print(f"Warning: {item} not found.")
                continue
            inputs_to_process = files_glob
        else:
            inputs_to_process = [item]

        for path in inputs_to_process:
            if os.path.isdir(path):
                files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.pdbqt')]
                for f_path in files:
                    name = os.path.basename(f_path).replace('.pdbqt', '')
                    with open(f_path, 'r') as fh:
                        smi = extract_smiles_from_content(fh.read())
                        if smi:
                            data.append({'ligand:number': name.upper(), 'SMILES': smi})
                            total_found += 1
                    
                    if len(data) >= args.chunk_size:
                        df = pd.DataFrame(data)
                        df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                        first = False
                        data = []

            elif tarfile.is_tarfile(path):
                with tarfile.open(path, 'r:*') as tar:
                    for member in tar.getmembers():
                        if member.isfile() and member.name.endswith('.pdbqt'):
                            name = os.path.basename(member.name).replace('.pdbqt', '')
                            f = tar.extractfile(member)
                            if f:
                                content = f.read().decode('utf-8', errors='ignore')
                                smi = extract_smiles_from_content(content)
                                if smi:
                                    data.append({'ligand:number': name.upper(), 'SMILES': smi})
                                    total_found += 1
                                    
                        if len(data) >= args.chunk_size:
                            df = pd.DataFrame(data)
                            df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                            first = False
                            data = []

            elif zipfile.is_zipfile(path):
                with zipfile.ZipFile(path, 'r') as z:
                    for member in z.namelist():
                        if member.endswith('.pdbqt'):
                            name = os.path.basename(member).replace('.pdbqt', '')
                            with z.open(member) as f:
                                content = f.read().decode('utf-8', errors='ignore')
                                smi = extract_smiles_from_content(content)
                                if smi:
                                    data.append({'ligand:number': name.upper(), 'SMILES': smi})
                                    total_found += 1
                                    
                        if len(data) >= args.chunk_size:
                            df = pd.DataFrame(data)
                            df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                            first = False
                            data = []

            elif path.endswith('.pdbqt'):
                name = os.path.basename(path).replace('.pdbqt', '')
                with open(path, 'r') as fh:
                    smi = extract_smiles_from_content(fh.read())
                    if smi:
                        data.append({'ligand:number': name.upper(), 'SMILES': smi})
                        total_found += 1

            if len(data) >= args.chunk_size:
                df = pd.DataFrame(data)
                df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                first = False
                data = []

    if data:
        df = pd.DataFrame(data)
        df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)

    print(f"Extracted {total_found} SMILES into {output_path}")

if __name__ == "__main__":
    main()
