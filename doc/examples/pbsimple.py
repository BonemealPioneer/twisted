
# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# This example program is cited in the Twisted paper for IPC10.

from twisted.spread import pb
from twisted.internet import main
class Echoer(pb.Root):
    def remote_echo(self, st):
        print 'echoing:', st
        return st
if __name__ == '__main__':
    app = main.Application("pbsimple")
    app.listenOn(8789, pb.BrokerFactory(Echoer()))
    app.run()
