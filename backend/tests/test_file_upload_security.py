"""
Phase 9 §9 — hostile uploads against the live-capture endpoint. The Pillow
probe, not the client's Content-Type or filename, decides what a file is.
"""

import io

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import EvidenceCapture
from apps.verification.tests.helpers import iso, make_fake_image_bytes, noon_on

from .helpers import AuthMixin, build_universe, make_participation


def _png_bytes(size=(300, 300)):
    return make_fake_image_bytes(fmt='PNG', size=size)


class UploadSecurityTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()
        # A second student with an open, in-progress version on today's event.
        # make_participation creates the registration itself.
        self.participation = make_participation(student=self.u.a.other_student, event=self.u.a.event)
        self._auth_as('studenta2')
        opened = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.assertEqual(opened.status_code, status.HTTP_201_CREATED, opened.data)
        self.version_id = opened.data['versions'][0]['id']
        self.url = reverse('evidence-version-captures', args=[self.version_id])

    def _upload(self, upload, role='PRIMARY', **overrides):
        payload = {
            'capture_role': role, 'image': upload,
            'device_capture_timestamp': iso(noon_on(self.u.a.event.event_date)),
            'latitude': '12.971600', 'longitude': '77.594600', 'gps_accuracy': 15,
        }
        payload.update(overrides)
        return self.client.post(self.url, payload, format='multipart')

    def _assert_rejected(self, response):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(EvidenceCapture.objects.filter(evidence_version_id=self.version_id).exists())

    def test_svg_with_script_is_rejected_whatever_it_claims_to_be(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script></svg>'
        for name, ctype in (('x.svg', 'image/svg+xml'), ('x.jpg', 'image/jpeg'), ('x.png', 'image/png')):
            self._assert_rejected(self._upload(SimpleUploadedFile(name, svg, content_type=ctype)))

    def test_html_javascript_and_executable_content_are_rejected(self):
        payloads = [
            ('page.jpg', b'<html><script>document.location="//evil"</script></html>'),
            ('run.jpg', b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff' + b'\x00' * 200),
            ('shell.png', b'#!/bin/sh\nrm -rf /\n'),
            ('java.jpg', b'javascript:alert(1)'),
            ('zip.jpg', b'PK\x03\x04' + b'\x00' * 100),
        ]
        for name, data in payloads:
            self._assert_rejected(self._upload(SimpleUploadedFile(name, data, content_type='image/jpeg')))

    def test_content_type_header_is_not_trusted_the_bytes_are(self):
        # Real PNG bytes announced as JPEG: accepted, and stored as what it IS.
        response = self._upload(SimpleUploadedFile('lie.jpg', _png_bytes(), content_type='image/jpeg'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['mime_type'], 'image/png')
        capture = EvidenceCapture.objects.get(pk=response.data['id'])
        self.assertTrue(capture.object_reference.name.endswith('.png'))

    def test_unsupported_real_image_formats_are_rejected(self):
        buffer = io.BytesIO()
        Image.new('RGB', (300, 300), (1, 2, 3)).save(buffer, format='GIF')
        self._assert_rejected(self._upload(SimpleUploadedFile('a.gif', buffer.getvalue(), content_type='image/gif')))
        buffer = io.BytesIO()
        Image.new('RGB', (300, 300), (1, 2, 3)).save(buffer, format='BMP')
        self._assert_rejected(self._upload(SimpleUploadedFile('a.bmp', buffer.getvalue(), content_type='image/bmp')))

    def test_empty_truncated_and_oversized_dimension_files_are_rejected(self):
        self._assert_rejected(self._upload(SimpleUploadedFile('empty.jpg', b'', content_type='image/jpeg')))
        truncated = make_fake_image_bytes()[:200]
        self._assert_rejected(self._upload(SimpleUploadedFile('cut.jpg', truncated, content_type='image/jpeg')))
        wide = make_fake_image_bytes(size=(8100, 120))
        self._assert_rejected(self._upload(SimpleUploadedFile('wide.jpg', wide, content_type='image/jpeg')))
        tiny = make_fake_image_bytes(size=(20, 20))
        self._assert_rejected(self._upload(SimpleUploadedFile('tiny.jpg', tiny, content_type='image/jpeg')))

    def test_oversized_byte_count_is_rejected_cleanly(self):
        padding = b'\x00' * (settings.MAX_CAPTURE_FILE_SIZE + 1)
        upload = SimpleUploadedFile('big.jpg', make_fake_image_bytes() + padding, content_type='image/jpeg')
        response = self._upload(upload)
        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE))
        self.assertFalse(EvidenceCapture.objects.filter(evidence_version_id=self.version_id).exists())

    def test_hostile_filenames_never_reach_the_storage_path(self):
        for name in ('../../secret.txt', '..\\..\\secret.txt', '/etc/passwd', 'C:\\Windows\\win.ini',
                     '<script>alert(1)</script>.jpg', 'a%00.jpg', '.jpg', 'x' * 500 + '.jpg'):
            response = self._upload(SimpleUploadedFile(name, make_fake_image_bytes(), content_type='image/jpeg'),
                                    role='ADDITIONAL')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, (name, response.data))
            stored = EvidenceCapture.objects.get(pk=response.data['id']).object_reference.name
            self.assertNotIn('..', stored)
            self.assertNotIn('secret', stored)
            self.assertNotIn('<', stored)
            self.assertNotIn('passwd', stored)
            self.assertTrue(stored.startswith(f'{self.u.a.other_student.id}/{self.participation.id}/'), stored)
            self.assertRegex(stored.rsplit('/', 1)[-1], r'^[0-9a-f]{32}\.jpg$')

    def test_polyglot_jpeg_with_trailing_script_is_stored_as_an_image_only(self):
        """Appended HTML does not stop it being a valid JPEG, so it is accepted
        — but it can only ever be served with an image content type through
        the authenticated view, never as a page."""
        data = make_fake_image_bytes() + b'<html><script>alert(1)</script></html>'
        response = self._upload(SimpleUploadedFile('poly.jpg', data, content_type='text/html'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        image = self.client.get(reverse('evidence-capture-image', args=[response.data['id']]))
        self.assertEqual(image.status_code, status.HTTP_200_OK)
        self.assertEqual(image['Content-Type'], 'image/jpeg')
        self.assertEqual(image['X-Content-Type-Options'], 'nosniff')

    def test_capture_role_is_a_closed_choice(self):
        for role in ('OWNER', 'primary', 'PRIMARY;DROP', '', '<b>'):
            response = self._upload(SimpleUploadedFile('a.jpg', make_fake_image_bytes(), content_type='image/jpeg'),
                                    role=role)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, role)

    def test_stored_files_live_only_under_the_private_root(self):
        response = self._upload(SimpleUploadedFile('ok.jpg', make_fake_image_bytes(), content_type='image/jpeg'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        capture = EvidenceCapture.objects.get(pk=response.data['id'])
        full_path = capture.object_reference.path
        self.assertTrue(full_path.startswith(str(settings.MEDIA_ROOT / 'participation_captures')), full_path)
        self.assertNotIn('image_url', {k for k in response.data if 'media' in str(response.data[k]).lower()})
        self.assertIn('/api/v1/evidence/captures/', response.data['image_url'])
