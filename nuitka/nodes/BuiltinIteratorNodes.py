#     Copyright 2015, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
""" Built-in iterator nodes.

These play a role in for loops, and in unpacking. They can something be
predicted to succeed or fail, in which case, code can become less complex.

The length of things is an important optimization issue for these to be
good.
"""

from nuitka.Builtins import calledWithBuiltinArgumentNamesDecorator
from nuitka.optimizations import BuiltinOptimization

from .NodeBases import (
    ExpressionBuiltinSingleArgBase,
    ExpressionChildrenHavingBase,
    StatementChildrenHavingBase
)


class ExpressionBuiltinLen(ExpressionBuiltinSingleArgBase):
    kind = "EXPRESSION_BUILTIN_LEN"

    builtin_spec = BuiltinOptimization.builtin_len_spec

    def getIntegerValue(self):
        return self.getValue().getIterationLength()

    def computeExpression(self, constraint_collection):
        from .NodeMakingHelpers import (
            makeConstantReplacementNode,
            wrapExpressionWithNodeSideEffects
        )

        new_node, change_tags, change_desc = ExpressionBuiltinSingleArgBase.\
          computeExpression(
            self,
            constraint_collection = constraint_collection
        )

        if new_node is self:
            arg_length = self.getIntegerValue()

            if arg_length is not None:
                change_tags = "new_constant"
                change_desc = "Predicted len argument"

                new_node = wrapExpressionWithNodeSideEffects(
                    new_node = makeConstantReplacementNode(arg_length, self),
                    old_node = self.getValue()
                )

                if new_node.isExpressionSideEffects():
                    change_desc += " maintaining side effects"

        return new_node, change_tags, change_desc


class ExpressionBuiltinIter1(ExpressionBuiltinSingleArgBase):
    kind = "EXPRESSION_BUILTIN_ITER1"

    def computeExpression(self, constraint_collection):
        value = self.getValue()

        # Iterator of an iterator can be removed.
        if value.isIteratorMaking():
            return value, "new_builtin", "Eliminated useless iterator creation."

        return value.computeExpressionIter1(
            iter_node             = self,
            constraint_collection = constraint_collection
        )

    def isIteratorMaking(self):
        return True

    def isKnownToBeIterable(self, count):
        if count is None:
            return True

        # TODO: Should ask value if it is.
        return None

    def getIterationLength(self):
        return self.getValue().getIterationLength()

    def extractSideEffects(self):
        # Iterator making is the side effect itself.
        if self.getValue().isCompileTimeConstant():
            return ()
        else:
            return (self,)

    def mayHaveSideEffects(self):
        if self.getValue().isCompileTimeConstant():
            return self.getValue().isKnownToBeIterable(None)

        return True

    def mayRaiseException(self, exception_type):
        value = self.getValue()

        if value.mayRaiseException(exception_type):
            return True

        if value.isKnownToBeIterable(None):
            return False

        return True

    def isKnownToBeIterableAtMin(self, count):
        assert type(count) is int

        iter_length = self.getValue().getIterationLength()
        return iter_length is not None and iter_length < count

    def isKnownToBeIterableAtMax(self, count):
        assert type(count) is int

        iter_length = self.getValue().getIterationLength()

        return iter_length is not None and count <= iter_length

    def onRelease(self, constraint_collection):
        # print "onRelease", self
        pass


class ExpressionBuiltinNext1(ExpressionBuiltinSingleArgBase):
    kind = "EXPRESSION_BUILTIN_NEXT1"

    def __init__(self, value, source_ref):
        ExpressionBuiltinSingleArgBase.__init__(
            self,
            value      = value,
            source_ref = source_ref
        )

    def getDetails(self):
        return {}

    def computeExpression(self, constraint_collection):
        # TODO: Predict iteration result if possible via SSA variable trace of
        # the iterator state.

        # Assume exception is possible. TODO: We might query the next from the
        # source with a computeExpressionNext slot, but we delay that.
        constraint_collection.onExceptionRaiseExit(BaseException)

        return self, None, None


class ExpressionSpecialUnpack(ExpressionBuiltinNext1):
    kind = "EXPRESSION_SPECIAL_UNPACK"

    def __init__(self, value, count, expected, source_ref):
        ExpressionBuiltinNext1.__init__(
            self,
            value      = value,
            source_ref = source_ref
        )

        self.count = count
        self.expected = expected

    def getDetails(self):
        result = ExpressionBuiltinNext1.getDetails(self)
        result["count"] = self.getCount()
        result["expected"] = self.getExpected()

        return result

    def getCount(self):
        return self.count

    def getExpected(self):
        return self.expected


class StatementSpecialUnpackCheck(StatementChildrenHavingBase):
    kind = "STATEMENT_SPECIAL_UNPACK_CHECK"

    named_children = (
        "iterator",
    )

    def __init__(self, iterator, count, source_ref):
        StatementChildrenHavingBase.__init__(
            self,
            values     = {
                "iterator" : iterator
            },
            source_ref = source_ref
        )

        self.count = count

    def getDetails(self):
        return {
            "count" : self.getCount(),
        }

    def getCount(self):
        return self.count

    getIterator = StatementChildrenHavingBase.childGetter("iterator")

    def computeStatement(self, constraint_collection):
        constraint_collection.onExpression(self.getIterator())
        iterator = self.getIterator()

        if iterator.mayRaiseException(BaseException):
            constraint_collection.onExceptionRaiseExit(
                BaseException
            )

        if iterator.willRaiseException(BaseException):
            from .NodeMakingHelpers import \
              makeStatementExpressionOnlyReplacementNode

            result = makeStatementExpressionOnlyReplacementNode(
                expression = iterator,
                node       = self
            )

            return result, "new_raise", """\
Explicit raise already raises implicitly building exception type."""

        # Remove the check if it can be decided at compile time.
        if iterator.isKnownToBeIterableAtMax(0):
            return None, "new_statements", """\
Determined iteration end check to be always true."""

        constraint_collection.onExceptionRaiseExit(
            BaseException
        )

        return self, None, None


class ExpressionBuiltinIter2(ExpressionChildrenHavingBase):
    kind = "EXPRESSION_BUILTIN_ITER2"

    named_children = (
        "callable",
        "sentinel",
    )

    @calledWithBuiltinArgumentNamesDecorator
    def __init__(self, callable_arg, sentinel, source_ref):
        ExpressionChildrenHavingBase.__init__(
            self,
            values     = {
                "callable" : callable_arg,
                "sentinel" : sentinel,
            },
            source_ref = source_ref
        )

    getCallable = ExpressionChildrenHavingBase.childGetter("callable")
    getSentinel = ExpressionChildrenHavingBase.childGetter("sentinel")

    def computeExpression(self, constraint_collection):
        # TODO: The "callable" should be investigated here, maybe it is not
        # really callable, or raises an exception.

        return self, None, None

    def isIteratorMaking(self):
        return True


class ExpressionBuiltinNext2(ExpressionChildrenHavingBase):
    kind = "EXPRESSION_BUILTIN_NEXT2"

    named_children = (
        "iterator",
        "default"
    )

    def __init__(self, iterator, default, source_ref):
        ExpressionChildrenHavingBase.__init__(
            self,
            values     = {
                "iterator" : iterator,
                "default"  : default,
            },
            source_ref = source_ref
        )

    getIterator = ExpressionChildrenHavingBase.childGetter("iterator")
    getDefault = ExpressionChildrenHavingBase.childGetter("default")

    def computeExpression(self, constraint_collection):
        # TODO: The "iterator" should be investigated here, if it is iterable,
        # or if the default is raising.
        return self, None, None
