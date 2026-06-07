import pandas as pd
import glob
import os
import argparse
import tarfile
import zipfile
import io

def process_pdbqt_content(content, name):
    """Extract score from PDBQT content."""
    for line in content.splitlines():
        if 'REMARK VINA RESULT:' in line:
            try:
                score = float(line.split()[3])
                return {'ligand:number': name.upper(), 'score': score}
            except:
                pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Collect docking results from PDBQT files or archives into a single CSV.")
    parser.add_argument("--input", nargs='+', required=True, help="Input PDBQT files, directories, or archives (.tar.gz, .zip)")
    parser.add_argument("--output", default="docking_scores.csv", help="Output CSV path")
    parser.add_argument("--chunk-size", type=int, default=5000, help="Batch size for writing")
    parser.add_argument("--compress", action="store_true", help="Compress output CSV using gzip")
    args = parser.parse_args()

    output_path = args.output
    if args.compress and not output_path.endswith('.gz'):
        output_path += '.gz'

    results = []
    total_found = 0
    first = True
    compression = 'gzip' if output_path.endswith('.gz') else None
    
    for item in args.input:
        if not os.path.exists(item):
            # Check if it's a glob
            files_glob = glob.glob(item)
            if not files_glob:
                print(f"Warning: {item} not found.")
                continue
            inputs_to_process = files_glob
        else:
            inputs_to_process = [item]

        for path in inputs_to_process:
            if os.path.isdir(path):
                for f in os.listdir(path):
                    if f.endswith('.pdbqt'):
                        full_f = os.path.join(path, f)
                        name = os.path.basename(f).replace('result_', '').replace('_out', '').replace('.pdbqt', '')
                        with open(full_f, 'r') as fh:
                            res = process_pdbqt_content(fh.read(), name)
                            if res:
                                results.append(res)
                                total_found += 1

            elif tarfile.is_tarfile(path):
                with tarfile.open(path, 'r:*') as tar:
                    for member in tar.getmembers():
                        if member.isfile() and member.name.endswith('.pdbqt'):
                            name = os.path.basename(member.name).replace('result_', '').replace('_out', '').replace('.pdbqt', '')
                            f = tar.extractfile(member)
                            if f:
                                content = f.read().decode('utf-8', errors='ignore')
                                res = process_pdbqt_content(content, name)
                                if res:
                                    results.append(res)
                                    total_found += 1
                                    
                        if len(results) >= args.chunk_size:
                            df = pd.DataFrame(results)
                            df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                            first = False
                            results = []

            elif zipfile.is_zipfile(path):
                with zipfile.ZipFile(path, 'r') as z:
                    for member in z.namelist():
                        if member.endswith('.pdbqt'):
                            name = os.path.basename(member).replace('result_', '').replace('_out', '').replace('.pdbqt', '')
                            with z.open(member) as f:
                                content = f.read().decode('utf-8', errors='ignore')
                                res = process_pdbqt_content(content, name)
                                if res:
                                    results.append(res)
                                    total_found += 1
                                    
                        if len(results) >= args.chunk_size:
                            df = pd.DataFrame(results)
                            df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                            first = False
                            results = []

            elif path.endswith('.pdbqt'):
                name = os.path.basename(path).replace('result_', '').replace('_out', '').replace('.pdbqt', '')
                with open(path, 'r') as fh:
                    res = process_pdbqt_content(fh.read(), name)
                    if res:
                        results.append(res)
                        total_found += 1

            # Flush results if chunk size reached
            if len(results) >= args.chunk_size:
                df = pd.DataFrame(results)
                df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)
                first = False
                results = []

    if results:
        df = pd.DataFrame(results)
        df.to_csv(output_path, mode='a', index=False, header=first, compression=compression)

    print(f"Collected {total_found} docking scores into {output_path}")

if __name__ == "__main__":
    main()
