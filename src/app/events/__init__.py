"""Optional event data (passes, duels, tackles, ...) from WhoScored, kept in the local store.

Understat only knows about shots, so measures like forward-pass ratio and defensive duels need a second
source. This package is deliberately separate: nothing in the rest of the app requires it, a missing or
empty store simply means those columns stay blank, and the network part (``fetch``) is the only piece that
needs the optional ``soccerdata`` dependency.
"""
