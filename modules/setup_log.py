#! python 2 and 3
"""
    Setup logging

    Copyright (C) 2017 Stefan Tapper, All rights reserved.

        This file is part of Pfad Aeffchen.

        Pfad Aeffchen is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.

        Pfad Aeffchen is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.

        You should have received a copy of the GNU General Public License
        along with Pfad Aeffchen.  If not, see <http://www.gnu.org/licenses/>.
"""
import os
import glob
import logging
try:
    # Available from Python >3.2
    from logging.handlers import QueueHandler, QueueListener
except ImportError:
    pass
import logging.config
from datetime import datetime
from modules.app_globals import PFAD_AEFFCHEN_LOG_NAME
from modules.setup_paths import get_user_directory


def setup_log_file(log_file_name=PFAD_AEFFCHEN_LOG_NAME, delete_existing_log_files=False):
    """ This should only be called once. It configures the logging module. All sub processes and
    threads inherit their settings from this configuration. """
    usr_profile = get_user_directory()
    log_file = os.path.join(usr_profile, log_file_name)

    if delete_existing_log_files:
        delete_existing_logs(log_file)

    log_conf = {
        'version': 1, 'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
                },
            'simple': {
                'format': '%(asctime)s %(module)s: %(message)s'
                },
            'file_formatter': {
                'format': '%(asctime)s - %(module)s: %(message)s'
                },
            },
        'handlers': {
            'console': {
                'level': 'DEBUG', 'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout', 'formatter': 'simple'},
            'file': {
                'level': 'DEBUG', 'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(usr_profile, log_file_name), 'maxBytes': 5000000, 'backupCount': 4,
                'formatter': 'file_formatter',
                },
            'null': {
                'level': 'DEBUG', 'class': 'logging.NullHandler', 'formatter': 'file_formatter',
                }
            },
        'loggers': {
            'aeffchen_logger': {
                'handlers': ['file', 'console'], 'propagate': False, 'level': 'INFO', },
            'watcher_logger': {
                'handlers': ['file', 'console'], 'propagate': False, 'level': 'DEBUG', },
            }
        }

    logging.config.dictConfig(log_conf)


def delete_existing_logs(log_file):
    # Delete all log files xxx.log, xxx.log1 etc.
    search_path = os.path.split(log_file)[0]
    search_file_name = os.path.split(log_file)[-1]

    search = search_path + '/*' + search_file_name + '*'

    for file in glob.glob(search):
        try:
            os.remove(file)
        except OSError or FileNotFoundError as e:
            print('Could not delete existing log file: %s', file)
            print(e)


class JobLogFile(object):
    fh = None            # Store file handler per job
    current_path = None  # Store log file location per job
    text_report = ''     # Store log file content as text
    usr_profile = get_user_directory()
    logger = None

    # TODO: Add image watcher log entries

    @classmethod
    def _reset(cls):
        cls.fh = None
        cls.current_path = None
        cls.text_report = ''

    @classmethod
    def setup(cls, job_title):
        """ Add a job log file handler while a job is running """
        cls._reset()

        cls.logger = logging.getLogger('JobLogger')
        cls.logger.setLevel(logging.DEBUG)

        filename = datetime.now().strftime('Job_%Y-%m-%d_%H-%M-%S.log')
        cls.current_path = os.path.join(cls.usr_profile, filename)

        formatter = logging.Formatter(fmt='%(asctime)s %(module)s: %(message)s')

        cls.fh = logging.FileHandler(cls.current_path)
        cls.fh.setFormatter(formatter)

        try:
            logging.root.addHandler(cls.fh)
            cls.logger.info('Starting job log for %s at %s', job_title, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        except Exception as e:
            print(e)

        return cls.fh

    @classmethod
    def finish(cls):
        """ Remove file handler and prepare log file content for text browser report """
        if cls.logger is None:
            return

        # Remove and close file handler
        try:
            cls.logger.removeHandler(cls.fh)
            logging.root.removeHandler(cls.fh)
            cls.fh.close()
        except Exception as e:
            cls.logger.error(e)
            print(e)

        # Read log file contents
        try:
            if cls.current_path:
                with open(cls.current_path, 'r') as f:
                    cls.text_report = f.read()
        except Exception as e:
            cls.logger.error(e)
            return

        # Format the text report as preformatted text
        cls.text_report = '<h4>Job Log</h4><pre>{}</pre>'.format(cls.text_report)

        # Remove job log file
        if cls.current_path:
            try:
                os.remove(cls.current_path)
            except Exception as e:
                cls.logger.error(e)
        cls.current_path = None


def setup_log_queue_listener(logger, queue):
    """
        Exclusive to Python >3.2
        Moves handlers from logger to QueueListener and returns the listener
        The listener needs to be started afterwwards with it's start method.
    """
    handler_ls = list()
    for handler in logger.handlers:
        print('Removing handler that will be added to queue listener: ', str(handler))
        handler_ls.append(handler)

    for handler in handler_ls:
        logger.removeHandler(handler)

    handler_ls = tuple(handler_ls)
    queue_handler = QueueHandler(queue)
    logger.addHandler(queue_handler)

    listener = QueueListener(queue, *handler_ls)
    return listener


def setup_queued_logger(name, queue):
    """ Create a logger and at a queue handler """
    queue_handler = QueueHandler(queue)
    logger = logging.getLogger(name)
    logger.addHandler(queue_handler)
    return logger


def add_queue_handler(logger, queue):
    """ Add a queue handler to an existing logger """
    queue_handler = QueueHandler(queue)
    logger.addHandler(queue_handler)
    return logger


def setup_logging(name=''):
    if name in ['aeffchen_logger', 'watcher_logger']:
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.info('Logging started for %s - %s', name, current_date)
    else:
        logger = logging.getLogger(name)

    return logger
