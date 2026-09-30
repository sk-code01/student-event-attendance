"""
Pagination classes.

The project default is DRF's plain `PageNumberPagination` at `PAGE_SIZE = 20`,
which is right for the operational lists (events, registrations, evidence,
notifications): they grow without bound and are meant to be paged through.

Reference data is different. Departments and colleges are a small, bounded set
that the UI renders as a **dropdown**, not as a paged table — and a dropdown
that silently shows only the first twenty options is worse than one that fails,
because the operator cannot tell that the option they want was omitted.

`ReferenceDataPagination` lets those endpoints accept `?page_size=`, capped so a
client still cannot ask the server for an unbounded result set.
"""

from rest_framework.pagination import PageNumberPagination


class ReferenceDataPagination(PageNumberPagination):
    """Page-number pagination that honours a client-supplied `page_size`.

    The cap matters: without `max_page_size`, `?page_size=100000` would be an
    invitation to make the server serialize the whole table on demand. 200 is
    comfortably above any realistic number of departments or colleges for one
    institution while keeping a single response small.
    """

    page_size_query_param = 'page_size'
    max_page_size = 200
