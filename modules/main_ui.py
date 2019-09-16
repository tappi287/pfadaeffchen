import logging
import os

import qt_ledwidget
from PyQt5 import QtWidgets
from PyQt5.uic import loadUi

from modules.app_globals import UI_FILE_MAIN, DESC_STRING, DESC_EN_STR
from modules.detect_lang import get_translation

# translate strings
de = get_translation()
de.install()
_ = de.gettext


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app_class, mod_dir, version):
        super(MainWindow, self).__init__()
        self.app = app_class
        logging.root.setLevel(logging.ERROR)
        ui_file = os.path.join(mod_dir, UI_FILE_MAIN)
        loadUi(ui_file, self)
        logging.root.setLevel(logging.DEBUG)

        # Set version window title
        title = self.windowTitle()
        title = f'{title} - v{version}'
        self.setWindowTitle(title)

        # Add LED widget
        self.led_widget = qt_ledwidget.LedWidget(self, self.ledLayout, led_size=24)

        self.actionBeenden.triggered.connect(self.close)

        # Translate Window content
        self.window_translations()

    def window_translations(self):
        # Description label
        desc_str = _("{0}").format(DESC_STRING, DESC_EN_STR)
        self.label_desc.setText(desc_str)

        self.label.setText(_("Pfad zur CSB Datei *.csb oder zur MayaBinary *.mb angeben:"))
        self.label_2.setText(_("Pfad zum Render Ausgabe Verzeichnis angeben:"))
        self.label_3.setText(_("Gültige IP Subnetze"))
        self.label_4.setText(_("Maya Version:"))
        self.label_5.setText(_("Renderer:"))
        self.enableQueue.setText(_("Warteschlange abarbeiten - De-/ oder Aktiviert "
                                   "die weitere Bearbeitung von Jobs in der Warteschlange"))
        self.pathLabel.setText(_("Kein Verzeichnis festgelegt."))
        self.sceneLabel.setText(_("Keine Datei gewählt."))
        self.startBtn.setText(_("Lokalen Job hinzufügen"))
        self.startRenderService.setText(_("Render Service starten"))

        # Menu
        self.menuDatei.setTitle(_("Datei"))
        self.menuFenster.setTitle(_("Fenster"))
        self.actionBeenden.setText(_("Beenden"))
        self.actionToggleWatcher.setText(_("Bildprozess Fenster"))
        self.actionReport.setText(_("Report speichern"))

        # ToolBox labels
        tab_labels = [_("Einführung"), _("Lokaler Job"), _("Einstellungen")]
        for idx, item_text in enumerate(tab_labels):
            self.toolBox.setItemText(idx, item_text)

        # Job Manager column names
        column_names = ["#", _("Job Titel"), _("Szenendatei"), _("Ausgabeverzeichnis"), _("Progress"),
                        _("Klient"), _("Funktion"), _("Bestätigung")]
        header_item = self.widgetJobManager.headerItem()
        for idx, item_name in enumerate(column_names):
            if idx < header_item.columnCount():
                header_item.setText(idx, item_name)

    def closeEvent(self, close_event):
        close_event.ignore()
        self.app.quit()
