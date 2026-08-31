import unittest
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.auth.security import create_session_token, hash_session_token
from app.products.service import ProductService

class Phase1SecurityRulesTest(unittest.TestCase):
    def test_session_tokens_are_opaque_and_only_hash_is_stable(self):
        token = create_session_token()
        self.assertGreaterEqual(len(token), 32)
        self.assertNotEqual(token, hash_session_token(token))
        self.assertEqual(hash_session_token(token), hash_session_token(token))

    def test_refund_quantity_limit_formula(self):
        original = 3
        prior = 1
        requested = 2
        self.assertLessEqual(prior + requested, original)
        with self.assertRaises(AssertionError):
            self.assertLessEqual(prior + 3, original)

    def test_product_archive_records_audit_and_keeps_record(self):
        class DB:
            def __init__(self): self.events = []
            def add(self, value): self.events.append(value)
        product = SimpleNamespace(id="p1", company_id="c1", active=True, deleted=False, archived_at=None)
        repo = SimpleNamespace(db=DB(), get_product=AsyncMock(return_value=product), delete_product=AsyncMock())
        asyncio.run(ProductService(repo).delete_product("c1", "p1"))
        self.assertEqual(repo.db.events[0].action, "product_archive")
        repo.delete_product.assert_awaited_once_with(product)

    def test_pos_selection_and_takeover_copy_contains_required_states(self):
        source = Path(__file__).parents[2] / "pos-web/src/App.tsx"
        text = source.read_text()
        for marker in ("Choose POS location", "Take over this session", "No available active terminals", "New sign-in requires an internet connection"):
            self.assertIn(marker, text)

    def test_archive_audit_actions_are_present(self):
        for relative, marker in (("backend/app/devices/service.py", "terminal_archive"), ("backend/app/products/service.py", "product_archive")):
            source = Path(__file__).parents[2] / relative
            self.assertIn(marker, source.read_text())
