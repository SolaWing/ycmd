#!/usr/bin/env python
#
# Copyright (C) 2011, 2012  Stephen Sugden <me@stephensugden.com>
#                           Google Inc.
#                           Stanislav Golovanov <stgolovanov@gmail.com>
#
# This file is part of YouCompleteMe.
#
# YouCompleteMe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# YouCompleteMe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with YouCompleteMe.  If not, see <http://www.gnu.org/licenses/>.

from ycmd.utils import ToUtf8IfNeeded
from ycmd.completers.completer import Completer
from ycmd import responses

try:
  import jedi
except ImportError:
  raise ImportError(
    'Error importing jedi. Make sure the jedi submodule has been checked out. '
    'In the YouCompleteMe folder, run "git submodule update --init --recursive"')


class JediCompleter( Completer ):
  """
  A Completer that uses the Jedi completion engine.
  https://jedi.readthedocs.org/en/latest/
  """

  def __init__( self, user_options ):
    super( JediCompleter, self ).__init__( user_options )
    self.in_query = False

  def SupportedFiletypes( self ):
    """ Just python """
    return [ 'python' ]

  def ShouldUseNow(self, request_data):
    # NOTE almost equal to super, except when cache is invalid, return False if self.in_query
    if not self.ShouldUseNowInner( request_data ):
      self._completions_cache.Invalidate()
      return False

    # We have to do the cache valid check and get the completions as part of one
    # call because we have to ensure a different thread doesn't change the cache
    # data.
    cache_completions = self._completions_cache.GetCompletionsIfCacheValid(
        request_data[ 'line_num' ],
        request_data[ 'start_column' ] )

    # If None, then the cache isn't valid and we know we should return true
    if cache_completions is None:
      return not self.in_query
    else:
      previous_results_were_valid = bool( cache_completions )
      return previous_results_were_valid


  def _GetJediScript( self, request_data ):
      filename = request_data[ 'filepath' ]
      contents = request_data[ 'file_data' ][ filename ][ 'contents' ]
      line = request_data[ 'line_num' ]
      # Jedi expects columns to start at 0, not 1
      column = request_data[ 'column_num' ] - 1

      return jedi.Script( contents, line, column, filename )


  def _GetExtraData( self, completion ):
      location = {}
      if completion.module_path:
        location[ 'filepath' ] = ToUtf8IfNeeded( completion.module_path )
      if completion.line:
        location[ 'line_num' ] = completion.line
      if completion.column:
        location[ 'column_num' ] = completion.column + 1

      if location:
        extra_data = {}
        extra_data[ 'location' ] = location
        return extra_data
      else:
        return None


  def ComputeCandidatesInner( self, request_data ):
    self.in_query = True
    script = self._GetJediScript( request_data )
    completions = script.completions()
    self.in_query = False
    return [ responses.BuildCompletionData(
                ToUtf8IfNeeded( completion.name ),
                ToUtf8IfNeeded( completion.description ),
                ToUtf8IfNeeded( completion.docstring() ),
                extra_data = self._GetExtraData( completion ) )
             for completion in script.completions() ]

  def DefinedSubcommands( self ):
    return [ 'GoToDefinition',
             'GoToDeclaration',
             'GoTo' ]


  def OnUserCommand( self, arguments, request_data ):
    if not arguments:
      raise ValueError( self.UserCommandsHelpMessage() )

    command = arguments[ 0 ]
    if command == 'GoToDefinition':
      return self._GoToDefinition( request_data )
    elif command == 'GoToDeclaration':
      return self._GoToDeclaration( request_data )
    elif command == 'GoTo':
      return self._GoTo( request_data )
    raise ValueError( self.UserCommandsHelpMessage() )


  def _GoToDefinition( self, request_data ):
    definitions = self._GetDefinitionsList( request_data )
    if definitions:
      return self._BuildGoToResponse( definitions )
    else:
      raise RuntimeError( 'Can\'t jump to definition.' )


  def _GoToDeclaration( self, request_data ):
    definitions = self._GetDefinitionsList( request_data, declaration = True )
    if definitions:
      return self._BuildGoToResponse( definitions )
    else:
      raise RuntimeError( 'Can\'t jump to declaration.' )


  def _GoTo( self, request_data ):
    definitions = ( self._GetDefinitionsList( request_data ) or
        self._GetDefinitionsList( request_data, declaration = True ) )
    if definitions:
      return self._BuildGoToResponse( definitions )
    else:
      raise RuntimeError( 'Can\'t jump to definition or declaration.' )


  def _GetDefinitionsList( self, request_data, declaration = False ):
    definitions = []
    script = self._GetJediScript( request_data )
    try:
      if declaration:
        definitions = script.goto_assignments()
      else:
        definitions = script.goto_definitions()
    except jedi.NotFoundError:
      raise RuntimeError(
                  'Cannot follow nothing. Put your cursor on a valid name.' )

    return definitions


  def _BuildGoToResponse( self, definition_list ):
    if len( definition_list ) == 1:
      definition = definition_list[ 0 ]
      if definition.in_builtin_module():
        if definition.is_keyword:
          raise RuntimeError(
                  'Cannot get the definition of Python keywords.' )
        else:
          raise RuntimeError( 'Builtin modules cannot be displayed.' )
      else:
        return responses.BuildGoToResponse( definition.module_path,
                                            definition.line,
                                            definition.column + 1 )
    else:
      # multiple definitions
      defs = []
      for definition in definition_list:
        if definition.in_builtin_module():
          defs.append( responses.BuildDescriptionOnlyGoToResponse(
                       'Builtin ' + definition.description ) )
        else:
          defs.append(
            responses.BuildGoToResponse( definition.module_path,
                                         definition.line,
                                         definition.column + 1,
                                         definition.description ) )
      return defs

