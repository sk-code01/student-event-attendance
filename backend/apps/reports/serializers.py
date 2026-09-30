from rest_framework import serializers


class ReportTypeSerializer(serializers.Serializer):
    """One allowlisted report type the caller may run."""

    key = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    formats = serializers.ListField(child=serializers.CharField(), read_only=True)


class ReportDatasetSerializer(serializers.Serializer):
    """A JSON preview of exactly the rows the exported file will contain.

    Rows are stringified lists aligned to `columns`, so the preview and every
    rendered format show identical content in an identical column order.
    """

    key = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    columns = serializers.ListField(child=serializers.CharField(), read_only=True)
    rows = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField(allow_blank=True)), read_only=True,
    )
    row_count = serializers.IntegerField(read_only=True)
    filters = serializers.CharField(read_only=True)
