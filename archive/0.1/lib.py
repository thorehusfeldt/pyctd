import argparse
import decimal
import math
import re
import sys
from abc import ABC
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

if hasattr(sys, "set_int_max_str_digits"):
	sys.set_int_max_str_digits(0)

decimal.setcontext(decimal.Context(
	prec=decimal.MAX_PREC,
	rounding=decimal.ROUND_HALF_EVEN,
	Emin=decimal.MIN_EMIN,
	Emax=decimal.MAX_EMAX,
	capitals=1,
	clamp=0,
	traps=[
		decimal.Clamped,
		decimal.DivisionByZero,
		decimal.Inexact,
		decimal.InvalidOperation,
		decimal.Rounded,
		decimal.Subnormal,
	],
))

class _ValueType(ABC):
	def __init__(self, value):
		self.value = value

	def __repr__(self):
		return f"{self.__class__.__name__}({repr(self.value)})"

	def __str__(self):
		return f"{self.__class__.__name__}({self.value})"

	def __bool__(self):
		raise TypeError(f"object of type '{self.__class__.__name__}' has no bool()")

	def __eq__(self, other):
		return self.value == other.value

	def __ne__(self, other):
		return self.value != other.value

	def __hash__(self):
		return hash(self.value)

class _CompareableValue(_ValueType, ABC):
	@staticmethod
	def _check_compare_type(lhs, rhs):
		if lhs.__class__ != rhs.__class__:
			raise TypeError(f"cannot compare {lhs.__class__.__name__} and {rhs.__class__.__name__}")

	def __lt__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return self.value < other.value

	def __le__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return self.value <= other.value

	def __ge__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return self.value >= other.value

	def __gt__(self, other):
		_CompareableValue._check_compare_type(self, other)
		return self.value > other.value

class Boolean(_ValueType):
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

class String(_CompareableValue):
	def __init__(self, value):
		assert isinstance(value, str)
		super().__init__(value)

class Number(_CompareableValue):
	@staticmethod
	def _check_combine_type(lhs, rhs):
		if lhs.__class__ != rhs.__class__:
			raise TypeError(f"cannot combine {lhs.__class__.__name__} and {rhs.__class__.__name__}")

	def __init__(self, value):
		assert isinstance(value, (int, decimal.Decimal))
		super().__init__(value)

	def is_integer(self):
		# we check the type, not the value!
		return isinstance(self.value, int)

	def __index__(self):
		if not self.is_integer():
			raise RuntimeError("expected integer but got float")
		return self.value

	def __int__(self):
		if not self.is_integer():
			raise RuntimeError("expected integer but got float")
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
			if res > 0 and (self.value < 0) != (other.value < 0):
				res -= other.value
			return Number(res)
		else:
			#seems to be an error in Checktestdata
			raise RuntimeError(f"can only perform modulo on integers")
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

	def __xor__(self, other):
		if not other.is_integer() or other.value < 0 or other.value.bit_length() > sys.maxsize.bit_length() + 1:
			raise TypeError(f"exponent must be an unsigned long")
		return Number(self.value ** other.value)

class VarType:
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
				raise RuntimeError(f"{self.name} is an array")
			if self.data is None:
				raise RuntimeError(f"{self.name} is not assigned")
			return self.data
		else:
			if self.data is not None:
				raise RuntimeError(f"{self.name} is not an array")
			if key not in self.entries:
				raise RuntimeError(f"missing key in {self.name}")
			return self.entries[key]

	def __setitem__(self, key, value):
		# TODO: handle var_a[None] = var_b[None]?
		assert isinstance(value, _ValueType), self.name
		if key == None:
			if self.entries:
				raise RuntimeError(f"cannot replace array {self.name} with single value")
			self.data = value
		else:
			if self.data is not None:
				raise RuntimeError(f"{self.name} is not an array")
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
		TypeError(f"{method} cannot be invoked with {arg.__class__.__name__}")
	if arg.data is not None:
		TypeError(f"{method} must be invoked with an array, but {arg.name} is a value")

