
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

"""S-expression-based persistence of python objects.

I do something very much like Pickle; however, pickle's main goal seems to be
efficiency (both in space and time); jelly's main goals are security, human
readability, and portability to other environments.


This is how Jelly converts various objects to s-expressions:

Integer: 1 --> 1

List: [1, 2] --> ['list', 1, 2]

String: "hello" --> "hello"

Float: 2.3 --> 2.3

Dictionary: {'a' : 1, 'b' : 'c'} --> ['dictionary', ['b', 'c'], ['a', 1]]

Module: UserString --> ['module', 'UserString']

Class: UserString.UserString --> ['class', ['module', 'UserString'], 'UserString']

Function: string.join --> ['function', 'join', ['module', 'string']]

Instance: s is an instance of UserString.UserString, with a __dict__ {'data': 'hello'}:
['instance', ['class', ['module', 'UserString'], 'UserString'], ['dictionary', ['data', 'hello']]]

Class Method: UserString.UserString.center:
['method', 'center', ['None'], ['class', ['module', 'UserString'], 'UserString']]

Instance Method: s.center, where s is an instance of UserString.UserString:
['method', 'center', ['instance', ['reference', 1, ['class', ['module', 'UserString'], 'UserString']], ['dictionary', ['data', 'd']]], ['dereference', 1]]

"""

import string
import pickle
import sys
import types
import copy

try:
    from new import instance
    from new import instancemethod
except:
    from org.python.core import PyMethod
    instancemethod = PyMethod

None_atom = "None"                  # N
# code
class_atom = "class"                # c
module_atom = "module"              # m
function_atom = "function"          # f

# references
dereference_atom = 'dereference'    # D
persistent_atom = 'persistent'      # p
reference_atom = 'reference'        # r

# mutable collections
dictionary_atom = "dictionary"      # d
list_atom = 'list'                  # l

# immutable collections
#   (assignment to __dict__ and __class__ still might go away!)
tuple_atom = "tuple"                # t
instance_atom = 'instance'          # i


# errors
unpersistable_atom = "unpersistable"# u

typeNames = {
    types.StringType: "string",
    types.IntType: "int",
    types.LongType: "long",
    types.FloatType: "float",
    types.ClassType: "class",
    types.DictType: "dictionary",
    types.ListType: "list",
    types.TupleType: "tuple",
    types.BuiltinMethodType: "builtin_function_or_method",
    types.FunctionType: "function",
    types.ModuleType: "module",
    types.InstanceType: "instance",
    types.MethodType: "instance_method",
    types.NoneType: "None",
    }

class Unpersistable:
    """
    This is an instance of a class that comes back when something couldn't be
    persisted.
    """
    def __init__(self, reason):
        """
        Initialize an unpersistable object with a descriptive `reason' string.
        """
        self.reason = reason

    def __repr__(self):
        return "Unpersistable(%s)" % repr(self.reason)

class _Jellier:
    """(Internal) This class manages state for a call to jelly()
    """
    def __init__(self, taster, persistentStore):
        """Initialize.
        """
        self.taster = taster
        # `preseved' is a dict of previously seen instances.
        self.preserved = {}
        # `cooked' is a dict of previously backreferenced instances to their `ref' lists.
        self.cooked = {}
        self.cooker = {}
        self._ref_id = 1
        self.persistentStore = persistentStore

    def _cook(self, object):
        """(internal)
        backreference an object
        """
        aList = self.preserved[id(object)]
        newList = copy.copy(aList)
        # make a new reference ID
        refid = self._ref_id
        self._ref_id = self._ref_id + 1
        # replace the old list in-place, so that we don't have to track the
        # previous reference to it.
        aList[:] = [reference_atom, refid, newList]
        self.cooked[id(object)] = [dereference_atom, refid]
        return aList

    def _prepare(self, object):
        """(internal)
        create a list for persisting an object to.  this will allow
        backreferences to be made internal to the object. (circular
        references).
        """
        # create a placeholder list to be preserved
        self.preserved[id(object)] = []
        # keep a reference to this object around, so it doesn't disappear!
        # (This isn't always necessary, but for cases where the objects are
        # dynamically generated by __getstate__ or getStateToCopyFor calls, it
        # is; id() will return the same value for a different object if it gets
        # garbage collected.  This may be optimized later.)
        self.cooker[id(object)] = object
        return []

    def _preserve(self, object, sexp):
        """(internal)
        mark an object's persistent list for later referral
        """
        #if I've been cooked in the meanwhile,
        if self.cooked.has_key(id(object)):
            # replace the placeholder empty list with the real one
            self.preserved[id(object)][2] = sexp
            # but give this one back.
            sexp = self.preserved[id(object)]
        else:
            self.preserved[id(object)] = sexp
        return sexp

    def jelly(self, object):
        """(internal) make a list
        """
        # if it's been previously backreferenced, then we're done
        if self.cooked.has_key(id(object)):
            return self.cooked[id(object)]
        # if it's been previously seen but NOT backreferenced,
        # now's the time to do it.
        if self.preserved.has_key(id(object)):
            self._cook(object)
            return self.cooked[id(object)]
        typnm = string.replace(typeNames[type(object)], ' ', '_')
