#     Copyright 2016, Kay Hayen, mailto:kay.hayen@gmail.com
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
""" Nodes for generator objects and their creations.

Generators are turned into normal functions that create generator objects,
whose implementation lives here. The creation itself also lives here.

"""

from nuitka.PythonVersions import python_version

from .Checkers import checkStatementsSequenceOrNone
from .FunctionNodes import ExpressionFunctionBodyBase
from .IndicatorMixins import (
    MarkLocalsDictIndicator,
    MarkUnoptimizedFunctionIndicator
)
from .NodeBases import ChildrenHavingMixin, ExpressionChildrenHavingBase
from .ReturnNodes import StatementReturn


class ExpressionMakeGeneratorObject(ExpressionChildrenHavingBase):
    kind = "EXPRESSION_MAKE_GENERATOR_OBJECT"

    named_children = (
        "generator_ref",
    )

    getGeneratorRef = ExpressionChildrenHavingBase.childGetter("generator_ref")

    def __init__(self, generator_ref, code_object, source_ref):
        assert generator_ref.getFunctionBody().isExpressionGeneratorObjectBody()

        ExpressionChildrenHavingBase.__init__(
            self,
            values     = {
                "generator_ref" : generator_ref,
            },
            source_ref = source_ref
        )

        self.code_object = code_object

    def getDetails(self):
        return {
            "code_object" : self.code_object
        }

    def getCodeObject(self):
        return self.code_object

    def computeExpression(self, constraint_collection):
        # TODO: Generator body may know something too.
        return self, None, None

    def mayRaiseException(self, exception_type):
        return False

    def mayHaveSideEffects(self):
        return False


class ExpressionGeneratorObjectBody(ExpressionFunctionBodyBase,
                                    MarkLocalsDictIndicator,
                                    MarkUnoptimizedFunctionIndicator):
    # We really want these many ancestors, as per design, we add properties via
    # base class mix-ins a lot, pylint: disable=R0901
    kind = "EXPRESSION_GENERATOR_OBJECT_BODY"

    named_children = (
        "body",
    )

    checkers = {
        # TODO: Is "None" really an allowed value.
        "body" : checkStatementsSequenceOrNone
    }

    if python_version >= 340:
        qualname_setup = None

    def __init__(self, provider, name, flags, source_ref):
        ExpressionFunctionBodyBase.__init__(
            self,
            provider    = provider,
            name        = name,
            is_class    = False,
            code_prefix = "genexpr" if name == "<genexpr>" else "genobj",
            flags       = flags,
            source_ref  = source_ref
        )

        MarkLocalsDictIndicator.__init__(self)

        MarkUnoptimizedFunctionIndicator.__init__(self)

        self.needs_generator_return_exit = False

    def getFunctionName(self):
        return self.name

    def getFunctionQualname(self):
        return self.getParentVariableProvider().getFunctionQualname()

    def markAsNeedsGeneratorReturnHandling(self, value):
        self.needs_generator_return_exit = max(
            self.needs_generator_return_exit,
            value
        )

    def needsGeneratorReturnHandling(self):
        return self.needs_generator_return_exit == 2

    def needsGeneratorReturnExit(self):
        return bool(self.needs_generator_return_exit)

    @staticmethod
    def needsCreation():
        return False

    getBody = ChildrenHavingMixin.childGetter("body")
    setBody = ChildrenHavingMixin.childSetter("body")


class StatementGeneratorReturn(StatementReturn):
    kind = "STATEMENT_GENERATOR_RETURN"

    def __init__(self, expression, source_ref):
        StatementReturn.__init__(
            self,
            expression = expression,
            source_ref = source_ref
        )
