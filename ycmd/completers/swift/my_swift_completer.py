# Copyright (C) 2011-2012 Stephen Sugden <me@stephensugden.com>
#                         Google Inc.
#                         Stanislav Golovanov <stgolovanov@gmail.com>
#               2017      ycmd contributors
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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # noqa
from future import standard_library
from future.utils import native
standard_library.install_aliases()

from ycmd.utils import ToBytes, ToUnicode, ProcessIsRunning
from ycmd.completers.completer import Completer
from ycmd.completers.completer_utils import GetFileContents
from ycmd import responses, utils, hmac_utils
from ycmd import extra_conf_store
from tempfile import NamedTemporaryFile
from io import BytesIO

import json
import logging
import subprocess
import sys
import os


BINARY_NOT_FOUND_MESSAGE = ( 'The specified sourceKitten {0} ' +
                             'was not found. Did you specify it correctly?' )
LOGFILE_FORMAT = 'swift_{port}_{std}_'
PATH_TO_SOURCEKITTEN = "sourcekitten"




class SwiftCompleter( Completer ):
  """
  A Completer that uses the SourceKitten.
  https://github.com/jpsim/SourceKitten
  """

  def __init__( self, user_options ):
    super( SwiftCompleter, self ).__init__( user_options )
    self._logger = logging.getLogger( __name__ )
    #  self._logfile_stdout = None
    #  self._logfile_stderr = None
    #  self._keep_logfiles = user_options[ 'server_keep_logfiles' ]
    self._flags_for_file = {}
    self._big_cache = []

    self._UpdateSourceKittenBinary( user_options.get( 'sourcekitten_binary_path' ) )


  def _UpdateSourceKittenBinary( self, binary ):
      if not binary: binary = PATH_TO_SOURCEKITTEN
      resolved_binary = utils.FindExecutable( binary )
      if not resolved_binary:
        msg = BINARY_NOT_FOUND_MESSAGE.format( binary )
        self._logger.error( msg )
        raise RuntimeError( msg )
      self._sourcekitten_binary_path = resolved_binary


  def SupportedFiletypes( self ):
    """ Just swift """
    return [ 'swift' ]


  def _GetExtraData( self, completion ):
      location = {}
      if completion[ 'module_path' ]:
        location[ 'filepath' ] = completion[ 'module_path' ]
      if completion[ 'line' ]:
        location[ 'line_num' ] = completion[ 'line' ]
      if completion[ 'column' ]:
        location[ 'column_num' ] = completion[ 'column' ] + 1

      if location:
        extra_data = {}
        extra_data[ 'location' ] = location
        return extra_data
      else:
        return None


  def FlagsForFile(self, filename):
    try:
      return self._flags_for_file[ filename ]
    except KeyError: pass

    abs_filename = os.path.abspath(filename)
    module = extra_conf_store.ModuleForSourceFile( filename )
    if not module or not module.FlagsForSwift: return [abs_filename]

    response = module.FlagsForSwift( filename )
    flags = response['flags']
    if abs_filename not in flags: flags = [abs_filename] + flags
    if response.get('do_cache', True): self._flags_for_file[filename] = flags
    return flags

  def RequestDataExtract(self, request_data, current=False):
      filename = request_data[ 'filepath' ]
      if not filename: return

      file_contents = utils.SplitLines( GetFileContents( request_data, filename ) )
      # 0 based line and column
      line = request_data[ 'line_num' ] - 1
      if current:
          column = request_data['column_num'] - 1
      else:
          column = request_data[ 'start_column' ] - 1
      additional_flags = self.FlagsForFile(filename)

      (source_bytes, offset) = ToBytesWithCursor(file_contents, line, column)
      return (abs_filename, source_bytes, offset, additional_flags)


  def QuickCandidates(self, request_data):
      if request_data['force_semantic'] and request_data[ 'query' ]:
          return self._big_cache
      return []

  def ComputeCandidatesInner( self, request_data ):
      data = self.RequestDataExtract(request_data)
      if data is None: return []

      output = self.request("source.request.codecomplete", {
          "key.sourcefile" : data[0],
          "key.sourcetext" : utils.ToUnicode( data[1] ),
          "key.offset" : data[2],
          "key.compilerargs" : data[3],
      } )
      if not output: return []

      completions = [ responses.BuildCompletionData(
        completion['key.name'],
        completion.get('key.typename'),
        detailed_info = completion.get('key.doc.brief'),
        menu_text     = completion.get('key.description'),
        kind          = KindFromKittenKind(completion.get('key.kind')),
        extra_data    = { 'template' : completion.get('key.sourcetext') }
      ) for completion in json.loads( output )["key.results"] ]
      # cache for QuickCandidates when big than 1M
      if len(output) > 1e6 :
          self._logger.debug("swift cache %d", len(output))
          self._big_cache = completions
      return completions



  def request(self, name, requestObject):
      request  = json.dumps(requestObject, ensure_ascii=False)
      request = "{key.request: " + name + "," + request[1:]
      self._logger.debug("swift request: %s", request)
      cmd = [self._sourcekitten_binary_path, 'request', '--yaml', request]
      handle = utils.SafePopen(
          cmd,
          stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE,
          universal_newlines = True)
      stdoutdata, stderrdata = handle.communicate()
      if handle.returncode != 0:
          self._logger.error(stdoutdata + stderrdata)
          return
      stdoutdata = ToUnicode(stdoutdata)
      self._logger.debug("swift %s response: %s", name, stdoutdata)
      return stdoutdata



  def GetSubcommandsMap( self ):
    return {
        'GetType' : SwiftCompleter.GetType,
        'GetDoc'  : SwiftCompleter.GetDoc,
        'GoTo'    : SwiftCompleter.GoTo,
    }

  def CursorRequest(self, request_data):
      data = self.RequestDataExtract(request_data, current=True)
      if data is None: return

      output = self.request("source.request.cursorinfo", {
          "key.sourcefile" : data[0],
          "key.sourcetext" : utils.ToUnicode( data[1] ),
          "key.offset" : data[2],
          "key.compilerargs" : data[3],
      } )
      if not output: return
      return json.loads(output)


  def GetType(self, request_data, args):
      cursorInfo = self.CursorRequest(request_data)
      if not cursorInfo: return

      return responses.BuildDisplayMessageResponse( ToUnicode(cursorInfo["key.typename"]) )

  def GetDoc(self, request_data, args):
      cursorInfo = self.CursorRequest(request_data)
      if not cursorInfo: return

      from xml.etree import ElementTree
      def textFromKey(key, tags):
          try:
              root = ElementTree.fromstring( cursorInfo[key] )
              def textInTag(t):
                  declaration = root.find( t ) if root.tag != t else root
                  return "".join(declaration.itertext()) if declaration is not None else ""
              return [ textInTag(t) for t in tags ]
          except:
              return [""] * len(tags)

      brief, full = textFromKey("key.doc.full_as_xml", ('Abstract', 'Discussion'))
      decl = textFromKey("key.annotated_decl", ["Declaration"])[0]

      return responses.BuildDetailedInfoResponse(
          '{filepath}:+{offset}\n{decl}\n\n{brief}\n\n{discuss}'.format(
              filepath = cursorInfo.get("key.filepath", "module"),
              offset = cursorInfo.get("key.offset", 0),
              decl = decl,
              brief = brief,
              discuss = full,
          ))

  def GoTo(self, request_data, args):
      cursorInfo = self.CursorRequest(request_data)
      if not cursorInfo: return

      if 'key.filepath' not in cursorInfo:
          return responses.BuildDisplayMessageResponse("goto module entity is not support yet!")
      
      return {
          'filepath': cursorInfo['key.filepath'],
          'byte_offset': cursorInfo['key.offset']
      }


