import ast

from rattle import PY3
from rattle.exceptions import DuplicateBlockError


class ParserState(object):
    """
    Used to keep state information during template parsing, e.g. current block.
    """

    def __init__(self, level=0):
        self.level = level

        self.base_class = 'object'
        self.functions = {}
        self.klass = None
        self.module_body = []
        self.root_func = None

    def add_function(self, name, func):
        """
        Adds a new block to the current template.

        :param str name: The block name.
        :param ast.FunctionDef func: The :class:`ast.FunctionDef` of the block.
        :raises: :class:`rattle.exceptions.DuplicateBlockError` if a block with
            the given name already exists.
        """
        if name in self.functions:
            raise DuplicateBlockError(name)
        self.functions[name] = func

    def append_to_block(self, value, name='root'):
        """
        Appends the given value to the body of the currently active block
        function.

        :param value: A :class:`ast.stmt` node.
        """
        self.functions[name].body.append(value)

    @property
    def class_name(self):
        return 'Template%s' % (self.level or '')

    def finalize(self):
        """
        Adds all functions to the class body.
        """
        self.klass.bases = [ast.Name(id=self.base_class, ctx=ast.Load())]
        if self.base_class != 'object':
            self.root_func = None
            del self.functions['root']
            self.klass.body.insert(0, ast.Pass())
            # self.functions['root'].body = [
            #     ast.Return(
            #         value=build_call(
            #             func=ast.Attribute(
            #                 value=build_call(
            #                     func=ast.Name(id='super', ctx=ast.Load()),
            #                     args=[
            #                         ast.Name(id=self.class_name, ctx=ast.Load()),
            #                         ast.Name(id='self', ctx=ast.Load())
            #                     ]
            #                 ),
            #                 attr='root', ctx=ast.Load()
            #             ),
            #             args=[
            #                 ast.Name(id='context', ctx=ast.Load())
            #             ]
            #         )
            #     )
            # ]
        self.klass.body.extend(list(self.functions.values()))


def production(generator, *rules):
    """
    Wrapper around :meth:`rply.ParserGenerator.production` to patch the rules
    into the production's docstring.

    :param generator: An instance of a :class:`rply.ParserGenerator`.
    :param rules: The rules matching this production.
    """

    def wrapper(func):
        docstring = [func.__doc__, '\n'] if func.__doc__ else []
        docstring.append("This production is used for the following rules::\n")

        for rule in rules:
            generator.production(rule)(func)
            docstring.append("    " + rule)

        docstring.append('\n.')
        func.__doc__ = '\n'.join(docstring)
        return func
    return wrapper


def build_call(func, args=[], kwargs=[]):
    """
    Constructs a :class:`ast.Call` node that calls the given function ``func``
    with the arguments ``args`` and keyword arguments ``kwargs``.

    This is equivalent to::

        func(*args, **kwargs)

    :param func: An AST that, when evaluated, returns a function.
    :param args: The positional arguments passed to the function.
    :param kwags: The keyword arguments passed to the function.
    :returns: Calls the function with the provided args and kwargs.
    :rtype: :class:`ast.Call`
    """
    return ast.Call(
        func=func,
        args=args,
        keywords=kwargs,
        starargs=None,
        kwargs=None
    )


def build_class(state):
    """
    Constructs a :class:`ast.ClassDef` node that wraps the entire template
    file. The class will have an entry function ``root`` with:

    .. function:: root(context)

        Starts the template parsing with the given context.

        :returns: Returns a generator of strings that can be joined to the
            rendered template.

    :returns: a 2-tuple with the class and the entry function
    """
    root_func = build_function('root')
    klass = ast.ClassDef(
        name=state.class_name,
        bases=[],
        keywords=[],
        starargs=None,
        kwargs=None,
        body=[],
        decorator_list=[]
    )
    state.klass = klass
    state.root_func = root_func
    state.add_function('root', root_func)
    return klass, root_func


def build_function(name, body=[]):
    args = {}
    if PY3:
        args.update({
            'args': [
                ast.arg(arg='self', annotation=None),
                ast.arg(arg='context', annotation=None),
            ],
            'kwonlyargs': [],
            'kw_defaults': [],
        })
    else:
        args['args'] = [
            ast.Name(id='self', ctx=ast.Param()),
            ast.Name(id='context', ctx=ast.Param())
        ]
    real_body = [
        # we add an empty string to guarantee for a string and generator on
        # root level
        build_yield(ast.Str(s=''))
    ]
    real_body.extend(body)
    return ast.FunctionDef(
        name=name,
        args=ast.arguments(
            vararg=None,
            kwarg=None,
            defaults=[],
            **args
        ),
        body=real_body,
        decorator_list=[]
    )


