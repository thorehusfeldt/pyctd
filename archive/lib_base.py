import re
import sys
from abc import ABC
from collections import Counter
from fractions import Fraction

if hasattr(sys, "set_int_max_str_digits"):
	sys.set_int_max_str_digits(0)

class InvalidInput(Exception):
	pass

class _ValueType(ABC):
	__slots__ = ("value",)

	def __init__(self, value):
		self.value = value

	def __repr__(self):
		return f"{self.__class__.__name__}({repr(self.value)})"

	def __str__(self):
		return f"{self.__class__.__name__}({self.value})"

	def __bool__(self):
		raise TypeError(f"object of type '{self.__class__.__name__}' has no bool()")

	def __invert__(self):
		raise TypeError(f"bad operand type for unary !: '{self.__class__.__name__}'")

class Boolean(_ValueType):
	__slots__ = ()

	@staticmethod
	def _check_combine_type(lhs, rhs):
		if lhs.__class__ != rhs.__class__:
			raise TypeError(f"cannot combine {lhs.__class__.__name__} and {rhs.__class__.__name__}")

	def __init__(self, value):
		assert isinstance(value, bool)
		super().__init__(value)

	def __bool__(self):
		return self.value

	def __invert__(self):
		return Boolean(not self.value)

	def __and__(self, other):
		Boolean._check_combine_type(self, other)
		return Boolean(self.value and other.value)

	def __or__(self, other):
		Boolean._check_combine_type(self, other)
		return Boolean(self.value or other.value)

class _CompareableValue(_ValueType, ABC):
	__slots__ = ()

	@staticmethod
	def _check_compare_type(lhs, rhs):
		if lhs.__class__ != rhs.__class__:
			raise TypeError(f"cannot compare {lhs.__class__.__name__} and {rhs.__class__.__name__}")

	def __hash__(self):
		return hash(self.value)

	def __eq__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return Boolean(self.value == other.value)

	def __ne__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return Boolean(self.value != other.value)

	def __lt__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return Boolean(self.value < other.value)

	def __le__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return Boolean(self.value <= other.value)

	def __ge__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return Boolean(self.value >= other.value)

	def __gt__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return Boolean(self.value > other.value)

class String(_CompareableValue):
	__slots__ = ()

	def __init__(self, value):
		assert isinstance(value, str)
		super().__init__(value)

class Number(_CompareableValue):
	__slots__ = ()

	@staticmethod
	def _check_combine_type(lhs, rhs):
		if lhs.__class__ != rhs.__class__:
			raise TypeError(f"cannot combine {lhs.__class__.__name__} and {rhs.__class__.__name__}")

	def __init__(self, value):
		assert isinstance(value, (int, Fraction))
		super().__init__(value)

	def is_integer(self):
		# we check the type, not the value!
		return isinstance(self.value, int)

	def __index__(self):
		if not self.is_integer():
			raise TypeError("expected integer but got float")
		return self.value

	def __int__(self):
		if not self.is_integer():
			raise TypeError("expected integer but got float")
		return self.value

	def __neg__(self):
		return Number(-self.value)

	def __add__(self, other):
		Number._check_combine_type(self, other)
		return Number(self.value + other.value)

	def __sub__(self, other):
		Number._check_combine_type(self, other)
		return Number(self.value - other.value)

	def __mul__(self, other):
		Number._check_combine_type(self, other)
		return Number(self.value * other.value)

	def __mod__(self, other):
		Number._check_combine_type(self, other)
		if self.is_integer() and other.is_integer():
			res = self.value % other.value
			if res != 0 and (self.value < 0) != (other.value < 0):
				res -= other.value
			return Number(res)
		else:
			#seems to be an error in Checktestdata
			raise TypeError(f"can only perform modulo on integers")
			#return Number(self.value % other.value)

	def __truediv__(self, other):
		Number._check_combine_type(self, other)
		if self.is_integer() and other.is_integer():
			res = abs(self.value) // abs(other.value)
			if (self.value < 0) != (other.value < 0):
				res = -res
			return Number(res)
		else:
			return Number(self.value / other.value)

	def __pow__(self, other):
		if not other.is_integer() or other.value < 0 or other.value.bit_length() > sys.maxsize.bit_length() + 1:
			raise TypeError(f"exponent must be an unsigned long")
		return Number(self.value ** other.value)

class VarType:
	__slots__ = ("name", "data", "entries", "value_count")

	def __init__(self, name):
		self.name = name
		self.data = None
		self.entries = {}
		self.value_count = Counter()

	def reset(self):
		self.data = None
		self.entries = {}
		self.value_count = Counter()

	def __getitem__(self, key):
		if key == None:
			if self.entries:
				raise TypeError(f"{self.name} is an array")
			if self.data is None:
				raise TypeError(f"{self.name} is not assigned")
			return self.data
		else:
			if self.data is not None:
				raise TypeError(f"{self.name} is not an array")
			if key not in self.entries:
				raise TypeError(f"missing key in {self.name}")
			return self.entries[key]

	def __setitem__(self, key, value):
		# TODO: handle var_a[None] = var_b[None]?
		assert isinstance(value, _ValueType), self.name
		if key == None:
			if self.entries:
				raise TypeError(f"cannot replace array {self.name} with single value")
			self.data = value
		else:
			if self.data is not None:
				raise TypeError(f"{self.name} is not an array")
			for key_part in key:
				# Checktestdata seems to enforce integers here
				if not isinstance(key_part, Number) or not key_part.is_integer():
					raise TypeError(f"key for {self.name} must be integer(s)")
			if key in self.entries:
				self.value_count[self.entries[key]] -= 1
			self.entries[key] = value
			self.value_count[value] += 1

def assert_array(method, arg):
	if not isinstance(arg, VarType):
		raise TypeError(f"{method} cannot be invoked with {arg.__class__.__name__}")
	if arg.data is not None:
		raise TypeError(f"{method} must be invoked with an array, but {arg.name} is a value")

def assert_type(method, arg, t):
	if not isinstance(arg, t):
		raise TypeError(f"{method} cannot be invoked with {arg.__class__.__name__}")

def msg_text(text):
	special = {
		" ": "<SPACE>",
		"\n": "<NEWLINE>",
		"": "<EOF>",
	}
	return special.get(text, text)
