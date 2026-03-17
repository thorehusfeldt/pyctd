import decimal
import re
from tokenizer import Token, TokenType
from lib import Boolean, String, Number, VarType

class ParserException(Exception):
	def __init__(self, msg, token):
		super().__init__(msg)
		self.token = token

ESCAPE_REGEX = re.compile(r'\\([0-7]{1,3}|[\n\\"ntrb])', re.DOTALL | re.MULTILINE)

def parse_string(token):
	assert token.type == TokenType.STRING
	def replace(match):
		text = match.groups()[0]
		if text == "\n":
			return ""
		if text in '\\"':
			return text
		if text in 'ntrb':
			return f"\\{text}".encode().decode("unicode_escape")
		# pythons unicode_escape decode warns for values > 3FF
		return chr(int(text, 8))
	text = ESCAPE_REGEX.sub(replace, token.text())
	assert len(text) >= 2
	assert text[0] == '"'
	assert text[-1] == '"'
	return text[1:-1]

class Comment:
	def __init__(self, tokens):
		self.tokens = tokens

	def __str__(self):
		comment = "".join(str(t) for t in self.tokens)
		return f"# {comment}"

class Command:
	def __init__(self, token, arguments = None):
		self.token = token
		self.arguments = arguments or []

	def __str__(self):
		args = ", ".join([str(arg) for arg in self.arguments])
		parts =[self.token, "(", *args, ")"]
		return "".join(map(str, parts))

class Variable:
	def __init__(self, name, arguments = None):
		self.name = name
		self.arguments = arguments or None

	def __str__(self):
		if self.arguments:
			args = ", ".join(map(str, self.arguments))
			return f"{self.name}[{args},]"
		else:
			#return str(self.token)
			return f"{self.name}[None]"

class Assignment:
	def __init__(self, lhs, rhs):
		self.lhs = lhs if isinstance(lhs, list) else [lhs]
		self.rhs = rhs if isinstance(lhs, list) else [rhs]
		assert(len(self.lhs) == len(self.rhs))

	def __str__(self):
		lhs = ", ".join(map(str, self.lhs))
		rhs = ", ".join(map(str, self.rhs))
		return f"{lhs} = {rhs}"

class Expression:
	def __init__(self, parts):
		self.parts = parts

	def __str__(self):
		return "".join(map(str, self.parts))

class BlockBegin:
	def __init__(self, command):
		self.command = command

	def __str__(self):
		return f"{self.command}:"

class If:
	def __init__(self, condition):
		self.condition = condition

	def __str__(self):
		return f"if {self.condition}:"

class For:
	def __init__(self, range, variable = "_"):
		self.range = range
		self.variable = variable

	def __str__(self):
		return f"for {self.variable} in {self.range}:"

def _ellipsis(*args):
	res = [*args]
	res.append(res)
	return res

