from collections import OrderedDict
from typing import Type, List

from django.core.exceptions import ImproperlyConfigured, ValidationError as DjangoValidationError

import graphene
from graphene.types.mutation import MutationOptions
from graphene.types.utils import yank_fields_from_attrs
from graphene_django.forms.converter import convert_form_field


### Generic helpers

def get_user_from_info(info, allow_anonymous=False):
    """
    Convenience method for getting the user object from the info argument
    that a Graphene Mutation receives in the `mutate` method.

    This exists because otherwise the same four lines would have to repeated
    in every mutation where a user is required.

    :param info: The info object as received by a `mutate` method on
      a graphene.Mutation.
    :param allow_anonymous: If True, anonymous user instances are returned;
      if False, they are replaced with None.
    """
    user = getattr(info.context, 'user', None)
    if user is not None and (user.is_anonymous and not allow_anonymous):
        user = None
    return user


def make_failable_objecttype(orig_type, name=None):
    meta = getattr(orig_type, '_meta', None)
    if meta is None and name is None:
        raise ImproperlyConfigured(
            "The original type passed doesn't have a name that we can generate "
            "a name from, please specify one explicitly."
        )
    new_name = name if name else 'Failable{}'.format(meta.name)

    class FailableWrapper(graphene.ObjectType):
        error = graphene.String()
        success = graphene.NonNull(graphene.Boolean)
        result = graphene.Field(orig_type)

        class Meta:
            name = new_name
    return graphene.Field(FailableWrapper)


### Mutations

class MutationExecutionException(Exception):
    pass


class ValidationError(graphene.ObjectType):
    field = graphene.String()
    messages = graphene.List(graphene.String)


class ValidationErrors(graphene.ObjectType):
    validation_errors = graphene.List(ValidationError)


class ExecutionError(graphene.ObjectType):
    error_message = graphene.NonNull(graphene.String)


class MutationError(graphene.Union):
    class Meta:
        types = (
            ValidationErrors,
            ExecutionError
        )


def create_validation_error_output(validation_error: DjangoValidationError):
    """
    Creates a beautiful ValidationErrors object so the Frontend can easily see where the
    validation failed.

    The according mutation needs to have an return field for the error typed as
    serious_django_graphene.MutationError. E.g.:
    ```
    class CreateEmployee(graphene.Mutation):

        class Arguments:
            some_input_arg = graphene.Int()

        employee = graphene.Field(EmployeeType)
        success = graphene.Boolean()
        error = MutationError()

        def mutate(self, info, some_input_arg):
            try:
                employee = EmployeeService.update(some_input_arg)
            except EmployeeService.exceptions as e:
                if type(e) is ValidationError:
                    return UpdateEmployee(employee=None,
                                          error=create_validation_error_output(e),
                                          success=False)
                else:
                    raise MutationExecutionException(str(e))
            return UpdateEmployee(employee=employee, success=True, error=None)
    ```

    :param validation_error: The ValidationError to be formated
    :return: A ValidationErrors graphene.ObjectType
    """
    validation_errors = [
        ValidationError(field=key, messages=value)
        for key, value in validation_error
    ]
    return ValidationErrors(validation_errors=validation_errors)


class FailableMutationOptions(MutationOptions):
    caught_exceptions = None   # type: List[Type[Exception]]


class FailableMutation(graphene.Mutation):
    @classmethod
    def __init_subclass_with_meta__(cls, caught_exceptions=None, _meta=None, **options):
        if not _meta:
            _meta = FailableMutationOptions(cls)

        caught_exceptions = caught_exceptions or ()
        if type(caught_exceptions) is list:
            caught_exceptions = tuple(caught_exceptions)
        _meta.caught_exceptions = caught_exceptions

        super().__init_subclass_with_meta__(_meta=_meta, **options)

    class Meta:
        abstract = True

    error = MutationError()
    success = graphene.NonNull(graphene.Boolean)

    @classmethod
    def mutate(cls, info, *args, **kwargs):
        if not hasattr(cls, 'do_mutate'):
            raise NotImplementedError(
                f"Default implementation of FailableMutation.mutate depends on do_mutate method being defined, but "
                f"{cls} does not have this method!"
            )

        exceptions = getattr(cls._meta, 'caught_exceptions', ())
        try:
            return cls.do_mutate(info, *args, **kwargs)
        except DjangoValidationError as e:
            return cls(error=create_validation_error_output(e), success=False)
        except exceptions as e:
            return cls(error=ExecutionError(error_message=str(e)), success=False)


### Mutations from Forms

def fields_for_form(form, only_fields, exclude_fields):
    fields = OrderedDict()
    for name, field in form.fields.items():
        is_not_in_only = only_fields and name not in only_fields
        is_excluded = name in exclude_fields
        if is_not_in_only or is_excluded:
            continue

        fields[name] = convert_form_field(field)
    return fields


class FormMutationOptions(MutationOptions):
    form_class = None
    fields_from_cleaned = []
    permissions = None


class FormMutation(FailableMutation):
    class Meta:
        abstract = True

    @classmethod
    def mutate(cls, root, info, **input):
        form = cls.get_form(root, info, **input)

        # Check form.is_valid() to see if we should mutate,
        # or return with ValidationErrors right away.
        if form.is_valid():
            try:
                result = cls.perform_mutate(form, info)
                # Do some defaulting for the `success` field based on the errors
                if not hasattr(result, 'success'):
                    result.success = getattr(result, 'error') is None
                return result
            except MutationExecutionException as e:
                return cls(
                    error=ExecutionError(error_message=str(e)),
                    success=False
                )
        else:
            validation_errors = [
                ValidationError(field=key, messages=value)
                for key, value in form.errors.items()
            ]
            return cls(
                error=ValidationErrors(validation_errors=validation_errors),
                success=False
            )

    @classmethod
    def get_form(cls, root, info, **input):
        form_kwargs = cls.get_form_kwargs(root, info, **input)
        return cls._meta.form_class(**form_kwargs)

    @classmethod
    def get_form_kwargs(cls, root, info, **input):
        kwargs = {"data": input}

        pk = input.pop("id", None)
        if pk:
            instance = cls._meta.model._default_manager.get(pk=pk)
            kwargs["instance"] = instance

        return kwargs

    @classmethod
    def __init_subclass_with_meta__(
        cls, form_class=None, only_fields=(), exclude_fields=(),
        _meta=None, **options
    ):
        if not form_class:
            raise Exception("form_class is required for FormMutation")

        form = form_class()
        arguments = yank_fields_from_attrs(
            fields_for_form(form, only_fields, exclude_fields),
            _as=graphene.Argument
        )
        if not _meta:
            _meta = FormMutationOptions(cls)
        _meta.form_class = form_class

        super().__init_subclass_with_meta__(
            _meta=_meta,
            arguments=arguments,
            **options
        )

    @classmethod
    def perform_mutate(cls, form, info):
        raise NotImplementedError(
            "perform_mutate needs to be overridden in the subclass!"
        )
