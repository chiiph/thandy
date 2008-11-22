# Copyright 2008 The Tor Project, Inc.  See LICENSE for licensing information.

import re
import sys

import thandy

class Schema:
    """A schema matches a set of possible Python objects, of types
       that are encodable in JSON."""
    def matches(self, obj):
        """Return True if 'obj' matches this schema, False if it doesn't."""
        try:
            self.checkMatch(obj)
        except thandy.FormatException:
            return False
        else:
            return True

    def checkMatch(self, obj):
        """Raise thandy.FormatException if 'obj' does not match this schema.
           Abstract method."""
        raise NotImplemented()

class Any(Schema):
    """
       Matches any single object.

       >>> s = Any()
       >>> s.matches("A String")
       True
       >>> s.matches([1, "list"])
       True
    """
    def checkMatch(self, obj):
        pass

class RE(Schema):
    """
       Matches any string that matches a given regular expression.

       >>> s = RE("h.*d")
       >>> s.matches("hello world")
       True
       >>> s.matches("Hello World")
       False
       >>> s.matches("hello world!")
       False
       >>> s.matches([33, "Hello"])
       False
    """
    def __init__(self, pat=None, modifiers=0, reObj=None, reName=None):
        """Make a new RE schema
             pat -- The pattern to match, or None if reObj is provided.
             modifiers -- Flags to use when compiling the pattern.
             reObj -- A compiled regular expression object.
        """
        if not reObj:
            if not pat.endswith("$"):
                pat += "$"
            reObj = re.compile(pat, modifiers)
        self._re = reObj
        if reName == None:
            if pat != None:
                reName = "pattern /%s/"%pat
            else:
                reName = "pattern"
        self._reName = reName
    def checkMatch(self, obj):
        if not isinstance(obj, basestring) or not self._re.match(obj):
            raise thandy.FormatException("%r did not match %s"
                                         %(obj,self._reName))

class Str(Schema):
    """
       Matches a particular string.

       >>> s = Str("Hi")
       >>> s.matches("Hi")
       True
       >>> s.matches("Not hi")
       False
    """
    def __init__(self, val):
        self._str = val
    def checkMatch(self, obj):
        if self._str != obj:
            raise thandy.FormatException("Expected %r; got %r"%(self._str, obj))

class AnyStr(Schema):
    """
       Matches any string, but no non-string object.

       >>> s = AnyStr()
       >>> s.matches("")
       True
       >>> s.matches("a string")
       True
       >>> s.matches(["a"])
       False
       >>> s.matches(3)
       False
       >>> s.matches(u"a unicode string")
       True
       >>> s.matches({})
       False
    """
    def __init__(self):
        pass
    def checkMatch(self, obj):
        if not isinstance(obj, basestring):
            raise thandy.FormatException("Expected a string; got %r"%obj)

class OneOf(Schema):
    """
       Matches an object that matches any one of several schemas.

       >>> s = OneOf([ListOf(Int()), Str("Hello"), Str("bye")])
       >>> s.matches(3)
       False
       >>> s.matches("bye")
       True
       >>> s.matches([])
       True
       >>> s.matches([1,2])
       True
       >>> s.matches(["Hi"])
       False
    """
    def __init__(self, alternatives):
        self._subschemas = alternatives

    def checkMatch(self, obj):
        for m in self._subschemas:
            if m.matches(obj):
                return

        raise thandy.FormatException("Object matched no recognized alternative")

class ListOf(Schema):
    """
       Matches a homogenous list of some subschema.

       >>> s = ListOf(RE("(?:..)*"))
       >>> s.matches("hi")
       False
       >>> s.matches([])
       True
       >>> s.matches({})
       False
       >>> s.matches(["Hi", "this", "list", "is", "full", "of", "even", "strs"])
       True
       >>> s.matches(["This", "one", "is not"])
       False

       >>> s = ListOf(Int(), minCount=3, maxCount=10)
       >>> s.matches([3]*2)
       False
       >>> s.matches([3]*3)
       True
       >>> s.matches([3]*10)
       True
       >>> s.matches([3]*11)
       False
    """
    def __init__(self, schema, minCount=0, maxCount=sys.maxint,listName="list"):
        self._schema = schema
        self._minCount = minCount
        self._maxCount = maxCount
        self._listName = listName
    def checkMatch(self, obj):
        if not isinstance(obj, (list, tuple)):
            raise thandy.FormatException("Expected %s; got %r"
                                         %(self._listName,obj))
        for item in obj:
            try:
                self._schema.checkMatch(item)
            except thandy.FormatException, e:
                raise thandy.FormatException("%s in %s"%(e, self._listName))

        if not (self._minCount <= len(obj) <= self._maxCount):
            raise thandy.FormatException("Length of %s out of range"
                                         %self._listName)

