# wdecoster
'''
Script for filtering and trimming of Oxford Nanopore technologies long reads.
Filtering can be done by calculating metrics while streaming,
or alternatively using a summary file as generated by albacore while basecalling.

Filtering can be done on length and average read basecall quality.
Trimming can be done from the beginning and the end of a read.

Reads from stdin, writes to stdout.

Intended to be used:
- directly after fastq extraction
- prior to mapping
- in a stream between extraction and mapping

Example usage:
gunzip -c reads.fastq.gz | \
 NanoFilt.py -q 10 -l 500 --headcrop 50 | \
 minimap2 genome.fa - | \
 samtools sort -@24 -o alignment.bam -
'''

from __future__ import print_function
from Bio import SeqIO
from argparse import ArgumentParser, ArgumentTypeError
import sys
from nanomath import ave_qual
from nanoget import process_summary
from nanofilt.version import __version__


def main():
    args = get_args()
    if args.tailcrop:
        args.tailcrop = -args.tailcrop
    if args.summary:
        filter_using_summary(sys.stdin, args)
    else:
        filter_stream(sys.stdin, args)


def get_args():
    parser = ArgumentParser(
        description="Perform quality and/or length and/or GC filtering of Nanopore fastq data.\
                     Reads on stdin.")
    parser.add_argument("-v", "--version",
                        help="Print version and exit.",
                        action="version",
                        version='NanoFilt {}'.format(__version__))
    parser.add_argument("-l", "--length",
                        help="Filter on a minimum read length",
                        default=1,
                        type=int)
    parser.add_argument("--headcrop",
                        help="Trim n nucleotides from start of read",
                        default=None,
                        type=int)
    parser.add_argument("--tailcrop",
                        help="Trim n nucleotides from end of read",
                        default=None,
                        type=int)
    parser.add_argument("-q", "--quality",
                        help="Filter on a minimum average read quality score",
                        default=0,
                        type=int)
    parser.add_argument("--minGC",
                        help="Sequences must have GC content >= to this.  Float between 0.0 and 1.0. \
                              Ignored if using summary file.",
                        default=0.0,
                        type=valid_GC)
    parser.add_argument("--maxGC",
                        help="Sequences must have GC content <= to this.  Float between 0.0 and 1.0. \
                              Ignored if using summary file.",
                        default=1.0,
                        type=valid_GC)
    parser.add_argument("-s", "--summary",
                        help="Use summary file for quality scores")
    parser.add_argument("--readtype",
                        help="Which read type to extract information about from summary. \
                              Options are 1D, 2D or 1D2",
                        default="1D",
                        choices=['1D', '2D', "1D2"])
    args = parser.parse_args()
    if args.minGC > args.maxGC:
        sys.exit("NanoFilt: error: argument --minGC should be smaller than --maxGC")
    return args


def valid_GC(x):
    x = float(x)
    if x < 0.0 or x > 1.0:
        raise ArgumentTypeError("{} not in range [0.0, 1.0]".format(x))
    return x


def filter_stream(fq, args):
    '''
    If a fastq record passes quality filter (optional) and length filter (optional), print to stdout
    Optionally trim a number of nucleotides from beginning and end.
    '''
    minlen = args.length + int(args.headcrop or 0) - (int(args.tailcrop or 0))
    for rec in SeqIO.parse(fq, "fastq"):
        if (args.minGC > 0.0 or args.maxGC < 1.0):
            # one of the GC arguments has been set, we need to calcualte GC
            gc = (rec.seq.upper().count("C") + rec.seq.upper().count("G")) / len(rec)
        else:
            gc = 0.50  # dummy variable
        if ave_qual(rec.letter_annotations["phred_quality"]) > args.quality \
                and len(rec) > minlen \
                and args.minGC <= gc <= args.maxGC:
            print(rec[args.headcrop:args.tailcrop].format("fastq"), end="")


def filter_using_summary(fq, args):
    '''
    Use the summary file from albacore for more accurate quality estimate
    Get the dataframe from nanoget, convert to dictionary
    '''
    data = {entry[0]: entry[1] for entry in process_summary(
        summaryfile=args.summary,
        threads="NA",
        readtype=args.readtype)[
        ["readIDs", "quals"]].itertuples(index=False)}
    try:
        for record in SeqIO.parse(fq, "fastq"):
            if data[record.id] > args.quality and len(record) > args.length:
                print(record[args.headcrop:args.tailcrop].format("fastq"), end="")
    except KeyError:
        sys.exit('\nERROR: mismatch between sequencing_summary and fastq file: \
                 {} was not found in the summary file.\nQuitting.'.format(record.id))


if __name__ == "__main__":
    main()
