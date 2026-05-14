import os
import numpy as np
import matplotlib.pyplot as plt

def plot_xvg(file_path, output_path=None):
    """Plots an XVG file and optionally saves it."""
    x, y = [], []
    with open(file_path) as f:
        for line in f:
            if line.startswith(("#", "@")):
                continue
            cols = line.split()
            if len(cols) >= 2:
                x.append(float(cols[0]))
                y.append(float(cols[1]))

    plt.figure(figsize=(8, 6))
    plt.plot(x, y, color="red", label="Data", linewidth=1.5)
    plt.title(f"XVG Plotter: {os.path.basename(file_path)}", fontsize=14)
    plt.xlabel("Time", fontsize=12)
    plt.ylabel("Value", fontsize=12)
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path)
    else:
        plt.show()
