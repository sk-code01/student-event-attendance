from django.db import IntegrityError
from django.test import TestCase

from apps.departments.models import Department


class DepartmentModelTests(TestCase):
    def test_department_code_must_be_unique(self):
        Department.objects.create(name='Computer Science', code='CS')
        with self.assertRaises(IntegrityError):
            Department.objects.create(name='Computer Science Duplicate', code='CS')

    def test_department_name_must_be_unique(self):
        Department.objects.create(name='Computer Science', code='CS1')
        with self.assertRaises(IntegrityError):
            Department.objects.create(name='Computer Science', code='CS2')

    def test_department_str_representation(self):
        department = Department.objects.create(name='Computer Science', code='CS')
        self.assertEqual(str(department), 'CS - Computer Science')
