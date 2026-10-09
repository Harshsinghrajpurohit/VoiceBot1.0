import ast
import operator

_MAX_LENGTH = 80
_MAX_POWER = 8

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def calculate(expression: str) -> str:
    cleaned = expression.strip()
    if not cleaned or len(cleaned) > _MAX_LENGTH:
        return "That calculation is not allowed."
    try:
        tree = ast.parse(cleaned, mode="eval")
        value = _eval(tree.body)
    except ZeroDivisionError:
        return "I can't divide by zero."
    except (SyntaxError, ValueError):
        return "That calculation is not allowed."
    return "The answer is " + _format_number(value) + "."


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):
            raise ValueError("not a number")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        left = _eval(node.left)
        right = _eval(node.right)
        if abs(right) > _MAX_POWER:
            raise ValueError("power too large")
        return left ** right
    raise ValueError("not allowed")


def _format_number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def needs_calculator(text: str) -> bool:
    """True only when the request is an arithmetic expression."""
    lowered = text.lower()
    if not any(character.isdigit() for character in lowered):
        return False
    words = set(lowered.replace("?", " ").replace(".", " ").split())
    if words & {"plus", "minus", "times", "multiplied", "divided"}:
        return True
    for symbol in ("+", "*", "/"):
        if symbol in lowered:
            return True
    return False
