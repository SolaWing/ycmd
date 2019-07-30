# Copyright (C) 2015-2018 ycmd contributors
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
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

import logging
import os
import re
from ycmd import responses, utils
from ycmd.utils import LOGGER
from ycmd.completers.language_server.simple_language_server_completer import (
    SimpleLSPCompleter )


LOGFILE_FORMAT = 'rubyls_'
PROJECT_ROOT_FILES = [
  'Gemfile',
  '.solargraph.yml',
]


def ShouldEnableCompleter():
    return FindExecutable()


def FindExecutable():
    for path in [os.path.join(os.path.dirname(__file__),
                              '../../..',
                              'third_party/solargraph/main.rb'),
                 'solargraph',
                 os.path.expanduser( '~/.rbenv/shims/solargraph' ) ]:
        solargraph = utils.FindExecutable( path )
        if solargraph:
            return solargraph


def _UseBundler(project_dir):
    lock = os.path.join(project_dir, 'Gemfile.lock')
    if os.path.isfile(lock):
        with open(lock) as f:
            return any('solargraph ' in line for line in f)
    return False


class RubyCompleter( SimpleLSPCompleter ):
  def __init__( self, user_options ):
    super( RubyCompleter, self ).__init__( user_options )

    self._command_line = None
    self._use_bundler = None

  def GetProjectRootFiles( self ):
    return PROJECT_ROOT_FILES


  def GetServerName( self ):
    return 'RubyCompleter'


  def GetCommandLine( self ):
    return self._command_line


  def SupportedFiletypes( self ):
    return [ 'ruby' ]

  def Language( self ):
      return "ruby"

  def GetCustomSubcommands( self ):
    return {
      # Handled by us
      'RestartServer': (
        lambda self, request_data, args: self._RestartServer( request_data )
      ),
      'GetDoc': (
        lambda self, request_data, args: self.GetDoc( request_data )
      ),
      'GetType': (
        lambda self, request_data, args: self.GetType( request_data )
      )
    }

  def ExtraDebugItems( self, request_data ):
    return [
      responses.DebugInfoItem( 'bundler', self._use_bundler )
    ]

  def PopenKwargs( self ):
    return { 'cwd': self._project_directory }

  def StartServer( self, request_data ):
    with self._server_state_mutex:
      lang_server_bin = FindExecutable()
      if not lang_server_bin:
        return False
      self._bin = lang_server_bin
      self._project_directory = self.GetProjectDirectory( request_data, None)
      self._use_bundler = _UseBundler(self._project_directory)
      if self._use_bundler:
          self._command_line = ['bundle', 'exec', lang_server_bin, "stdio"]
      else:
          self._command_line = [lang_server_bin, "stdio"]
      self._settings['logLevel'] = self._ServerLoggingLevel
      # self._settings['logLevel'] = 'debug'

      return super().StartServer(request_data)

  # def _ShouldResolveCompletionItems( self ):
  #   # FIXME: solargraph only append documentation into completionItem
  #   # ignore it to avoid performance issue.
  #   return False


  def ComputeCandidatesInner( self, request_data, *args ):
      # LOGGER.debug("request_data pos is %s.%s.%s", request_data[ 'line_num' ], request_data[ 'line_value' ], self.GetCodepointForCompletionRequest( request_data ))
      results = super().ComputeCandidatesInner(request_data, *args)
      if results == []: # solargraph first may return empty response. return None to avoid cache and no request
          return None
      #  TODO:  <09-10-18, yourname> #
      # LOGGER.debug("twice: request_data pos is %s.%s.%s", request_data[ 'line_num' ], request_data[ 'line_value' ], self.GetCodepointForCompletionRequest( request_data ))
      # super().ComputeCandidatesInner(request_data)

      # request_data[ 'start_codepoint' ] = request_data[ 'start_codepoint' ] + 1
      # LOGGER.debug("third: request_data pos is %s.%s.%s", request_data[ 'line_num' ], request_data[ 'line_value' ], self.GetCodepointForCompletionRequest( request_data ))
      # super().ComputeCandidatesInner(request_data)
      return results

  def GetType( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )
    LOGGER.debug("%s", hover_response)

    # RLS returns a list that may contain the following elements:
    # - a documentation string;
    # - a documentation url;
    # - [{language:rust, value:<type info>}].

    ty = None
    if isinstance( hover_response, str ):
        ty = hover_response
    if isinstance( hover_response, dict):
        ty = hover_response.get("value")
        if ty:
            m = re.search(r'=(?:>|&gt;)\s*(.*)$', ty, re.M)
            if m:
                ty = m.group(1)

    if ty:
        return responses.BuildDisplayMessageResponse( ty )

    raise RuntimeError( 'Unknown type.' )


  def GetDoc( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )

    documentation = None
    if isinstance( hover_response, str ):
        documentation = hover_response
    if isinstance( hover_response, dict):
        documentation = hover_response.get("value")

    if not documentation:
      raise RuntimeError( 'No documentation available for current context.' )

    return responses.BuildDetailedInfoResponse( documentation )

  @property
  def _ServerLoggingLevel( self ):
      return {
          logging.DEBUG: "debug",
          logging.INFO: "info",
          logging.WARN: "warn",
      }.get(LOGGER.getEffectiveLevel(), "warn")

# ex: sw=2 sts=2
