"""Interface de Dofus Price Helper (CustomTkinter), rangée par thème.

`from dofus_helper import gui` puis `gui.X` : X est cherché dans tous les fichiers du dossier
(voir dofus_helper/_gather.py). App (app.py) rassemble les morceaux de la fenêtre.
"""
from __future__ import annotations

from .. import core  # noqa: F401  (gestion DPI activée avant Tk)
from .._gather import gather
from . import common, popups, helpers, tray, news  # noqa: I001  (ordre : common configure le thème)
from . import home, tabs, options, journal, results, wizard, loops, watch, hud, tour
from . import app

gather(__name__, (common, popups, helpers, tray, news, home, tabs, options, journal, results, wizard,
                  loops, watch, hud, tour, app))
