
# Abstract representation of chat "model" classes

from locals import ONLINE, OFFLINE

from twisted.protocols.protocol import Protocol

class AbstractGroup:
    def __init__(self,name,baseClient,chatui):
        self.name = name
        self.client = baseClient
        self.chat = chatui

class AbstractPerson:
    def __init__(self,name,baseClient,chatui):
        self.name = name
        self.client = baseClient
        self.status = OFFLINE
        self.chat = chatui

class AbstractClientMixin:
    """Designed to be mixed in to a Protocol implementing class.

    Inherit from me first.
    """
    def __init__(self, account, chatui):
        for base in self.__class__.__bases__:
            if issubclass(base, Protocol):
                self.__class__._protoBase = base
                break
        else:
            pass
        self.account = account
        self.chat = chatui

    def connectionMade(self):
        self.account._isOnline = 1
        self._protoBase.connectionMade(self)
        
    def connectionFailed(self):
        self.account._isConnecting = 0
        self.account._isOnline = 0
        self._protoBase.connectionFailed(self)

    def connectionLost(self):
        self.account._isConnecting = 0
        self.account._isOnline = 0
        self._protoBase.connectionLost(self)


class AbstractAccount:
    _isOnline = 0
    _isConnecting = 0

    def __setstate__(self, d):
        if d.has_key('isOnline'):
            del d['isOnline']
        if d.has_key('_isOnline'):
            del d['_isOnline']
        if d.has_key('_isConnecting'):
            del d['_isConnecting']
        self.__dict__ = d
        self.port = int(self.port)

    def __getstate__(self):
        self._isOnline = 0
        self._isConnecting = 0
        return self.__dict__

    def isOnline(self):
        return self._isOnline

    def startLogOn(self, chatui):
        raise NotImplementedError()

    def logOn(self, chatui):
        if (not self._isConnecting) and (not self._isOnline):
            self._isConnecting = 1
            self.startLogOn(chatui)
        else:
            print 'already connecting'


