"""loupe engine package: the substrate every analysis module imports.

Kept import-light on purpose: loupe joins a per-edit hook stack where every
spawn counts, so nothing is re-exported here. Import submodules explicitly
(``from loupe import state``) and pay only for what you use.
"""
