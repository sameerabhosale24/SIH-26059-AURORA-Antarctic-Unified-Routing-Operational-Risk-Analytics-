"""Real-time relays: the two sockets that carry live operational data.

* :mod:`app.services.relays.gps_relay` — own-ship NMEA into ``vessel_state``
* :mod:`app.services.relays.ais_relay` — AISStream.io into ``ais_track``

Both are long-running asyncio tasks started from the application lifespan
rather than APScheduler jobs: a scheduled job fires, does its work and ends,
while a relay *is* a connection that must be held open and re-opened when it
drops. They share one contract — an unconfigured source starts nothing, a
dead socket is retried with backoff, and a write failure never kills the
reader.
"""
