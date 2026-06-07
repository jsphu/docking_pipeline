import sys
import argparse
import os

# Add project root to sys.path to ensure src can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.plotting import plot_xvg


def main():
    parser = argparse.ArgumentParser(description="XVG Plotter Wrapper", prog="plot")
    parser.add_argument("file", help="Path to the .xvg file")
    parser.add_argument("--output", "-o", help="Path to save the plot (optional)")
    args = parser.parse_args()

    plot_xvg(args.file, args.output)


if __name__ == "__main__":
    main()