class Struct(Schema):
    """
       Matches a non-homogenous list of items.

       >>> s = Struct([ListOf(AnyStr()), AnyStr(), Str("X")])
       >>> s.matches(False)
       False
       >>> s.matches("Foo")
       False
       >>> s.matches([[], "Q", "X"])
       True
       >>> s.matches([[], "Q", "D"])
       False
       >>> s.matches([[3], "Q", "X"])
       False
       >>> s.matches([[], "Q", "X", "Y"])
       False

       >>> s = Struct([Str("X")], allowMore=True)
       >>> s.matches([])
       False
       >>> s.matches(["X"])
       True
       >>> s.matches(["X", "Y"])
       True
       >>> s.matches(["X", ["Y", "Z"]])
       True
       >>> s.matches([["X"]])
       False
    """
    def __init__(self, subschemas, allowMore=False, structName="list"):
        self._subschemas = subschemas[:]
        self._allowMore = allowMore
        self._structName = structName
    def checkMatch(self, obj):
        if not isinstance(obj, (list, tuple)):
            raise thandy.FormatException("Expected %s; got %r"
                                         %(self._structName,obj))
        elif len(obj) < len(self._subschemas):
            raise thandy.FormatException(
                "Too few fields in %s"%self._structName)
        elif len(obj) > len(self._subschemas) and not self._allowMore:
            raise thandy.FormatException(
                "Too many fields in %s"%self._structName)
        for item, schema in zip(obj, self._subschemas):
            schema.checkMatch(item)

class DictOf(Schema):
    """
       Matches a mapping from items matching a particular key-schema
       to items matching a value-schema.  Note that in JSON, keys must
       be strings.

       >>> s = DictOf(RE(r'[aeiou]+'), Struct([AnyStr(), AnyStr()]))
       >>> s.matches("")
       False
       >>> s.matches({})
       True
       >>> s.matches({"a": ["x", "y"], "e" : ["", ""]})
       True
       >>> s.matches({"a": ["x", 3], "e" : ["", ""]})
       False
       >>> s.matches({"a": ["x", "y"], "e" : ["", ""], "d" : ["a", "b"]})
       False
    """
    def __init__(self, keySchema, valSchema):
        self._keySchema = keySchema
        self._valSchema = valSchema
    def checkMatch(self, obj):
        try:
            iter = obj.iteritems()
        except AttributeError:
            raise thandy.FormatException("Expected a dict; got %r"%obj)

        for k,v in iter:
            self._keySchema.checkMatch(k)
            self._valSchema.checkMatch(v)

class Opt:
    """Helper; applied to a value in Obj to mark it optional.

       >>> s = Obj(k1=Str("X"), k2=Opt(Str("Y")))
       >>> s.matches({'k1': "X", 'k2': "Y"})
       True
       >>> s.matches({'k1': "X", 'k2': "Z"})
       False
       >>> s.matches({'k1': "X"})
       True
    """
    def __init__(self, schema):
        self._schema = schema
    def checkMatch(self, obj):
        self._schema.checkMatch(obj)

class Obj(Schema):
    """
       Matches a dict from specified keys to key-specific types.  Unrecognized
       keys are allowed.

       >>> s = Obj(a=AnyStr(), bc=Struct([Int(), Int()]))
       >>> s.matches({'a':"ZYYY", 'bc':[5,9]})
       True
       >>> s.matches({'a':"ZYYY", 'bc':[5,9], 'xx':5})
       True
       >>> s.matches({'a':"ZYYY", 'bc':[5,9,3]})
       False
       >>> s.matches({'a':"ZYYY"})
       False

    """
    def __init__(self, _objname="object", **d):
        self._objname = _objname
        self._required = d.items()


    def checkMatch(self, obj):
        for k,schema in self._required:
            try:
                item = obj[k]
            except KeyError:
                if not isinstance(schema, Opt):
                    raise thandy.FormatException("Missing key %s in %s"
                                                 %(k,self._objname))

            else:
                try:
                    schema.checkMatch(item)
                except thandy.FormatException, e:
                    raise thandy.FormatException("%s in %s.%s"
                                                 %(e,self._objname,k))


class Int(Schema):
    """
       Matches an integer.

       >>> s = Int()
       >>> s.matches(99)
       True
       >>> s.matches(False)
       False
       >>> s.matches(0L)
       True
       >>> s.matches("a string")
       False
       >>> Int(lo=10, hi=30).matches(25)
       True
       >>> Int(lo=10, hi=30).matches(5)
       False
    """
    def __init__(self, lo=-sys.maxint, hi=sys.maxint):
        self._lo = lo
        self._hi = hi
    def checkMatch(self, obj):
        if isinstance(obj, bool) or not isinstance(obj, (int, long)):
            # We need to check for bool as a special case, since bool
            # is for historical reasons a subtype of int.
            raise thandy.FormatException("Got %r instead of an integer"%obj)
        elif not (self._lo <= obj <= self._hi):
            raise thandy.FormatException("%r not in range [%r,%r]"
                                         %(obj, self._lo, self._hi))

class Bool(Schema):
    """
       Matches a boolean.

       >>> s = Bool()
       >>> s.matches(True) and s.matches(False)
       True
       >>> s.matches(11)
       False
    """
    def __init__(self):
        pass
    def checkMatch(self, obj):
        if not isinstance(obj, bool):
            raise thandy.FormatException("Got %r instead of a boolean"%obj)
