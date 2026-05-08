import pandas as pd
import argparse

parser = argparse.ArgumentParser()

parser.add_argument("FILE")
parser.add_argument("LIG1")
parser.add_argument("LIG2")

parser.add_argument("-m", "--minimum", default=100.0, type=float)
parser.add_argument("-o", "--output", default="sorted_file.csv")
parser.add_argument("-r", "--reference")
parser.add_argument("-s", "--smilesonly", action="store_true")

args = parser.parse_args()

df = pd.read_csv(args.FILE)

newdf = pd.DataFrame()

newdf["multi-index"] = df[f"{args.LIG1}-model-1"] * df[f"{args.LIG2}-model-1"]

newdf["ligand:number"] = (
    df["path-name"].astype(str) + ":" + df["ligand-number"].astype(str)
)
newdf[args.LIG1] = df[f"{args.LIG1}-model-1"]
newdf[args.LIG2] = df[f"{args.LIG2}-model-1"]

sorted = newdf.sort_values(by=["multi-index"], ascending=False)
sorted = sorted[sorted["multi-index"] >= args.minimum]

sorted = sorted.drop(columns=["multi-index"])

order = ["SMILES", "ligand:number", args.LIG1, args.LIG2]

if args.reference:
    ref = pd.read_csv(args.reference)
    ref["ligand:number"] = (
        ref["path-name"].astype(str) + ":" + ref["ligand-number"].astype(str)
    )
    sorted = pd.merge(
        sorted, ref[["ligand:number", "SMILES"]], on="ligand:number", how="left"
    )

if args.reference and args.smilesonly:
    sorted = sorted[["SMILES", "ligand:number"]]
else:
    if not args.reference:
        order.pop(0)

    sorted = sorted.reindex(columns=order)

print("Total ligands remain: ", len(sorted))

sorted.to_csv(args.output, index=False)
