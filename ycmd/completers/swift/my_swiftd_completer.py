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
from io import BytesIO

import json
import logging
from subprocess import PIPE
import sys
import os
import threading
import tempfile

_logger = logging.getLogger( __name__ )
# _logger.setLevel(logging.DEBUG)

import re
header_pattern = re.compile(rb'(\S+)\s*:\s*(\S+)')

# BINARY_NOT_FOUND_MESSAGE = ( 'The specified sourceKitten {0} ' +
#                              'was not found. Did you specify it correctly?' )
# LOGFILE_FORMAT = 'swift_{port}_{std}_'

# see: https://github.com/apple/swift/blob/master/tools/SourceKit/docs/Protocol.md
PATH_TO_SOURCEKITTEN = os.path.abspath( os.path.join(
    os.path.dirname(__file__),
    '../../..',
    'third_party/SourceKitten',
    '.build/release',
    "sourcekitten"))

def ShouldEnableSwiftCompleter():
    return os.path.exists(PATH_TO_SOURCEKITTEN)

class SwiftCompleter( Completer ):
  """
  A Completer that uses the SourceKitten.
  https://github.com/jpsim/SourceKitten
  """

  def __init__( self, user_options ):
    super().__init__( user_options )
    #  self._logfile_stdout = None
    #  self._logfile_stderr = None
    #  self._keep_logfiles = user_options[ 'server_keep_logfiles' ]
    self._flags_for_file = {}
    self._big_cache = []

    # Used to ensure that starting/stopping of the server is synchronized
    self._request_id = 0
    self._server_state_mutex = threading.RLock()
    self._server_handle = None # type: subprocess.Popen
    self._sourcekitten_binary_path = PATH_TO_SOURCEKITTEN
    self._StartServer()

  def SupportedFiletypes( self ):
    """ Just swift """
    return [ 'swift' ]

  def _StartServer(self, request_data = None):
      with self._server_state_mutex:
          if self._server_handle: return
          _logger.info( 'Starting SwiftLSP Language Server...' )
          self._server_stderr = utils.CreateLogfile( 'SwiftD_stderr_' )
          with utils.OpenForStdHandle( self._server_stderr ) as stderr:
              self._server_handle = utils.SafePopen([self._sourcekitten_binary_path, "daemon"],
                                                    stdin = PIPE, stdout = PIPE, stderr = stderr) # type: subprocess.Popen

  def _StopServer(self):
      with self._server_state_mutex:
          _logger.info( 'Shutting down SwiftLSP...' )
          if not self._ServerIsRunning():
              _logger.info( 'SwiftLSP Language server not running' )
              return
          _logger.info( 'Stopping Swift server with PID {0}'.format(
              self._server_handle.pid ) )

          try:
              self._SendNotification("end")
              self._server_handle.communicate()
          except Exception as e:
              _logger.exception( 'Error while stopping SwiftLSP server' )
          else:
              self._server_handle = None

  def _ServerIsRunning(self):
      return self._server_handle is not None

  def _RestartServer( self, request_data ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer( request_data )

  def _SendNotification(self, method, params=None):
      with self._server_state_mutex:
          r = {"method": method}
          if params: r["params"] = params

          d = json.dumps(r).encode()
          _logger.info(f"send notification len({len(d)}): {method}")
          self._writePackage(d)

  def _SendRequest(self, method, params=None):
      with self._server_state_mutex:
          self._request_id += 1
          r = {"id": self._request_id, "method": method}
          if params: r["params"] = params

          d = json.dumps(r).encode()
          _logger.debug(f"send request len({len(d)}): {d}")
          self._writePackage(d)
          #  TODO: 先同步串行, 以后可能改成根据id串行, 且需要比对id
          return self.__GetResponse()

  def _writePackage(self, data):
      self._server_handle.stdin.write(b'Content-Length:%d\r\n\r\n'%(len(data)))
      self._server_handle.stdin.write(data)
      self._server_handle.stdin.flush()

  def __GetResponse(self):
    # with self._server_state_mutex:
    headers = {}
    while True:
        line = self._server_handle.stdout.readline()
        if len(line) < 3: break

        m = header_pattern.search(line)
        if m: headers[m.group(1)] = m.group(2)

    try:
        content_length = int(headers[b'Content-Length'])
        r = json.loads( self._server_handle.stdout.read(content_length))
        error = None
        if isinstance(r, dict): error = r.get("error")
        if error:
            _logger.error(f"response error: {error}")
        else:
            _logger.debug(f"get response: {r}")
        return r
    except (KeyError, ValueError) as e:
        _logger.exception( 'Error while read package' )
        return {}

  # def _GetExtraData( self, completion ):
  #     location = {}
  #     if completion[ 'module_path' ]:
  #       location[ 'filepath' ] = completion[ 'module_path' ]
  #     if completion[ 'line' ]:
  #       location[ 'line_num' ] = completion[ 'line' ]
  #     if completion[ 'column' ]:
  #       location[ 'column_num' ] = completion[ 'column' ] + 1

  #     if location:
  #       extra_data = {}
  #       extra_data[ 'location' ] = location
  #       return extra_data
  #     else:
  #       return None

  # def OnFileReadyToParse( self, request_data ):
  #   self._StartServer( request_data )
  #   return super().OnFileReadyToParse( request_data )

  def DebugInfo( self, request_data ):
    items = []
    filename = request_data[ 'filepath' ]
    if filename:
        flags = self.FlagsForFile(filename)
        flags_item = responses.DebugInfoItem(
          key = 'flags', value = '{0}'.format( list( flags ) ) )
        filename_item = responses.DebugInfoItem(
          key = 'translation unit', value = filename )
        items.append(flags_item)
        items.append(filename_item)
    return responses.BuildDebugInfoResponse(
      name = "Swift",
      servers = [
        responses.DebugInfoServer(
          name = "Swift Language Server",
          handle = self._server_handle,
          executable = self._sourcekitten_binary_path,
          logfiles = [
            self._server_stderr,
          ],
        )
      ],
      items = items,
    )

  def FlagsForFile(self, filename):
    try:
      return self._flags_for_file[ filename ]
    except KeyError: pass

    module = extra_conf_store.ModuleForSourceFile( filename )
    if not module or not module.FlagsForSwift: return [filename]

    response = module.FlagsForSwift( filename )
    flags = response['flags']
    if filename not in flags: flags = [filename] + flags
    if response.get('do_cache', True):
        self._flags_for_file[filename] = flags
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
      return (filename, source_bytes, offset, additional_flags)


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
          _logger.debug("swift cache %d", len(output))
          self._big_cache = completions
      return completions

  def request(self, name, requestObject):
      request  = json.dumps(requestObject, ensure_ascii=False)
      # sourcekitd only support direct name, can't ecode as json string
      request = "{key.request: " + name + "," + request[1:]
      return self._SendRequest("yaml", request).get("result")

  def GetSubcommandsMap( self ):
    return {
        'GetType' : SwiftCompleter.GetType,
        'GetDoc'  : SwiftCompleter.GetDoc,
        'GoTo'    : SwiftCompleter.GoTo,
        'RestartServer': (
            lambda self, request_data, args: self._RestartServer( request_data )
        ),
    }

  def CursorRequest(self, request_data):
      return self._CursorRequest( self.RequestDataExtract(request_data, current=True) )

  def _CursorRequest(self, data):
      if data is None: return

      output = self.request("source.request.cursorinfo", {
          "key.sourcefile" : data[0],
          "key.sourcetext" : utils.ToUnicode( data[1] ),
          "key.offset" : data[2],
          "key.compilerargs" : data[3],
      } )
      if not output: return
      return json.loads(output)

  def _InterfacePath(self, moduleName):
      return os.path.join( tempfile.gettempdir(), moduleName + ".swift")

  def _ModuleVirtualName(self, moduleName):
      return self._InterfacePath(moduleName)

  def _OpenInterface(self, data, moduleName):
      if not moduleName or data is None: return
      output = self.request("source.request.editor.open.interface", {
          "key.name": self._ModuleVirtualName(moduleName),
          "key.modulename": moduleName,
          "key.compilerargs": data[3],
      })
      if not output: return
      interface = json.loads(output)
      source = interface.get("key.sourcetext")
      if source:
          with open(self._InterfacePath(moduleName), "w") as f:
              f.write(source)
      return interface

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
      data = self.RequestDataExtract(request_data, current=True)
      cursorInfo = self._CursorRequest(data)
      if not cursorInfo: return

      if 'key.filepath' not in cursorInfo:
          moduleName = cursorInfo.get('key.modulename')
          # open module and goto
          interface = self._OpenInterface(data, moduleName)
          if interface:
              filepath = self._InterfacePath(moduleName)
              offset = 0

              usr = cursorInfo.get('key.usr')
              if usr:
                  output = self.request("source.request.editor.find_usr", {
                      "key.usr": usr,
                      "key.sourcefile": self._ModuleVirtualName(moduleName)
                  })
                  if output:
                      r = json.loads(output)
                      offset = r.get("key.offset", 0)
              return {
                  'filepath': filepath,
                  'byte_offset': offset
              }
          return responses.BuildDisplayMessageResponse("error in goto symbol, please see logs for detail")

      return {
          'filepath': cursorInfo['key.filepath'],
          'byte_offset': cursorInfo['key.offset']
      }


def ToBytesWithCursor(file_contents, line, column):
    assert line >= 0
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
