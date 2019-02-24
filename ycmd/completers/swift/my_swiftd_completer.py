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

from ycm_core import DiffString
from ycmd.utils import ToBytes, ToUnicode, LineColumnFromByteOffset, ProcessIsRunning
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
_logger.setLevel(logging.DEBUG)

import re
import time
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
    self.max_diagnostics_to_display = user_options[ 'max_diagnostics_to_display' ]
    self._flags_for_file = {}
    self._big_cache = []
    self._source_repository = {}
    self._open_modules = {}

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
              self._server_handle = utils.SafePopen(
                  [self._sourcekitten_binary_path, "daemon"],
                  env = ({"SOURCEKIT_LOGGING": "3"} if _logger.level == logging.DEBUG else None),
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
    if not module or not hasattr(module, 'FlagsForSwift'): return [filename]

    response = module.FlagsForSwift( filename )
    flags = response['flags']
    if response.get('do_cache', True):
        self._flags_for_file[filename] = flags
    return flags

  def RequestDataExtract(self, request_data, current=False):
      filename = request_data[ 'filepath' ]
      if not filename: return

      contents = GetFileContents( request_data, filename )
      # 1 based line and column
      line = request_data[ 'line_num' ]
      if current:
          column = request_data['column_num']
      else:
          column = request_data[ 'start_column' ]
      additional_flags = self.FlagsForFile(filename)

      offset = len(utils.ToBytes(contents[:LineOffsetInStr(contents, line)])) + column - 1
      return (filename, contents, offset, additional_flags)

  def OnFileReadyToParse( self, request_data ):
    filename = request_data[ 'filepath' ]
    if not filename: return
    # 限制不要重复编译
    contents = GetFileContents( request_data, filename )
    with self._server_state_mutex:
        file_state = self._source_repository.get(filename)
        if file_state is None:
            if filename in self._open_modules:
                return # module file 不需要编译, rare cause delay in rare execute branch
            file_state = {'parse_id': 0, 'last_contents': contents}
            self._source_repository[filename] = file_state

            output = self.request("source.request.editor.open", {
                "key.sourcefile": filename,
                "key.name": filename,
                "key.sourcetext": contents,
                "key.compilerargs": self.FlagsForFile(filename),
                "key.enablesyntaxmap": 0,
                "key.enablesubstructure": 0
            }) # type: dict
            if output is None: _logger.warn("editor open error!"); return
        else:
            diff = DiffString(file_state['last_contents'], contents)
            file_state['last_contents'] = contents
            file_state['parse_id'] += 1
            file_state.pop('last_diag', None)
            output = self.request("source.request.editor.replacetext", {
                "key.sourcefile": filename,
                "key.name": filename,
                "key.offset": diff[0],
                "key.length": diff[1],
                "key.sourcetext": diff[2],
            })
            if output is None: _logger.warn("editor open error!"); return
        parse_id = file_state['parse_id']

    diag = output.get("key.diagnostics")
    c = 0
    while not diag and output.get("key.diagnostic_stage") == "source.diagnostic.stage.swift.parse":
        if c > 5: _logger.warn("get diag timeout!"); return
        time.sleep(1)
        c += 1
        if file_state['parse_id'] != parse_id: # new request, ignore old loop query
            return

        output = self.request("source.request.editor.replacetext", {
            "key.sourcefile": filename,
            "key.name": filename,
            "key.offset": 0,
            "key.length": 0,
            "key.sourcetext": "",
        })
        if output is None: _logger.warn("get diag error!"); return
        diag = output.get("key.diagnostics")

    if not diag: return
    bytes_contents = utils.ToBytes(contents)
    diag = list(filter(bool, map(lambda d: ConvertToYCMDDiag(d, bytes_contents), diag)))
    _logger.debug("%d diags", len(diag))
    with self._server_state_mutex:
        if file_state['parse_id'] == parse_id: # no changes, save last diag
            file_state['last_diag'] = diag

    return responses.BuildDiagnosticResponse(diag, filename, self.max_diagnostics_to_display)

  def OnBufferUnload( self, request_data ):
    filename = request_data[ 'filepath' ]
    if not filename: return
    with self._server_state_mutex:
        if filename in self._open_modules: return
        file_state = self._source_repository.pop(filename, None)
        if file_state: file_state['parse_id'] += 1 # cancel waiting parsing
        self.request("source.request.editor.close", {
            "key.sourcefile": filename,
            "key.name": filename,
        })

  def QuickCandidates(self, request_data):
      if request_data['force_semantic'] and request_data[ 'query' ]:
          return self._big_cache
      return []

  def ComputeCandidatesInner( self, request_data ):
      data = self.RequestDataExtract(request_data)
      if data is None: return []

      output = self.request("source.request.codecomplete", {
          "key.sourcefile" : data[0],
          "key.sourcetext" : data[1],
          "key.offset" : data[2],
          "key.compilerargs" : data[3],
      } )
      if output is None: return []

      completions = [ responses.BuildCompletionData(
        completion['key.name'],
        completion.get('key.typename'),
        detailed_info = completion.get('key.doc.brief'),
        menu_text     = completion.get('key.description'),
        kind          = KindFromKittenKind(completion.get('key.kind')),
        extra_data    = { 'template' : completion.get('key.sourcetext') }
      ) for completion in output["key.results"] ]
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
        'FixIt' : SwiftCompleter.Fixit,
        'DocComment': SwiftCompleter.DocComment,
    }

  def CursorRequest(self, request_data):
      return self._CursorRequest( self.RequestDataExtract(request_data, current=True) )

  def _CursorRequest(self, data):
      if data is None: return

      return self.request("source.request.cursorinfo", {
          "key.sourcefile" : data[0],
          "key.sourcetext" : data[1],
          "key.offset" : data[2],
          "key.compilerargs" : data[3],
      } )

  def _InterfacePath(self, moduleName):
      return os.path.realpath(os.path.join( tempfile.gettempdir(), moduleName + ".swift"))

  def _ModuleVirtualName(self, moduleName):
      return self._InterfacePath(moduleName)

  def _OpenInterface(self, data, moduleName):
      """
      :return bool: 是否打开成功
      """
      if not moduleName or data is None: return
      filename = self._InterfacePath(moduleName)
      if filename in self._open_modules: return True # already open, don't need to reopen

      interface = self.request("source.request.editor.open.interface", {
          "key.name": self._ModuleVirtualName(moduleName),
          "key.modulename": moduleName,
          "key.compilerargs": data[3],
      })
      if interface is None: return
      source = interface.get("key.sourcetext")
      if source:
          with open(filename, "w") as f:
              f.write(source)
          # with open(filename+"raw", "w") as f:
          #     f.write(output) # cache the openInterface output, since recall open interface is slow
          self._open_modules[filename] = data[3]
          self._flags_for_file[filename] = data[3] # use same compile flags as open args
      return interface

  def GetType(self, request_data, args):
      cursorInfo = self.CursorRequest(request_data)
      if not cursorInfo: return

      typename = ToUnicode(cursorInfo.get("key.typename", "UNKNOWN"))
      return responses.BuildDisplayMessageResponse( typename )

  def GetDoc(self, request_data, args):
      cursorInfo = self.CursorRequest(request_data)
      if not cursorInfo: return

      from xml.etree import ElementTree
      def textInTag(root, t):
          if root is None: return ""
          declaration = root.find( t ) if root.tag != t else root
          return "".join(declaration.itertext()) if declaration is not None else ""

      def XMLFrom(key):
          try: return ElementTree.fromstring( cursorInfo[key] )
          except: return None

      v = {}
      v['Declaration'] = textInTag(XMLFrom('key.annotated_decl'), 'Declaration')
      doc = XMLFrom('key.doc.full_as_xml')
      if doc:
          CommentParts = doc.find('CommentParts')
          if CommentParts:
              v['Abstract'] = textInTag(CommentParts, 'Abstract')
              v['Discussion'] = textInTag(CommentParts, 'Discussion')
              v['Parameters'] = CommentParts.find('Parameters')
              v['ResultDiscussion'] = textInTag(CommentParts, 'ResultDiscussion')
          else:
              v['Abstract'] = textInTag(doc, 'Abstract')
              v['Discussion'] = textInTag(doc, 'Discussion')

      lines = ['{filepath}:+{offset}'.format(
          filepath = cursorInfo.get("key.filepath", "module"),
          offset = cursorInfo.get("key.offset", 0)
      ), v['Declaration']]

      t = v.get('Abstract')
      if t: lines.append(''); lines.append(t)
      t = v.get('Discussion')
      if t: lines.append(''); lines.append(t)
      t = v.get('Parameters')
      if t:
          lines.append(''); lines.append("Parameters:")
          for p in t.findall('Parameter'):
              lines.append("- {name}: {desc}".format(name=textInTag(p, 'Name'), desc=textInTag(p, 'Discussion')))
      t = v.get('ResultDiscussion')
      if t: lines.append(''); lines.append("Returns: " + t)

      return responses.BuildDetailedInfoResponse( os.linesep.join(lines) )

  def GoTo(self, request_data, args):
      data = self.RequestDataExtract(request_data, current=True)
      cursorInfo = self._CursorRequest(data)
      if not cursorInfo: return

      if 'key.filepath' not in cursorInfo:
          moduleName = cursorInfo.get('key.modulename')
          # open module and goto
          opened = self._OpenInterface(data, moduleName)
          if opened:
              filepath = self._InterfacePath(moduleName)
              offset = 0

              usr = cursorInfo.get('key.usr')
              if usr:
                  output = self.request("source.request.editor.find_usr", {
                      "key.usr": usr,
                      "key.sourcefile": self._ModuleVirtualName(moduleName)
                  })
                  if output is not None:
                      offset = output.get("key.offset", 0)
              return {
                  'filepath': filepath,
                  'byte_offset': offset
              }
          return responses.BuildDisplayMessageResponse("error in goto symbol, please see logs for detail")

      return {
          'filepath': cursorInfo['key.filepath'],
          'byte_offset': cursorInfo['key.offset']
      }

  def DocComment(self, request_data, args):
      cursorInfo = self.CursorRequest(request_data)
      if not cursorInfo: return
      line = request_data[ 'line_num' ]
      filename = request_data[ 'filepath' ]
      line_value = request_data['line_value'] # type: str
      indent = len(line_value) - len(line_value.lstrip())
      prefix = indent * " " + "///"

      from xml.etree import ElementTree
      root = ElementTree.fromstring( cursorInfo['key.fully_annotated_decl'] )
      if root.tag.startswith('decl.function'):
          def yieldArgs():
              for i in root.iterfind("decl.var.parameter"):
                  name = i.find("decl.var.parameter.name")
                  # bool(Element) return false for empty child
                  if name is None: name = i.find("decl.var.parameter.argument_label")
                  if name is None: continue
                  yield "".join(name.itertext())
          args = list(yieldArgs())
          text = [" Description"]
          if len(args) > 0:
              text.append("")
              text.append(" - Parameters:")
              text.extend("   - %s: "%(i) for i in args)
          text.append(' - Returns: ')
          text = "".join("".join((prefix, i, os.linesep)) for i in text)
      else:
          text = prefix + os.linesep # simply add at top line
      start = responses.Location(line, 1, filename)
      return responses.BuildFixItResponse(
          [responses.FixIt(
              start,
              [responses.FixItChunk(text, responses.Range(start, start))]
          )]
      )

  def Fixit(self, request_data, args):
    filename = request_data[ 'filepath' ]
    contents = GetFileContents( request_data, filename )

    line = request_data[ 'line_num' ]
    column = request_data[ 'column_num' ]
    location = responses.Location(line, column, filename)

    with self._server_state_mutex:
        file_state = self._source_repository.get(filename)
        if file_state is None: return
        if file_state['last_contents'] != contents: # force reparse
            self.OnFileReadyToParse(request_data)
        diag = file_state.get('last_diag')
        if diag is None: return
        for fixits in (d.fixits_ for d in diag
                       if d.fixits_ and LocationInRange(location, d.location_extent_) ):
            return responses.BuildFixItResponse(fixits)
        # no accurate column match, try only line match
        for fixits in (d.fixits_ for d in diag
                       if d.fixits_ and LocationLineInRange(location, d.location_extent_) ):
            return responses.BuildFixItResponse(fixits)
        return

