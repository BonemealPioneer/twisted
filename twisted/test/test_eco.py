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
from pyunit import unittest
from twisted.eco import eco, sexpy
atom = sexpy.Atom

class EcoTestCase(unittest.TestCase):
    
    def testConsify(self):
        c = eco.consify([1,2,3,["a","b"]])
        assert c == [1, [2, [3, [["a", ["b", []]], []]]]]

    def testEval(self):
        assert eco.eval('[+ 2 3]') == 5
        assert eco.eval('[let [[x 1] [y 2]] [+ x y]]') == 3
        assert eco.eval('''[if [eq [+ 3 3] 0] [foo 1 2 3]
                            [list 1 2 3]]''') == [1, [2, [3, []]]]
        assert eco.eval('[let [[x [cons 1 2]]] [and [eq x [cons 1 2]] [not [is x [cons 1 2]]]]]')
        assert not eco.eval('[]')
        assert eco.eval('[let [[x [list 1 2]]] [and [eq [car x] 1] [eq [cdr x] [cons 2 []]] [eq [cadr x] 2]]]')
        assert eco.eval('[fn [a b] [+ a b]]')(1,2) == 3
        eco.eval('[def fn my-add [a b] [+ a b]]')
        assert eco.eval('[my-add 5 10]') == 15

    def testBackquote(self):
        assert eco.eval("[let [[x [list 1 2 3]] [y [list 7 3 2]]] (a b ,x d ,@y)]") == [atom('a'), [atom('b'), [[1, [2, [3, []]]], [atom('d'), [7, [3, [2, []]]]]]]]
    def testMacros(self):        
        eco.eval('[def macro mung [x] (+ ,[cadr x] ,[caddr x])]')
        assert eco.eval('[mung [* 10 5]] ') == 15
        assert eco.eval("[let [[x [macroexpand (mung [* 10 5])]]] [and [eq [car x] '+] [eq [cadr x] 10] [eq [caddr x] 5]]]")

    def testMultiFormEvaluation(self):
        assert eco.eval('[+ 1 1] [+ 2 2]') == 4
        assert eco.eval('[def fn add [x y] [+ x y]] [add 2 3]') == 5

testCases = [EcoTestCase]
