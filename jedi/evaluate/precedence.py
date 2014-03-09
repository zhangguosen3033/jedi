"""
Handles operator precedence.
"""

from jedi.parser import representation as pr
from jedi import debug
from jedi.common import PushBackIterator


class PythonGrammar(object):
    """
    Some kind of mirror of http://docs.python.org/3/reference/grammar.html.
    """

    class MultiPart(str):
        def __new__(cls, first, second):
            self = str.__new__(cls, first)
            self.second = second
            return self

        def __str__(self):
            return str.__str__(self) + ' ' + self.second

    FACTOR = '+', '-', '~'
    POWER = '**',
    TERM = '*', '/', '%', '//'
    ARITH_EXPR = '+', '-'

    SHIFT_EXPR = '<<', '>>'
    AND_EXPR = '&',
    XOR_EXPR = '^',
    EXPR = '|',

    COMPARISON = ('<', '>', '==', '>=', '<=', '!=', 'in',
                  MultiPart('not', 'in'), MultiPart('is', 'not'), 'is')

    NOT_TEST = 'not',
    AND_TEST = 'and',
    OR_TEST = 'or',

    #TEST = or_test ['if' or_test 'else' test] | lambdef

    SLICE = ':',
    ORDER = (POWER, TERM, ARITH_EXPR, SHIFT_EXPR, AND_EXPR, XOR_EXPR,
             EXPR, COMPARISON, AND_TEST, OR_TEST, SLICE)

    FACTOR_PRIORITY = 0  # highest priority
    LOWEST_PRIORITY = len(ORDER)
    NOT_TEST_PRIORITY = LOWEST_PRIORITY - 3  # priority only lower for `and`/`or`
    SLICE_PRIORITY = LOWEST_PRIORITY - 1  # priority only lower for `and`/`or`


class Precedence(object):
    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right

    def parse_tree(self, strip_literals=False):
        def process(which):
            try:
                which = which.parse_tree(strip_literals)
            except AttributeError:
                pass
            if strip_literals and isinstance(which, pr.Literal):
                which = which.value
            return which

        return (process(self.left), self.operator, process(self.right))

    def __repr__(self):
        return '(%s %s %s)' % (self.left, self.operator, self.right)


def create_precedence(expression_list):
    iterator = PushBackIterator(expression_list)
    return _check_operator(iterator)


def _syntax_error(element, msg='SyntaxError in precedence'):
    debug.warning('%s: %s, %s' % (msg, element, element.start_pos))


def _get_number(iterator, priority=PythonGrammar.LOWEST_PRIORITY):
    el = next(iterator)
    if isinstance(el, pr.Operator):
        if el in PythonGrammar.FACTOR:
            right = _get_number(iterator, PythonGrammar.FACTOR_PRIORITY)
        elif el in PythonGrammar.NOT_TEST \
                and priority >= PythonGrammar.NOT_TEST_PRIORITY:
            right = _get_number(iterator, PythonGrammar.NOT_TEST_PRIORITY)
        elif el in PythonGrammar.SLICE \
                and priority >= PythonGrammar.SLICE_PRIORITY:
            iterator.push_back(el)
            return None
        else:
            _syntax_error(el)
            return _get_number(iterator, priority)
        return Precedence(None, el, right)
    else:
        return el


def _check_operator(iterator, priority=PythonGrammar.LOWEST_PRIORITY):
    try:
        left = _get_number(iterator, priority)
    except StopIteration:
        return None

    for el in iterator:
        if not isinstance(el, pr.Operator):
            _syntax_error(el)
            continue

        operator = None
        for check_prio, check in enumerate(PythonGrammar.ORDER):
            if check_prio >= priority:
                # respect priorities.
                iterator.push_back(el)
                return left

            try:
                match_index = check.index(el)
            except ValueError:
                continue

            match = check[match_index]
            if isinstance(match, PythonGrammar.MultiPart):
                next_tok = next(iterator)
                if next_tok != match.second:
                    iterator.push_back(next_tok)
                    if el == 'is':  # `is not` special case
                        match = 'is'
                    else:
                        continue

            operator = match
            break

        if operator is None:
            _syntax_error(el)
            continue

        if operator == '**':
            check_prio += 1  # to the power of is right-associative
        right = _check_operator(iterator, check_prio)
        if right is None and not operator in PythonGrammar.SLICE:
            _syntax_error(iterator.current, 'SyntaxError operand missing')
        else:
            left = Precedence(left, str(operator), right)
    return left