#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error: Failed to load {path}: {e}")
        sys.exit(1)


def sync(source_path: Path, target_path: Path):
    if not source_path.is_file():
        print(f"Error: Source path {source_path} is not a file.")
        sys.exit(1)

    source_data = load_json(source_path)
    if not source_data:
        print(f"Warning: Source file {source_path} is empty.")
        return

    target_data = load_json(target_path)

    missing_keys = set(source_data.keys()) - set(target_data.keys())

    if not missing_keys:
        print("No missing keys found.")
        return

    for key in missing_keys:
        target_data[key] = ""

    try:
        with target_path.open("w", encoding="utf-8") as f:
            json.dump(target_data, f, ensure_ascii=False, indent=4, sort_keys=True)
        print(f"Successfully added {len(missing_keys)} keys to {target_path}.")
    except Exception as e:
        print(f"Error: Failed to write to {target_path}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Path to the source json file")
    parser.add_argument("target", help="Path to the target json file")
    args = parser.parse_args()

    source_path = Path(args.source)
    target_path = Path(args.target)

    for path in [source_path, target_path]:
        if not path.exists():
            print(f"Error: File {path} does not exist.")
            sys.exit(1)
        if path.suffix.lower() != ".json":
            print(f"Error: File {path} is not a json file.")
            sys.exit(1)

    sync(source_path, target_path)


if __name__ == "__main__":
    main()
