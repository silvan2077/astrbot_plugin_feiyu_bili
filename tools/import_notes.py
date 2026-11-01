"""Import exported DSH notes into a chosen plugin viewing database."""
import argparse
import json
import pathlib
import sys

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from core.history import History


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=pathlib.Path)
    parser.add_argument('--database',required=True,type=pathlib.Path)
    args=parser.parse_args()
    if args.input.is_symlink() or not args.input.is_file() or args.input.stat().st_size>4*1024*1024:
        parser.error('Input must be a regular JSON file no larger than 4 MiB')
    payload=json.loads(args.input.read_text(encoding='utf-8-sig'))
    if payload.get('version')!=1:parser.error('Unsupported schema version')
    args.database.parent.mkdir(parents=True,exist_ok=True)
    history=History(args.database)
    try:print('Imported records:',history.ingest(payload['records']))
    finally:history.close()


if __name__=='__main__':main()
