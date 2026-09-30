from django.db import IntegrityError
from django.test import TestCase

from apps.colleges.models import College


class CollegeModelTests(TestCase):
    def test_college_code_must_be_unique(self):
        College.objects.create(name='Engineering College', code='ENGG')
        with self.assertRaises(IntegrityError):
            College.objects.create(name='Engineering College Duplicate', code='ENGG')

    def test_college_str_representation(self):
        college = College.objects.create(name='Engineering College', code='ENGG')
        self.assertEqual(str(college), 'ENGG - Engineering College')
