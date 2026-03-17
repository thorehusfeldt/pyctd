import argparse
import re
import sys
from pathlib import Path

from tokenizer import tokenize
from parser import parse, Command, ParserException

parser = argparse.ArgumentParser(description="Checktestdata tool written in Python.")
parser.add_argument(
	"ctd_file",
	metavar="ctd_file",
	type=Path,
	help="The .ctd checker source file"
)
parser.add_argument(
	"--debug",
	"-d",
	action="store_true",
	help="Print debug messages",
)
parser.add_argument(
	"--generate",
	"-g",
	action="store_true",
	help="Print debug messages",
)
parser.add_argument(
	"--constraints_file",
	dest="constraints_file",
	metavar="constraints_file",
	default=None,
	type=Path,
	required=False,
	help="The file to write constraints to file to use.",
)

config = parser.parse_args()

def debug(*args, **kwargs):
	if not config.debug:
		return
	kwargs.setdefault("file", sys.stderr)
	print(*args, **kwargs)

try:
	debug(f"Reading: {config.ctd_file}")
	raw_ctd = config.ctd_file.read_text()
	debug(f"Generating tokens")
	tokens = tokenize(raw_ctd)
	debug(f"Parsing tokens")
	parser = parse(tokens, debug = config.debug)
	debug(f"Generating python code")
	if config.generate:
		python_code = parser.python_code(standalone = True)
		file = Path("generated.py")
		debug(f"Writing python code to: {file}")
		file.write_text(python_code)
	else:
		python_code = parser.python_code()
		python_globals = parser.python_globals()
		debug(f"Compiling generated python code")
		compiled = compile(python_code, "<generated from ctd>", "exec")
		debug(f"Running generated code")
		try:
			exec(compiled, python_globals)
		except Exception as e:
			print(e, file=sys.stderr)
			sys.exit(1)
	debug(f"Done")
except Exception as e:
	print(e, file=sys.stderr)
	sys.exit(2)
