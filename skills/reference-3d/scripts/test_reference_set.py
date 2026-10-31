import tempfile
import unittest
from pathlib import Path
import reference_set as r

class ReferenceSetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base/'source.png'
        self.source.write_bytes(b'approved identity')
        self.root = Path(r.prepare(self.source, self.base/'cache')['set'])
        self.image = self.base/'view.png'
        self.prompt = self.base/'prompt.txt'; self.prompt.write_text('Exact view instruction')
        self.receipt = self.base/'receipt.json'; self.receipt.write_text('{"requested_model":"gpt-6.1-sol","effort":"low","observed_model":null}')

    def add(self, index):
        self.image.write_bytes(b'fixture image '+str(index).encode())
        return r.record(self.root, f'view-{index:02}', self.image, self.prompt, self.receipt)

    def test_cache_plan_and_resume(self):
        self.assertEqual(r.prepare(self.source, self.base/'cache')['set'], str(self.root))
        self.assertEqual(len(r.plan()), 20)
        self.assertEqual(len({(v['azimuth'],v['elevation']) for v in r.plan()}),20)
        first = self.add(1)
        self.assertEqual(r.record(self.root, 'view-01', self.image, self.prompt, self.receipt), first)
        self.image.write_bytes(b'replacement')
        with self.assertRaisesRegex(ValueError, 'never overwrite'):
            r.record(self.root, 'view-01', self.image, self.prompt, self.receipt)
        self.assertEqual(len(r.verify(self.root)[1]['views']),1)

    def test_incomplete_duplicate_and_wrong_model(self):
        self.add(1)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            r.record(self.root, 'view-02', self.image, self.prompt, self.receipt)
        with self.assertRaisesRegex(ValueError, 'twenty'):
            r.seal(self.root)
        with self.assertRaisesRegex(ValueError, 'coordinator'):
            r.record(self.root, 'view-02', self.image, self.prompt, self.receipt, model='gpt-6-astra')

    def test_seal_and_tampering(self):
        for i in range(1,21): self.add(i)
        seal = r.seal(self.root)
        self.assertEqual(r.seal(self.root), seal)
        r.verify(self.root, require_sealed=True)
        (self.root/'view-03'/'image').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Changed image'):
            r.verify(self.root)

    def test_source_and_plan_tampering(self):
        (self.root/'source.image').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Identity'):
            r.verify(self.root)
        with self.assertRaisesRegex(ValueError, 'differs'):
            r.prepare(self.source,self.base/'cache')

    def test_partial_record_resume_and_conflict(self):
        target = self.root/'view-01'; target.mkdir()
        self.image.write_bytes(b'view one')
        (target/'image').write_bytes(b'conflicting abandoned image')
        with self.assertRaisesRegex(ValueError,'Partial'):
            r.record(self.root,'view-01',self.image,self.prompt,self.receipt)
        (target/'image').write_bytes(self.image.read_bytes())
        r.record(self.root,'view-01',self.image,self.prompt,self.receipt)
        self.assertEqual(len(r.verify(self.root)[1]['views']),1)

if __name__ == '__main__': unittest.main()
