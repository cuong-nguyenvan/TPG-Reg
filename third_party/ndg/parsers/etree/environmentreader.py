"""NDG XACML ElementTree based Environment Element reader 

NERC DataGrid
"""
__author__ = "P J Kershaw"
__date__ = "16/03/10"
__copyright__ = "(C) 2010 Science and Technology Facilities Council"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__license__ = "BSD - see LICENSE file in top-level directory"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__revision__ = "$Id: environmentreader.py 7955 2011-12-21 18:29:45Z rwilkinson $"
from ndg.xacml.core.environment import Environment
from ndg.xacml.parsers.etree.targetchildreader import TargetChildReader
    

class EnvironmentReader(TargetChildReader):
    '''ElementTree based XACML Rule parser
    @cvar TYPE: XACML type to instantiate from parsed object
    @type TYPE: type
    '''
    TYPE = Environment
 