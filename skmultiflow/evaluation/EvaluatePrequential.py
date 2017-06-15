__author__ = 'Guilherme Matsumoto'

from skmultiflow.evaluation.BaseEvaluator import BaseEvaluator
from skmultiflow.classification.Perceptron import PerceptronMask
from sklearn.metrics import cohen_kappa_score
from skmultiflow.visualization.EvaluationVisualizer import EvaluationVisualizer
from skmultiflow.core.utils.utils import dict_to_tuple_list
from skmultiflow.core.utils.data_structures import FastBuffer
import sys, argparse
from timeit import default_timer as timer
import numpy as np
import math
import logging
import warnings


class EvaluatePrequential(BaseEvaluator):
    def __init__(self, n_wait=200, max_instances=100000, max_time=float("inf"), output_file=None,
                 show_plot=False, batch_size=1, pretrain_size=200, show_kappa = False):
        super().__init__()
        # default values
        self.n_wait = n_wait
        self.max_instances = max_instances
        self.max_time = max_time
        self.batch_size = batch_size
        self.pretrain_size = pretrain_size
        self.show_plot = show_plot
        self.show_kappa = show_kappa
        self.classifier = None
        self.stream = None
        self.output_file = output_file
        self.visualizer = None
        # performance stats
        self.global_correct_predicts = 0
        self.partial_correct_predicts = 0
        self.global_sample_count = 0
        self.partial_sample_count = 0
        self.global_accuracy = 0
        # kappa stats
        self.global_kappa = 0.0
        self.kappa_count = 0
        self.kappa_predicts = FastBuffer(200)
        self.kappa_true_labels = FastBuffer(200)

        warnings.filterwarnings("ignore", ".*invalid value encountered in true_divide.*")

    def eval(self, stream, classifier):
        if self.show_plot:
            self.start_plot(self.n_wait, stream.get_plot_name())
        self.classifier = classifier
        self.stream = stream
        self.classifier = self.train_and_test(stream, classifier)
        return self.classifier

    def train_and_test(self, stream = None, classifier = None):
        logging.basicConfig(format='%(message)s', level=logging.INFO)
        init_time = timer()
        self.classifier = classifier
        self.stream = stream
        self._reset_partials()
        self._reset_globals()
        prediction = None
        logging.info('Generating %s classes.', str(self.stream.get_num_classes()))

        rest = self.stream.estimated_remaining_instances() if (self.stream.estimated_remaining_instances() != -1 and
                                                               self.stream.estimated_remaining_instances() <=
                                                               self.max_instances) \
            else self.max_instances

        if (self.pretrain_size > 1):
            msg = 'Pretraining on ' + str(self.pretrain_size) + ' samples.'
            logging.info('Pretraining on %s samples.', str(self.pretrain_size))
            X, y = self.stream.next_instance(self.pretrain_size)
            #self.classifier.partial_fit(X, y, self.stream.get_classes(), True)
            self.classifier.partial_fit(X, y, self.stream.get_classes())
        else:
            X, y = None, None

        logging.info('Evaluating...')
        while ((self.global_sample_count < self.max_instances) & (timer() - init_time < self.max_time)
                   & (self.stream.has_more_instances())):
            X, y = self.stream.next_instance(self.batch_size)
            if X is not None and y is not None:
                prediction = self.classifier.predict(X)
                self.visualizer.on_new_data(y, prediction)
                self.global_sample_count += self.batch_size
                self.partial_sample_count += self.batch_size
                self.kappa_predicts.add_element(np.ravel(prediction))
                self.kappa_true_labels.add_element(np.ravel(y))
                for i in range(len(prediction)):
                    nul_count = self.global_sample_count - self.batch_size
                    if ((prediction[i] == y[i]) and not (self.global_sample_count > self.max_instances)):
                        self.partial_correct_predicts += 1
                        self.global_correct_predicts += 1
                    if ((nul_count + i + 1) % (rest/20)) == 0:
                        logging.info('%s%%', str(((nul_count+i+1) // (rest / 20)) * 5))
                self.classifier.partial_fit(X, y)

                if ((self.global_sample_count % self.n_wait) == 0 | (self.global_sample_count >= self.max_instances)):
                    self.kappa_count += 1
                    self.update_metrics()

        end_time = timer()
        logging.info('Evaluation time: %s', str(round(end_time - init_time, 3)))
        logging.info('Total instances: %s', str(self.global_sample_count))
        logging.info('Global accuracy: %s', str(round(self.global_correct_predicts/self.global_sample_count, 3)))
        logging.info('Global kappa statistic %s', str(round(self.global_kappa, 3)))

            ####
            ## TODO
            ## fix the problem you created, the visualizer has to be dumb, he just receives statistics
            ##
            ##


        if self.show_plot:
            self.visualizer.hold()
        return self.classifier

    def partial_fit(self, X, y):
        if self.classifier is not None:
            self.classifier.partial_fit(X, y)
            return self
        else:
            return self

    def predict(self, X):
        if self.classifier is not None:
            self.classifier.predict(X)
            return self
        else:
            return self

    def update_plot(self, partial_accuracy, num_instances):
        self.visualizer.on_new_train_step(partial_accuracy, num_instances)
        pass

    def update_metrics(self):
        """ Updates the metrics of interest.
        
            It's possible that cohen_kappa_score will return a NaN value, which happens if the predictions
            and the true labels are in perfect accordance, causing pe=1, which results in a division by 0.
            If this is detected the plot will assume it to be 1.
        
        :return: No return.
        """
        self.global_accuracy = ((self.global_sample_count - self.partial_sample_count) / self.global_sample_count) * \
                               self.global_accuracy + (self.partial_sample_count / self.global_sample_count) * \
                                                      (self.partial_correct_predicts/self.partial_sample_count)
        partial_kappa = 0.0
        partial_kappa = cohen_kappa_score(self.kappa_predicts.get_queue(), self.kappa_true_labels.get_queue())
        #logging.info('%s', str(round(partial_kappa, 3)))
        if not math.isnan(partial_kappa):
            self.global_kappa = ((self.kappa_count-1)/self.kappa_count)*self.global_kappa + partial_kappa*(1/self.kappa_count)
        else:
            self.global_kappa = ((self.kappa_count-1)/self.kappa_count)*self.global_kappa + 1*(1/self.kappa_count)
        if self.show_plot:
            if self.show_kappa:
                if not math.isnan(partial_kappa):
                    self.update_plot([self.partial_correct_predicts / self.partial_sample_count, partial_kappa], self.global_sample_count)
                else:
                    self.update_plot([self.partial_correct_predicts / self.partial_sample_count, 1],
                                     self.global_sample_count)
            else:
                self.update_plot([self.partial_correct_predicts/self.partial_sample_count], self.global_sample_count)
        self._reset_partials()

    def _reset_partials(self):
        self.partial_sample_count = 0
        self.partial_correct_predicts = 0

    def _reset_globals(self):
        self.global_sample_count = 0
        self.global_correct_predicts = 0
        self.global_accuracy = 0.0

    def start_plot(self, n_wait, dataset_name):
        self.visualizer = EvaluationVisualizer(n_wait=n_wait, dataset_name=dataset_name, show_kappa=self.show_kappa)
        pass

    def set_params(self, dict):
        params_list = dict_to_tuple_list(dict)
        for name, value in params_list:
            if name == 'n_wait':
                self.n_wait = value
            elif name == 'max_instances':
                self.max_instances = value
            elif name == 'max_time':
                self.max_time = value
            elif name == 'output_file':
                self.output_file = value
            elif name == 'show_plot':
                self.show_plot = value
            elif name == 'batch_size':
                self.batch_size = value
            elif name == 'pretrain_size':
                self.pretrain_size = value