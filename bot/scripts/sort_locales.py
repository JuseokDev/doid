#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def sort_json_file(file_path: Path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)

        print(f"info: {file_path} sorted")
    except Exception as e:
        print(f"error: failed to sort {file_path}: {e}")


def sort(path: Path):
    if path.is_file():
        if path.suffix.lower() == ".json":
            sort_json_file(path)
        else:
            print(f"error: {path} is not a json file")
    elif path.is_dir():
        files = list(path.glob("*.json"))
        if not files:
            print(f"warning: no json files found in {path}")
            return

        for file in files:
            sort_json_file(file)
    else:
        print(f"error: path {path} does not exist")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("path", nargs="?", default="./locales", help="Path to the locale directory or file")

    args = parser.parse_args()

    path = Path(args.path)
    sort(path)


if __name__ == "__main__":
    main()
