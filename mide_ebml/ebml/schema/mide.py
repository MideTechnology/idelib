import os.path
from .specs import parse_specdata


_Elements, MideDocument = parse_specdata(os.path.join(os.path.dirname(__file__), 'mide.xml'), 'MideDocument', 'mide', 1)


for name, element in _Elements.iteritems():
	globals()[name] = element
