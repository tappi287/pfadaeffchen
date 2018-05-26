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
import logging
import logging.config
from datetime import datetime
from modules.app_globals import PFAD_AEFFCHEN_LOG_NAME
from modules.setup_paths import get_user_directory


def setup_log_file(log_file_name=PFAD_AEFFCHEN_LOG_NAME):
    usr_profile = get_user_directory()

    log_conf = {
        'version': 1, 'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
                },
            'simple': {
                'format': '%(module)s: %(message)s'
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
            },
        'loggers': {
            'aeffchen_logger': {
                'handlers': ['file', 'console'], 'propagate': True, 'level': 'DEBUG', },
            'watcher_logger': {
                'handlers': ['file', 'console'], 'propagate': True, 'level': 'DEBUG', }
            }
        }

    logging.config.dictConfig(log_conf)


class JobLogFile(object):
    fh = None            # Store file handler per job
    current_path = None  # Store log file location per job
    text_report = ''     # Store log file content as text
    usr_profile = get_user_directory()
    logger = None

    @classmethod
    def _reset(cls):
        cls.fh = None
        cls.current_path = None
        cls.text_report = ''

    @classmethod
    def setup(cls, job_title, logger):
        """ Add a job log file handler while a job is running """
        cls._reset()

        cls.logger = logging.getLogger('JobLogger')

        filename = datetime.now().strftime('Job_%Y-%m-%d_%H-%M-%S.log')
        cls.current_path = os.path.join(cls.usr_profile, filename)

        formatter = logging.Formatter(fmt='%(module)s: %(message)s')

        cls.fh = logging.FileHandler(cls.current_path)
        cls.fh.setFormatter(formatter)

        try:
            cls.logger.addHandler(cls.fh)
            logger.addHandler(cls.fh)
            cls.logger.info('Starting job log for %s at %s', job_title, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        except Exception as e:
            print(e)

        return cls.fh

    @classmethod
    def finish(cls, logger):
        """ Remove file handler and prepare log file content for text browser report """
        if cls.logger is None:
            return

        # Remove and close file handler
        try:
            cls.logger.removeHandler(cls.fh)
            logger.removeHandler(cls.fh)
            cls.fh.close()
        except Exception as e:
            cls.logger.error(e)

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


def setup_logging(name=''):
    """
    logging.basicConfig(
        filename='my_matte_layer_creation.log', level=logging.DEBUG, format='%(processName)s %(message)s'
        )
    """

    if name in ['aeffchen_logger', 'watcher_logger']:
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger = logging.getLogger(name)
        logger.info('Logging started for %s - %s', name, current_date)
        logger.setLevel(logging.DEBUG)
    else:
        logger = logging.getLogger(name)

    return logger
