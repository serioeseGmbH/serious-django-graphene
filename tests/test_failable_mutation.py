from types import SimpleNamespace

import graphene
from django.test import TestCase

from serious_django_graphene import FailableMutation, ExecutionError


class FailableMutationTest(TestCase):
    def test_default_mutate_fails_without_do_mutate(self):
        class MyFailableMutation(FailableMutation):
            some_result = graphene.Int()

        mut = MyFailableMutation()
        self.assertRaises(NotImplementedError, lambda *_: mut.mutate(SimpleNamespace()))

    def test_default_mutate_calls_do_mutate(self):
        class MyFailableMutation(FailableMutation):
            __method_calls__ = 0
            some_result = graphene.Int()

            @classmethod
            def do_mutate(cls, info, *args, **kwargs):
                cls.__method_calls__ += 1
                return cls(some_result=42)

        mut = MyFailableMutation()
        self.assertEqual(MyFailableMutation.__method_calls__, 0)
        mutation_result = mut.mutate(SimpleNamespace())
        self.assertEqual(mutation_result.some_result, 42)
        self.assertEqual(MyFailableMutation.__method_calls__, 1)
        mut.mutate(SimpleNamespace())
        self.assertEqual(MyFailableMutation.__method_calls__, 2)

    def test_declared_exceptions_are_caught_others_are_not(self):
        class SomeException(BaseException):
            pass

        class MyFailableMutation(FailableMutation):
            some_result = graphene.Int()

            class Meta:
                caught_exceptions = [SomeException]

            @classmethod
            def do_mutate(cls, info, value=None, *args, **kwargs):
                if value is None:
                    raise SomeException("oh no!")
                elif value is 69:
                    raise ValueError("nice")
                return cls(some_result=value)

        # Do not raise when expected exception occurs, but expect result.error to be present
        mut, raised = MyFailableMutation(), False
        try:
            result = mut.mutate(SimpleNamespace())
        except:
            raised = True
        self.assertFalse(raised)
        self.assertIsInstance(result.error, ExecutionError)

        # Do not raise when no exception occurs, and expect result.error to not be present
        mut, raised = MyFailableMutation(), False
        try:
            result = mut.mutate(SimpleNamespace(), value=100)
        except:
            raised = True
        self.assertFalse(raised)
        self.assertIsNone(result.error)

        # Raise when unexpected exception occurs
        mut = MyFailableMutation()
        self.assertRaises(ValueError, lambda *_: mut.mutate(SimpleNamespace(), value=69))
