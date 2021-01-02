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

"""Define classes used for parsing GPX and KML XML files."""

from __future__ import division

from xml.parsers.expat import ParserCreate, ExpatError
from dateutil.parser import parse as parse_date
from re import compile as re_compile
from gi.repository import Gtk
from calendar import timegm
from time import clock

from gpsmath import Coordinates
from common import add_polygon_to_map


class XMLSimpleParser:
    """A simple wrapper for the Expat XML parser."""
    
    def __init__(self, rootname, watchlist):
        self.rootname = rootname
        self.watchlist = watchlist
        self.call_start = None
        self.call_end = None
        self.element = None
        self.tracking = None
        self.state = {}
        
        self.parser = ParserCreate()
        self.parser.StartElementHandler = self.element_root
    
    def parse(self, filename, call_start, call_end):
        """Begin the loading and parsing of the XML file."""
        self.call_start = call_start
        self.call_end = call_end
        try:
            with open(filename) as xml:
                self.parser.ParseFile(xml)
        except ExpatError:
            raise IOError
   
    def element_root(self, name, attributes):
        """Called on the root XML element, we check if it's the one we want."""
        if self.rootname != None and name != self.rootname:
            raise IOError
        self.parser.StartElementHandler = self.element_start
    
    def element_start(self, name, attributes):
        """Only collect the attributes from XML elements that we care about."""
        if not self.tracking:
            if name not in self.watchlist:
                return
            if self.call_start(name, attributes):
                # Start tracking this element, accumulate everything under it.
                self.tracking = name
                self.parser.CharacterDataHandler = self.element_data
                self.parser.EndElementHandler = self.element_end
        
        if self.tracking is not None:
            self.element = name
            self.state[name] = ''
            self.state.update(attributes)
    
    def element_data(self, data):
        """Accumulate all data for an element.
        
        Expat can call this handler multiple times with data chunks.
        """
        if not data or data.strip() == '':
            return
        self.state[self.element] += data
    
    def element_end(self, name):
        """When the tag closes, pass it's data to the end callback and reset."""
        if name != self.tracking:
            return
        
        self.call_end(name, self.state)
        self.tracking = None
        self.state.clear()
        self.parser.CharacterDataHandler = None
        self.parser.EndElementHandler = None


class TrackFile(Coordinates):
    """Parent class for all types of GPS track files.
    
    Subclasses must implement element_start and element_end, and call them in
    the base class.
    """
    
    def __init__(self, filename, root, watch, progressbar):
        self.progress = progressbar
        self.clock    = clock()
        self.append   = None
        self.tracks   = {}
        
        self.parser = XMLSimpleParser(root, watch)
        self.parser.parse(filename, self.element_start, self.element_end)
        
        keys = self.tracks.keys()
        self.alpha = min(keys)
        self.omega = max(keys)
    
    def element_start(self, name, attributes):
        """Placeholder for a method that gets overridden in subclasses."""
        return False
    
    def element_end(self, name, state):
        """Occasionally redraw the screen so the user can see what's happening."""
        if clock() - self.clock > .2:
            self.progress.pulse()
            while Gtk.events_pending():
                Gtk.main_iteration()
            self.clock = clock()


# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re_compile(r'[:TZ-]').split


class GPXFile(TrackFile):
    """Parse a GPX file."""
    
    def __init__(self, filename, progress):
        TrackFile.__init__(self, filename, 'gpx',
                           ['trkseg', 'trkpt'], progress)
    
    def element_start(self, name, attributes):
        """Adds a new polygon for each new segment, and watches for track points."""
        if name == 'trkseg':
            self.append = add_polygon_to_map()
        return name == 'trkpt'
    
    def element_end(self, name, state):
        """Collect and use all the parsed data.
        
        This method does most of the heavy lifting, including parsing time
        strings into UTC epoch seconds, appending to the ChamplainMarkerLayers,
        keeping track of the first and last points loaded.
        """
        # We only care about the trkpt element closing, because that means
        # there is a new, fully-loaded GPX point to play with.
        if name != 'trkpt':
            return
        try:
            timestamp = timegm(map(int, split(state['time'])[0:6]))
            lat = float(state['lat'])
            lon = float(state['lon'])
        except Exception as error:
            print error
            # If any of lat, lon, or time is missing, we cannot continue.
            # Better to just give up on this track point and go to the next.
            return
        
        self.tracks[timestamp] = self.append(lat, lon, float(state.get('ele', 0.0)))
        
        TrackFile.element_end(self, name, state)


class KMLFile(TrackFile):
    """Parse a KML file."""
    
    def __init__(self, filename, progress):
        self.whens    = []
        self.coords   = []
        
        TrackFile.__init__(self, filename, 'kml', ['gx:Track',
                           'when', 'gx:coord'], progress)
    
    def element_start(self, name, attributes):
        """Adds a new polygon for each new gx:Track, and watches for location data."""
        if name == 'gx:Track':
            self.append = add_polygon_to_map()
            return False
        return True
    
    def element_end(self, name, state):
        """Watch for complete pairs of when and gx:coord tags.
        
        This is accomplished by maintaining parallel arrays of each tag.
        """
        if name == 'when':
            try:
                timestamp = timegm(parse_date(state['when']).utctimetuple())
            except Exception as error:
                print error
                return
            self.whens.append(timestamp)
        if name == 'gx:coord':
            self.coords.append(state['gx:coord'].split())
        
        complete = min(len(self.whens), len(self.coords))
        if complete > 0:
            for i in range(0, complete):
                self.tracks[self.whens[i]] = \
                    self.append(float(self.coords[i][1]), \
                                float(self.coords[i][0]), \
                                float(self.coords[i][2]))
            self.whens = self.whens[complete:]
            self.coords = self.coords[complete:]
        
        TrackFile.element_end(self, name, state)

