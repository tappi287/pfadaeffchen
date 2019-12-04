"""
    Render Job class

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
from datetime import datetime

from modules.detect_lang import get_translation

de = get_translation()
_ = de.gettext


class JobStatus:
    """ Defines Job status for use in local modules """
    # 0 - file transfer, 1 - queue, 2 - scene editing, 3 - rendering, 4 - Image detection, 5 - finished, 6 - failed
    file_transfer = 0
    queued = 1
    scene_loading = 2
    rendering = 3
    image_detection = 4
    finished = 5
    failed = 6
    aborted = 7


class Job:
    """ Holds information about a render job """
    status_desc_list = [_('Datentransfer'), _('Warteschlange'), _('Szene wird vorbereitet'),
                        _('Rendering'), _('Bilderkennung'),
                        _('Abgeschlossen'), _('Fehlgeschlagen'), _('Abgebrochen')]
    combo_box_items = [_('Zum Anfang der Warteschlange'), _('Ans Ende der Warteschlange'), _('Abbrechen')]
    button_txt = _('Ausführen')

    def __init__(self, job_title, scene_file, render_dir, renderer,
                 ignore_hidden_objects='1', maya_delete_hidden='1', use_scene_settings='0',
                 client='Server'):
        self.title = job_title

        self.remote_file = scene_file  # available for clients to locate scene file
        self.local_file = ''  # will be set after file transfer
        self._file = scene_file  # file property

        self.render_dir = render_dir
        self.renderer = renderer

        # CSB Import option ignoreHiddenObject
        self.ignore_hidden_objects = ignore_hidden_objects

        # Maya Layer Creation process optional argument
        self.maya_delete_hidden = maya_delete_hidden

        # Use render settings of the maya binary scene instead of creating
        self.use_scene_settings = use_scene_settings

        # Class version
        self.version = 2

        # Client hostname
        self.client = client

        # Creation time as datetime object
        self.created = datetime.now().timestamp()

        # Index in Service Manager Job queue
        self.remote_index = 0

        # File transfer status in Service Manager Job queue
        self.scene_file_is_local = False

        self.__img_num = 0
        self.total_img_num = 0
        self.__progress = 0

        # Status
        # 0 - file transfer, 1 - queue, 2 - scene editing, 3 - rendering, 4 - Image detection, 5 - finished, 6 - failed
        self.__status = 0
        self.status_name = self.status_desc_list[self.__status]
        self.in_progress = False

    @property
    def file(self):
        """ Return scene file location, preferring local scene file """
        if self.local_file:
            return self.local_file
        else:
            return self._file

    @file.setter
    def file(self, value):
        self._file = value

    @property
    def img_num(self):
        return self.__img_num

    @img_num.setter
    def img_num(self, val: int):
        """ Updating number of rendered images also updates progress """
        self.__img_num = val
        self.update_progress()

    @property
    def status(self):
        return self.__status

    @status.setter
    def status(self, status: int=0):
        if 1 < status < 5:
            self.in_progress = True
        elif 4 < status < 2:
            self.in_progress = False

        # Status failed/aborted
        if status > 5:
            self.progress = 0

        # Status finished
        if status == 5:
            self.progress = 100

        self.__status = status

        if status > len(self.status_desc_list):
            self.status_name = _('Unbekannt')
        else:
            self.status_name = self.status_desc_list[status]

    @property
    def progress(self):
        return self.__progress

    @progress.setter
    def progress(self, val: int):
        val = min(100, max(0, val))

        self.__progress = val

    def set_failed(self):
        self.progress = 0
        self.in_progress = False

        # Canceled jobs should not appear as failed
        if self.status != 7:
            self.status = 6

    def set_canceled(self):
        self.set_failed()
        self.status = 7

    def set_finished(self):
        if self.status >= 6:
            # Failed or aborted job can not be finished
            return

        self.progress = 100
        self.in_progress = False
        self.status = 5

    def update_progress(self):
        if self.status > 4:
            return

        # Display number of rendered images
        if self.status == 3:
            if self.img_num and self.total_img_num:
                self.status_name = _('{0:03d}/{1:03d} Layer erstellt').format(self.img_num, self.total_img_num)

                if self.renderer == 'arnold':
                    percent = min(100, max(0, self.img_num - 1) * 10)
                    self.status_name = f'Rendering {int(percent):02d}%'

        value = 0

        if self.total_img_num > 0:
            # Set job progress by number of created images
            value = (100 * max(1, self.img_num)) / max(1, self.total_img_num)
            # Add a 5% gap for image detection duration
            value = round(value * 0.95)

        self.progress = value
