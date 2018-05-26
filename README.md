# pfadaeffchen
Network render service for Autodesk Maya
[![Latest PyPI version](https://img.shields.io/badge/version-v0.95-blue.svg)](https://github.com/tappi287/pfadaeffchen/releases) [![License: GPLv3](https://img.shields.io/dub/l/vibe-d.svg)](https://opensource.org/licenses/GPL-3.0)

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
