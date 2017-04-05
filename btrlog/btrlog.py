#!/usr/bin/python

# This is a hacky convenience tool

import argparse
import collections
import itertools
import logging
import os
import pipes
import re
import subprocess
import dateutil.parser

LOGGER = logging.getLogger()

def build_parser():
    parser = argparse.ArgumentParser(prog='btrlog', description='If you have btrfs snapshots show how they change over time')
    parser.add_argument('--debug', action='store_true', help='Print debug output')
    parser.add_argument('mount', type=str, help='While system to operate on')
    parser.add_argument('commit', nargs='?', help='Show what changed in this snapshot (regular expression)', type=str)
    parser.add_argument('--no-files', action='store_true', help='Do not display the files that have changed')

    show_mx = parser.add_mutually_exclusive_group()
    show_mx.add_argument('--all', nargs='?', help='Show all changes before')
    show_mx.add_argument('--single', nargs='?', help='Show just this change')
    return parser

Snapshot = collections.namedtuple('Snapshot', 'snapshot transaction old_transaction')

def get_subvolumes(mount):
    string = subprocess.check_output(
        "/usr/bin/sudo btrfs subvolume list {} | cut -d ' ' -f 4,9".format(pipes.quote(mount)),
        shell=True)
    transactions = []
    snapshots = []
    for l in string.splitlines():
        transaction, snapshot = l.split()
        snapshots.append(snapshot)
        transactions.append(transaction)

    pairs = zip(snapshots, transactions)
    pairs.sort(key=lambda x: -int(x[1]))
    snapshots = [p[0] for p in pairs]
    transactions = [p[1] for p in pairs]

    snapshots = [os.path.join(mount, snapshot) for snapshot in snapshots]

    old_transactions = transactions[1:] + ['0']
    info =  zip(snapshots, transactions, old_transactions)
    snapshots = itertools.starmap(Snapshot, info)
    return snapshots


def main():
    args = build_parser().parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    subvolumes = get_subvolumes(args.mount)

    if args.commit:
        subvolumes = [x for x in subvolumes if re.search(args.commit, x.snapshot)]

        if not subvolumes:
            raise Exception('No such subvolumes')
        elif len(subvolumes) != 1:
            raise Exception('Matches multiple commits')


    for subvolume in subvolumes:
        creation_time = get_creation_time(subvolume.snapshot)
        LOGGER.debug('Getting changed files for %r', subvolume)
        if args.no_files:
            print creation_time, subvolume.snapshot
        else:
            changed_files = find_changed_files(args.mount, subvolume)
            for filename in changed_files:
                print creation_time, subvolume.snapshot, filename


def get_creation_time(snapshot):
    data = subprocess.check_output(['btrfs', 'subvolume', 'show', snapshot])
    for line in data.splitlines():
        line = line.strip()
        if line.startswith('Creation time'):
            date_string = line.split(':', 1)[1].strip()
            return dateutil.parser.parse(date_string, fuzzy=True).isoformat()
    else:
        raise Exception('Could not find creation time')



def find_changed_files(mount, subvolume):
    changes = subprocess.check_output(['btrfs', 'subvolume', 'find-new', subvolume.snapshot, subvolume.old_transaction])
    files = []

    for index, line in enumerate(changes.splitlines()):
        if not line.strip():
            continue
        if line == '#':
            continue
        if line.startswith('transid marker was'):
            continue

        try:
            filename = line.split()[16]
        except:
            print index, repr(line)
            raise

        filename = os.path.join(mount, filename)

        if filename.strip():
            files.append(filename)

    return files

if __name__ == '__main__':
    main()