def LocationInRange(location, location_range):
    """ return true if location in location_range """
    if location.filename_ != location_range.start_.filename_: return False
    after_start = (location.line_number_ > location_range.start_.line_number_ or
                   (location.line_number_ == location_range.start_.line_number_ and
                    location.column_number_ >= location_range.start_.column_number_))
    before_end = (location.line_number_ < location_range.end_.line_number_ or
                  (location.line_number_ == location_range.end_.line_number_ and
                   location.column_number_ < location_range.end_.column_number_))
    return after_start and before_end

def LocationLineInRange(location, location_range):
    """return true is location's line no in location_range, column may not in location_range"""
    if location.filename_ != location_range.start_.filename_: return False
    after_start = location.line_number_ >= location_range.start_.line_number_
    before_end = location.line_number_ <= location_range.end_.line_number_
    return after_start and before_end

def BuildRangeFromOffset(name, bytes_contents, offset, length):
    start = LineColumnFromByteOffset(bytes_contents, offset)
    end = LineColumnFromByteOffset(bytes_contents[offset:], length) # don't recount lines
    if end[0] == 1:
        end = (start[0], start[1] + end[1] - 1)
    else:
        end = (start[0] + end[0] - 1, end[1])
    return responses.Range( responses.Location(*start, name),
                            responses.Location(*end, name) )

