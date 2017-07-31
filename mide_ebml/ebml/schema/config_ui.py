import os.path
from .specs import parse_specdata


_Elements, ConfigUIDocument = parse_specdata(os.path.join(os.path.dirname(__file__), 'config_ui.xml'), 'ConfigUIDocument', 'mide.ss.config', 1)


for name, element in _Elements.iteritems():
	globals()[name] = element