class Parser:
	def __init__(self, tokens, debug = False):
		self.tokens = tokens
		self.debug = debug
		self.lines = None
		self.variables = None
		self.constants = None

	def _add_debug_comment(self, indent):
		if self.debug and self.tokens.get_buffered():
			self.lines.append((indent, Comment(self.tokens.get_buffered(clear = True))))

	def add_line(self, indent, line):
		self._add_debug_comment(indent)
		self.lines.append((indent, line))

	def add_constant(self, token):
		value = None
		match token.type:
			case TokenType.INTEGER:
				value = Number(int(token.text()))
			case TokenType.FLOAT:
				value = Number(decimal.Decimal(token.text()))
			case TokenType.STRING:
				value = String(parse_string(token))
			case _:
				assert False
		name = f"const_{len(self.constants)}"
		self.constants[name] = value
		return name

	def add_variable(self, token):
		assert token.type == TokenType.VARNAME
		name = f"var_{token.text()}"
		if name not in self.variables:
			self.variables[name] = VarType(token.text())
		return name

	SIGNATURES = {
		# tests
		"MATCH": ["_value"],
		"ISEOF": None,
		"UNIQUE": _ellipsis("_varname"),
		"INARRAY": ["_value", "_varname"],
		# functions
		"STRLEN": ["_value"],
		# commands
		"SPACE": None,
		"NEWLINE": None,
		"EOF": None,
		"INT": ["_expr", "_expr", ["_constraint_variable"]],
		"FLOAT": ["_expr", "_expr", ["_constraint_variable", [TokenType.OPTION]]],
		"FLOATP": ["_expr", "_expr", "_value", "_value", ["_constraint_variable", [TokenType.OPTION]]],
		"STRING": ["_value"],
		"REGEX": ["_value", ["_variable"]],
		"ASSERT": ["_test_expr"],
		"SET": _ellipsis("_set_argument"),
		"UNSET": _ellipsis("_varname"),
		# control flow
		"REP": ["_expr", ["_command"]],
		"REPI": ["_variable", "_expr", ["_command"]],
		"WHILE": ["_test_expr", ["_command"]],
		"WHILEI": ["_variable", "_test_expr", ["_command"]],
		"IF": ["_test_expr"],
	}

	def _parse_signature(self, token):
		parsed_args = []
		variable = None
		def recurse(args):
			nonlocal variable
			for i, arg in enumerate(args):
				optional = isinstance(arg, list)
				if i == 0:
					assert not optional
				else:
					has_more = self.tokens.has(type = TokenType.COMMA)
					if not has_more and optional:
						break
					self.tokens.pop(expected_type = TokenType.COMMA)

				if optional:
					recurse(arg)
				elif arg == TokenType.OPTION:
					parsed_args.append(f"FLOAT_REGEX.{self.tokens.pop(expected_type = TokenType.OPTION).text()}")
				elif arg in ["_variable", "_constraint_variable"]:
					assert variable is None
					variable = self._variable()
					if arg == "_constraint_variable":
						constraint = self.variables[variable.name].name
						parsed_args.append(repr(constraint));
				elif isinstance(arg, str):
					parsed_args.append(getattr(self, arg)())
				else:
					assert False, f"signature error: {arg}"

		args = Parser.SIGNATURES[token.text()]
		if args is not None:
			self.tokens.pop(expected_type = TokenType.OPENPAR)
			recurse(args)
			self.tokens.pop(expected_type = TokenType.CLOSEPAR)
		return parsed_args, variable

	def _set_argument(self):
		lhs = self._variable()
		self.tokens.pop(expected_type = TokenType.ASSIGN)
		rhs = self._expr()
		return Assignment(lhs, rhs)

	def _command(self):
		token = self.tokens.pop(expected_type = TokenType.COMMAND)
		args, variable = self._parse_signature(token)
		if token.text() == "SET":
			assert variable is None
			assert all(isinstance(a, Assignment) for a in args)
			lhs = sum([a.lhs for a in args], [])
			rhs = sum([a.rhs for a in args], [])
			command = Assignment(lhs, rhs)
		else:
			command = Command(token, args)
			if variable is not None:
				command = Assignment(variable, command)
		return command

	def _function(self):
		token = self.tokens.pop(expected_type = TokenType.FUNCTION)
		args, variable = self._parse_signature(token)
		assert variable is None
		return Command(token, args)

	def _test(self):
		token = self.tokens.pop(expected_type = TokenType.TEST)
		args, variable = self._parse_signature(token)
		assert variable is None
		return Command(token, args)

	def _varname(self):
		token = self.tokens.pop(expected_type = TokenType.VARNAME)
		name = self.add_variable(token)
		return name

	def _variable(self):
		token = self.tokens.pop(expected_type = TokenType.VARNAME)
		args = None
		if self.tokens.has(type = TokenType.OPENBRACKET):
			self.tokens.pop()
			args = [self._expr()]
			while self.tokens.has(type = TokenType.COMMA):
				self.tokens.pop()
				args.append(self._expr())
			self.tokens.pop(expected_type = TokenType.CLOSEBRACKET)
		name = self.add_variable(token)
		return Variable(name, args)

	def _value(self):
		token = self.tokens.peek()
		match token.type:
			case TokenType.STRING | TokenType.INTEGER | TokenType.FLOAT:
				constant = self.add_constant(self.tokens.pop())
				return constant
			case TokenType.VARNAME:
				return self._variable()
			case TokenType.FUNCTION:
				return self._function()
			case _:
				raise ParserException(f"expected expression, but got '{token.text()}'", token)

	def _expr(self):
		parts = []
		def recurse():
			while True:
				nonlocal parts
				while self.tokens.has(type = TokenType.MATH, text = "-"):
					parts.append(self.tokens.pop())
				token = self.tokens.peek()
				match token.type:
					case TokenType.STRING | TokenType.INTEGER | TokenType.FLOAT:
						constant = self.add_constant(self.tokens.pop())
						parts.append(constant)
					case TokenType.OPENPAR:
						parts.append(self.tokens.pop())
						recurse()
						parts.append(self.tokens.pop(expected_type = TokenType.CLOSEPAR))
					case TokenType.VARNAME:
						parts.append(self._variable())
					case TokenType.FUNCTION:
						parts.append(self._function())
					case _:
						raise ParserException(f"expected expression, but got '{token.text()}'", token)
				if not self.tokens.has(type=TokenType.MATH):
					return
				op = self.tokens.pop().text()
				to_python = {"^": "**"}
				parts.append(to_python.get(op, op))
		recurse()
		return Expression(parts)

	def _test_expr(self):
		parts = []
		def recurse():
			nonlocal parts
			while True:
				while self.tokens.has(type = TokenType.NOT):
					self.tokens.pop()
					# we use inversion to represent logical not
					parts.append("~")
				token = self.tokens.peek()
				match token.type:
					case TokenType.OPENPAR:
						parts.append(self.tokens.pop())
						recurse()
						parts.append(self.tokens.pop(expected_type = TokenType.CLOSEPAR))
					case TokenType.TEST:
						parts.append(self._test())
					case TokenType.STRING | TokenType.INTEGER | TokenType.FLOAT | TokenType.VARNAME | TokenType.FUNCTION:
						lhs = self._expr()
						compare = self.tokens.pop(expected_type = TokenType.COMPARE)
						rhs = self._expr()
						parts += ["(", lhs, compare, rhs,")"]
					case _:
						raise ParserException(f"expected expression, but got '{token.text()}'", token)
				if not self.tokens.has(type=TokenType.LOGICAL):
					return
				op = self.tokens.pop().text()
				to_python = {
					"&&": " and ",
					"||": " or "
				}
				parts.append(to_python.get(op, op))
		recurse()
		return Expression(parts)

	def _parse_block(self, indent):
		token = self.tokens.pop(expected_type = TokenType.CONTROLFLOW)
		args, variable = self._parse_signature(token)

		def handle_loop_args(loop_var):
			if len(args) > 1:
				self.add_line(indent + 1, If(f"{loop_var} > 0"))
				self.add_line(indent + 2, args[1])
			if variable is not None:
				self.add_line(indent + 1, Assignment(variable, Command("Number", loop_var)))

		match token.text():
			case "REP" | "REPI":
				loop_var = "_"
				self.add_line(indent, For(f"range({args[0]})", loop_var))
				handle_loop_args(loop_var)
			case "WHILE" | "WHILEI":
				loop_var = "_"
				self.add_line(indent, For("count(0)", loop_var))
				self.add_line(indent + 1, If(Expression(["not ", "(", args[0], ")"])))
				self.add_line(indent + 2, "break")
				handle_loop_args(loop_var)
			case "IF":
				assert variable is None
				self.add_line(indent, If(*args))
			case _:
				assert False

		def handle_block():
			count = self._parse_commands(indent + 1)
			if not count:
				self.add_line(indent + 1, "pass")

		handle_block()
		if token.text() == "IF" and self.tokens.has(type = TokenType.ELSE):
			self.tokens.pop(expected_type = TokenType.ELSE)
			self.add_line(indent, BlockBegin("else"))
			handle_block()
		self.tokens.pop(expected_type = TokenType.END)
		self._add_debug_comment(indent)

	def _parse_command(self, indent):
		self.add_line(indent, self._command())

	def _parse_commands(self, indent):
		count = 0
		while not self.tokens.empty():
			token = self.tokens.peek()
			match token.type:
				case TokenType.ELSE | TokenType.END:
					return count
				case TokenType.CONTROLFLOW:
					count += 1
					self._parse_block(indent)
				case TokenType.COMMAND:
					count += 1
					self._parse_command(indent)
				case _:
					raise ParserException(f"expected command, but got '{token.text()}'", token)
			
	def parse(self):
		if self.lines is None:
			self.lines = []
			self.variables = {}
			self.constants = {}
			self._parse_commands(0)
			if not self.tokens.empty():
				token = self.tokens.peek()
				assert token.type in [TokenType.ELSE, TokenType.END]
				raise ParserException(f"Unmatched '{token.text()}'", token)
			self.add_line(0, Command("EOF"))

	def python_code(self, standalone = False):
		self.parse()
		generated = [
			"from lib import *",
			"from itertools import count",
		]
		if standalone:
			generated.append("from decimal import Decimal")
			for name, value in self.constants.items():
				generated.append(f"{name} = {repr(value)}")
			for name, value in self.variables.items():
				generated.append(f"{name} = VarType({repr(value.name)})")
		generated.append("init_lib()")
		INDENT = "    "
		for indent, line in self.lines:
			generated.append(f"{INDENT * indent}{line}")
		generated.append("finalize_lib()")
		return "\n".join(generated) + "\n"

	def python_globals(self):
		return {**self.constants, **self.variables}


def parse(tokens, debug = False):
	parser = Parser(tokens, debug = debug)
	parser.parse()
	return parser
