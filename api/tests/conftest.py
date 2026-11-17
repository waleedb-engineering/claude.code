"""pytest-Einstieg: gleiche Voreinstellung wie beim Direktaufruf der Testdateien."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("CLIPFORGE_API_AUTH", "off")
