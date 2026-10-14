"""NDG XACML common parsing data

NERC DataGrid
"""
__author__ = "R B Wilkinson"
__date__ = "02/11/11"
__copyright__ = "(C) 2011 Science and Technology Facilities Council"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__license__ = "BSD - see LICENSE file in top-level directory"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__revision__ = "$Id: common.py 8078 2012-06-19 14:10:35Z pjkersha $"

class Common(object):
    """
    Holds data that is common to different readers when parsing policy
    documents.
    """
    def __init__(self, policyFinder):
        """
        @param policyFinder: policy finder
        @type policyFinder: ndg.xacml.finder.policyfinderbase.PolicyFinderBase
        subclass
        """
        self.policyFinder = policyFinder
