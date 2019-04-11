import json

from django.utils.module_loading import import_string
from django.test import RequestFactory, TestCase

import graphene.test

class GrapheneAPITest(TestCase):
    base = '/graphql/'
    schema_src = 'some.schema'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schema = import_string(self.schema_src)

    # adapted from https://stackoverflow.com/a/47762174/3090225
    def execute(self, query, user=None, variables=None, files=None,  **kwargs):
        # Construct context
        request_factory = RequestFactory()
        context = request_factory.get(self.base)
        context.user = user
        if files and type(files) == dict:
            for file in files:
                context.FILES[file] = files[file]

        # Create Graphene test client instance and use it to execute the query
        client = graphene.test.Client(self.schema)
        result = client.execute(
            query,
            context=context,
            variables=variables,
            **kwargs
        )
        return result

    def assertExecuteReturns(self, query, expected_result, **kwargs):
        """
        Custom assert function to idiomatically test the common pattern of
        executing a query and comparing the result dict to an expected
        result dict.

        :param query: The GraphQL query to execute.
        :param expected_result: The expected result dict to compare against.
        """
        return self.assertEqual(
            self.execute(query, **kwargs),
            expected_result
        )

class GrapheneMutationTest(GrapheneAPITest):
    mutation = None

    def mutate(self, user=None, variables=None, **kwargs):
        return self.execute(self.mutation, user, variables, **kwargs)


class GrapheneFormMutationTest(GrapheneMutationTest):
    gql_mutation_name = None
    
    def get_data(self, result):
        if not isinstance(result, dict):
            raise ValueError("Must pass a dict as value to get_data()!")
        if not 'data' in result or\
           not self.gql_mutation_name in result['data'] or\
           result['data'][self.gql_mutation_name] is None:
            raise Exception("Could not access data on result object {}!".format(result))
        return result['data'][self.gql_mutation_name]

    def get_error(self, result):
        err = self.get_data(result)['error'] or {}
        validation_errs = err.get('validationErrors')
        execution_err = err.get('errorMessage')

        if validation_errs is not None:
            return validation_errs
        elif execution_err is not None:
            return execution_err
        return None

    def assertSuccessful(self, result):
        """
        Asserts that the result is the result of a successfully executed
        mutation. This means that:
          - result['data'][name]['success'] is present and True, and
          - result['data'][name]['error'] is None
        (where `name` is self.gql_mutation_name).
        """
        self.assertIn('data', result)
        self.assertIn(self.gql_mutation_name, result['data'])
        self.assertTrue(
            self.get_data(result).get('success', False),
            str(self.get_data(result))
        )
        self.assertIsNone(self.get_error(result))

    def assertThrew(self, result):
        """
        Asserts that the result is the result of a mutation that was executed
        and threw an internal exception that was not caught. This means that:
          - result['data'] is None
          - result['errors'] is present
        """
        self.assertIsNone(result['data'])
        self.assertIsNotNone(result['errors'])

    def assertErrored(self, result):
        """
        Asserts that the result is the result of a non-successfully executed
        mutation. This means that:
          - result['data'][name]['success'] is present and False, and
          - result['data'][name]['error'] is present
        (where `name` is self.gql_mutation_name).
        """
        self.assertIn('data', result)
        self.assertIn(self.gql_mutation_name, result['data'])
        self.assertFalse(
            self.get_data(result).get('success', True),
            str(self.get_data(result))
        )
        self.assertIsNotNone(self.get_error(result))
