# Twisted, the Framework of Your Internet
# Copyright (C) 2001-2003 Matthew W. Lefkowitz
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
#

"""
A simple guard framework for implementing web sites that only need
'Anonymous' vs 'Logged on' distinction, but nothing more.

If you need
 * multiple levels of access, or
 * multiple-interface applications, or
 * anything else more complex than 'Logged on' and 'Not logged on'

you need to use twisted.web.woven.guard directly.
"""

from twisted.cred import portal, checkers as checkerslib
from twisted.web import resource, util
from twisted.web.woven import guard
from twisted.python import components
from zope.interface import implements


class Authenticated:

    def __init__(self, name=None):
        self.name = name

    def __nonzero__(self):
        return bool(self.name)


class MarkAuthenticatedResource:

    implements(resource.IResource)

    isLeaf = False

    def __init__(self, resource, name):
        self.authenticated = Authenticated(name)
        self.resource = resource

    def render(self, request):
        request.setComponent(Authenticated, self.authenticated)
        return self.resource.render(request)

    def getChildWithDefault(self, path, request):
        request.setComponent(Authenticated, self.authenticated)
        return self.resource.getChildWithDefault(path, request)
components.backwardsCompatImplements(MarkAuthenticatedResource)


class MarkingRealm:

    implements(portal.IRealm)

    def __init__(self, resource, nonauthenticated=None):
        self.resource = resource
        self.nonauthenticated = (nonauthenticated or
                                 MarkAuthenticatedResource(resource, None))

    def requestAvatar(self, avatarId, mind, *interfaces):
        if resource.IResource not in interfaces:
            raise NotImplementedError("no interface")
        if avatarId:
            return (resource.IResource,
                    MarkAuthenticatedResource(self.resource, avatarId),
                    lambda:None)
        else:
            return resource.IResource, self.nonauthenticated, lambda:None
components.backwardsCompatImplements(MarkingRealm)


def parentRedirect(_):
    return util.ParentRedirect()

def guardResource(resource, checkers, callback=parentRedirect, errback=None,
                  nonauthenticated=None):
    myPortal = portal.Portal(MarkingRealm(resource, nonauthenticated))
    for checker in checkers+[checkerslib.AllowAnonymousAccess()]:
        myPortal.registerChecker(checker)
    un = guard.UsernamePasswordWrapper(myPortal,
                                       callback=callback, errback=errback)
    return guard.SessionWrapper(un)
