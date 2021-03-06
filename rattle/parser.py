
import ast

import rply

from .lexer import lg
from .utils.parser import build_call, get_filter_func, get_lookup_name


pg = rply.ParserGenerator(
    [rule.name for rule in lg.rules],
    precedence=[
        ('left', ['COMMA']),
        ('right', ['ASSIGN']),
        ('left', ['PIPE']),
        ('left', ['AND', 'OR']),
        ('left', ['EQUAL', 'NEQUAL',
                  'LT', 'LTE', 'GT', 'GTE',
                  'IN', 'NOTIN',
                  'ISNOT', 'IS']),
        ('left', ['PLUS', 'MINUS']),
        ('left', ['MUL', 'DIV', 'MOD']),
        ('left', ['LSQB', 'RSQB']),
        ('left', ['DOT']),
        ('left', ['LPAREN', 'RPAREN']),
    ],
)

"""

arg     :   expr

arg_list    :   arg
            |   arg_list COMMA arg

expr    :   literal
        |   expr DOT NAME

        |   expr PLUS expr
        |   expr MINUS expr
        |   expr MUL expr
        |   expr DIV expr
        |   expr MOD expr

        |   expr EQUAL expr
        |   expr NEQUAL expr
        |   expr LT expr
        |   expr LTE expr
        |   expr GT expr
        |   expr GTE expr
        |   expr IN expr
        |   expr NOTIN expr
        |   expr ISNOT expr
        |   expr IS expr

        |   expr filter
        |   LPAREN expr RPAREN
        |   expr LSQB expr RSQB
        |   expr LPAREN RPAREN
        |   expr LPAREN arg_list RPAREN
        |   expr LPAREN kwarg_list RPAREN
        |   expr LPAREN arg_list COMMA kwarg_list RPAREN

filter  :   PIPE lookup_name
        |   PIPE lookup_name COLON literal
        |   PIPE lookup_name LPAREN RPAREN
        |   PIPE lookup_name LPAREN arg_list RPAREN
        |   PIPE lookup_name LPAREN kwarg_list RPAREN
        |   PIPE lookup_name LPAREN arg_list COMMA kwarg_list RPAREN

kwarg   :   NAME ASSIGN expr

kwarg_list  :   kwarg
            |   kwarg_list COMMA kwarg

literal :  name
        |  number
        |  string

lookup_name : NAME
            | lookup_name DOT NAME

name    :  NAME

number  :  NUMBER

string  :  STRING

"""

lg.ignore(r"\s+")


@pg.production('arg : expr')
def arg_expr(p):
    return p[0]


@pg.production('arg_list : arg')
def arg_list_arg(p):
    return p


@pg.production('arg_list : arg_list COMMA arg')
def arg_list_append(p):
    arg_list, _, arg = p
    arg_list.append(arg)
    return arg_list


@pg.production('expr : literal')
def expr_literal(p):
    return p[0]


@pg.production('expr : expr DOT NAME')
def expr_DOT_NAME(p):
    lterm, _, rterm = p
    return ast.Attribute(
        value=lterm,
        attr=rterm.getstr(),
        ctx=ast.Load(),
    )


_binop_mapping = {
    'PLUS': ast.Add,
    'MINUS': ast.Sub,
    'MUL': ast.Mult,
    'DIV': ast.Div,
    'MOD': ast.Mod,
}


@pg.production('expr : expr PLUS expr')
@pg.production('expr : expr MINUS expr')
@pg.production('expr : expr MUL expr')
@pg.production('expr : expr DIV expr')
@pg.production('expr : expr MOD expr')
def expr_binop(p):
    lterm, op, rterm = p
    operator = _binop_mapping[op.gettokentype()]
    return ast.BinOp(left=lterm, op=operator(), right=rterm)


_cmpop_mapping = {
    'EQUAL': ast.Eq,
    'NEQUAL': ast.NotEq,
    'LT': ast.Lt,
    'LTE': ast.LtE,
    'GT': ast.Gt,
    'GTE': ast.GtE,
    'IN': ast.In,
    'NOTIN': ast.NotIn,
    'ISNOT': ast.IsNot,
    'IS': ast.Is,
}


@pg.production('expr : expr EQUAL expr')
@pg.production('expr : expr NEQUAL expr')
@pg.production('expr : expr LTE expr')
@pg.production('expr : expr LT expr')
@pg.production('expr : expr GTE expr')
@pg.production('expr : expr GT expr')
@pg.production('expr : expr IN expr')
@pg.production('expr : expr NOTIN expr')
@pg.production('expr : expr ISNOT expr')
@pg.production('expr : expr IS expr')
def expr_cmpop(p):
    lterm, op, rterm = p
    operator = _cmpop_mapping[op.gettokentype()]
    return ast.Compare(left=lterm, ops=[operator()], comparators=[rterm])