def ToBytesWithCursor(file_contents, line, column):
    offset = column
    with BytesIO() as f:
        if line > 0:
            f.write( utils.ToBytes( "\n".join(file_contents[:line]) ) )
            f.write( b"\n" )
            offset += f.tell()
            f.write( utils.ToBytes( "\n".join(file_contents[line:]) ) )
            f.write( b"\n" )
            f.flush()
            return (f.getvalue(), offset)

def KindFromKittenKind(sourcekind):
      return {
          "source.lang.swift.decl.class"                    : "CLASS",
          "source.lang.swift.decl.enum"                     : "ENUM",    # enum type
          "source.lang.swift.decl.enumelement"              : "ENUMELEMENT",    # enum element
          "source.lang.swift.decl.function.free"            : "FUNCTION",
          "source.lang.swift.decl.function.method.instance" : "METHOD",
          "source.lang.swift.decl.function.method.class"    : "METHOD",
          "source.lang.swift.decl.protocol"                 : "PROTOCOL",
          "source.lang.swift.decl.struct"                   : "STRUCT",
          "source.lang.swift.decl.typealias"                : "ALIAS",
          "source.lang.swift.decl.var.global"               : "VARIABLE",
          "source.lang.swift.decl.var.instance"             : "VARIABLE",
          "source.lang.swift.decl.var.class"                : "VARIABLE",
          "source.lang.swift.decl.var.local"                : "IDENTIFIER",
          "source.lang.swift.keyword"                       : "KEYWORD",
          "source.lang.swift.literal.color"                 : "LITERALCOLOR",
          "source.lang.swift.literal.image"                 : "LITERALIMAGE",
      }.get(sourcekind, 'UNKNOWN')
