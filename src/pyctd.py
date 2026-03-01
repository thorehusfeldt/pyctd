import argparse
import re
import sys
import traceback
from pathlib import Path

from tokenizer import tokenize
from parser import parse, Command, ParserException

GENERATED_DEBUG_NAME = "<generated from ctd>"

def parse_args():
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
	    nargs="?",
	    const=Path("generated.py"),
	    default=None,
	    type=Path,
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

	return parser.parse_args()

def main():
	config = parse_args()

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
		parser = parse(tokens, debug_comments = config.debug)
		debug(f"Generating python code")
		if config.generate is not None:
			python_code = parser.python_code(standalone = True)
			file = config.generate
			debug(f"Writing python code to: {file}")
			file.write_text(python_code)
		else:
			python_code = parser.python_code()
			python_globals = parser.python_globals()
			debug(f"Compiling generated python code")
			compiled = compile(python_code, GENERATED_DEBUG_NAME, "exec")
			debug(f"Running generated code")
			try:
				exec(compiled, python_globals)
			except RuntimeError as e:
				print(e, file=sys.stderr)
				sys.exit(1)
			except Exception as e:
				print(e, file=sys.stderr)
				for frame in traceback.extract_tb(e.__traceback__):
					if frame.filename == GENERATED_DEBUG_NAME:
						line = parser.guess_line(python_code, frame.lineno)
						if line:
							print(f"Source {line[0].line}:{line[0].column}", file=sys.stderr)
							print("".join(map(str, line)))
						break
				sys.exit(2)
		debug(f"Done")
	except Exception as e:
		print(e, file=sys.stderr)
		sys.exit(2)
