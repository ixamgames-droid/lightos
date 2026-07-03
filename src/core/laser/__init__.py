"""Laser-Punkt-Streaming (LAS-05): neutrales Frame-Modell + Netzwerk-Backends.

Getrennt vom DMX-Pfad: Netzwerk-Laser (``PatchedFixture.protocol`` in
``LASER_NETWORK_PROTOCOLS``) werden NICHT über die 44-Hz-Universe-Pipeline
bedient, sondern vom :class:`~src.core.laser.laser_output.LaserOutputManager`
in einem eigenen Thread mit Punktlisten gefüttert.
"""
