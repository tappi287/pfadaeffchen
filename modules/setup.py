from pathlib import Path
from distutils.core import setup
from Cython.Build import cythonize

# Compile with:
# python setup.py build_ext -b "D:\Docs\py\pfadaeffchen"

mod_dir = Path(__file__).parent
module_file = mod_dir / 'decrypto_dict.pyx'
print(module_file.as_posix())

setup(
    ext_modules=cythonize(module_file.as_posix())
    )
