import unittest
from datetime import datetime, timezone

import collectors.arxiv_collector as arxiv


NOW=datetime.now(timezone.utc).isoformat()
ATOM=f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:ar="http://arxiv.org/schemas/atom"><entry><id>http://arxiv.org/abs/2607.00001</id><title>Controllable Video Diffusion</title><summary>We introduce a video generation model with camera control and temporal consistency.</summary><published>{NOW}</published><updated>{NOW}</updated><author><name>Alice</name></author><author><name>Bob</name></author><category term="cs.CV"/><ar:primary_category term="cs.CV"/><link title="pdf" href="https://arxiv.org/pdf/2607.00001"/></entry><entry><id>http://arxiv.org/abs/2607.00002</id><title>Image Classification</title><summary>An image-only benchmark.</summary><published>{NOW}</published></entry></feed>'''


class ArxivCollectorTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self): self.old_fetch=arxiv.fetch_arxiv
 async def asyncTearDown(self): arxiv.fetch_arxiv=self.old_fetch
 async def test_atom_authors_categories_pdf_relevance_and_classification(self):
  entries=arxiv.parse_entries(ATOM); self.assertEqual(entries[0].authors,['Alice','Bob']); self.assertEqual(entries[0].categories,['cs.CV']); self.assertEqual(entries[0].pdf_url,'https://arxiv.org/pdf/2607.00001'); self.assertEqual(entries[0].classification,'controllability'); self.assertFalse(arxiv.relevant(entries[1],'video generation'))
 async def test_date_filter_empty_and_workflow_safe_failure(self):
  async def fake(*_args): return ATOM
  arxiv.fetch_arxiv=fake
  results,diag=await arxiv.collect_arxiv_with_diagnostics('video generation',30,10); self.assertEqual(len(results),1); self.assertEqual(diag['relevant_count'],1)
  with self.assertRaises(arxiv.ArxivError): arxiv.parse_entries('<feed>')
 async def test_malformed_and_timeout_diagnostics(self):
  async def malformed(*_args): return '<feed>'
  arxiv.fetch_arxiv=malformed
  results,diag=await arxiv.collect_arxiv_with_diagnostics('video generation',30,10); self.assertEqual(results,[]); self.assertIn('malformed XML',diag['reason'])
