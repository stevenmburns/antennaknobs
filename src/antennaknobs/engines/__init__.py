try:
    from .pynec import PyNECEngine
except ImportError:
    PyNECEngine = None

from .momwire import MomwireEngine
from .nec5 import NEC5Engine, find_nec5

__all__ = ["PyNECEngine", "MomwireEngine", "NEC5Engine", "find_nec5"]
