"""
Reference-data endpoints must be able to return everything in one page.

Departments and colleges feed **dropdowns**. Before `ReferenceDataPagination`
was applied, the frontend sent `?page_size=100` and DRF silently ignored it
(`page_size_query_param` was never configured), so any institution with more
than twenty departments would have seen a truncated dropdown with no
indication that options were missing — the operator would simply not find the
department they were looking for.

These tests pin both halves: the client can ask for a bigger page, and it
cannot ask for an unbounded one.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.colleges.models import College
from apps.departments.models import Department

User = get_user_model()


class ReferenceDataPaginationTests(APITestCase):
    def setUp(self):
        # More than the project-wide default PAGE_SIZE of 20.
        for n in range(25):
            Department.objects.create(name=f'Department {n:02d}', code=f'D{n:02d}')
            College.objects.create(name=f'College {n:02d}', code=f'C{n:02d}')

    def test_default_page_size_still_applies_when_none_is_requested(self):
        response = self.client.get(reverse('department-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 20)
        self.assertEqual(response.data['count'], 25)

    def test_a_client_can_request_every_department_in_one_page(self):
        response = self.client.get(reverse('department-list'), {'page_size': 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 25)
        self.assertIsNone(response.data['next'])

    def test_a_client_can_request_every_college_in_one_page(self):
        response = self.client.get(reverse('college-list'), {'page_size': 100})
        self.assertEqual(len(response.data['results']), 25)

    def test_page_size_is_capped_so_it_cannot_be_used_to_dump_the_table(self):
        """Without a cap, `?page_size=100000` would let any caller ask the
        server to serialize the whole table on demand."""
        for n in range(25, 210):
            Department.objects.create(name=f'Department {n:03d}', code=f'D{n:03d}')
        response = self.client.get(reverse('department-list'), {'page_size': 100000})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 200)  # max_page_size

    def test_a_nonsense_page_size_falls_back_to_the_default(self):
        response = self.client.get(reverse('department-list'), {'page_size': 'lots'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 20)
