#! usr/bin/python_3
"""
    -------------
    Pfad Aeffchen
    -------------

    Basic path rendering functionality with a PyQt5 Gui

    This application should be run from Python 3.x interpreter while
    a few other modules will be run inside Autodesk Maya's mayapy Python 2.7 interpreter
    Most generic modules are compatible with 2.x and 3.x

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
import sys
import os
import logging
from multiprocessing import Queue

from modules.detect_lang import get_ms_windows_language, get_translation
from modules.main_app import PfadAeffchenApp
from modules.setup_log import setup_logging, setup_log_file, setup_log_queue_listener
from modules.setup_paths import get_current_modules_dir
from modules.app_globals import *

# get MS Windows language
os.environ.setdefault('LANGUAGE', get_ms_windows_language()[:2])

# translate strings
de = get_translation()
de.install()
_ = de.gettext

#TODO: Exception hook for main and image watcher process
#TODO: log image processor to Job log
#TODO:  Reduce psd layer count, compare target_look values with look values
#       create a dict of mappings target_look = source_look
#       then merge either renderlayers or images
#       less renderlayer would also greatly reduce render time
#
# pipenv 2018.5.18


def set_version(mod_dir):
    """ Write version info from pfad_aeffchen.cfg to resource directory
        to make it available to the installer version of the app aswell.
    """
    cfg_file = os.path.join(mod_dir, 'pfad_aeffchen.cfg')
    if not os.path.exists(cfg_file):
        LOGGER.info('%s does not exist.', cfg_file)
        # We're probably not in Dev environment
        return

    with open(cfg_file, 'r') as f:
        for line in f.readlines():
            if line.startswith('version'):
                # Version info found
                LOGGER.debug('Version info found.')
                version = line[line.find('=') + 1:]
                break
        else:
            LOGGER.debug('No Version info found.')
            # No version info found
            return

    # Write version info to resource directory
    version_info_file = os.path.join(mod_dir, 'res/version.txt')
    with open(version_info_file, 'w') as f:
        LOGGER.debug('Writing version to file %s.', version)
        f.write(version)


def read_version(mod_dir):
    version_info_file = os.path.join(mod_dir, 'res/version.txt')
    if not os.path.exists(version_info_file):
        return 'x.x'

    with open(version_info_file, 'r') as f:
        version = f.read()

    return version


def setup_aeffchen_log():
    global LOGGER
    setup_log_file(PFAD_AEFFCHEN_LOG_NAME, delete_existing_log_files=True)
    LOGGER = setup_logging('aeffchen_logger')


def main():
    # Setup log
    setup_aeffchen_log()

    # Prepare a multiprocess logging queue
    logging_queue = Queue(-1)

    # This will move all handlers from LOGGER to the queue listener
    log_listener = setup_log_queue_listener(LOGGER, logging_queue)
    # Start log queue listener in it's own thread
    log_listener.start()

    mod_dir = get_current_modules_dir()
    LOGGER.info('Modules directory: %s', mod_dir)

    # Set version file if we are in Dev environment
    set_version(mod_dir)

    # Get version info
    version = read_version(mod_dir)
    LOGGER.debug('Running version: %s', version)

    app = PfadAeffchenApp(mod_dir, version, LOGGER, logging_queue)
    result = app.exec_()
    LOGGER.debug('---------------------------------------')
    LOGGER.debug('Qt application finished with exitcode %s', result)

    log_listener.stop()
    logging.shutdown()
    sys.exit()


if __name__ == '__main__':
    """ 
        Only in debug! Nsis installer will start main() directly.
        Do not declare anything here!
    """
    main()
