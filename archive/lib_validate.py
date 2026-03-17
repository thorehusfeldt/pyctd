import argparse
import re
import sys
from enum import Enum
from fractions import Fraction
from pathlib import Path

from checktestdata.lib_base import *

INTEGER_REGEX = re.compile(r"0|-?[1-9][0-9]*")
FLOAT_PARTS = re.compile(r"-?([0-9]*)(?:\.([0-9]*))?(?:[eE](.*))?")
class FLOAT_OPTION(Enum):
	ANY = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?(?:0|[1-9][0-9]*))?")
	FIXED = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
	SCIENTIFIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?(?:0|[1-9][0-9]*))")

	def msg(self):
		return "float" if self == FLOAT_OPTION.ANY else f"{self.name.lower()} float"

class _Reader:
	def __init__(self, raw):
		self.raw = raw
		self.pos = 0
		self.line = 1
		self.column = 1
		self.space_tokenizer = re.compile(r'[\s]|[^\s]*', re.DOTALL | re.MULTILINE)

	def _advance(self, text):
		self.pos += len(text)
		newline = text.find("\n")
		if newline >= 0:
			self.line += text.count("\n")
			self.column = len(text) - newline
		else:
			self.column += len(text)

	def peek_char(self):
		return self.raw[self.pos:self.pos+1]

	def peek_until_space(self):
		return self.space_tokenizer.match(self.raw, self.pos).group()

	def pop_string(self, expected):
		if not self.raw.startswith(expected, self.pos):
			got = self.raw[self.pos:self.pos+len(expected)]
			msg = f"{self.line}:{self.column} got: {msg_text(got)}, but expected {msg_text(expected)}"
			raise InvalidInput(msg)
		self._advance(expected)

	def pop_regex(self, regex):
		match = regex.match(self.raw, self.pos)
		if not match:
			got = self.peek_until_space()
			msg = f"{self.line}:{self.column} got: {msg_text(got)}, but expected '{regex.pattern}'"
			raise InvalidInput(msg)
		text = match.group()
		self._advance(text)
		return text

	def pop_pattern(self, pattern):
		regex = re.compile(pattern, re.DOTALL | re.MULTILINE)
		return self.pop_regex(regex)

	def pop_token(self, regex):
		match = regex.match(self.raw, self.pos)
		if not match:
			return None, self.line, self.column
		else:
			text = match.group()
			line, column = self.line, self.column
			self.pos += len(text)
			if text == "\n":
				self.line += 1
				self.column = 1
			else:
				self.column += len(text)
			return text, line, column

class Constraints:
	__slots__ = ("file", "entries")

	def __init__(self, file):
		self.file = file
		self.entries = {}

	def log(self, name, value, min_value, max_value):
		if self.file is None or name is None:
			return
		a, b, c, d, e, f = self.entries.get(name, (False, False, min_value, max_value, value, value))
		a |= value == min_value
		b |= value == max_value
		c = min(c, value)
		d = max(d, value)
		e = min(e, min_value)
		f = max(f, max_value)
		self.entries[name] = (a, b, c, d, e, f)

	def write(self):
		if self.file is None:
			return
		lines = []
		def to_string(value):
			if isinstance(value, bool):
				return str(int(value))
			if isinstance(value, Fraction):
				return str(float(value))
			return str(value)
		for name, entries in self.entries.items():
			string = " ".join(map(to_string, entries))
			lines.append(f"{name} {name} {string}")
		self.file.write_text("\n".join(lines))

reader = None
constraints = None
standalone = __name__ == "__main__"

def init_lib():
	if standalone:
		def excepthook(exc_type, exc_value, exc_traceback):
			if exc_type == InvalidInput:
				print(exc_value, file=sys.stderr)
				sys.exit(43)
			else:
				sys.__excepthook__(exc_type, exc_value, exc_traceback)
				sys.exit(1)
		sys.excepthook = excepthook

	global reader, constraints
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--constraints_file",
		default=None,
		type=Path,
		required=False,
		help="The file to write constraints to file to use.",
	)
	if standalone:
		args = parser.parse_args()
	else:
		args, _ = parser.parse_known_args()

	constraints = Constraints(args.constraints_file)
	raw = sys.stdin.read()
	reader = _Reader(raw)

def finalize_lib():
	constraints.write()
	if __name__ == "__main__":
		sys.exit(42)

# Methods used by Checktestdata

def MATCH(arg):
	assert_type("MATCH", arg, String)
	char = reader.peek_char()
	if not char:
		return False
	return Boolean(char in arg.value)

def ISEOF():
	return Boolean(not reader.peek_char())

