#! python 2 and 3
"""
    -------------
    Pfad Aeffchen
    -------------
    GLOBALS

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
DESC_STRING = "Dieser Batch Prozess erstellt Render Layer mit einer Vordergrund Matte fuer jedes Material " \
              "der Szene und gibt diese als PSD Datei mit Ebenen aus. " \
              "Die Kamera der DeltaGen Szene muss beim Speichern der benoetigten Kamera entsprechen. " \
              "Ein MayaBinary benoetigt eine Kamera mit Namen <i>'Camera'</i> " \
              "mit der benoetigten Perspektive.<br><br>" \
              "<b>Hinweis</b>: Unsichtbare Objekte werden aus der Szene entfernt. " \
              "Stelle sicher das du nicht benoetigte Gruppen wie zum Beispiel " \
              "<i>'EXT', 'materials', 'myFancy6000objectMaterialLibary'</i> ausgeblendet hast. " \
              "Dies beschleunigt das Rendering enorm!<br><br>" \
              "<b>Renderer</b><br>" \
              "mayaSoftware - langsam aber zuverlaessig, Ergebnisse sind auf jedem Rechner identisch, " \
              "bestes Anti-Aliasing fuer Naehte und sehr kleine Objekte<br>" \
              "mayaHardware2 - *sehr* schnell aber unzuverlaessig, Ergebnisse koennen je nach Grafikhardware " \
              "und Treiber abweichen, Anti-Aliasing fast identisch zu DeltaGen"

DESC_EN_STR = "This batch process creates render layer with a foreground matte for every material in the scene " \
              "and creates a layered PSD file. You must save your DeltaGen scene with the viewport set to the " \
              "camera you want to display your layers with. Maya binaries need a camera with the name " \
              "<i>'Camera'</i><br><br>" \
              "<b>Hidden</b> objects will be removed from the render scene. " \
              "Make sure you hide unnecessary objects that will not be visible or do not add any valuable path info. " \
              "This will accelerate render times by a good amount." \
              "<br><br>" \
              "<b>Available renderer:</b><br>" \
              "mayaSoftware - very slow but accurate, results on different machines do not vary and anti-aliasing " \
              "for very small objects like stitches is excellent<br>" \
              "mayaHardware2 - *very* fast but unreliable, results vary by OS, hardware and drivers, anti-aliasing " \
              "is almost identical to DeltaGen" \

DEFAULT_VERSION = '2017'
AVAILABLE_RENDERER = ['mayaSoftware', 'mayaHardware2']
COMPATIBLE_VERSIONS = ['2017', '2016.5']

OUTPUT_DIR_NAME = 'render_output'

JOB_DATA_EOS = b'End-Of-Job-Data'


# Socket address to communicate with processes
# Port 0 means to select an arbitrary unused port
class SocketAddress:
    main = ('localhost', 9005)
    watcher = ('localhost', 9006)
    time_out = 20

    # Service broadcast
    service_magic = 'paln3s'
    service_port = 52121

    # List of valid IP subnet's
    valid_subnet_patterns = ['192.168.178', '192.168.13']


# Default image parameters
class ImgParams:
    extension = 'sgi'
    res_x = 3840
    res_y = 2160
    maya_detection_format = 'iff'


UI_FILE_MAIN = 'res/Pfad_Aeffchen.ui'
UI_FILE_SUB = 'res/Renderprozess_Depp.ui'
UI_FILE_LED = 'res/LED_widget.ui'

PFAD_AEFFCHEN_LOG_NAME = 'pfad_aeffchen.log'
WATCHER_PROCESS_LOG_NAME = 'image_watcher_pfad_aeffchen.log'
