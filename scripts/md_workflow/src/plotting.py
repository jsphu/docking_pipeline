import os
import numpy as np
import matplotlib.pyplot as plt

def plot_xvg(file_path, output_path=None):
    """Plots an XVG file and optionally saves it. Handles multiple Y columns."""
    x, y_data = [], []
    labels = []
    title = f"Plot: {os.path.basename(file_path)}"
    xlabel = "Time"
    ylabel = "Value"

    if not os.path.exists(file_path):
        print(f"Warning: File {file_path} not found.")
        return

    with open(file_path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            if line.startswith("@"):
                if 'title "' in line:
                    title = line.split('title "')[1].split('"')[0]
                elif 'xaxis  label "' in line:
                    xlabel = line.split('xaxis  label "')[1].split('"')[0]
                elif 'yaxis  label "' in line:
                    ylabel = line.split('yaxis  label "')[1].split('"')[0]
                elif ' s' in line and 'legend "' in line:
                    labels.append(line.split('legend "')[1].split('"')[0])
                continue
            
            cols = line.split()
            if len(cols) >= 2:
                try:
                    x.append(float(cols[0]))
                    y_values = [float(v) for v in cols[1:]]
                    if not y_data:
                        y_data = [[] for _ in range(len(y_values))]
                    for i, val in enumerate(y_values):
                        y_data[i].append(val)
                except ValueError:
                    continue

    if not x:
        print(f"Warning: No data found in {file_path}")
        return

    plt.figure(figsize=(10, 6))
    for i, y in enumerate(y_data):
        label = labels[i] if i < len(labels) else f"Column {i+1}"
        plt.plot(x, y, label=label, linewidth=1.5)

    plt.title(title, fontsize=14)
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    if labels or len(y_data) > 1:
        plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300)
        plt.close()
    else:
        plt.show()
