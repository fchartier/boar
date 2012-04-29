#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2010 Mats Ekberg
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from blobrepo import repository
import jsonrpc
import os, time, threading
import front
import sys

class TcpIpBoarServer:
    """This is a boar server that accepts connections on a tcp
    port."""

    def __init__(self, repopath, port = 50000):
        self.repopath = repopath
        self.server = jsonrpc.Server(jsonrpc.JsonRpc20(),
                                     jsonrpc.TransportTcpIp(timeout=60.0,
                                                            addr=("0.0.0.0", port)))
    def serve(self):
        repo = repository.Repo(self.repopath)
        fr = front.Front(repo)
        self.server.register_instance(fr, "front")
        self.server.serve()


class StdioBoarServer:
    """This is a boar server that uses stdin/stdout to communicate
    with the client. When initialized, this server hides the real
    sys.stdin and sys.stdout so that print commands can not
    accidentially corrupt the communication."""

    def __init__(self, repopath):
        self.repopath = repopath
        cmd_stdin = sys.stdin
        cmd_stdout = sys.stdout
        sys.stdin = None
        sys.stdout = sys.stderr
        self.server = jsonrpc.Server(jsonrpc.JsonRpc20(), 
                                     jsonrpc.TransportStream(cmd_stdin, cmd_stdout))
        sys.stdin = None
        sys.stdout = sys.stderr

    def serve(self):
        repo = repository.Repo(self.repopath)
        fr = front.Front(repo)
        self.server.register_instance(fr, "front")        
        self.server.serve()

class ThreadedBoarServer(TcpIpBoarServer):
    """This class is similar to TcpIpBoarServer, only that this
    server allows the main thread to continue doing other
    things. Useful for testing, when the same process needs to act as
    both client and server. """

    def __init__(self, repopath, port = 50000):
        TcpIpBoarServer.__init__(self, repopath, port)

    def serve(self):
        def super_serve():
            TcpIpBoarServer.serve(self)
        self.serverThread = threading.Thread(target = super_serve)
        self.serverThread.setDaemon(True)
        self.serverThread.start()

def main():
    repopath = unicode(sys.argv[1])
    server = StdioBoarServer(repopath)
    print "Serving"
    pid = server.serve()
    print "Done serving"

if __name__ == "__main__":
    main()
