# pfadaeffchen
Network render service for Autodesk Maya

[![Latest PyPI version](https://img.shields.io/badge/version-v0.95-blue.svg)](https://github.com/tappi287/pfadaeffchen/releases) [![GitHub license](https://img.shields.io/github/license/tappi287/pfadaeffchen.svg)

Creates a matte for every material in your Maya scene and outputs a layered PSD file.

![Screenshot](https://github.com/tappi287/pfadaeffchen/blob/master/res/Screenshot.PNG?raw=true)

### Requirements
 - [x] Autodesk Maya 2016.5 or 2017 Update 4+
 - [x] Microsoft Windows 7 x64 or newer

### Usage
 1. Install the [latest release](https://github.com/tappi287/pfadaeffchen/releases)
 2. Run the application
 3. Add a local job via the local job tab

### Create the installer yourself
 1. Install [Nullsoft install system](http://nsis.sourceforge.net/Download)
 2. Install [pynsist](https://pynsist.readthedocs.io/en/latest/) `pip install pynsist`
 3. Download / clone the project, go to ``pfad_aeffchen`` folder that contains ``pfad_aeffchen.cfg``
 4. From your command prompt run pynsist inside the project folder:
	```bash
	cd <project_folder>
	pynsist pfad_aeffchen.cfg
	```
### Build requirements
The packages listed in the ''requirements.txt'' are needed to run the application from your local Python interpreter. They are not needed for building the installer. Pynsist will download the required wheels when building the installer.
 - [x] PyQt5 `pip install PyQt5`
 - [x] qt_ledwidget `pip install qt-ledwidget`

### License
The GUI application is following the PyQt5 license, releasing under GPLv3.
Modules inside the ''maya_mod'' folder are availabe under the MIT license since they are executed separately in Maya's bundled mayapy Python interpreter.
