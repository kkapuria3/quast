# -*- coding: utf-8 -*-

from __future__ import with_statement

import os
import tempfile
import platform
import subprocess
import itertools
import csv
import shutil

from libs import reporting
from libs.fastaparser import read_fasta, write_fasta, rev_comp
from qutils import id_to_str, print_timestamp

def merge_gffs(gffs, out_path):
    '''Merges all GFF files into a single one, dropping GFF header.'''
    with open(out_path, 'w') as out_file:
        out_file.write('##gff-version 3\n')
        for gff_path in gffs:
            with open(gff_path, 'r') as gff_file:
                out_file.writelines(itertools.islice(gff_file, 2, None))

    return out_path


def parse_gff(gff_path):
    with open(gff_path) as gff_file:
        r = csv.reader(
            itertools.ifilter(lambda l: not l.startswith("#"), gff_file),
            delimiter='\t')
        for id, _source, type, start, end, score, strand, phase, extra in r:
            if type != 'mRNA':
                continue  # We're only interested in genes here.

            attrs = dict(kv.split("=") for kv in extra.split(";"))
            yield id, attrs.get('Name'), int(start), int(end), strand


def glimmerHMM(tool_dir, fasta_path, out_path, gene_lengths, err_path):
    def run(contig_path, tmp_path):
        with open(err_path, 'a') as err_file:
            p = subprocess.call([tool_exec, contig_path,
                                 '-d', trained_dir,
                                 '-g', '-o', tmp_path],
                stdout=err_file, stderr=err_file)
            assert p is 0

    if platform.system() == 'Darwin':
        tool_exec = os.path.join(tool_dir, 'macosx')
    elif platform.architecture()[0] == '64bit':
        tool_exec  = os.path.join(tool_dir, 'linux_64')
    else:
        tool_exec  = os.path.join(tool_dir, 'linux_32')

    # Note: why arabidopsis? for no particular reason, really.
    trained_dir = os.path.join(tool_dir, 'trained', 'arabidopsis')

    contigs = {}
    gffs = []
    base_dir = tempfile.mkdtemp()
    for id, seq in read_fasta(fasta_path):
        contig_path = os.path.join(base_dir, id + '.fasta')
        gff_path = os.path.join(base_dir, id + '.gff')

        write_fasta(contig_path, [(id, seq)])
        run(contig_path, gff_path)
        gffs.append(gff_path)
        contigs[id] = seq

    out_gff_path = merge_gffs(gffs, out_path + '_genes.gff')
    out_fasta_path = out_path + '_genes.fasta'
    unique, total = set(), 0
    genes = []
    cnt = [0] * len(gene_lengths)
    for contig, gene_id, start, end, strand in parse_gff(out_gff_path):
        total += 1

        if strand == '+':
            gene_seq = contigs[contig][start:end + 1]
        else:
            gene_seq = rev_comp(contigs[contig][start:end + 1])

        if gene_seq not in unique:
            unique.add(gene_seq)

        genes.append((gene_id, gene_seq))

        for idx, gene_length in enumerate(gene_lengths):
            cnt[idx] += end - start > gene_length

    write_fasta(out_fasta_path, genes)
    shutil.rmtree(base_dir)

    return out_gff_path, out_fasta_path, len(unique), total, cnt

def do(fasta_paths, gene_lengths, out_dir, lib_dir):
    print_timestamp()
    print 'Running GlimmerHMM...'

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    tool_dir = os.path.join(lib_dir, 'glimmer')

    for id, fasta_path in enumerate(fasta_paths):
        report = reporting.get(fasta_path)

        print ' ', id_to_str(id), os.path.basename(fasta_path),

        out_name = os.path.basename(fasta_path)
        out_path = os.path.join(out_dir, out_name)
        err_path = os.path.join(out_dir, 'glimmer.errors')
        out_gff_path, out_fasta_path, unique, total, cnt = glimmerHMM(tool_dir,
            fasta_path, out_path, gene_lengths, err_path)

        print(', Genes = %i unique, %i total' % (unique, total))
        print('    Glimmer output: %s and %s' % (out_gff_path, out_fasta_path))

        report.add_field(reporting.Fields.GENEMARKUNIQUE, unique)
        report.add_field(reporting.Fields.GENEMARK, cnt)

        print '  Done'

if __name__ == '__main__':
    fasta_pathes = ['../test_data/assembly_10K_1.fasta', '../test_data/assembly_10K_2.fasta']
    print fasta_pathes
    out_dir = '../run_test_data/glimmer_out'
    lib_dir = ''
    gene_lengths = [100, 1000, 10000]
    do(fasta_pathes, gene_lengths, out_dir, lib_dir)