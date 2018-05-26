"""
# Detect if we are running in a Maya standalone instance
try:
    import maya.standalone
    maya.standalone.initialize()

    # We are not in standalone
    standalone = False
except Exception as e:
    # We are in standalone instance
    standalone = True
    print(e)
    pass
"""

import maya.cmds as cmds
import os
import sys

# Open Command port for MayaCharm
try:
    if not cmds.commandPort(':4434', q=True):
        cmds.commandPort(n=':4434')
except Exception as e:
    # print(e)
    pass

# Extend sys.path so we can import local modules from dev environment
user_path = os.path.abspath(os.getenv('USERPROFILE'))
modules_path = os.path.abspath(os.path.join(user_path, 'Nextcloud/py/maya_scripts'))

# print 'Extending Python Path with: ' + modules_path
sys.path.append(modules_path)