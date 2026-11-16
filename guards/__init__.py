"""The guards on a Role's own writes, as pure functions: what a push may land, byte for byte (issue 838).

None is built yet. This package is listed in config/hooks.json before it holds one, as a protected path and as what
verify imports, so that the first guard is never a file a Role could change.
"""
