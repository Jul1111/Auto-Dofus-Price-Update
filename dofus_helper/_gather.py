"""Un module qui en rassemble plusieurs (`core` pour le moteur, `gui` pour l'interface).

`core.X` lit X dans le fichier qui le définit. Remplacer `core.X` (ce que font les tests :
monkeypatch.setattr(core, "grab_screen", ...)) le remplace dans ce fichier ET dans ceux qui
l'importent : comme quand tout tenait dans un seul fichier.
"""
from __future__ import annotations

import sys
import types


def gather(module_name: str, modules: tuple) -> None:
    """`modules` dans l'ordre des dépendances : un module n'importe que ceux d'avant, le 1er qui
    connaît un nom est donc celui qui le définit (les suivants n'en ont qu'une copie importée)."""
    target = sys.modules[module_name]

    def holders(name):
        return [m for m in modules if name in m.__dict__]

    def forward(name):
        # Une vraie propriété (pas seulement __getattr__) : monkeypatch la voit, et remet
        # l'ancienne valeur à la fin du test.
        def get(self):
            return holders(name)[0].__dict__[name]

        def set(self, value):
            for m in holders(name):
                setattr(m, name, value)
        return property(get, set)

    class Gathered(types.ModuleType):
        def __getattr__(self, name):          # nom apparu après le chargement (rare)
            found = holders(name)
            if found:
                return found[0].__dict__[name]
            raise AttributeError(f"module {module_name!r} has no attribute {name!r}")

        def __dir__(self):
            names = set(super().__dir__())
            for m in modules:
                names.update(n for n in m.__dict__ if not n.startswith("__"))
            return sorted(names)

    for m in modules:
        for name in list(m.__dict__):
            # les noms propres au module rassembleur (sous-modules, `gather`...) restent à lui
            if not name.startswith("__") and name not in target.__dict__ and not hasattr(Gathered, name):
                setattr(Gathered, name, forward(name))
    target.__class__ = Gathered
