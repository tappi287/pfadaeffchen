import os
import sys
from subprocess import call

print('-------------------------')
print('Run translation tools')
print('-------------------------')
py_path = os.path.dirname(sys.executable)
print('Python executable: ' + py_path)

tool_dir = os.path.abspath(os.path.join(py_path, 'Tools\\i18n\\'))
print('Tools dir: ' + tool_dir)
pygettext = os.path.abspath(os.path.join(tool_dir, 'pygettext.py'))
print(pygettext)
msgfmt = os.path.abspath(os.path.join(tool_dir, 'msgfmt.py'))
print(msgfmt)
current_modules_dir = os.path.dirname(__file__)
current_modules_dir = os.path.abspath(os.path.join(current_modules_dir, '../'))
print(current_modules_dir)


def create_pot():
    args = 'python "' + pygettext + '" -p locale -d pfad_aeffchen pfad_aeffchen.py modules/*.py'
    print('Calling: ' + str(args))
    call(args, cwd=current_modules_dir)


def create_mo():
    args = 'python "' + msgfmt + '" -o en/LC_MESSAGES/pfad_aeffchen.mo en/LC_MESSAGES/pfad_Aeffchen'
    print('Calling: ' + str(args))
    call(args, cwd=os.path.join(current_modules_dir, 'locale'))

    args = 'python "' + msgfmt + '" -o de/LC_MESSAGES/pfad_aeffchen.mo de/LC_MESSAGES/pfad_Aeffchen'
    print('Calling: ' + str(args))
    call(args, cwd=os.path.join(current_modules_dir, 'locale'))


def main():
    print('\nChoose an action:\n0 - Create pot template file\n1 - Create mo binary files for de+en')
    choice = input('Your choice: ')

    if choice not in ['1', '0']:
        print('Invalid choice.')
        main()

    if choice == '0':
        create_pot()

    if choice == '1':
        create_mo()


if __name__ == '__main__':
    main()
