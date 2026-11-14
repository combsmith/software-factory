"""The guards on a Role's own writes, as pure functions: what a push may land, byte for byte.

Nothing in this package opens a file, a socket or a process, reads the environment, or reads the clock, and it
imports nothing but `__future__` and itself. See AGENTS.md.
"""
