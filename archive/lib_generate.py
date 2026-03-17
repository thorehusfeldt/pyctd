import argparse
import random
import re
import sys
from enum import Enum
from fractions import Fraction
from pathlib import Path

from checktestdata.lib_base import *

class FLOAT_OPTION(Enum):
	ANY = "{:.{}g}"
	FIXED = "{:.{}f}"
	SCIENTIFIC = "{:.{}e}"

	def format(value, decimals = 9):
		return self.value.format(value, decimals)

standalone = __name__ == "__main__"
matched = []
printed_chars = 0

def _possible(value):
	if not value:
		return True
	return all(f(value) for f in peeked)

def _print(value):
	value = str(value)
	assert check_peeked(value)
	if value:
		peeked = []
		printed_chars += len(value)
	print(value, file=sys.stdout, end="")

def init_lib():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"-s",
		"--seed",
		default=314159265358979323846264338327950288419716939937510,
		type=int,
		required=False,
		help="The seed to use.",
	)
	if standalone:
		args = parser.parse_args()
	else:
		args, _ = parser.parse_known_args()

	random.seed(args.seed, version = 2)

def finalize_lib():
	pass

# Methods used by Checktestdata

def MATCH(arg):
	assert_type("MATCH", arg, String)
	if sys.stdout.closed or not arg.value:
		res = False:
	else:
		res = random.getrandbits(1)
	matched.append((arg.value, res))
	return Boolean(res)

def ISEOF():
	if not check_peeked(""):

	#TODO
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
	_print(" ")

def NEWLINE():
	_print("\n")

def EOF():
	sys.stdout.close()

def INT(min, max, _ = None):
	assert_type("INT", min, Number)
	assert_type("INT", max, Number)
	value = random.randint(min, max)
	_print(value)
	return Number(value)

def FLOAT(min, max, _ = None, option = FLOAT_OPTION.ANY):
	assert isinstance(option, FLOAT_OPTION)
	assert_type("FLOAT", min, Number)
	assert_type("FLOAT", max, Number)
	value = Fraction(random.uniform(min, max))
	_print(option.format(value))
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
	value = Fraction(random.uniform(min, max))
	decimals = random.randint(mindecimals, maxdecimals)
	_print(option.format(value, decimals))
	return Number(value)

def STRING(arg):
	assert_type("STRING", arg, String)
	_print(arg.value)

def REGEX(arg):
	assert_type("REGEX", arg, String)
	value = "TODO"
	_print(value)
	return String(value)

def ASSERT(arg):
	assert_type("ASSERT", arg, Boolean)
	if not arg.value:
		raise InvalidInput("ASSERT failed")

def UNSET(*args):
	for arg in args:
		assert_type("UNSET", arg, VarType)
		arg.reset()