### this next block not _necessarily_ correct due to some tricks in
### NetJellier's _jelly_instance...
##        if not self.taster.isTypeAllowed(typnm):
##            raise InsecureJelly("Type %s not jellyable." % typnm)
        typfn = getattr(self, "_jelly_%s" % typnm, None)
        if typfn:
            return typfn(object)
        else:
            return self.unpersistable("type: %s" % repr(type(object)))

    def _jelly_string(self, st):
        """(internal) Return the serialized representation of a string.

        This just happens to be the string itself.
        """
        return st
    
    def _jelly_int(self, nt):
        """(internal)
        Return the serialized representation of an integer (which is the
        integer itself).
        """
        return nt

    def _jelly_long(self, ng):
        """(internal)

        Return the serialized representation of a long integer (this will only
        work for long ints that can fit into a regular integer, currently, but
        that limitation is temporary)
        """
        return ng

    def _jelly_float(self, loat):
        """(internal)
        Return the serialized representation of a float (which is the float
        itself).
        """
        return loat

    ### these have to have unjelly equivalents

    def _jelly_instance(self, instance):
        '''Jelly an instance.

        In the default case, this returns a list of 3 items::

          (instance (class ...) (dictionary ("attrib" "val")) )

        However, if I was created with a persistentStore method, then that
        method will be called with the 'instance' argument.  If that method
        returns a string, I will return::

          (persistent "...")
        '''
        # like pickle's persistent_id
        sxp = self._prepare(instance)
        persistent = None
        if self.persistentStore:
            persistent = self.persistentStore(instance, self)
        if persistent is not None:
            tp = type(persistent)
            sxp.append(persistent_atom)
            sxp.append(persistent)
        elif self.taster.isModuleAllowed(instance.__class__.__module__):
            if self.taster.isClassAllowed(instance.__class__):
                sxp.append(instance_atom)
                sxp.append(self.jelly(instance.__class__))
                if hasattr(instance, '__getstate__'):
                    state = instance.__getstate__()
                else:
                    state = instance.__dict__
                sxp.append(self.jelly(state))
            else:
                self.unpersistable("instance of class %s deemed insecure" % str(instance.__class__), sxp)
        else:
            self.unpersistable("instance from module %s deemed insecure" % str(instance.__class__.__module__), sxp)
        return self._preserve(instance, sxp)


    def _jelly_class(self, klaus):
        ''' (internal) Jelly a class.
        returns a list of 3 items: (class "module" "name")
        '''
        if self.taster.isModuleAllowed(klaus.__module__):
            if self.taster.isClassAllowed(klaus):
                jklaus = self._prepare(klaus)
                jklaus.append(class_atom)
                jklaus.append(self.jelly(sys.modules[klaus.__module__]))
                jklaus.append(klaus.__name__)
                return self._preserve(klaus, jklaus)
            else:
                return self.unpersistable("class %s deemed insecure" % str(klaus))
        else:
            return self.unpersistable("class from module %s deemed insecure" % str(klaus.__module__))


    def _jelly_dictionary(self, dict):
        ''' (internal) Jelly a dictionary.
        returns a list of n items of the form (dictionary (attribute value) (attribute value) ...)
        '''
        jdict = self._prepare(dict)
        jdict.append(dictionary_atom)
        for key, val in dict.items():
            jkey = self.jelly(key)
            jval = self.jelly(val)
            jdict.append([jkey, jval])
        return self._preserve(dict, jdict)

    def _jelly_list(self, lst):
        ''' (internal) Jelly a list.
        returns a list of n items of the form (list "value" "value" ...)
        '''
        jlst = self._prepare(lst)
        jlst.append(list_atom)
        for item in lst:
            jlst.append(self.jelly(item))
        return self._preserve(lst, jlst)

    def _jelly_None(self, nne):
        ''' (internal) Jelly "None".
        returns the list (none).
        '''
        return [None_atom]

    def _jelly_instance_method(self, im):
        ''' (internal) Jelly an instance method.
        return a list of the form (method "name" (instance ...) (class ...))
        '''
        jim = self._prepare(im)
        jim.append("method")
        jim.append(im.im_func.__name__)
        jim.append(self.jelly(im.im_self))
        jim.append(self.jelly(im.im_class))
        return self._preserve(im, jim)

    def _jelly_tuple(self, tup):
        ''' (internal) Jelly a tuple.
        returns a list of n items of the form (tuple "value" "value" ...)
        '''
        jtup = self._prepare(tup)
        jtup.append(tuple_atom)
        for item in tup:
            jtup.append(self.jelly(item))
        return self._preserve(tup, jtup)

    def _jelly_builtin_function_or_method(self, lst):
        """(internal)
        Jelly a builtin function.  This is currently unimplemented.
        """
        raise 'currently unimplemented'

    def _jelly_function(self, func):
        ''' (internal) Jelly a function.
        Returns a list of the form (function "name" (module "name"))
        '''
        name = func.__name__
        module = sys.modules[pickle.whichmodule(func, name)]
        if self.taster.isModuleAllowed(module.__name__):
            jfunc = self._prepare(func)
            jfunc.append(function_atom)
            jfunc.append(name)
            jfunc.append(self.jelly(module))
            return self._preserve(func, jfunc)
        else:
            return self.unpersistable("module %s deemed insecure" % str(module.__name__))

    def _jelly_module(self, module):
        '''(internal)
        Jelly a module.  Return a list of the form (module "name")
        '''
        if self.taster.isModuleAllowed(module.__name__):
            jmod = self._prepare(module)
            jmod.append(module_atom)
            jmod.append(module.__name__)
            return self._preserve(module, jmod)
        else:
            return self.unpersistable("module %s deemed insecure" % str(module.__name__))

    def unpersistable(self, reason, sxp=None):
        '''(internal)
        Returns an sexp: (unpersistable "reason").  Utility method for making
        note that a particular object could not be serialized.
        '''
        if sxp is None:
            sxp = []
        sxp.append(unpersistable_atom)
        sxp.append(reason)
        return sxp

