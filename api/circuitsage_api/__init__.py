"""CircuitSage API — FastAPI shell over the circuitsolver core (design §5).

Dependency direction is one-way: api → core. The core never imports
anything from here.
"""

__version__ = "0.1.0"
