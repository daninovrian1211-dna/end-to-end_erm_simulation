import argparse

from . import calibrate, generate_all

parser = argparse.ArgumentParser(description="Generate data sintetis ASB ke data/raw")
parser.add_argument("--out", default=str(calibrate.RAW_DIR))
parser.add_argument("--seed", type=int, default=None)
args = parser.parse_args()
for p in generate_all(args.out, args.seed):
    print(p)
