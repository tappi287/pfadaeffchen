"""
    check if a file is in use by another process on MS Windows
    from https://stackoverflow.com/questions/11114492/check-if-a-file-is-not-open-not-used-by-other-process-in-python

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
import psutil
from pathlib import Path


class CheckFileAccess(object):
    def __init__(self, file, print_msg: bool=False):
        self.process_id = None
        self.process_name = None
        self.file = file
        self.print_msg = print_msg

    def check(self):
        result = self._check_process_for_opened_files(self.file, self.print_msg)

        if result:
            self.process_id, self.process_name = result
            return True

        return False

    @staticmethod
    def _check_process_for_opened_files(file: Path, print_msg: bool = False):
        for proc in psutil.process_iter():
            try:
                file_list = None

                try:
                    # this returns the list of opened files by the current process
                    file_list = proc.open_files()
                except PermissionError as e:
                    if print_msg:
                        print(e)
                    continue

                if file_list:
                    if print_msg:
                        print(proc.pid, proc.name)

                    for nt in file_list:
                        if print_msg:
                            print("\t", nt.path)

                        if Path(nt.path).as_posix() == file.as_posix():
                            return proc.pid, proc.name

            # This catches a race condition where a process ends
            # before we can examine its files or access to the process is denied
            except Exception as e:
                if e:
                    if print_msg:
                        print('Error accessing process. ', e)

        return False
