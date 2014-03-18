
import ast
from tokenize import *

from collections import namedtuple
from StringIO import StringIO

from .tokenise import tokenise, TOKEN_TEXT, TOKEN_VAR, TOKEN_BLOCK

class TemplateSyntaxError(Exception):
    pass

### Back-ported from Py3
EXACT_TOKEN_TYPES = {
    '(':   LPAR,
    ')':   RPAR,
    '[':   LSQB,
    ']':   RSQB,
    ':':   COLON,
    ',':   COMMA,
    ';':   SEMI,
    '+':   PLUS,
    '-':   MINUS,
    '*':   STAR,
    '/':   SLASH,
    '|':   VBAR,
    '&':   AMPER,
    '<':   LESS,
    '>':   GREATER,
    '=':   EQUAL,
    '.':   DOT,
    '%':   PERCENT,
    '{':   LBRACE,
    '}':   RBRACE,
    '==':  EQEQUAL,
    '!=':  NOTEQUAL,
    '<=':  LESSEQUAL,
    '>=':  GREATEREQUAL,
    '~':   TILDE,
    '^':   CIRCUMFLEX,
    '<<':  LEFTSHIFT,
    '>>':  RIGHTSHIFT,
    '**':  DOUBLESTAR,
    '+=':  PLUSEQUAL,
    '-=':  MINEQUAL,
    '*=':  STAREQUAL,
    '/=':  SLASHEQUAL,
    '%=':  PERCENTEQUAL,
    '&=':  AMPEREQUAL,
    '|=':  VBAREQUAL,
    '^=': CIRCUMFLEXEQUAL,
    '<<=': LEFTSHIFTEQUAL,
    '>>=': RIGHTSHIFTEQUAL,
    '**=': DOUBLESTAREQUAL,
    '//':  DOUBLESLASH,
    '//=': DOUBLESLASHEQUAL,
    '@':   AT
}

class TokenInfo(namedtuple('TokenInfo', 'type string start end line')):
    def __repr__(self):
        annotated_type = '%d (%s)' % (self.type, tok_name[self.type])
        return ('TokenInfo(type=%s, string=%r, start=%r, end=%r, line=%r)' %
                self._replace(type=annotated_type))

    @property
    def exact_type(self):
        if self.type == OP and self.string in EXACT_TOKEN_TYPES:
            return EXACT_TOKEN_TYPES[self.string]
        else:
            return self.type
###

def token_stream(content):
    '''Fix the hole in Py2, change token types to their real types'''
    for token in generate_tokens(StringIO(content).readline):
        yield TokenInfo(*token)

def _context_lookup(x):
    '''Return AST for looking up x in the Context'''
    return ast.Subscript(
        value=ast.Name(id='context', ctx=ast.Load()),
        slice=ast.Index(value=ast.Str(s=x), ctx=ast.Load()),
        ctx=ast.Load(),
    )

def _make_number(tok):
    '''Turn a token of type NUMBER into an ast.Num'''
    if '.' in tok.string:
        val = float(tok.string)
    else:
        val = int(tok.string)
    return ast.Num(n=val)

def _convert_name_or_literal(tok):

    if tok.exact_type == STRING:
        code = ast.Str(s=tok.string[1:-1])
    elif tok.exact_type == NUMBER:
        code = _make_number(tok)
    elif tok.exact_type == NAME:
        code = _context_lookup(tok.string)
    else:
        raise TemplateSyntaxError(content)
    return code

def parse_expr(content):
    '''Turn a content string into AST'''
    stream = token_stream(content)

    # First token MUST be either a literal, or name
    tok = next(stream)
    code = _convert_name_or_literal(tok)

    for tok in stream:
        if tok.exact_type == ENDMARKER:
            break
        if tok.exact_type == DOT:
            tok = next(stream)
            if not tok.exact_type == NAME:
                raise TemplateSyntaxError(content)
            attr = tok.string
            code = ast.Attribute(value=code, attr=attr, ctx=ast.Load())
        elif tok.exact_type == LSQB:  # [
            tok = next(stream)
            lookup = _convert_name_or_literal(tok)
            code = ast.Subscript(
                value=code,
                slice=ast.Index(value=lookup, ctx=ast.Load()),
                ctx=ast.Load()
            )
            tok = next(stream)
            if not tok.exact_type == RSQB:
                raise TemplateSyntaxError('Expected ], found: %r' % tok)
        else:
            raise TemplateSyntaxError('Found unexpected token %r', tok)
    return code


def parse_block_tag(content, stream):
    parts = token_stream(content)

    tok = next(parts)
    if tok.exact_type != NAME:
        raise TemplateSyntaxError("Expected NAME: found %r" % tok)


class Template(object):
    def __init__(self, source):
        self.source = source

        code = self.parse()
        ast.fix_missing_locations(code)
        self.func = compile(code, filename="<template>", mode="exec")

    def _token_to_code(self, token):
        '''Given a Token instance, convert it to AST'''
        code = None
        if token.mode == TOKEN_TEXT:
            code = ast.Str(s=token.content)
        elif token.mode == TOKEN_VAR:
            # parse
            code = parse_expr(token.content)
        elif token.mode == TOKEN_BLOCK:
            # Parse args/kwargs
            parse_block_tag(token.content, self.stream)
            # create tag class instance
        else:
            # Must be a comment
            pass

        if code is not None:
            return token._position(code)

    def parse(self):
        '''Convert the parsed tokens into a list of expressions
        Then join them'''
        steps = []
        self.stream = tokenise(self.source)
        for token in self.stream:
            code = self._token_to_code(token)
            if code is not None:
                steps.append(code)

        # result = [str(x) for x in steps]
        return ast.Module(
            body=[ast.Assign(
                targets=[ast.Name(id='result', ctx=ast.Store())],
                value=ast.ListComp(
                    elt=ast.Call(
                        func=ast.Name(id='str', ctx=ast.Load()),
                        args=[
                            ast.Name(id='x', ctx=ast.Load()),
                        ],
                        keywords=[],
                    ),
                    generators=[
                        ast.comprehension(
                            target=ast.Name(id='x', ctx=ast.Store()),
                            iter=ast.List(elts=steps, ctx=ast.Load()),
                            ifs=[]
                        )
                    ]
                )
            )
        ])

    def render(self, context):
        ctx = {'context': context}
        exec(self.func, ctx)
        return u''.join(ctx['result'])

