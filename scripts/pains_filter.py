import pandas as pd
from rdkit import Chem
from rdkit.Chem import FilterCatalog
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from functools import partial

# Global catalog for workers
_WORKER_CATALOG = None

def init_worker():
    """Initialize worker process by loading PAINS catalog once."""
    global _WORKER_CATALOG
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    _WORKER_CATALOG = FilterCatalog.FilterCatalog(params)

def process_single_mol(row_tuple):
    """Worker function to check a single molecule for PAINS using global catalog."""
    idx, row = row_tuple
    smiles = row["SMILES"]
    mol = Chem.MolFromSmiles(smiles)

    if mol:
        for atom in mol.GetAtoms():
            atom.SetNumRadicalElectrons(0)
            atom.SetNoImplicit(False)
        try:
            Chem.SanitizeMol(mol)
        except:
            pass
        
        if _WORKER_CATALOG.HasMatch(mol):
            return "PAINS"
        else:
            return row.to_dict()
    else:
        return "INVALID"

def apply_pains_filter(input_files, output_csv, output_smi=None, chunk_size=5000, compress=False, cpus=os.cpu_count()):
    work_dir = "work_pains"
    os.makedirs(work_dir, exist_ok=True)
    
    part_files_csv = []
    part_files_smi = []
    pains_count = 0
    total_initial = 0
    total_clean = 0
    part_idx = 0

    print(f"Applying parallel PAINS filter with {cpus} CPUs (chunk_size={chunk_size})...")

    final_output_csv = output_csv
    if compress and not final_output_csv.endswith('.gz'):
        final_output_csv += '.gz'
    compression = 'gzip' if final_output_csv.endswith('.gz') else None

    with ProcessPoolExecutor(max_workers=cpus, initializer=init_worker) as executor:
        for input_file in input_files:
            if not os.path.exists(input_file):
                print(f"Warning: {input_file} not found. Skipping.")
                continue

            if input_file.endswith('.csv') or input_file.endswith('.csv.gz'):
                reader = pd.read_csv(input_file, chunksize=chunk_size)
            else:
                reader = pd.read_csv(input_file, sep=None, engine='python', names=['SMILES', 'ligand:number'], chunksize=chunk_size)

            for chunk in reader:
                if 'SMILES' not in chunk.columns or 'ligand:number' not in chunk.columns:
                    if len(chunk.columns) >= 2:
                        chunk.columns = ['SMILES', 'ligand:number'] + list(chunk.columns[2:])
                    elif len(chunk.columns) == 1:
                        chunk.columns = ['SMILES']
                        chunk['ligand:number'] = [f"LIG_{i}_{part_idx}" for i in range(len(chunk))]
                    else:
                        continue

                total_initial += len(chunk)

                # Parallel map
                results = list(executor.map(process_single_mol, chunk.iterrows()))
                
                pains_free_data = []
                for res in results:
                    if res == "PAINS":
                        pains_count += 1
                    elif res == "INVALID":
                        pass
                    else:
                        pains_free_data.append(res)

                if pains_free_data:
                    pains_free_df = pd.DataFrame(pains_free_data)
                    total_clean += len(pains_free_df)
                    
                    csv_part = os.path.join(work_dir, f"part_{part_idx}.csv")
                    pains_free_df.to_csv(csv_part, index=False)
                    part_files_csv.append(csv_part)
                    
                    if output_smi:
                        smi_part = os.path.join(work_dir, f"part_{part_idx}.smi")
                        pains_free_df[['SMILES', 'ligand:number']].to_csv(smi_part, sep=' ', index=False, header=False)
                        part_files_smi.append(smi_part)
                    
                    part_idx += 1

    # Merge partitions
    if part_files_csv:
        first = True
        for part in part_files_csv:
            df_part = pd.read_csv(part)
            df_part.to_csv(final_output_csv, mode='a', index=False, header=first, compression=compression)
            first = False
            os.remove(part)
    else:
        # Create an empty output file with header if possible
        print("-" * 30)
        print("No ligands passed the rules being applied.")
        
        if final_output_csv.endswith('.gz'):
            import gzip
            with gzip.open(final_output_csv, 'wb') as f:
                pass
        else:
            with open(final_output_csv, 'w') as f:
                pass

    if output_smi:
        final_output_smi = output_smi
        if compress and not final_output_smi.endswith('.gz'):
            final_output_smi += '.gz'
        
        if part_files_smi:
            import gzip
            open_func = gzip.open if final_output_smi.endswith('.gz') else open
            mode = 'wt' if final_output_smi.endswith('.gz') else 'w'
            with open_func(final_output_smi, mode) as f_out:
                for part in part_files_smi:
                    with open(part, 'r') as f_in:
                        f_out.write(f_in.read())
                    os.remove(part)
        else:
            if final_output_smi.endswith('.gz'):
                import gzip
                with gzip.open(final_output_smi, 'wb') as f:
                    pass
            else:
                with open(final_output_smi, 'w') as f:
                    pass

    try: os.rmdir(work_dir)
    except: pass

    print("-" * 30)
    print(f"PAINS filtering complete.")
    print(f"Initial leads: {total_initial}")
    print(f"PAINS matches removed: {pains_count}")
    print(f"Final clean leads: {total_clean}")
    print(f"Clean leads saved to: {final_output_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs='+', required=True, help="Input CSV or SMI file(s)")
    parser.add_argument("--output", default="filtered_ligands_pains_free.csv", help="Output CSV path")
    parser.add_argument("--smi-output", default=None, help="Output SMI path (optional)")
    parser.add_argument("--chunk-size", type=int, default=5000, help="Processing chunk size")
    parser.add_argument("--cpus", type=int, default=os.cpu_count(), help="Number of CPUs to use")
    parser.add_argument("--compress", action="store_true", help="Compress output files using gzip")
    args = parser.parse_args()
    apply_pains_filter(args.input, args.output, args.smi_output, args.chunk_size, args.compress, args.cpus)