class NotKnown:
    def __init__(self):
        self.dependants = []

    def addDependant(self, mutableObject, key):
        self.dependants.append( (mutableObject, key) )

    def resolveDependants(self, newObject):
        for mut, key in self.dependants:
            mut[key] = newObject
            if isinstance(newObject, NotKnown):
                newObject.addDependant(mut, key)

    def __hash__(self):
        assert 0, "I am not to be used as a dictionary key."


class _Tuple(NotKnown):
    def __init__(self, l):
        NotKnown.__init__(self)
        self.l = l
        self.locs = []
        for idx in xrange(len(l)):
            if isinstance(l[idx], NotKnown):
                self.locs.append(idx)
                l[idx].addDependant(self, idx)

    def __setitem__(self, n, obj):
        self.l[n] = obj
        if not isinstance(obj, NotKnown):
            self.locs.remove(n)
            if not self.locs:
                self.resolveDependants(tuple(self.l))

class _DictKeyAndValue:
    def __init__(self, dict):
        self.dict = dict
    def __setitem__(self, n, obj):
        if n not in (1, 0):
            raise AssertionError("DictKeyAndValue should only ever be called with 0 or 1")
        if n: # value
            self.value = obj
        else:
            self.key = obj
        if hasattr(self, "key") and hasattr(self, "value"):
            self.dict[self.key] = self.value


class _Dereference(NotKnown):
    def __init__(self, id):
        NotKnown.__init__(self)
        self.id = id

