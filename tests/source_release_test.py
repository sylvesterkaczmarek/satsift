#!/usr/bin/env python3
"""Adversarial source-candidate packaging and independent inventory verification."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import source_release as release


class SourceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.repo = self.parent / "checkout"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Release test")
        self.git("config", "user.email", "release@example.invalid")
        self.git("config", "core.autocrlf", "false")
        (self.repo / ".gitignore").write_text(".local-only\n")
        (self.repo / ".gitattributes").write_text("source.txt export-ignore\n")
        (self.repo / "source.txt").write_bytes(b"retained bytes\r\n")
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "run").write_text("#!/bin/sh\nexit 0\n")
        (self.repo / "tools" / "run").chmod(0o755)
        self.commit()
        self.output = self.parent / "candidate"

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE)

    def commit(self):
        self.git("add", "--all")
        self.git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Source fixture")

    def build(self):
        return release.build(self.repo, self.output)

    def manifest(self):
        return json.loads((self.output / "source" / release.MANIFEST).read_text())

    def save_manifest(self, value):
        (self.output / "source" / release.MANIFEST).write_text(json.dumps(value))

    def test_exact_bytes_modes_no_history_or_ignored_files_and_deterministic_archive(self):
        (self.repo / ".local-only").write_text("local material outside the release")
        result = self.build()
        source = self.output / "source"
        self.assertEqual((source / "source.txt").read_bytes(), b"retained bytes\r\n")
        self.assertFalse((source / ".git").exists())
        self.assertFalse((source / ".local-only").exists())
        self.assertEqual((source / "tools/run").stat().st_mode & 0o777, 0o755)
        self.assertEqual(result["source_tree"], self.git("rev-parse", "HEAD^{tree}").decode().strip())
        release.verify_directory(source, result["source_tree"])
        archive = self.output / "satsift-source-candidate.tar.gz"
        with tarfile.open(archive) as reader:
            members = reader.getmembers()
            self.assertTrue(all(item.isfile() for item in members))
            self.assertTrue(all(item.mtime == 0 and item.uid == 0 and item.gid == 0 for item in members))
            self.assertTrue(all(item.uname == "" and item.gname == "" and not item.pax_headers for item in members))
            self.assertTrue(all("/.git/" not in item.name for item in members))
        again = self.parent / "again"
        release.build(self.repo, again)
        self.assertEqual(archive.read_bytes(), (again / archive.name).read_bytes())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertEqual(result["archive_sha256"], digest)
        self.assertEqual((self.output / (archive.name + ".sha256")).read_text(), digest + "  " + archive.name + "\n")

    def test_uncommitted_and_untracked_work_is_rejected(self):
        for staged in (False, True):
            (self.repo / "source.txt").write_text("changed")
            if staged:
                self.git("add", "source.txt")
            with self.assertRaises(release.ReleaseError):
                self.build()
            self.git("reset", "--hard", "--quiet", "HEAD")
        (self.repo / "untracked.txt").write_text("pending")
        with self.assertRaises(release.ReleaseError):
            self.build()

    def test_existing_and_in_checkout_outputs_are_rejected(self):
        self.output.mkdir()
        (self.output / "keep").write_text("unchanged")
        with self.assertRaises(release.ReleaseError):
            self.build()
        self.assertEqual((self.output / "keep").read_text(), "unchanged")
        with self.assertRaises(release.ReleaseError):
            release.build(self.repo, self.repo / "candidate")

    def test_tracked_symlinks_and_private_paths_are_rejected(self):
        (self.repo / "linked").symlink_to("source.txt")
        self.commit()
        with self.assertRaises(release.ReleaseError):
            self.build()
        (self.repo / "linked").unlink()
        (self.repo / ".env").write_text("placeholder")
        self.commit()
        with self.assertRaises(release.ReleaseError):
            self.build()

    def test_noncanonical_and_colliding_inventory_is_rejected(self):
        self.build()
        original = self.manifest()
        for invalid in ("../outside", "/outside", "a//b", "a/./b", "a\\b", ".git/config", "node_modules/code"):
            altered = json.loads(json.dumps(original))
            altered["files"][0]["path"] = invalid
            self.save_manifest(altered)
            with self.subTest(path=invalid), self.assertRaises(release.ReleaseError):
                release.verify_directory(self.output / "source")
        altered = json.loads(json.dumps(original))
        altered["files"].append(dict(altered["files"][0]))
        self.save_manifest(altered)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(self.output / "source")

    def test_content_modes_extra_files_and_symlinks_are_rejected(self):
        self.build()
        source = self.output / "source"
        target = source / "source.txt"
        old = target.read_bytes()
        target.write_text("changed")
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        target.write_bytes(old)
        target.chmod(0o755)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        target.chmod(0o644)
        extra = source / ".env"
        extra.write_text("unexpected")
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        extra.unlink()
        extra.mkdir()
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        extra.rmdir()
        target.unlink()
        target.symlink_to(self.repo / "source.txt")
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)

    def test_manifest_cannot_hide_content_tampering_or_wrong_expected_tree(self):
        self.build()
        source = self.output / "source"
        manifest = self.manifest()
        item = next(row for row in manifest["files"] if row["path"] == "source.txt")
        data = b"tampered"
        (source / "source.txt").write_bytes(data)
        item.update(size=len(data), sha256=release.sha256(data), git_blob=release.object_hash("blob", data, "sha1"))
        self.save_manifest(manifest)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        manifest["source_tree"] = release.tree_hash(manifest["files"], "sha1")
        self.save_manifest(manifest)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source, self.git("rev-parse", "HEAD^{tree}").decode().strip())

    def test_sensitive_matches_are_rejected_without_echoing_values(self):
        samples = (
            b"/Users/" + b"private-owner/source",
            b"prompt " + b"123",
            b"generated by " + b"ChatGPT",
            b"ghp_" + b"A" * 36,
            b"-----BEGIN " + b"PRIVATE KEY-----",
        )
        for sample in samples:
            with self.subTest(sample_type=len(sample)), self.assertRaises(release.ReleaseError) as caught:
                release.scan_content("source.txt", sample)
            self.assertNotIn(sample.decode(), str(caught.exception))
        private = b"private-" + b"hosting-name"
        with self.assertRaises(release.ReleaseError) as caught:
            release.scan_content("source.txt", b"data " + private, (private,))
        self.assertNotIn(private.decode(), str(caught.exception))

    def test_manifest_inventory_can_be_used_after_test_outputs_are_created(self):
        self.build()
        source = self.output / "source"
        generated = source / "__pycache__"
        generated.mkdir()
        (generated / "test.pyc").write_bytes(b"temporary test output")
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        verified = release.verify_directory(source, exact=False)
        self.assertEqual(len(verified["files"]), 4)


    def test_actual_archive_extracts_and_verifies_against_trusted_receipt(self):
        receipt = self.build()
        destination = self.parent / "extracted"
        destination.mkdir()
        with tarfile.open(self.output / "satsift-source-candidate.tar.gz") as reader:
            # This archive is created by this test; all entries were checked as regular.
            self.assertTrue(all(item.isfile() and item.name.startswith("satsift/") and ".." not in Path(item.name).parts for item in reader.getmembers()))
            reader.extractall(destination)
        verified = release.verify_directory(destination / "satsift", receipt["source_tree"], expected_commit=receipt["source_commit"])
        self.assertEqual(len(verified["files"]), 4)

    def test_manifest_metadata_is_strict_and_content_scanned(self):
        self.build()
        original = self.manifest()
        for key, value in (("extra", "unexpected"), ("status", "unreviewed")):
            changed = dict(original)
            changed[key] = value
            self.save_manifest(changed)
            with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                release.verify_directory(self.output / "source")
        changed = dict(original)
        private = "private-" + "metadata-value"
        changed["extra"] = private
        self.save_manifest(changed)
        with self.assertRaises(release.ReleaseError) as caught:
            release.verify_directory(self.output / "source", original["source_tree"], deny_literals=(private.encode(),))
        self.assertIn("deny-list", str(caught.exception))
        self.assertNotIn(private, str(caught.exception))

    def test_manifest_links_modes_and_claimed_commit_are_checked(self):
        receipt = self.build()
        source = self.output / "source"
        manifest_file = source / release.MANIFEST
        outside = self.parent / "manifest-link"
        os.link(manifest_file, outside)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        outside.unlink()
        manifest_file.chmod(0o755)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source)
        manifest_file.chmod(0o644)
        changed = self.manifest()
        changed["source_commit"] = "0" * 40
        self.save_manifest(changed)
        with self.assertRaises(release.ReleaseError):
            release.verify_directory(source, receipt["source_tree"], expected_commit=receipt["source_commit"])

    def test_sensitive_filename_is_checked_and_redacted(self):
        private = "private-" + "filename-value"
        with self.assertRaises(release.ReleaseError) as caught:
            release.scan_content(private + ".txt", b"ordinary content", (private.encode(),))
        self.assertNotIn(private, str(caught.exception))
        token_name = "ghp_" + "A" * 36
        with self.assertRaises(release.ReleaseError) as caught:
            release.scan_content(token_name + ".txt", b"ordinary content")
        self.assertNotIn(token_name, str(caught.exception))

if __name__ == "__main__":
    unittest.main()
