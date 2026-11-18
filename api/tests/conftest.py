"""pytest-Einstieg: gleiche Voreinstellung wie beim Direktaufruf der Testdateien."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("CLIPFORGE_API_AUTH", "off")


class _NoRealKeyring:
    """Tests nutzen nie den echten OS-Schlüsselbund (Windows hat einen, Linux-CI
    meist nicht). Fake-Module, die Tests in sys.modules legen, gehen vor."""

    def find_spec(self, name, path=None, target=None):
        if name == "keyring" or name.startswith("keyring."):
            raise ImportError("echter keyring in Tests gesperrt")
        return None


sys.meta_path.insert(0, _NoRealKeyring())
