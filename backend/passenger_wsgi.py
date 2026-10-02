"""Entry point for cPanel's "Setup Python App" (Phusion Passenger).

Used on shared hosting only — a VPS with its own gunicorn/systemd setup has
no reason to touch this file. cPanel creates and manages its own virtualenv
for the app and imports this file looking for a WSGI callable named
`application`; everything past that is normal Django. See docs/HOSTING.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# cPanel's "Setup Python App" page lets you set environment variables in its
# own UI (persisted across restarts, no code change needed) — set DJANGO_ENV
# there if you can. This default is only a fallback for that not being
# available, or for running this file somewhere else that behaves like
# Passenger.
os.environ.setdefault("DJANGO_ENV", "production")

from config.wsgi import application  # noqa: E402