class _Unjellier:
    def __init__(self, taster, persistentLoad):
        self.taster = taster
        self.persistentLoad = persistentLoad
        self.references = {}
        self.postCallbacks = []

    def unjelly(self, obj):
        o = self._unjelly(obj)
        for m in self.postCallbacks:
            m()
        return o

    def _unjelly(self, obj):
        if type(obj) is not types.ListType:
            return obj
        jelType = obj[0]
        if not self.taster.isTypeAllowed(jelType):
            raise InsecureJelly(jelType)
        thunk = getattr(self, '_unjelly_%s'%jelType)
        ret = thunk(obj[1:])
        return ret

    def _unjelly_None(self, exp):
        return None

    def unjellyInto(self, obj, loc, jel):
        o = self._unjelly(jel)
        if isinstance(o, NotKnown):
            o.addDependant(obj, loc)
        obj[loc] = o
        return o

    def _unjelly_dereference(self, lst):
        refid = lst[0]
        x = self.references.get(refid)
        if x is not None:
            return x
        der = _Dereference(refid)
        self.references[refid] = der
        return der

    def _unjelly_reference(self, lst):
        refid = lst[0]
        exp = lst[1]
        o = self._unjelly(exp)
        ref = self.references.get(refid)
        if (ref is None):
            self.references[refid] = o
        elif isinstance(ref, NotKnown):
            ref.resolveDependants(o)
            self.references[refid] = o
        else:
            assert 0, "Multiple references with same ID!"
        return o

    def _unjelly_tuple(self, lst):
        l = range(len(lst))
        finished = 1
        for elem in l:
            if isinstance(self.unjellyInto(l, elem, lst[elem]), NotKnown):
                finished = 0
        if finished:
            return tuple(l)
        else:
            return _Tuple(l)

    def _unjelly_list(self, lst):
        l = range(len(lst))
        for elem in l:
            self.unjellyInto(l, elem, lst[elem])
        return l

    def _unjelly_dictionary(self, lst):
        d = {}
        for k, v in lst:
            kvd = _DictKeyAndValue(d)
            self.unjellyInto(kvd, 0, k)
            self.unjellyInto(kvd, 1, v)
        return d


    def _unjelly_module(self, rest):
        moduleName = rest[0]
        if type(moduleName) != types.StringType:
            raise InsecureJelly("Attempted to unjelly a module with a non-string name.")
        if not self.taster.isModuleAllowed(moduleName):
            raise InsecureJelly("Attempted to unjelly module named %s" % repr(moduleName))
        mod = __import__(moduleName, {}, {},"x")
        return mod

    def _unjelly_class(self, rest):
        mod = self._unjelly(rest[0])
        if type(mod) is not types.ModuleType:
            raise InsecureJelly("class has a non-module module")
        name = rest[1]
        klaus = getattr(mod, name)
        if type(klaus) is not types.ClassType:
            raise InsecureJelly("class %s unjellied to something that isn't a class: %s" % (repr(name), repr(klaus)))
        if not self.taster.isClassAllowed(klaus):
            raise InsecureJelly("class not allowed: %s" % str(klaus))
        return klaus

    def _unjelly_function(self, rest):
        module = self._unjelly(rest[1])
        if type(module) is not types.ModuleType:
            raise InsecureJelly("function references a non-module module")
        function = getattr(module, rest[0])
        return function

    def _unjelly_persistent(self, rest):
        if self.persistentLoad:
            pid = rest[0]
            pload = self.persistentLoad(rest[0],self)
            return pload
        else:
            return Unpersistable("persistent callback not found")

    def _unjelly_instance(self, rest):
        clz = self._unjelly(rest[0])
        if type(clz) is not types.ClassType:
            raise InsecureJelly("Instance found with non-class class.")
        if hasattr(clz, "__setstate__"):
            inst = instance(clz, {})
            state = self._unjelly(rest[1])
            inst.__setstate__(state)
        else:
            state = self._unjelly(rest[1])
            inst = instance(clz, state)
        if hasattr(clz, 'postUnjelly'):
            self.postCallbacks.append(inst.postUnjelly)
        return inst

    def _unjelly_unpersistable(self, rest):
        return Unpersistable(rest[0])

    def _unjelly_method(self, rest):
        ''' (internal) unjelly a method
        '''
        im_name = rest[0]
        im_self = self._unjelly(rest[1])
        im_class = self._unjelly(rest[2])
        if im_class.__dict__.has_key(im_name):
            if im_self is None:
                im = getattr(im_class, im_name)
            else:
                im = instancemethod(im_class.__dict__[im_name],
                                    im_self,
                                    im_class)
        else:
            raise 'instance method changed'
        return im