def assert_type(method, arg, t):
	if not isinstance(arg, t):
		TypeError(f"{method} cannot be invoked with {arg.__class__.__name__}")

def msg_text(text):
	special = {
		" ": "<SPACE>",
		"\n": "<NEWLINE>",
		"": "<EOF>",
	}
	return special.get(text, text)

INTEGER_REGEX = re.compile(r"0|-?[1-9][0-9]*")
FLOAT_PARTS = re.compile(r"-?([0-9]*)(\.[0-9]*)?([eE].*)?")
class FLOAT_REGEX(Enum):
	ANY = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
	FIXED = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
	SCIENTIFIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)")

	def msg(self):
		return "" if self == FLOAT_REGEX.ANY else self.name.lower()

@dataclass
class _Token:
	text: str
	line: int
	column: int

	def __str__(self):
		return self.text

	def __repr__(self):
		return f"{self.line}:{self.column}{{{self.text}}}"

class _Reader:
	def __init__(self, raw):
		self.raw = raw

		def generator():
			base_tokenizer = re.compile(r'[\s]|[^\s]*', re.DOTALL | re.MULTILINE)
			line = 1
			column = 1
			for match in base_tokenizer.finditer(self.raw):
				start = match.start()
				end = match.end()
				text = self.raw[start:end]
				
				yield _Token(text, line, column)
				if text == "\n":
					line += 1
					column = 1
				else:
					column += len(text)
			while True:
				yield _Token("", line, column)

		self.generator = generator()
		self.next = next(self.generator)

	def peek(self):
		return self.next

	def pop(self, expected = None):
		got, self.next = self.next, next(self.generator)
		if expected is not None and got.text != expected:
			msg = f"{got.line}:{got.column} got: {msg_text(got.text)}, but expected {msg_text(expected)}"
			raise RuntimeError(msg)
		return got

class Constraints:
	def __init__(self, file):
		self.file = file
		self.entries = {}

	def log(self, name, value, min_value, max_value):
		if self.file is None or name is None:
			return
		a, b, c, d, e, f = self.entries.get(name, (False, False, min_value, max_value, value, value))
		a |= value == min_value
		b |= value == max_value
		c = min(c, min_value)
		d = max(d, max_value)
		e = min(e, value)
		f = max(f, value)
		self.entries[name] = (a, b, c, d, e, f)

	def write(self):
		if self.file is None:
			return
		lines = []
		for name, entries in self.entries.items():
			a, b, c, d, e, f = entries
			lines.append(f"{name} {name} {int(a)} {int(b)} {c} {d} {e} {f}")
		self.file.write_text("\n".join(lines))

reader = None
constraints = None

def init_lib():
	global reader, constraints
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--constraints_file",
		dest="constraints_file",
		metavar="constraints_file",
		default=None,
		type=Path,
		required=False,
		help="The file to write constraints to file to use.",
	)
	args, unknown = parser.parse_known_args()
	constraints = Constraints(args.constraints_file)

	raw = sys.stdin.read()
	reader = _Reader(raw)

def finalize_lib():
	constraints.write()

# Methods used by Checktestdata

def MATCH(arg):
	assert_type("MATCH", arg, String)
	return Boolean(reader.peek().text[:1] in arg.value)

def ISEOF():
	return Boolean(reader.peek().text == "")

def UNIQUE(arg, *args):
	assert_array("UNIQUE", arg)
	for other in args:
		assert_array("UNIQUE", other)
		if arg.entries.keys() != other.entries.keys():
			raise RuntimeError(f"{arg.name} and {other.name} must have the same keys for UNIQUE")
	def make_entry(key):
		return (arg[key], *(other[key] for other in args))
	unique = {make_entry(key) for key in arg.entries.keys()}
	return Boolean(len(unique) == len(arg.entries))

def INARRAY(value, array):
	assert isinstance(value, _ValueType)
	assert_array("INARRAY", array)
	return Boolean(array.value_count[0] > 0)

def STRLEN(arg):
	assert_type("STRLEN", arg, String)
	return Number(len(arg.value))

def SPACE():
	reader.pop(expected = " ")