@pg.production('expr : expr filter')
def expr_filter(p):
    arg, (filter, args, kwargs) = p
    return build_call(filter, [arg] + args, kwargs)


@pg.production('expr : LPAREN expr RPAREN')
def expr_binop_paren(p):
    return p[1]


@pg.production('expr : expr LSQB expr RSQB')
def expr_SUBSCRIPT(p):
    src, _, subscript, _ = p
    return ast.Subscript(
        value=src,
        slice=ast.Index(value=subscript, ctx=ast.Load()),
        ctx=ast.Load(),
    )


@pg.production('expr : expr LPAREN RPAREN')
def expr_empty_call(p):
    func, _, _ = p
    return build_call(func)


@pg.production('expr : expr LPAREN arg_list RPAREN')
def expr_args_call(p):
    func, _, args, _ = p
    return build_call(func, args)


@pg.production('expr : expr LPAREN kwarg_list RPAREN')
def expr_kwargs_call(p):
    func, _, kwargs, _ = p
    return build_call(func, kwargs=kwargs)


@pg.production('expr : expr LPAREN arg_list COMMA kwarg_list RPAREN')
def expr_full_call(p):
    func, _, args, _, kwargs, _ = p
    return build_call(func, args, kwargs)


@pg.production('filter : PIPE lookup_name COLON literal')
def filter_colon_arg(p):
    _, filt, _, arg = p
    filter_name = get_lookup_name(filt)
    filter_func = get_filter_func(filter_name)
    return filter_func, [arg], []


@pg.production('filter : PIPE lookup_name')
def filter_pipe_lookup_name(p):
    filter_name = get_lookup_name(p[1])
    filter_func = get_filter_func(filter_name)
    return filter_func, [], []


@pg.production('filter : PIPE lookup_name LPAREN RPAREN')
def filter_pipe_lookup_empty_call(p):
    filter_name = get_lookup_name(p[1])
    filter_func = get_filter_func(filter_name)
    return filter_func, [], []


@pg.production('filter : PIPE lookup_name LPAREN arg_list RPAREN')
def filter_pipe_lookup_args_call(p):
    _, filter, _, args, _ = p
    filter_name = get_lookup_name(filter)
    filter_func = get_filter_func(filter_name)
    return filter_func, args, []


@pg.production('filter : PIPE lookup_name LPAREN kwarg_list RPAREN')
def filter_pipe_lookup_kwargs_call(p):
    _, filter, _, kwargs, _ = p
    filter_name = get_lookup_name(filter)
    filter_func = get_filter_func(filter_name)
    return filter_func, [], kwargs


@pg.production('filter : PIPE lookup_name LPAREN arg_list COMMA kwarg_list RPAREN')
def filter_pipe_lookup_full_call(p):
    _, filter, _, args, _, kwargs, _ = p
    filter_name = get_lookup_name(filter)
    filter_func = get_filter_func(filter_name)
    return filter_func, args, kwargs


@pg.production('kwarg : NAME ASSIGN expr')
def kwarg_assignment(p):
    name, _, expr = p
    return ast.keyword(arg=name.getstr(), value=expr)


@pg.production('kwarg_list : kwarg')
def kwarg_list_kwarg(p):
    return p


@pg.production('kwarg_list : kwarg_list COMMA kwarg')
def kwarg_list_append(p):
    kwarg_list, _, kwarg = p
    kwarg_list.append(kwarg)
    return kwarg_list


@pg.production('literal : name')
@pg.production('literal : number')
@pg.production('literal : string')
def literal(p):
    return p[0]


@pg.production('lookup_name : NAME')
def lookup_name_NAME(p):
    return [ast.Str(s=p[0].getstr())]


@pg.production('lookup_name : lookup_name DOT NAME')
def lookup_name_append(p):
    lookup_name, _, name = p
    lookup_name.append(ast.Str(s=name.getstr()))
    return lookup_name


@pg.production('name : NAME')
def name_NAME(p):
    """
    Look up a NAME in Context
    """
    return ast.Subscript(
        value=ast.Name(id='context', ctx=ast.Load()),
        slice=ast.Index(value=ast.Str(s=p[0].getstr()), ctx=ast.Load()),
        ctx=ast.Load(),
    )


@pg.production('number : NUMBER')
def number_NUMBER(p):
    number = p[0].getstr()
    if '.' in number or 'e' in number or 'E' in number:
        cast = float
    else:
        cast = int
    return ast.Num(n=cast(number))


@pg.production('string : STRING')
def string_STRING(p):
    return ast.Str(s=p[0].getstr()[1:-1])


@pg.error
def error(token):
    raise ValueError('Unexpected token: %r' % token)
