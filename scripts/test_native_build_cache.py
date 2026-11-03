"""Exercise the real OpenSSL envelope with disposable data, not production keys."""
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import native_build_cache as cache
from native_build_performance import select_jobs, configure


class BuildCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vg-cache-test-')
        self.root = Path(self.temporary.name)
        self.source, self.bundle = self.root/'source', self.root/'sealed'
        self.target = self.root/'restored'
        self.context = {'schema':1,'test':'disposable','arch':'arm64'}
        self.environment = patch.dict(os.environ, {'IPA_EXPORT_PASSWORD':secrets.token_hex(32)})
        self.environment.start()
        path = self.source/'cas'/'ab'/('ab'*32)
        path.parent.mkdir(parents=True)
        path.write_bytes(b'PRIVATE-CACHE-MARKER' * 100)
        action = self.source/'ac'/'cd'/('cd'*32)
        action.parent.mkdir(parents=True)
        action.write_bytes(b'action-result')
        (self.source/'signing.p12').write_bytes(b'MUST-NOT-BE-SELECTED')

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def seal(self):
        self.assertTrue(cache.seal(self.source,self.bundle,self.context))

    def test_round_trip_and_exclusion(self):
        self.seal()
        self.assertNotIn(b'PRIVATE-CACHE-MARKER',(self.bundle/'cache.enc').read_bytes())
        self.assertEqual(sorted(p.name for p in self.bundle.iterdir()),['cache.enc','manifest.json'])
        self.assertTrue(cache.restore(self.target,self.bundle,self.context))
        self.assertFalse((self.target/'signing.p12').exists())
        self.assertEqual((self.target/'cas'/'ab'/('ab'*32)).read_bytes(),b'PRIVATE-CACHE-MARKER'*100)

    def test_ciphertext_tampering_rejected_before_decryption(self):
        self.seal()
        blob=self.bundle/'cache.enc';data=bytearray(blob.read_bytes());data[-10]^=1;blob.write_bytes(data)
        with patch.object(cache,'cipher',side_effect=AssertionError('decrypt must not run')):
            with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,self.context)
        self.assertFalse(self.target.exists())

    def test_metadata_and_key_tampering(self):
        self.seal()
        p=self.bundle/'manifest.json';data=json.loads(p.read_bytes());data['metadata']['bytes']-=1;p.write_bytes(cache.canonical(data))
        with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,self.context)
        self.seal()
        with patch.dict(os.environ,{'IPA_EXPORT_PASSWORD':secrets.token_hex(32)}):
            with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,self.context)

    def test_context_existing_destination_and_limits(self):
        self.seal()
        with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,{'different':True})
        with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,self.context,max_expanded=2)
        self.target.mkdir();(self.target/'keep').write_text('keep')
        with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,self.context)
        self.assertEqual((self.target/'keep').read_text(),'keep')
        self.assertFalse(cache.seal(self.source,self.root/'too-small',self.context,max_encrypted=1))
        self.assertFalse(cache.restore(self.root/'absent',self.root/'missing',self.context))

    def test_archive_traversal_links_and_size_lies(self):
        # Even an authenticated malformed archive must not escape the staging directory.
        for name,link,declared in [('../outside',False,1),('cas/aa/'+'aa'*32,True,0),('cas/aa/'+'aa'*32,False,0)]:
            with self.subTest(name=name,link=link,declared=declared):
                self.bundle.mkdir(exist_ok=True)
                plain=self.root/'malformed.tar.gz'
                with tarfile.open(plain,'w:gz') as tar:
                    item=tarfile.TarInfo(name)
                    if link:item.type=tarfile.SYMTYPE;item.linkname='../../outside';tar.addfile(item)
                    else:item.size=1;tar.addfile(item,io.BytesIO(b'x'))
                blob=self.bundle/'cache.enc';cache.cipher(plain,blob)
                metadata=dict(schema=1,context=self.context,bytes=blob.stat().st_size,expanded_bytes=declared,files=1,sha256=cache.digest(blob))
                _,key=cache.keys();manifest=dict(metadata=metadata,tag=hmac.digest(key,cache.canonical(metadata),'sha256').hex())
                (self.bundle/'manifest.json').write_bytes(cache.canonical(manifest))
                with self.assertRaises(ValueError):cache.restore(self.target,self.bundle,self.context)
                self.assertFalse((self.root/'outside').exists())
                self.assertFalse(self.target.exists())

    def test_resource_thresholds_and_names(self):
        gib=1024**3
        self.assertEqual(select_jobs(3,8*gib),2)
        self.assertEqual(select_jobs(4,16*gib),2)
        self.assertEqual(select_jobs(4,24*gib),3)
        self.assertEqual(select_jobs(8,32*gib),4)
        for name in ('../secret','cas/aa/../../secret','cas/aa/not-a-hash','cas/aa/a\\b','/cas/aa/ab','certs/aa/ab'):
            self.assertFalse(cache.valid_name(name),name)
        self.assertTrue(cache.valid_name('cas/ab/'+'ab'*32))

    def test_configuration_preserves_release_settings(self):
        project=self.root/'project';project.mkdir()
        rc=project/'.bazelrc';rc.write_text('build --jobs=2\nbuild --some-existing-option\n')
        with patch.dict(os.environ,{'RUNNER_TEMP':str(self.root)}),patch('native_build_performance.os.cpu_count',return_value=8),patch('native_build_performance.subprocess.check_output',side_effect=[str(32*1024**3),'Xcode 27.1\nBuild version test']):
            configure(project)
        self.assertEqual(rc.read_text(),'build --jobs=4\nbuild --some-existing-option\n')
        self.assertEqual(json.loads((self.root/'native-cache-context.json').read_bytes())['configuration'],'release_arm64')


if __name__=='__main__':
    unittest.main()
