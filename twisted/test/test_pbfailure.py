# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.trial import unittest

from twisted.spread import pb
from twisted.internet import reactor, defer
from twisted.python import log, failure

##
# test exceptions
##
class PoopError(Exception): pass
class FailError(Exception): pass
class DieError(Exception): pass
class TimeoutError(Exception): pass

####
# server-side
####
class SimpleRoot(pb.Root):
    def remote_poop(self):
        return defer.fail(failure.Failure(PoopError("Someone threw poopie at me!")))

    def remote_fail(self):
        raise FailError("I'm a complete failure! :(")

    def remote_die(self):
        raise DieError("*gack*")


class PBFailureTest(unittest.TestCase):

    compare = unittest.TestCase.assertEquals
    unsafeTracebacks = 0

    def setUp(self):
        self._setUpServer()
        self._setUpClient()

    def _setUpServer(self):
        self.serverFactory = pb.PBServerFactory(SimpleRoot())
        self.serverFactory.unsafeTracebacks = self.unsafeTracebacks
        self.serverPort = reactor.listenTCP(0, self.serverFactory, interface="127.0.0.1")

    def _setUpClient(self):
        portNo = self.serverPort.getHost().port
        self.clientFactory = pb.PBClientFactory()
        self.clientConnector = reactor.connectTCP("127.0.0.1", portNo, self.clientFactory)

    def tearDown(self):
        return defer.gatherResults([
            self._tearDownServer(),
            self._tearDownClient()])

    def _tearDownServer(self):
        return self.serverPort.stopListening()

    def _tearDownClient(self):
        self.clientConnector.disconnect()
        return defer.succeed(None)

    def testPBFailures(self):
        d = self.clientFactory.getRootObject()
        d.addCallback(self.connected)
        d.addCallback(self.cleanupLoggedErrors)
        return d

    def addFailingCallbacks(self, remoteCall, expectedResult):
        for m in (self.failurePoop, self.failureFail, self.failureDie, self.failureNoSuch, lambda x: x):
            remoteCall.addCallbacks(self.success, m, callbackArgs=(expectedResult,))
        return remoteCall

    ##
    # callbacks
    ##

    def cleanupLoggedErrors(self, ignored):
        errors = log.flushErrors(PoopError, FailError, DieError, AttributeError)
        self.assertEquals(len(errors), 4)
        return ignored

    def connected(self, persp):
        methods = (('poop', 42), ('fail', 420), ('die', 4200), ('nosuch', 42000))
        return defer.gatherResults([
            self.addFailingCallbacks(persp.callRemote(meth), result) for (meth, result) in methods])

    def success(self, result, expectedResult):
        self.assertEquals(result, expectedResult)
        return result

    def failurePoop(self, fail):
        fail.trap(PoopError)
        self.compare(fail.traceback, "Traceback unavailable\n")
        return 42

    def failureFail(self, fail):
        fail.trap(FailError)
        self.compare(fail.traceback, "Traceback unavailable\n")
        return 420

    def failureDie(self, fail):
        fail.trap(DieError)
        self.compare(fail.traceback, "Traceback unavailable\n")
        return 4200

    def failureNoSuch(self, fail):
        # XXX maybe PB shouldn't send AttributeErrors? and make generic exception
        # for no such method?
        fail.trap(AttributeError)
        self.compare(fail.traceback, "Traceback unavailable\n")
        return 42000


class PBFailureTestUnsafe(PBFailureTest):

    compare = unittest.TestCase.failIfEquals
    unsafeTracebacks = 1
