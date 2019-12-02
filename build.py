import configparser
import os
import shutil
from subprocess import Popen

from modules.setup_paths import get_current_modules_dir

# Nsis Config file to read wheels from
# needs to be manually updated if new packages/wheels required!
CFG_FILE = os.path.join(get_current_modules_dir(), 'nsi', 'pfad_aeffchen.cfg')


def update_nsis_pypi_wheels(cfg: configparser.ConfigParser, pip: configparser.ConfigParser):
    pypi_wheels: str = cfg.get('Include', 'pypi_wheels')
    str_wheels = pypi_wheels.split('\n')
    cfg_wheels = dict()

    print('Nsis wheels:', str_wheels)
    print('Pip wheels: ', [p for p in pip.items('packages')])
    pip_wheels = [p[0] for p in pip.items('packages')]

    # Compare Nsis and Pip wheel versions and update cfg_wheels dict with pip versions
    for wheel in str_wheels:
        wheel_name, wheel_version = wheel.split('==')
        cfg_wheels[wheel_name] = wheel_version

        if wheel_name.casefold() in pip_wheels:
            pip_version = pip['packages'][wheel_name]  # Get the pip version
            pip_version = pip_version.replace('"', '').replace("'", "")  # Remove " and ' from version string

            if pip_version == '*':
                continue

            if pip_version.startswith('=='):
                pip_version = pip_version[2:]

            print('Updating', wheel_name, 'to', pip_version)
            cfg_wheels[wheel_name] = pip_version

    cfg_wheel_str = ''
    for name, version in cfg_wheels.items():
        cfg_wheel_str += f'{name}=={version}\n'

    print('\nUpdated Nsis Include/pypi_wheels entry:', cfg_wheel_str)

    # Update Nsis config
    cfg['Include']['pypi_wheels'] = cfg_wheel_str


def rem_build_dir():
    build_dir = os.path.join(get_current_modules_dir(), 'build')

    if not os.path.exists(build_dir):
        return

    try:
        shutil.rmtree(build_dir)
        print('Removed build directory:', build_dir)
    except Exception as e:
        print('Could not remove build directory:', e)


def move_installer(cfg: configparser.ConfigParser):
    installer_file = f"{cfg.get('Application', 'name')}_{cfg.get('Application', 'version')}.exe"
    installer_dir = os.path.join(get_current_modules_dir(), 'build', 'nsis')
    dist_dir = os.path.join(get_current_modules_dir(), 'dist')

    try:
        if not os.path.exists(dist_dir):
            os.mkdir(dist_dir)
            print('Created dist directory:', dist_dir)
    except Exception as e:
        print('Could not create dist directory:', e)
        return

    # Move installer
    try:
        dist_file = os.path.join(dist_dir, installer_file)

        if os.path.exists(dist_file):
            os.remove(dist_file)

        shutil.move(os.path.join(installer_dir, installer_file), dist_file)
        print('Moved installer file to:', dist_file)
    except Exception as e:
        print('Could not move installer file:', e)
        return

    rem_build_dir()


def main():
    rem_build_dir()

    # Pip wheel config Pipfile
    pip_file = os.path.join(get_current_modules_dir(), 'Pipfile')

    # Temporary config file to create during build process
    build_cfg = os.path.join(get_current_modules_dir(), 'pfad_aeffchen_build.cfg')

    if not os.path.exists(CFG_FILE) or not os.path.exists(pip_file):
        print('Pip or nsis cfg file not found ', CFG_FILE, pip_file)
        return

    cfg = configparser.ConfigParser(allow_no_value=True)
    pip = configparser.ConfigParser()

    with open(CFG_FILE, 'r') as f:
        cfg.read_file(f)

    with open(pip_file, 'r') as f:
        pip.read_file(f)

    update_nsis_pypi_wheels(cfg, pip)

    with open(build_cfg, 'w') as f:
        cfg.write(f)

    print('Written updated Nsis build configuration to:', build_cfg)

    args = ['pynsist', build_cfg]
    p = Popen(args=args)
    p.wait()

    if p.returncode != 0:
        print('PyNsist could not build installer!')
        return

    move_installer(cfg)

    # Rename and move temporary build cfg
    try:
        build_cfg_dist = os.path.join(get_current_modules_dir(), 'dist',
                                      f"build_cfg_{cfg.get('Application', 'version')}.cfg")

        if os.path.exists(build_cfg_dist):
            os.remove(build_cfg_dist)

        shutil.move(build_cfg, build_cfg_dist)
    except Exception as e:
        print('Could not move temporary Nsis build configuration:', e)


if __name__ == '__main__':
    main()
