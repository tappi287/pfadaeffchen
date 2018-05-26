"""
    Pfad Aeffchen language detection

    https://stackoverflow.com/questions/3425294/how-to-detect-the-os-default-language-in-python#3425316

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
import locale
import ctypes
from gettext import translation
from modules.setup_paths import get_current_modules_dir


def get_ms_windows_language():
    """ Currently we only support english and german """
    windll = ctypes.windll.kernel32

    # Get the language setting of the Windows GUI
    try:
        os_lang = windll.GetUserDefaultUILanguage()
    except Exception as e:
        print(e)
        return

    # Convert language code to string
    lang = locale.windows_locale.get(os_lang)

    # Only return supported languages
    if not lang.startswith('de'):
        lang = 'en'

    return lang


def get_translation():
    locale_dir = os.path.join(get_current_modules_dir(), 'locale')
    return translation('pfad_aeffchen', localedir=locale_dir)