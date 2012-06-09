# Copyright (C) 2010 Robert Park <rbpark@exolucere.ca>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Control how the map is navigated."""

from __future__ import division

from gi.repository import Gtk, Gdk

from common import Widgets, gst, map_view, bind_properties
from gpsmath import Coordinates, valid_coords

def move_by_arrow_keys(accel_group, acceleratable, keyval, modifier):
    """Move the map view by 5% of its length in the given direction."""
    key, view = Gdk.keyval_name(keyval), map_view
    factor    = (0.45 if key in ('Up', 'Left') else 0.55)
    lat       = view.get_center_latitude()
    lon       = view.get_center_longitude()
    if key in ('Up', 'Down'):
        lat = view.y_to_latitude(view.get_height() * factor)
    else:
        lon = view.x_to_longitude(view.get_width() * factor)
    if valid_coords(lat, lon):
        view.center_on(lat, lon)

def remember_location(view):
    """Add current location to history stack."""
    history = list(gst.get('history'))
    location = tuple([view.get_property(x) for x in
        ('latitude', 'longitude', 'zoom-level')])
    if history[-1] != location:
        history.append(location)
    gst.set_history(history[-30:])

def go_back(*ignore):
    """Return the map view to where the user last set it."""
    history = list(gst.get('history'))
    lat, lon, zoom = history.pop()
    if valid_coords(lat, lon):
        map_view.set_zoom_level(zoom)
        map_view.center_on(lat, lon)
    if len(history) > 1:
        gst.set_history(history)
    else:
        gst.reset('history')

def zoom_button_sensitivity(view, signal, in_sensitive, out_sensitive):
    """Ensure zoom buttons are only sensitive when they need to be."""
    zoom = view.get_zoom_level()
    out_sensitive(view.get_min_zoom_level() != zoom)
    in_sensitive( view.get_max_zoom_level() != zoom)

Widgets.zoom_in_button.connect('clicked', lambda *ignore: map_view.zoom_in())
Widgets.zoom_out_button.connect('clicked', lambda *ignore: map_view.zoom_out())
Widgets.back_button.connect('clicked', go_back)

for key in ['latitude', 'longitude', 'zoom-level']:
    gst.bind(key, map_view, key)

accel = Gtk.AccelGroup()
Widgets.main.add_accel_group(accel)
for key in [ 'Left', 'Right', 'Up', 'Down' ]:
    accel.connect(Gdk.keyval_from_name(key),
        Gdk.ModifierType.MOD1_MASK, 0, move_by_arrow_keys)

map_view.connect('notify::zoom-level', zoom_button_sensitivity,
    Widgets.zoom_in_button.set_sensitive, Widgets.zoom_out_button.set_sensitive)
map_view.connect('realize', remember_location)

center = Coordinates()
lat_binding = bind_properties(map_view, 'latitude', center)
lon_binding = bind_properties(map_view, 'longitude', center)
center.do_modified(True)
center_binding = bind_properties(center, 'geoname', Widgets.main, 'title')
center.timeout_seconds = 10 # Reduces the rate that the titlebar updates

