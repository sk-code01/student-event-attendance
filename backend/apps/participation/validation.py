"""
Server-side validation for a single live-camera capture. Every function
here treats its input as untrusted client-supplied evidence metadata (see
project rule: "the client is never the final trust boundary") and raises
rest_framework.serializers.ValidationError with a clear, safe message on
failure — nothing here ever leaks a stack trace or internal exception.
"""

import hashlib
import io
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from apps.participation.geo import haversine_distance_meters

_FORMAT_TO_MIME = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
_MIN_DIMENSION_PX = 100
_MAX_DIMENSION_PX = 8000
_MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


def validate_and_identify_image(uploaded_file) -> tuple[str, int, str]:
    """
    Validates file size, decodability, and actual (not client-claimed)
    content type. Returns (mime_type, file_size, sha256_hash).
    """
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)

    file_size = len(data)
    if file_size == 0:
        raise serializers.ValidationError('The uploaded file is empty.')
    if file_size > settings.MAX_CAPTURE_FILE_SIZE:
        raise serializers.ValidationError(
            f'The uploaded file exceeds the maximum allowed size of {settings.MAX_CAPTURE_FILE_SIZE} bytes.',
        )

    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise serializers.ValidationError('The uploaded file is not a valid image.')

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        width, height = image.size
        detected_format = image.format
    except Exception:
        raise serializers.ValidationError('The uploaded file could not be decoded as an image.')

    mime_type = _FORMAT_TO_MIME.get(detected_format or '')
    if mime_type is None or mime_type not in settings.ALLOWED_IMAGE_MIME_TYPES:
        raise serializers.ValidationError('Unsupported image type.')

    if width < _MIN_DIMENSION_PX or height < _MIN_DIMENSION_PX:
        raise serializers.ValidationError('Image resolution is too small to be valid evidence.')
    if width > _MAX_DIMENSION_PX or height > _MAX_DIMENSION_PX:
        raise serializers.ValidationError('Image resolution is unreasonably large.')

    sha256_hash = hashlib.sha256(data).hexdigest()
    return mime_type, file_size, sha256_hash


def validate_certificate_file(uploaded_file) -> tuple[str, int, str]:
    """
    Validates an uploaded certificate and returns (mime_type, file_size,
    sha256_hash).

    A certificate is usually a PDF but is just as often a photo or scan of a
    printed one, so both are accepted. As with capture images the type is
    determined from the file's own bytes — a PDF by its magic number, an
    image by decoding it — and never from the client-supplied Content-Type,
    which an attacker controls.
    """
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)

    file_size = len(data)
    if file_size == 0:
        raise serializers.ValidationError('The uploaded file is empty.')
    if file_size > settings.MAX_CERTIFICATE_FILE_SIZE:
        raise serializers.ValidationError(
            f'The certificate exceeds the maximum allowed size of {settings.MAX_CERTIFICATE_FILE_SIZE} bytes.',
        )

    if data[:5] == b'%PDF-':
        mime_type = 'application/pdf'
    else:
        try:
            probe = Image.open(io.BytesIO(data))
            probe.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
            detected_format = image.format
        except (UnidentifiedImageError, OSError, ValueError):
            raise serializers.ValidationError('The certificate must be a PDF or an image file.')
        mime_type = _FORMAT_TO_MIME.get(detected_format or '')

    if mime_type is None or mime_type not in settings.ALLOWED_CERTIFICATE_MIME_TYPES:
        raise serializers.ValidationError('Unsupported certificate file type.')

    sha256_hash = hashlib.sha256(data).hexdigest()
    return mime_type, file_size, sha256_hash


def validate_gps(*, latitude, longitude, accuracy) -> None:
    """Distinguishes 'GPS unavailable' (accuracy missing) from 'GPS
    available but inaccurate' (accuracy present but too large) — both block
    submission, but a missing accuracy must never be treated as perfect."""
    if latitude is None or longitude is None:
        raise serializers.ValidationError('Location is required to submit participation evidence.')
    if accuracy is None:
        raise serializers.ValidationError('Location accuracy could not be determined.')
    if accuracy > settings.MAX_GPS_ACCURACY_METERS:
        raise serializers.ValidationError(
            f'Location accuracy ({accuracy:.0f}m) does not meet the required precision '
            f'({settings.MAX_GPS_ACCURACY_METERS}m). Move to an area with a clearer GPS signal and try again.',
        )
    if not (-90 <= float(latitude) <= 90) or not (-180 <= float(longitude) <= 180):
        raise serializers.ValidationError('Invalid GPS coordinates.')


def compute_venue_distance(event, *, latitude, longitude):
    """Returns (venue_distance_meters | None, location_warning: bool). Never
    raises — a venue mismatch is a warning, not a rejection reason."""
    if not event.has_venue_coordinates:
        return None, False
    distance = haversine_distance_meters(
        float(latitude), float(longitude), float(event.venue_latitude), float(event.venue_longitude),
    )
    return distance, distance > settings.VENUE_WARNING_DISTANCE_METERS


def validate_device_timestamp_for_event(device_capture_timestamp, event_date) -> None:
    """
    The authoritative event-date check. Compares the LOCAL DATE (per
    settings.TIME_ZONE) of the capture's own device timestamp against the
    event's date — never against "today" at request time, so a delayed
    offline sync of a same-day capture is still accepted, while a capture
    genuinely taken on the wrong day is rejected regardless of when it's
    uploaded.

    device_capture_timestamp is client-supplied evidence metadata, not a
    cryptographically trustworthy value — a malicious client could send any
    timestamp. The only defense here is bounding it against implausible
    future values; full spoofing resistance is out of scope for this phase
    (documented as a known limitation).
    """
    if device_capture_timestamp is None:
        raise serializers.ValidationError('A device capture timestamp is required.')

    now = timezone.now()
    if device_capture_timestamp > now + _MAX_FUTURE_CLOCK_SKEW:
        raise serializers.ValidationError('The capture timestamp is in the future.')

    capture_local_date = timezone.localtime(device_capture_timestamp).date()
    if capture_local_date != event_date:
        raise serializers.ValidationError(
            'This capture was not taken on the event date and cannot be accepted.',
        )
