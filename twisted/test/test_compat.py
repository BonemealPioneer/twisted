# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.trial import unittest

import os, sys, types

class IterableCounter:
    def __init__(self, lim=0):
        self.lim = lim
        self.i = -1

    def __iter__(self):
        return self

    def next(self):
        self.i += 1
        if self.i >= self.lim:
            raise StopIteration
        return self.i
        
class CompatTestCase(unittest.TestCase):
    def testDict(self):
        d1 = {'a': 'b'}
        d2 = dict(d1)
        self.assertEquals(d1, d2)
        d1['a'] = 'c'
        self.assertNotEquals(d1, d2)
        d2 = dict(d1.items())
        self.assertEquals(d1, d2)

#        d2 = dict(a='c')
#        self.assertEquals(d1, d2)
#        d2 = dict(d1, b='c')
#        d3 = dict(d1.items(), b='c')
#        d1['b'] = 'c'
#        self.assertEquals(d1, d2)
#        self.assertEquals(d1, d3)

    def testBool(self):
        self.assertEquals(bool('hi'), True)
        self.assertEquals(bool(True), True)
        self.assertEquals(bool(''), False)
        self.assertEquals(bool(False), False)

    def testIteration(self):
        lst1, lst2 = range(10), []
        
        for i in iter(lst1):
            lst2.append(i)
        self.assertEquals(lst1, lst2)
        del lst2[:]

        try:
            iterable = iter(lst1)
            while 1:
                lst2.append(iterable.next())
        except StopIteration:
            pass
        self.assertEquals(lst1, lst2)
        del lst2[:]

        for i in iter(IterableCounter(10)):
            lst2.append(i)
        self.assertEquals(lst1, lst2)
        del lst2[:]

        try:
            iterable = iter(IterableCounter(10))
            while 1:
                lst2.append(iterable.next())
        except StopIteration:
            pass
        self.assertEquals(lst1, lst2)
        del lst2[:]

        for i in iter(IterableCounter(20).next, 10):
            lst2.append(i)
        self.assertEquals(lst1, lst2)
        
    def testIsinstance(self):
        self.assert_(isinstance(u'hi', types.StringTypes))
        self.assert_(isinstance(self, unittest.TestCase))
        # I'm pretty sure it's impossible to implement this
        # without replacing isinstance on 2.2 as well :(
        # self.assert_(isinstance({}, dict))

    def testStrip(self):
        self.assertEquals(' x '.lstrip(' '), 'x ')
        self.assertEquals(' x x'.lstrip(' '), 'x x')
        self.assertEquals(' x '.rstrip(' '), ' x')
        self.assertEquals('x x '.rstrip(' '), 'x x')

        self.assertEquals('\t x '.lstrip('\t '), 'x ')
        self.assertEquals(' \tx x'.lstrip('\t '), 'x x')
        self.assertEquals(' x\t '.rstrip(' \t'), ' x')
        self.assertEquals('x x \t'.rstrip(' \t'), 'x x')

        self.assertEquals('\t x '.strip('\t '), 'x')
        self.assertEquals(' \tx x'.strip('\t '), 'x x')
        self.assertEquals(' x\t '.strip(' \t'), 'x')
        self.assertEquals('x x \t'.strip(' \t'), 'x x')
