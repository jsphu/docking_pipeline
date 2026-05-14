import sys
import argparse
from src.plotting import plot_xvg


def main():
    parser = argparse.ArgumentParser(description="XVG Plotter Wrapper")
    parser.add_argument("file", help="Path to the .xvg file")
    parser.add_argument("--output", "-o", help="Path to save the plot (optional)")
    args = parser.parse_args()

    plot_xvg(args.file, args.output)


if __name__ == "__main__":
    main()