def ConvertFixit(location, desc, chunks, bytes_contents):
    if not chunks: return None
    chunks = [responses.FixItChunk(c["key.sourcetext"],
                                   BuildRangeFromOffset(location.filename_, bytes_contents,
                                                        c["key.offset"], c["key.length"]))
              for c in chunks]
    return responses.FixIt( location, chunks, desc )

def LocationFromDiag(sourcekit_diag):
    path = sourcekit_diag.get("key.filepath")
    line = sourcekit_diag.get("key.line")
    if not path or not line: return None
    column = sourcekit_diag.get("key.column", 1)
    return responses.Location(line, column, path)


def ConvertToYCMDDiag(sourcekit_diag, bytes_contents):
    start = LocationFromDiag(sourcekit_diag)
    if start is None: return
    try:
        length = sourcekit_diag["key.ranges"][0]["key.length"]
    except Exception as e:
        _logger.debug("get ranges error: %s", e)
        length = 1
    end = responses.Location(start.line_number_, start.column_number_+length, start.filename_)
    r = responses.Range(start, end)

    fixits = []
    f = ConvertFixit(start, "", sourcekit_diag.get("key.fixits"), bytes_contents)
    if f: fixits.append(f)
    
    for subdiag in sourcekit_diag.get("key.diagnostics", []):
        l = LocationFromDiag(subdiag)
        f = ConvertFixit(l, subdiag.get("key.description",""), subdiag.get("key.fixits"), bytes_contents)
        if f: fixits.append(f)

    #  TODO: swiftc compiler args #
    return responses.Diagnostic(
        ranges = [r],
        location = r.start_,
        location_extent = r,
        text = sourcekit_diag.get("key.description"),
        kind = DiagTypeFromKitten(sourcekit_diag.get("key.severity")),
        fixits = fixits
    )

# return 0 if line overflow
def LineOffsetInStr(file_contents, line):
    i = -1
    while line > 1:
        i = file_contents.find("\n", i + 1)
        if i < 0: return 0
        line -= 1
    return i + 1

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

def DiagTypeFromKitten(sourcekind):
    return {
        "source.diagnostic.severity.note": "INFORMATION",
        "source.diagnostic.severity.warning": "WARNING",
        "source.diagnostic.severity.error": "ERROR"
    }.get(sourcekind)