def NEWLINE():
	reader.pop(expected = "\n")

def EOF():
	reader.pop(expected = "")

def INT(min, max, constraint = None):
	assert_type("INT", min, Number)
	assert_type("INT", max, Number)
	raw = reader.pop()
	if not INTEGER_REGEX.fullmatch(raw.text):
		raise RuntimeError(f"{raw.line}:{raw.column} expected an integer but got {msg_text(raw.text)}")
	value = int(raw.text)
	if value < min.value or value > max.value:
		raise RuntimeError(f"{raw.line}:{raw.column} integer outside of range [{min}, {max}]")
	constraints.log(constraint, value, min.value, max.value)
	return Number(value)

def FLOAT(min, max, constraint = None, option = FLOAT_REGEX.ANY):
	assert isinstance(option, FLOAT_REGEX)
	assert_type("FLOAT", min, Number)
	assert_type("FLOAT", max, Number)
	raw = reader.pop()
	if not option.value.fullmatch(raw.text):
		raise RuntimeError(f"{raw.line}:{raw.column} expected a {option.msg()} float but got {msg_text(raw.text)}")
	value = decimal.Decimal(raw.text)
	if value < min.value or value > max.value:
		raise RuntimeError(f"{raw.line}:{raw.column} float outside of range [{min}, {max}]")
	constraints.log(constraint, value, min.value, max.value)
	return Number(value)

def FLOATP(min, max, mindecimals, maxdecimals, constraint = None, option = FLOAT_REGEX.ANY):
	assert isinstance(option, FLOAT_REGEX)
	assert_type("FLOATP", min, Number)
	assert_type("FLOATP", max, Number)
	assert_type("FLOATP", mindecimals, Number)
	assert_type("FLOATP", maxdecimals, Number)
	if not isinstance(mindecimals.value, int) and mindecimals.value >= 0:
		raise RuntimeError(f"FLOATP(mindecimals) must be a non-negative integer")
	if not isinstance(maxdecimals.value, int) and maxdecimals.value >= 0:
		raise RuntimeError(f"FLOATP(maxdecimals) must be a non-negative integer")
	raw = reader.pop()
	if not option.value.fullmatch(raw.text):
		raise RuntimeError(f"{raw.line}:{raw.column} expected a {option.msg()} float but got {msg_text(raw.text)}")
	leading, decimals, exponent = FLOAT_PARTS.fullmatch(raw.text).groups()
	decimals = 0 if decimals is None else len(decimals) - 1
	has_exp = exponent is not None
	if decimals < mindecimals.value or decimals > maxdecimals.value:
		raise RuntimeError(f"{raw.line}:{raw.column} float decimals outside of range [{min}, {max}]")
	if has_exp and (len(leading) != 1 or leading == "0"):
		raise RuntimeError(f"{raw.line}:{raw.column} scientific float should have exactly one non-zero before the decimal dot")
	value = decimal.Decimal(raw.text)
	if value < min.value or value > max.value:
		raise RuntimeError(f"{raw.line}:{raw.column} float outside of range [{min}, {max}]")
	constraints.log(constraint, value, min.value, max.value)
	return Number(value)

def STRING(arg):
	assert_type("STRING", arg, String)
	reader.pop(expected = arg.value)

def REGEX(arg):
	assert_type("REGEX", arg, String)
	# TODO we currently tokenize the input ourself
	# => there is never any whitespace that could be matched
	# => every other call must be SPACE/NEWLINE, it is not possible to do something like REGEX() REGEX()...
	got = reader.pop()
	if not re.fullmatch(arg.value, got.text, re.DOTALL | re.MULTILINE):
		msg = f"{got.line}:{got.column} got: {msg_text(got.text)}, but expected {arg.value}"
		raise RuntimeError(msg)
	return String(got.text)

def ASSERT(arg):
	assert_type("ASSERT", arg, Boolean)
	if not arg.value:
		raise RuntimeError("ASSERT failed")

def UNSET(*args):
	for arg in args:
		assert_type("UNSET", arg, VarType)
		arg.reset()
