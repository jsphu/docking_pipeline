# 1. Create a mapping of [Internal Name] -> [Original Path]
# We use a temp file to store "Name|Path"
echo "Mapping original results..."
sed 's/:/|/' ligand_names.txt >name_map.txt

shuf name_map.txt >name_map2.txt
mv name_map2.txt name_map.txt

# 2. Iterate through the ligands in your 'oops' directory
echo "Matching files in oops/ to original locations..."
for lig_file in *.pdbqt; do
  [ -e "$lig_file" ] || continue

  # Get the internal name of the current file in oops/
  current_name="$(grep -oPm1 "Name\s+=\s+\K.*" "$lig_file")"

  if [ -n "$current_name" ]; then
    # Find the original path from our map using the name
    original_entry=$(grep -Fm1 "|$current_name$" name_map.txt)

    if [ -n "$original_entry" ]; then
      # Extract the path (everything after the |)
      original_path="${original_entry%|*}"
      dest_dir="${original_path%/*}"

      real_dir="${dest_dir/6NJS/5TBM}"

      # echo "[MATCH FOUND]"
      # echo "File: $lig_file"
      # echo "Internal Name: $current_name"
      # echo "Target Directory: $real_dir"

      # Uncomment the line below once the dry run looks correct
      mv -vi "$lig_file" "$real_dir/"
    fi
  fi
done

rm name_map.txt