def UNIQUE(arg, *args):
	assert_array("UNIQUE", arg)
	for other in args:
		assert_array("UNIQUE", other)
		if arg.entries.keys() != other.entries.keys():
			raise InvalidInput(f"{arg.name} and {other.name} must have the same keys for UNIQUE")
	def make_entry(key):
		return (arg[key], *(other[key] for other in args))
	unique = {make_entry(key) for key in arg.entries.keys()}
	return Boolean(len(unique) == len(arg.entries))

def INARRAY(value, array):
	assert_array("INARRAY", array)
	return Boolean(array.value_count[value] > 0)

def STRLEN(arg):
	assert_type("STRLEN", arg, String)
	return Number(len(arg.value))

def SPACE():
	reader.pop_string(" ")

def NEWLINE():
	reader.pop_string("\n")

def EOF():
	got = reader.peek_char()
	if got:
		msg = f"{reader.line}:{reader.column} got: {msg_text(got)}, but expected {msg_text('')}"
		raise InvalidInput(msg)

def INT(min, max, constraint = None):
	assert_type("INT", min, Number)
	assert_type("INT", max, Number)
	text, line, column = reader.pop_token(INTEGER_REGEX)
	if text is None:
		got = reader.peek_until_space()
		raise InvalidInput(f"{line}:{column} expected an integer but got {msg_text(got)}")
	value = int(text)
	if value < min.value or value > max.value:
		raise InvalidInput(f"{line}:{column} integer {text} outside of range [{min.value}, {max.value}]")
	constraints.log(constraint, value, min.value, max.value)
	return Number(value)

def FLOAT(min, max, constraint = None, option = FLOAT_OPTION.ANY):
	assert isinstance(option, FLOAT_OPTION)
	assert_type("FLOAT", min, Number)
	assert_type("FLOAT", max, Number)
	text, line, column = reader.pop_token(option.value)
	if text is None:
		got = reader.peek_until_space()
		raise InvalidInput(f"{line}:{column} expected a {option.msg()} but got {msg_text(got)}")
	value = Fraction(text)
	if value < min.value or value > max.value:
		raise InvalidInput(f"{line}:{column} float {text} outside of range [{min.value}, {max.value}]")
	if text.startswith("-") and value == 0:
		raise InvalidInput(f"{line}:{column} float {text} should have no sign")
	constraints.log(constraint, value, min.value, max.value)
	return Number(value)

def FLOATP(min, max, mindecimals, maxdecimals, constraint = None, option = FLOAT_OPTION.ANY):
	assert isinstance(option, FLOAT_OPTION)
	assert_type("FLOATP", min, Number)
	assert_type("FLOATP", max, Number)
	assert_type("FLOATP", mindecimals, Number)
	assert_type("FLOATP", maxdecimals, Number)
	if not isinstance(mindecimals.value, int) and mindecimals.value >= 0:
		raise InvalidInput(f"FLOATP(mindecimals) must be a non-negative integer")
	if not isinstance(maxdecimals.value, int) and maxdecimals.value >= 0:
		raise InvalidInput(f"FLOATP(maxdecimals) must be a non-negative integer")
	text, line, column = reader.pop_token(option.value)
	if text is None:
		got = reader.peek_until_space()
		raise InvalidInput(f"{line}:{column} expected a {option.msg()} but got {msg_text(got)}")
	leading, decimals, exponent = FLOAT_PARTS.fullmatch(text).groups()
	decimals = 0 if decimals is None else len(decimals)
	has_exp = exponent is not None
	if decimals < mindecimals.value or decimals > maxdecimals.value:
		raise InvalidInput(f"{line}:{column} float decimals outside of range [{mindecimals.value}, {maxdecimals.value}]")
	if has_exp and (len(leading) != 1 or leading == "0"):
		raise InvalidInput(f"{line}:{column} scientific float should have exactly one non-zero before the decimal dot")
	value = Fraction(text)
	if value < min.value or value > max.value:
		raise InvalidInput(f"{line}:{column} float {text} outside of range [{min.value}, {max.value}]")
	if text.startswith("-") and value == 0:
		raise InvalidInput(f"{line}:{column} float {text} should have no sign")
	constraints.log(constraint, value, min.value, max.value)
	return Number(value)

def STRING(arg):
	assert_type("STRING", arg, String)
	reader.pop_string(arg.value)

def REGEX(arg):
	assert_type("REGEX", arg, String)
	return String(reader.pop_pattern(arg.value))

def ASSERT(arg):
	assert_type("ASSERT", arg, Boolean)
	if not arg.value:
		raise InvalidInput("ASSERT failed")

def UNSET(*args):
	for arg in args:
		assert_type("UNSET", arg, VarType)
		arg.reset()
