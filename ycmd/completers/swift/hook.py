# Copyright (C) 2011, 2012 Stephen Sugden <me@stephensugden.com>
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

from ycmd.completers.swift.my_swiftd_completer import SwiftCompleter as SwiftD, ShouldEnableSwiftCompleter
# from ycmd.completers.swift.my_swift_completer import SwiftCompleter
# from ycmd.completers.swift.swiftls_completer import SwiftCompleter as LSP, ShouldEnableSwiftCompleter


def GetCompleter( user_options ):
    # only support PM, only kinda work. may I should write mine in future
    if ShouldEnableSwiftCompleter():
        return SwiftD( user_options )
