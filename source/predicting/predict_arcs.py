#!/usr/bin/env python


from __future__ import print_function
import argparse
import codecs
import logging
import os
import pickle
import subprocess
import sys

import cort
from cort.core import corpora
from cort.core import mention_extractor
from cort.coreference import cost_functions
from cort.coreference import experiments
from cort.coreference import features
from cort.coreference import instance_extractors
from cort.util import import_helper
from multiprocessing import freeze_support

from predicting.fake_perceptron import TFPerceptron
from predicting.arc_extractor import InstanceExtractor
from extension.antecedent_trees import extract_substructures_limited

__author__ = 'loliveira'

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(''message)s')


def parse_args():
    parser = argparse.ArgumentParser(description='Predict coreference '
                                                 'relations.')
    parser.add_argument('-in',
                        required=True,
                        dest='input_filename',
                        help='The input file. Must follow the format of the '
                             'CoNLL shared tasks on coreference resolution '
                             '(see http://conll.cemantix.org/2012/data.html).)')
    parser.add_argument('-model',
                        required=True,
                        dest='model',
                        help='The model learned via cort-train.')
    parser.add_argument('-out',
                        dest='output_filename',
                        required=True,
                        help='The output file the predictions will be stored'
                             'in (in the CoNLL format.')
    parser.add_argument('-ante',
                        dest='ante',
                        help='The file where antecedent predictions will be'
                             'stored to.')
    parser.add_argument('-clusterer',
                        dest='clusterer',
                        required=True,
                        help='The clusterer to use.')
    parser.add_argument('-gold',
                        dest='gold',
                        help='Gold data (in the CoNLL format) for evaluation.')

    return parser.parse_args()


def get_scores(output_data, gold_data):
    scorer_output = subprocess.check_output([
        "perl",
        cort.__path__[0] + "/reference-coreference-scorers/v8.01/scorer.pl",
        "all",
        gold_data,
        os.getcwd() + "/" + output_data,
        "none"]).decode()

    metrics = ['muc', 'bcub', 'ceafm', 'ceafe', 'blanc']

    metrics_results = {}

    metric = None

    results_formatted = ""

    for line in scorer_output.split("\n"):
        if not line:
            continue
        print(f"scorer_output: {scorer_output}")
        splitted = line.split()

        if splitted[0] == "METRIC":
            metric = line.split()[1][:-1]

        if (metric != 'blanc' and line.startswith("Coreference:")) \
                or (metric == 'blanc' and line.startswith("BLANC:")):
            metrics_results[metric] = (
                float(splitted[5][:-1]),
                float(splitted[10][:-1]),
                float(splitted[12][:-1]),
            )

    results_formatted += "\tR\tP\tF1\n"

    for metric in metrics:
        results_formatted += metric + "\t" + \
                             "\t".join([str(val) for val in metrics_results[metric]]) + "\n"
    results_formatted += "\n"
    average = (metrics_results["muc"][2] + metrics_results["bcub"][2] +
               metrics_results["ceafe"][2]) / 3
    results_formatted += "conll\t\t\t" + format(average, '.2f') + "\n"

    return results_formatted


if __name__ == "__main__":
    freeze_support()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(''message)s')

    if sys.version_info[0] == 2:
        logging.warning("You are running cort under Python 2. cort is much more "
                        "efficient under Python 3.3+.")
    args = parse_args()

    logging.info("Loading model.")
    perceptron = TFPerceptron(args.model)

    extractor = InstanceExtractor(args.model)

    logging.info("Reading in data.")
    testing_corpus = corpora.Corpus.from_file(
        "testing",
        codecs.open(args.input_filename, "r", "utf-8"))

    logging.info("Extracting system mentions.")
    for doc in testing_corpus:
        doc.system_mentions = mention_extractor.extract_system_mentions(doc)

    mention_entity_mapping, antecedent_mapping = experiments.predict(
        testing_corpus,
        extractor,
        perceptron,
        import_helper.import_from_path(args.clusterer)
    )

    testing_corpus.read_coref_decisions(mention_entity_mapping, antecedent_mapping)

    logging.info("Write corpus to file.")
    testing_corpus.write_to_file(codecs.open(args.output_filename, "w", "utf-8"))

    if args.ante:
        logging.info("Write antecedent decisions to file")
        testing_corpus.write_antecedent_decisions_to_file(open(args.ante, "w"))

    if args.gold:
        logging.info("Evaluate.")
        print(get_scores(args.output_filename, args.gold))

    logging.info("Done.")
