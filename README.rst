========================
Serious Django: Graphene
========================

https://github.com/serioeseGmbH/serious-django-graphene

serious-django-graphene offers a couple of extensions for Graphene development in Django.

1. ``get_user_from_info`` returns the request's user from the passed info object.

   We use this function all the time, for example, to do permission checks on the current user.

2. ``FormMutation`` is based on ``FailableMutation`` (see below).

   It defines a Graphene mutation based on a plain old Django form. What is this good for?
   Well, we want to employ the builtin capabilities of Django for input validation and
   conversion. Why reinvent the wheel to do checks like "string of max length 50" inside
   Graphene mutations when Forms can do that for you, and have extensible validators?

   This is essentially a cleaned up and changed version of the FormMutation delivered with
   graphene-django itself. The difference is mainly in how we model the returned data in an
   expectable pattern, see FailableMutation.

2. ``FailableMutation`` defines a mutation that contains:

   - A ``success`` boolean flag
   - An ``error`` value, present only if an error occurred, which is (a union of) either

     - A list of ``ValidationError`` in the format like Django returns for validation errors, or
     - An ``ExecutionError``, which just contains an ``error_message`` String.

If you need additional fields, add them by inheriting from ``FailableMutation``.

3. ``make_failable_objecttype`` turns an existing graphene.ObjectType into a Field that contains:

   - A ``result`` field which is an optional value of the original type
   - A ``error`` field which is an optional String value, present only if an error occurred
   - A ``success`` boolean flag field. Strictly seen, this is superfluous, as the `null`-ness of
     ``result`` or ``error`` can be checked. However, its existence improves semantics on the
     client, as they can now just check ``if(result.success) { ... }``.


Quick start
-----------

1. Install the package with pip::

    pip install serious-django-graphene

2. Add "serious_django_graphene" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...
        'serious_django_graphene',
    ]

3. Import and use ``serious_django_graphene`` wherever you need the Graphene extensions

4. Import and use ``serious_django_graphene.testing`` wherever you need the Graphene test extensions
