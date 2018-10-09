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
import threading
import time
from subprocess import STDOUT, PIPE
from ycmd import responses, utils
from ycmd.completers.language_server import language_server_completer
from collections import deque


_logger = logging.getLogger( __name__ )


LOGFILE_FORMAT = 'rubyls_'
PROJECT_FILE_TAILS = [
  'Gemfile',
  '.solargraph.yml',
]

def ShouldEnableCompleter():
    return FindExecutable()

def FindExecutable():
    for path in [ 'solargraph', os.path.expanduser( '~/.rbenv/shims/solargraph' ) ]:
      solargraph = utils.FindExecutable( path )
      if solargraph:
        return solargraph

def _FindProjectDir( starting_dir ):
  project_path = starting_dir
  project_type = None

  for folder in utils.PathsToAllParentFolders( starting_dir ):
    for project_file, tail in _MakeProjectFilesForPath( folder ):
      if os.path.isfile( project_file ):
        return folder

  return project_path

def _MakeProjectFilesForPath( path ):
  for tail in PROJECT_FILE_TAILS:
    yield os.path.join( path, tail ), tail

class RubyCompleter( language_server_completer.LanguageServerCompleter ):
  def __init__( self, user_options ):
    super( RubyCompleter, self ).__init__( user_options )

    self._server_keep_logfiles = user_options[ 'server_keep_logfiles' ]

    # Used to ensure that starting/stopping of the server is synchronized
    self._server_state_mutex = threading.RLock()
    self._server_starting = threading.Event()
    self._server_handle = None
    self._server_logfile = None
    self._server_started = False
    self._server_status = None

    self._bin = None
    self._project_dir = None

    self._notification_queue = deque()

    self._connection = None


  def SupportedFiletypes( self ):
    return [ 'ruby' ]


  def GetSubcommandsMap( self ):
    return {
      # Handled by base class
      'Format': (
        lambda self, request_data, args: self.Format( request_data )
       ),
      'GoToDeclaration': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoTo': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoToDefinition': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoToReferences': (
        lambda self, request_data, args: self.GoToReferences( request_data )
      ),
      'RefactorRename': (
        lambda self, request_data, args: self.RefactorRename( request_data,
                                                              args )
      ),

      # Handled by us
      'RestartServer': (
        lambda self, request_data, args: self._RestartServer( request_data )
      ),
      'StopServer': (
        lambda self, request_data, args: self._StopServer()
      ),
      'GetDoc': (
        lambda self, request_data, args: self.GetDoc( request_data )
      ),
      'GetType': (
        lambda self, request_data, args: self.GetType( request_data )
      )
    }


  def GetConnection( self ):
    return self._connection


  def OnFileReadyToParse( self, request_data ):
    self._StartServer( request_data )

    return super( RubyCompleter, self ).OnFileReadyToParse( request_data )

  def DebugInfo( self, request_data ):
    return responses.BuildDebugInfoResponse(
      name = 'Ruby',
      servers = [
        responses.DebugInfoServer(
          name = 'Ruby Language Server',
          handle = self._server_handle,
          executable = self._bin,
          logfiles = [
            self._server_logfile
          ],
          extras = [
            responses.DebugInfoItem( 'status', self._server_status ),
            responses.DebugInfoItem( 'Project Directory', self._project_dir ),
          ]
        )
      ],
    )


  def Shutdown( self ):
    self._StopServer()


  def ServerIsHealthy( self ):
    return self._ServerIsRunning()


  def ServerIsReady( self ):
    return ( self.ServerIsHealthy() and
             super( RubyCompleter, self ).ServerIsReady() )


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )


  def _RestartServer( self, request_data ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer( request_data )


  def _StartServer( self, request_data ):
    with self._server_state_mutex:
      if self._server_starting.is_set():
        raise RuntimeError( 'Already starting server.' )

      self._server_starting.set()

    thread = threading.Thread( target = self._StartServerInThread,
                               args = ( request_data, ) )
    thread.daemon = True
    thread.start()


  def _StartServerInThread( self, request_data ):
    try:
      if self._server_started:
        return

      self._server_started = True

      lang_server_bin = FindExecutable()
      if not lang_server_bin:
        return
      self._bin = lang_server_bin
      self._project_dir = _FindProjectDir(
        os.path.dirname( request_data[ 'filepath' ] ) )

      _logger.info( 'Starting Ruby Language Server...' )

      self._server_logfile = utils.CreateLogfile( LOGFILE_FORMAT )

      env = os.environ.copy()
      # if _logger.isEnabledFor( logging.DEBUG ):
      #   utils.SetEnviron( env, 'RUST_LOG', 'rls::server=trace' )
      #   utils.SetEnviron( env, 'RUST_BACKTRACE', '1' )

      # RLS may use the wrong standard library if the active toolchain is not
      # the same as the one the server is running on. Set the active toolchain
      # through the RUSTUP_TOOLCHAIN environment variable.
      # utils.SetEnviron( env, 'RUSTUP_TOOLCHAIN', self._toolchain )

      with utils.OpenForStdHandle( self._server_logfile ) as stderr:
        self._server_handle = utils.SafePopen( [lang_server_bin, "stdio"],
                                               stdin = PIPE,
                                               stdout = PIPE,
                                               stderr = stderr,
                                               env = env )

      if not self._ServerIsRunning():
        self._Notify( 'Ruby Language Server failed to start.' )
        return

      _logger.info( 'Ruby Language Server started.' )

      self._connection = (
        language_server_completer.StandardIOLanguageServerConnection(
          self._server_handle.stdin,
          self._server_handle.stdout,
          self.GetDefaultNotificationHandler() )
      )

      self._connection.start()

      try:
        self._connection.AwaitServerConnection()
      except language_server_completer.LanguageServerConnectionTimeout:
        self._Notify( 'Ruby Language Server failed to start, or did not '
                      'connect successfully.' )
        self._StopServer()
        return

      self.SendInitialize( request_data )
    finally:
      self._server_starting.clear()


  def _StopServer( self ):
    with self._server_state_mutex:
      _logger.info( 'Shutting down Ruby Language Server...' )
      # We don't use utils.CloseStandardStreams, because the stdin/out is
      # connected to our server connector. Just close stderr.
      #
      # The other streams are closed by the LanguageServerConnection when we
      # call Close.
      if self._server_handle and self._server_handle.stderr:
        self._server_handle.stderr.close()

      # Tell the connection to expect the server to disconnect.
      if self._connection:
        self._connection.Stop()

      if not self._ServerIsRunning():
        _logger.info( 'Ruby Language Server not running' )
        self._CleanUp()
        return

      _logger.info( 'Stopping Ruby Language Server with PID {0}'.format(
         self._server_handle.pid ) )

      try:
        self.ShutdownServer()

        # By this point, the server should have shut down and terminated. To
        # ensure that isn't blocked, we close all of our connections and wait
        # for the process to exit.
        #
        # If, after a small delay, the server has not shut down we do NOT kill
        # it; we expect that it will shut itself down eventually. This is
        # predominantly due to strange process behaviour on Windows.
        if self._connection:
          self._connection.Close()

        utils.WaitUntilProcessIsTerminated( self._server_handle,
                                            timeout = 15 )

        _logger.info( 'Ruby Language server stopped' )
      except Exception:
        _logger.exception( 'Error while stopping Ruby Language Server' )
        # We leave the process running. Hopefully it will eventually die of its
        # own accord.

      # Tidy up our internal state, even if the completer server didn't close
      # down cleanly.
      self._CleanUp()


  def _CleanUp( self ):
    self._server_handle = None
    self._server_started = False
    self._server_status = None
    self._connection = None
    self.ServerReset()
    if not self._server_keep_logfiles:
      if self._server_logfile:
        utils.RemoveIfExists( self._server_logfile )
        self._server_logfile = None


  def _ShouldResolveCompletionItems( self ):
    # FIXME: solargraph only append documentation into completionItem
    # ignore it to avoid performance issue.
    return False


  def ComputeCandidatesInner( self, request_data ):
      # _logger.debug("request_data pos is %s.%s.%s", request_data[ 'line_num' ], request_data[ 'line_value' ], self.GetCodepointForCompletionRequest( request_data ))
      results = super().ComputeCandidatesInner(request_data)
      if results == []: # solargraph first may return empty response. return None to avoid cache and no request
          return None
      #  TODO:  <09-10-18, yourname> #
      # _logger.debug("twice: request_data pos is %s.%s.%s", request_data[ 'line_num' ], request_data[ 'line_value' ], self.GetCodepointForCompletionRequest( request_data ))
      # super().ComputeCandidatesInner(request_data)

      # request_data[ 'start_codepoint' ] = request_data[ 'start_codepoint' ] + 1
      # _logger.debug("third: request_data pos is %s.%s.%s", request_data[ 'line_num' ], request_data[ 'line_value' ], self.GetCodepointForCompletionRequest( request_data ))
      # super().ComputeCandidatesInner(request_data)
      return results

  def _GetProjectDirectory(self, request_data):
    return self._project_dir

  # def HandleNotificationInPollThread( self, notification ):
  #   _logger.debug("RX: Received Notification: %s", notification)
  #   super( RubyCompleter, self ).HandleNotificationInPollThread( notification )


  def _Notify( self, message, level = 'error' ):
    getattr( _logger, level )( message )
    self._notification_queue.append(
      responses.BuildDisplayMessageResponse( message ) )


  def PollForMessagesInner( self, request_data, timeout ):
    expiration = time.time() + timeout
    while True:
      if time.time() > expiration:
        return True

      # If there are messages pending in the queue, return them immediately
      messages = self._GetPendingMessages( request_data )
      if messages:
        return messages

      try:
        return [ self._notification_queue.popleft() ]
      except IndexError:
        time.sleep( 0.1 )


  def GetType( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )

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


  def HandleServerCommand( self, request_data, command ):
    return None
