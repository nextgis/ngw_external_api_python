from qgis.core import *
from qgis.gui import *

__author__ = 'yellow'
__license__ = ''
__date__ = '2015'


def qgisLog(msg, level=QgsMessageLog.INFO):
    QgsMessageLog.logMessage(msg, "NGW API", level)
