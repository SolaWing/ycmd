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

    module = extra_conf_store.ModuleForSourceFile( filename )
    if not module or not module.FlagsForSwift: return []

    response = module.FlagsForSwift( filename )
    flags = response['flags']
    if response.get('do_cache', True): self._flags_for_file[filename] = flags
    return flags

  def QuickCandidates(self, request_data):
      return self._big_cache


  def ComputeCandidatesInner( self, request_data ):
      filename = request_data[ 'filepath' ]
      if not filename: return

      file_contents = utils.SplitLines( GetFileContents( request_data, filename ) )
      # 0 based line and column
      line = request_data[ 'line_num' ] - 1
      column = request_data[ 'start_column' ] - 1
      offset = column
      additional_flags = self.FlagsForFile(filename)

      with NamedTemporaryFile(suffix=".swift") as f:
          f.write( utils.ToBytes( "\n".join(file_contents[:line]) ) )
          f.write( b"\n" )
          offset += f.tell()
          f.write( utils.ToBytes( "\n".join(file_contents[line:]) ) )
          f.write( b"\n" )
          f.flush()

          cmd = [self._sourcekitten_binary_path,
                 'complete', '--file', f.name, '--offset', str(offset),
                 '--'] + additional_flags
          self._logger.debug("swift request[%d:%d]: %s", line, column, utils.JoinLinesAsUnicode(cmd))
          phandle = utils.SafePopen(
            cmd,# cwd = "/Users/wang/Desktop/feng/ifengnwsphone/newProject/",
            stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE,
            universal_newlines = True,
          )
          stdoutdata, stderrdata = phandle.communicate()
          if phandle.returncode != 0:
              self._logger.error(stdoutdata + stderrdata)
              return
          stdoutdata = ToUnicode(stdoutdata)
          self._logger.debug("swift response[%d:%d]: %s", line, column, stdoutdata)
      completions = [ responses.BuildCompletionData(
        completion['name'],
        completion.get('typeName'),
        detailed_info = completion.get('docBrief'),
        menu_text = completion.get('descriptionKey'),
        kind = self._kindFromKittenKind(completion.get('kind')),
        extra_data = { 'template' : completion.get('sourcetext') }
      ) for completion in json.loads( stdoutdata ) ]
      # cache for QuickCandidates when big than 1M
      if len(stdoutdata) > 1e6 : self._big_cache = completions
      return completions

  def _kindFromKittenKind(self, sourcekind):
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


  def GetSubcommandsMap( self ):
    return {
      #  'GoToDefinition' : ( lambda self, request_data, args:
      #                       self._GoToDefinition( request_data ) ),
      #  'GoToDeclaration': ( lambda self, request_data, args:
      #                       self._GoToDeclaration( request_data ) ),
      #  'GoTo'           : ( lambda self, request_data, args:
      #                       self._GoTo( request_data ) ),
      #  'GetDoc'         : ( lambda self, request_data, args:
      #                       self._GetDoc( request_data ) ),
      #  'GoToReferences' : ( lambda self, request_data, args:
      #                       self._GoToReferences( request_data ) ),
      #  'StopServer'     : ( lambda self, request_data, args:
      #                       self.Shutdown() ),
      #  'RestartServer'  : ( lambda self, request_data, args:
      #                       self.RestartServer( *args ) )
    }


  #  def _GoToDefinition( self, request_data ):
  #    definitions = self._GetDefinitionsList( '/gotodefinition',
  #                                            request_data )
  #    if not definitions:
  #      raise RuntimeError( 'Can\'t jump to definition.' )
  #    return self._BuildGoToResponse( definitions )


  #  def _GoToDeclaration( self, request_data ):
  #    definitions = self._GetDefinitionsList( '/gotoassignment',
  #                                            request_data )
  #    if not definitions:
  #      raise RuntimeError( 'Can\'t jump to declaration.' )
  #    return self._BuildGoToResponse( definitions )


  #  def _GoTo( self, request_data ):
  #    try:
  #      return self._GoToDefinition( request_data )
  #    except Exception as e:
  #      self._logger.exception( e )
  #      pass

  #    try:
  #      return self._GoToDeclaration( request_data )
  #    except Exception as e:
  #      self._logger.exception( e )
  #      raise RuntimeError( 'Can\'t jump to definition or declaration.' )


  #  def _GetDoc( self, request_data ):
  #    try:
  #      definitions = self._GetDefinitionsList( '/gotodefinition',
  #                                              request_data )
  #      return self._BuildDetailedInfoResponse( definitions )
  #    except Exception as e:
  #      self._logger.exception( e )
  #      raise RuntimeError( 'Can\'t find a definition.' )


  #  def _GoToReferences( self, request_data ):
  #    definitions = self._GetDefinitionsList( '/usages', request_data )
  #    if not definitions:
  #      raise RuntimeError( 'Can\'t find references.' )
  #    return self._BuildGoToResponse( definitions )


  #  def _GetDefinitionsList( self, handler, request_data ):
  #    try:
  #      response = self._GetResponse( handler, request_data )
  #      return response[ 'definitions' ]
  #    except Exception as e:
  #      self._logger.exception( e )
  #      raise RuntimeError( 'Cannot follow nothing. '
  #                          'Put your cursor on a valid name.' )


  #  def _BuildGoToResponse( self, definition_list ):
  #    if len( definition_list ) == 1:
  #      definition = definition_list[ 0 ]
  #      if definition[ 'in_builtin_module' ]:
  #        if definition[ 'is_keyword' ]:
  #          raise RuntimeError( 'Cannot get the definition of Python keywords.' )
  #        else:
  #          raise RuntimeError( 'Builtin modules cannot be displayed.' )
  #      else:
  #        return responses.BuildGoToResponse( definition[ 'module_path' ],
  #                                            definition[ 'line' ],
  #                                            definition[ 'column' ] + 1 )
  #    else:
  #      # multiple definitions
  #      defs = []
  #      for definition in definition_list:
  #        if definition[ 'in_builtin_module' ]:
  #          defs.append( responses.BuildDescriptionOnlyGoToResponse(
  #                       'Builtin ' + definition[ 'description' ] ) )
  #        else:
  #          defs.append(
  #            responses.BuildGoToResponse( definition[ 'module_path' ],
  #                                         definition[ 'line' ],
  #                                         definition[ 'column' ] + 1,
  #                                         definition[ 'description' ] ) )
  #      return defs


  #  def _BuildDetailedInfoResponse( self, definition_list ):
  #    docs = [ definition[ 'docstring' ] for definition in definition_list ]
  #    return responses.BuildDetailedInfoResponse( '\n---\n'.join( docs ) )


  #  def DebugInfo( self, request_data ):
  #    with self._server_lock:
  #      jedihttp_server = responses.DebugInfoServer(
  #        name = 'JediHTTP',
  #        handle = self._jedihttp_phandle,
  #        executable = PATH_TO_JEDIHTTP,
  #        address = '127.0.0.1',
  #        port = self._jedihttp_port,
  #        logfiles = [ self._logfile_stdout, self._logfile_stderr ] )

  #      python_interpreter_item = responses.DebugInfoItem(
  #        key = 'Python interpreter',
  #        value = self._sourcekitten_binary_path )

  #      return responses.BuildDebugInfoResponse(
  #        name = 'Python',
  #        servers = [ jedihttp_server ],
  #        items = [ python_interpreter_item ] )
