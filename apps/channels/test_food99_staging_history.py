from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, RequestFactory
from django.contrib.admin.sites import AdminSite

from apps.channels.food99_staging import classify_fingerprint
from apps.channels.admin import Food99StagedOrderAdmin
from apps.channels.models import Food99StagedOrder


class FingerprintComparisonTests(SimpleTestCase):
    def test_legacy_unchanged(self):
        self.assertEqual(classify_fingerprint('original', '', 'original'), 'UNCHANGED')

    def test_changed_once_then_unchanged(self):
        self.assertEqual(classify_fingerprint('original', 'original', 'new'), 'CHANGED_REVIEW_REQUIRED')
        self.assertEqual(classify_fingerprint('original', 'new', 'new'), 'UNCHANGED')

    def test_revert_is_new_revision(self):
        self.assertEqual(classify_fingerprint('original', 'new', 'original'), 'CHANGED_REVIEW_REQUIRED')


class ReviewAdminPermissionsTests(SimpleTestCase):
    def setUp(self):
        self.admin = Food99StagedOrderAdmin(Food99StagedOrder, AdminSite())
        self.request = RequestFactory().get('/admin/channels/food99stagedorder/')

    def test_regular_user_cannot_view(self):
        self.request.user = SimpleNamespace(is_active=True, is_superuser=False)
        self.assertFalse(self.admin.has_view_permission(self.request))
        self.assertFalse(self.admin.has_module_permission(self.request))

    def test_superuser_can_review_but_not_edit(self):
        self.request.user = SimpleNamespace(is_active=True, is_superuser=True)
        self.assertTrue(self.admin.has_view_permission(self.request))
        self.assertFalse(self.admin.has_change_permission(self.request))
        self.assertFalse(self.admin.has_add_permission(self.request))
        self.assertFalse(self.admin.has_delete_permission(self.request))

    def test_encrypted_payload_not_presented(self):
        self.assertIn('encrypted_snapshot', self.admin.exclude)
        self.assertIn('latest_encrypted_snapshot', self.admin.exclude)
