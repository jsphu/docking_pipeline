#!/usr/bin/env bash

PIPELINEDIR="$1"
RESULTSPREFIX="$2"
shift 2
COMP1="$1"
COMP2="$2"

if [[ -z $PIPELINEDIR || -z $RESULTSPREFIX ]]; then
  echo "usage: $0 <Pipeline-Directory> <Results-Directory-Prefix> <Compared-Name> <Compared-Name>"
  echo ""
  echo "Examples:"
  echo "      $0 /home/me/docking_pipeline/ results- 5TBM 6NJS"
  echo "      $0 /home/me/docking_pipeline/ scores- 5ASD 12FD"
  exit 1
fi

docking_scores() {
  local prot=${1?a protein name required.}
  local head=${2:-10}
  local only_table=${3:-false}

  (
    cd "$PIPELINEDIR/${RESULTSPREFIX}${prot^^}" || return 1

    scores=$(grep -rHA1 'MODEL ' . | sed -n '/MODEL/ {N; s/\n/ /; p}' | awk -F'[: ]+' '{
        # $1 is filename, $3 is Model Number, $7 is Vina Score
        file = $1;
        sub(/\.pdbqt-REMARK$/, "", file);
        sub(/\.pdbqt$/, "", file);
        sub(/^\.\//, "", file);
        print "'${prot^^}':" file "(Model-" $3 ")\t" $7
    }')

    if $only_table; then
      echo "$scores"
    else
      echo "Listing ligands for ${prot^^}"
      echo "$scores" | sort -k2,2n | head -n "$head" | column -t -N 'PROTEIN:LIGAND,AFFINITY'
    fi
  )
}

scores_comparison() {
  local first=$1
  local second=$2
  if [[ -z $first || -z $second ]]; then
    return 1
  fi
  local pythonscript="/tmp/python$$.py"

  cat <<PYEOF >$pythonscript
import re
import sys

def extract_sort_key(line):
    # 1. Extract Ligand ID (e.g., lig_00001_out)
    lig_match = re.search(r"(lig_\d+_out)", line)
    lig_id = lig_match.group(1) if lig_match else ""

    # 2. Extract Library Name
    # We look for the part after the protein code (CODE:./LIBRARY/...)
    path_match = re.search(r":\./([^/]+)", line)
    if not path_match: # Handle cases without ./
        path_match = re.search(r":([^/]+)", line)
    
    lib_name = path_match.group(1).lower() if path_match else ""

    # 3. Extract Model Number for a stable tie-breaker sort
    model_match = re.search(r"\(Model (\d+)\)", line)
    model_num = int(model_match.group(1)) if model_match else 0

    # 4. Protein Code (5TBM vs 6NJS)
    prot_code = line.split(":")[0]

    # Priority: Ligand ID -> Library -> Protein Code -> Model Number
    return (lig_id, lib_name, prot_code, model_num)

if len(sys.argv) < 2:
    print("usage: python sort.py <INPUT> <OUTPUT>")
    sys.exit(1)

with open(sys.argv[1], "r") as f:
    lines = [l for l in f if l.strip()]

lines.sort(key=extract_sort_key)

with open(sys.argv[2], "w") as f:
    f.writelines(lines)
PYEOF

  # Temporary file for the raw combined data
  local raw_combined="/tmp/raw_docking_$$"

  echo "Gathering scores for $first and $second..."

  # Run both, append to same file
  docking_scores "$first" 0 true >"$raw_combined"
  docking_scores "$second" 0 true >>"$raw_combined"

  echo "Sorting and Grouping..."
  python3 $pythonscript "$raw_combined" "final_comparison_$$.txt"

  rm -v "${pythonscript}" "${raw_combined}"
  echo "Done! Check final_comparison_$$.txt"
}

scores_comparison "$COMP1" "$COMP2"