class _Dummy:
    """(Internal)
    Dummy class, used for unserializing instances.
    """




#### Published Interface.


class InsecureJelly(Exception):
    """
    This exception will be raised when a jelly is deemed `insecure'; e.g. it
    contains a type, class, or module disallowed by the specified `taster'
    """



class DummySecurityOptions:
    """DummySecurityOptions() -> insecure security options
    Dummy security options -- this class will allow anything.
    """
    def isModuleAllowed(self, moduleName):
        """DummySecurityOptions.isModuleAllowed(moduleName) -> boolean
        returns 1 if a module by that name is allowed, 0 otherwise
        """
        return 1

    def isClassAllowed(self, klass):
        """DummySecurityOptions.isClassAllowed(class) -> boolean
        Assumes the module has already been allowed.  Returns 1 if the given
        class is allowed, 0 otherwise.
        """
        return 1

    def isTypeAllowed(self, typeName):
        """DummySecurityOptions.isTypeAllowed(typeName) -> boolean
        Returns 1 if the given type is allowed, 0 otherwise.
        """
        return 1



class SecurityOptions:
    """
    This will by default disallow everything, except for 'none'.
    """

    basicTypes = ["dictionary", "list", "tuple",
                  "reference", "dereference", "unpersistable",
                  "persistent"]

    def __init__(self):
        """SecurityOptions()
        Initialize.
        """
        # I don't believe any of these types can ever pose a security hazard,
        # except perhaps "reference"...
        self.allowedTypes = {"None": 1,
                             "string": 1,
                             "int": 1,
                             "float": 1}
        self.allowedModules = {}
        self.allowedClasses = {}

    def allowBasicTypes(self):
        """SecurityOptions.allowBasicTypes()
        Allow all `basic' types.  (Dictionary and list.  Int, string, and float are implicitly allowed.)
        """
        apply(self.allowTypes, self.basicTypes)

    def allowTypes(self, *types):
        """SecurityOptions.allowTypes(typeString): Allow a particular type, by its name.
        """
        for typ in types:
            self.allowedTypes[string.replace(typ, ' ', '_')]=1

    def allowInstancesOf(self, *classes):
        """SecurityOptions.allowInstances(klass, klass, ...): allow instances of the specified classes
        This will also allow the 'instance', 'class', and 'module' types, as well as basic types.
        """
        self.allowBasicTypes()
        self.allowTypes("instance", "class", "module")
        for klass in classes:
            self.allowModules(klass.__module__)
            self.allowedClasses[klass] = 1

    def allowModules(self, *modules):
        """SecurityOptions.allowModules(module, module, ...): allow modules by name
        This will also allow the 'module' type.
        """
        for module in modules:
            if type(module) == types.ModuleType:
                module = module.__name__
            self.allowedModules[module] = 1

    def isModuleAllowed(self, moduleName):
        """SecurityOptions.isModuleAllowed(moduleName) -> boolean
        returns 1 if a module by that name is allowed, 0 otherwise
        """
        return self.allowedModules.has_key(moduleName)

    def isClassAllowed(self, klass):
        """SecurityOptions.isClassAllowed(class) -> boolean
        Assumes the module has already been allowed.  Returns 1 if the given
        class is allowed, 0 otherwise.
        """
        return self.allowedClasses.has_key(klass)

    def isTypeAllowed(self, typeName):
        """SecurityOptions.isTypeAllowed(typeName) -> boolean
        Returns 1 if the given type is allowed, 0 otherwise.
        """
        return self.allowedTypes.has_key(typeName)





def jelly(object, taster = DummySecurityOptions(), persistentStore = None):
    """Serialize to s-expression.

    Returns a list which is the serialized representation of an object.  An
    optional 'taster' argument takes a SecurityOptions and will mark any
    insecure objects as unpersistable rather than serializing them.
    """
    return _Jellier(taster, persistentStore).jelly(object)


def unjelly(sexp, taster = DummySecurityOptions(), persistentLoad = None):
    """Unserialize from s-expression.

    Takes an list that was the result from a call to jelly() and unserializes
    an arbitrary object from it.  The optional 'taster' argument, an instance
    of SecurityOptions, will cause an InsecureJelly exception to be raised if a
    disallowed type, module, or class attempted to unserialize.
    """
    return _Unjellier(taster, persistentLoad).unjelly(sexp)


