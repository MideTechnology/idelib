import os.path
from .specs import parse_specdata


_Elements, MideManifest = parse_specdata(os.path.join(os.path.dirname(__file__), 'manifest.xml'), 'MideManifest', 'manifest', 1)


for name, element in _Elements.iteritems():
	globals()[name] = element