def build_str_join(l):
    """
    Constructs a :class:`ast.Call` that joins all elements of ``l`` with an
    empty string (``''``).

    This is equivalent to::

        ''.join(l)

    :params list l: A string or list of strings.
    :returns: ``l`` joined by ``''``
    :rtype: str
    """
    return build_call(
        func=ast.Attribute(value=ast.Str(s=''), attr='join', ctx=ast.Load()),
        args=[l]
    )


def build_yield(value):
    """
    Constructs a :class:`ast.Yield` expression to be used in the block
    functions.

    This is equivalent to::

        yield value

    :param ast.expr value: Any AST `expr` node (e.g. :class:`ast.Str`,
        :class:`ast.Call`) that is or returns a string.
    :returns: A yield expression (``ast.Expr(ast.Yield(value))``) with the
        given value.
    :rtype: :class:`ast.Expr`
    """
    return ast.Expr(value=ast.Yield(value=value))


def build_yield_from(name):
    to_call = ast.Attribute(
        value=ast.Name(id='self', ctx=ast.Load()),
        attr=name,
        ctx=ast.Load()
    )
    call = build_call(
        func=to_call,
        args=[ast.Name(id='context', ctx=ast.Load())]
    )
    if hasattr(ast, 'YieldFrom'):  # TODO: Switch to "if PY3" at some point
        # YieldFrom is a new feature in Python 3.3
        return ast.Expr(value=ast.YieldFrom(value=call))
    else:
        return ast.For(
            target=ast.Name(id='_', ctx=ast.Store()),
            iter=call,
            body=[
                build_yield(ast.Name(id='_', ctx=ast.Load()))
            ],
            orelse=[]
        )


def get_filter_func(name):
    """
    Looks up the filter given by ``name`` in a context variable ``'filters'``.

    This is equivalent to::

        filters[name]

    :param str name: The filter name.
    :returns: A filter function.
    :rtype: ast.Subscript
    """
    return ast.Subscript(
        value=ast.Name(id='filters', ctx=ast.Load()),
        slice=ast.Index(value=name, ctx=ast.Load()),
        ctx=ast.Load(),
    )


def get_lookup_name(names):
    """
    Joins all ``names`` by ``'.'``.

    This is equivalent to::

        '.'.join(names)

    :param names: A list of one or more :class:`ast.Str` notes that will be
        joined by a dot and will be used to find a filter or tag function /
        class.
    :type names: list of :class:`ast.Str`
    :returns: ``'.'.join(names)``
    :rtype: :class:`ast.Call`
    """
    func = ast.Attribute(
        value=ast.Str(s='.'),
        attr='join',
        ctx=ast.Load()
    )
    args = [ast.List(
        elts=names,
        ctx=ast.Load()
    )]
    return build_call(func, args)


def split_tag_args_string(s):
    args = []
    current = []
    escaped, quote, squote = False, False, False
    parens = 0
    for c in s:
        if escaped:
            escaped = False
            current.append('\\')
            current.append(c)
            continue

        if c == '"':
            if not squote:
                quote = not quote
        elif c == "'":
            if not quote:
                squote = not squote
        elif c == "(":
            if not quote and not squote:
                parens += 1
        elif c == ")":
            if not quote and not squote:
                if parens <= 0:
                    raise ValueError('Closing un-open parenthesis in `%s`' % s)
                parens -= 1
        elif c == "\\":
            escaped = True
            continue
        elif c == " ":
            if not quote and not squote and parens == 0:
                if current:
                    if current[0] == current[-1] and current[0] in ('"', "'"):
                        current = current[1:-1]
                    args.append(''.join(current))
                    current = []
                continue
        current.append(c)
    if not escaped and not quote and not squote and parens == 0:
        if current:
            if current[0] == current[-1] and current[0] in ('"', "'"):
                current = current[1:-1]
            args.append(''.join(current))
    else:
        if quote:
            raise ValueError('Un-closed double quote in `%s`' % s)
        if squote:
            raise ValueError('Un-closed single quote in `%s`' % s)
        if parens > 0:
            raise ValueError('Un-closed parenthesis (%d still open) in `%s`' %
                             (parens, s))
        if escaped:
            raise ValueError('Un-used escaping in `%s`' % s)
    return args


def update_source_pos(node, token):
    """
    Updates the AST node ``node`` with the position information, such as line
    number and column number, from the lexer's token ``token``.
    """
    node.lineno = token.source_pos.lineno
    node.col_offset = token.source_pos.colno
    return node
