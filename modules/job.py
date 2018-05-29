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


class Job(object):
    """ Holds information about a render job """
    status_description = [_('Warteschlange'), _('Szene wird vorbereitet'),
                          _('Rendering'), _('Bilderkennung'),
                          _('Abgeschlossen'), _('Fehlgeschlagen'), _('Abgebrochen')]
    combo_box_items = [_('Zum Anfang der Warteschlange'), _('Ans Ende der Warteschlange'), _('Abbrechen')]
    button_txt = _('Ausführen')

    def __init__(self, job_title, scene_file, render_dir, renderer, ignore_hidden_objects='1', client='Server'):
        self.title = job_title
        self.file = scene_file
        self.render_dir = render_dir
        self.renderer = renderer

        # CSB Import option ignoreHiddenObject
        self.ignore_hidden_objects = ignore_hidden_objects

        # Class version
        self.version = 1

        # Client hostname
        self.client = client

        # Creation time as datetime object
        self.created = datetime.now().timestamp()

        # Index in Service Manager Job queue
        self.remote_index = 0

        self.__img_num = 0
        self.total_img_num = 0
        self.__progress = 0

        # Status 0 - queue, 1 - scene editing, 2 - rendering, 3 - Image detection, 4 - finished, 5 - failed
        self.__status = 0
        self.status_name = self.status_description[self.__status]
        self.in_progress = False

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
        if 0 < status < 4:
            self.in_progress = True
        elif 3 < status < 1:
            self.in_progress = False

        # Status failed/aborted
        if status > 4:
            self.progress = 0

        # Status finished
        if status == 4:
            self.progress = 100

        self.__status = status

        if status > len(self.status_description):
            status_desc = _('Unbekannt')
        else:
            status_desc = self.status_description[status]

        self.status_name = status_desc

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
        if self.status != 6:
            self.status = 5

    def set_canceled(self):
        self.set_failed()
        self.status = 6

    def set_finished(self):
        if self.status >= 5:
            # Failed or aborted job can not be finished
            return

        self.progress = 100
        self.in_progress = False
        self.status = 4

    def update_progress(self):
        if self.status > 3:
            return

        # Display number of rendered images
        if self.status == 2:
            if self.img_num and self.total_img_num:
                self.status_name = _('{0:03d}/{1:03d} Layer erstellt').format(self.img_num, self.total_img_num)

        value = 0

        if self.total_img_num > 0:
            # Set job progress by number of created images
            value = (100 * max(1, self.img_num)) / max(1, self.total_img_num)
            # Add a 5% gap for image detection duration
            value = round(value * 0.95)

        self.progress = value
