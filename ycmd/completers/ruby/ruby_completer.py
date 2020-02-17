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
    return False
    lock = os.path.join(project_dir, 'Gemfile.lock')
    if os.path.isfile(lock):
        with open(lock) as f:
            return any('solargraph ' in line for line in f)
    return False


def _UseSorbet(project_dir):
    lock = os.path.join(project_dir, 'Gemfile.lock')
    if os.path.isfile(lock):
        with open(lock) as f:
          if any('sorbet-static ' in line for line in f):
            for path in ['srb', os.path.expanduser('~/.rbenv/shims/srb')]:
              srb = utils.FindExecutable(path)
              if srb:
                return srb
    return None



class RubyCompleter( SimpleLSPCompleter ):
  def __init__( self, user_options ):
    super( RubyCompleter, self ).__init__( user_options )

    self._command_line = None
    self._current_server_type = "solargraph"
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
      ),
      'SwitchServerType': RubyCompleter.SwitchServerType,
    }

  def ExtraDebugItems( self, request_data ):
    return [
      responses.DebugInfoItem( 'bundler', self._use_bundler ),
      responses.DebugInfoItem( 'server type', self._current_server_type )
    ]

  def PopenKwargs( self ):
    return { 'cwd': self._project_directory }

  def SwitchServerType(self, request_data, args):
    if self._current_server_type == "sorbet":
      self._current_server_type = "solargraph"
    else:
      self._current_server_type = "sorbet"
    self._RestartServer(request_data)

  def StartServer( self, request_data ):
    with self._server_state_mutex:
      self._project_directory = self.GetProjectDirectory( request_data, None)
      sorbet = None
      if self._current_server_type != 'solargraph':
        sorbet = _UseSorbet(self._project_directory)
      if sorbet:
        self._bin = sorbet
        self._current_server_type = "sorbet"
        self._command_line = [sorbet, 't', '--lsp',
                              "--enable-all-beta-lsp-features",
                              "--enable-experimental-lsp-quick-fix"]
        if self._ServerLoggingLevel == 'debug':
          self._command_line.append('--verbose')
      else:
        lang_server_bin = FindExecutable()
        if not lang_server_bin:
          return False
        self._bin = lang_server_bin
        self._use_bundler = _UseBundler(self._project_directory)
        self._current_server_type = "solargraph"
        if self._use_bundler:
            self._command_line = ['bundle', 'exec', lang_server_bin, "stdio"]
        else:
            self._command_line = [lang_server_bin, "stdio"]
            # self._command_line = ["nc", "127.0.0.1", "7658"]
            self._settings['diagnostics'] = True
            self._settings['formatting'] = True
      self._settings['logLevel'] = self._ServerLoggingLevel
      # self._settings['logLevel'] = 'debug'

      return super().StartServer(request_data)

  # def _ShouldResolveCompletionItems( self ):
  #   # FIXME: solargraph only append documentation into completionItem
  #   # ignore it to avoid performance issue.


  def ShouldUseNowInner(self, request_data):
    # sorbet only completions when have query
    if (self._current_server_type == "sorbet" and
        request_data[ 'column_codepoint' ] <= request_data['start_codepoint']):
      return False

    return super().ShouldUseNowInner(request_data)

  def GetCodepointForCompletionRequest( self, request_data ):
    if self._current_server_type == "sorbet":
      return request_data['column_codepoint']
    return super().GetCodepointForCompletionRequest(request_data)

  def ComputeCandidatesInner( self, request_data, *args ):
      results = super().ComputeCandidatesInner(request_data, *args)
      if self._current_server_type == "sorbet":
        # sorbet use current word as filter, no matter which point pass.
        # so back should retrigger a filter
        return (results[0], True)
      return results

  def _CandidatesFromCompletionItems( self, items, resolve, *args):
    # sorbet的text edit的修正点计算错误，需要过滤。换成insert_text
    if self._current_server_type == "sorbet":
      def fix(item):
        edit = item.pop("textEdit", None)
        if edit:
          item['insertText'] = edit['newText']
        return item

      items = [fix(i) for i in items]
    return super()._CandidatesFromCompletionItems(items, resolve, *args)

  def GetType( self, request_data ):
    ty = self.GetHover(request_data)

    if ty:
      m = re.search(r'=(?:>|&gt;|~)\s*.*$', ty, re.M)
      if m:
        ty = m.group(0)

      return responses.BuildDisplayMessageResponse( ty )

    raise RuntimeError( 'Unknown type.' )

  def GetHover(self, request_data):
    hover_response = self.GetHoverResponse( request_data )

    documentation = None
    if isinstance( hover_response, str ):
        documentation = hover_response
    if isinstance( hover_response, dict):
        documentation = hover_response.get("value")

    return documentation

  def GetDoc( self, request_data ):
    documentation = self.GetHover(request_data)
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
