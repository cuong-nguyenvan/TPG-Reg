"""NDG XACML Context Action type

NERC DataGrid
"""
__author__ = "P J Kershaw"
__date__ = "24/03/10"
__copyright__ = "(C) 2010 Science and Technology Facilities Council"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__license__ = "BSD - see LICENSE file in top-level directory"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__revision__ = "$Id: action.py 7087 2010-06-25 11:23:09Z pjkersha $"
from ndg.xacml.core.context import RequestChildBase


class Action(RequestChildBase):
    """XACML Context Action type"""
    ELEMENT_LOCAL_NAME = 'Action'

