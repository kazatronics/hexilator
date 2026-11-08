# SPDX-License-Identifier: Apache-2.0
"""Tests for mise-tasks/install, run against a scratch source repo. No FreeCAD needed."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.environ.get("HEXILATOR_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))
INSTALL = os.path.join(ROOT, "mise-tasks", "install")

# Commits in the scratch repos need an identity; an empty address keeps any address out of here.
IDENT = ["-c", "user.name=hexilator-test", "-c", "user.email=", "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main"]


def clean_env(**extra):
    """The environment without git's variables (the test itself may run inside a hook)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra)
    return env


def git(*args, cwd=None, env=None):
    return subprocess.run(["git", *IDENT, *args], cwd=cwd, env=env or clean_env(), check=True,
                          capture_output=True, text=True).stdout.strip()


def package_xml(version):
    return "<package>\n  <version>%s</version>\n</package>\n" % version


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hexilator-install-")
        self.src = os.path.join(self.tmp, "src")
        self.data = os.path.join(self.tmp, "data")
        self.dest = os.path.join(self.data, "Mod", "Hexilator")
        os.makedirs(self.src)
        git("init", "-q", cwd=self.src)
        self.commit("1.2.3")
        git("tag", "v1.2.3", cwd=self.src)
        self.c1 = git("rev-parse", "HEAD", cwd=self.src)
        self.commit("1.2.4")
        self.c2 = git("rev-parse", "HEAD", cwd=self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def commit(self, version):
        with open(os.path.join(self.src, "package.xml"), "w") as f:
            f.write(package_xml(version))
        git("add", "package.xml", cwd=self.src)
        git("commit", "-q", "-m", "v" + version, cwd=self.src)

    def install(self, ref, **extra):
        env = clean_env(FREECAD_USER_DATA=self.data, HEXILATOR_SOURCE=self.src, **extra)
        return subprocess.run(["bash", INSTALL, ref], env=env, capture_output=True, text=True,
                              cwd=self.tmp)

    def installed(self):
        head = git("rev-parse", "HEAD", cwd=self.dest)
        with open(os.path.join(self.dest, "package.xml")) as f:
            return head, f.read()

    def assertInstalled(self, res, sha, version):
        self.assertEqual(res.returncode, 0, res.stderr)
        head, xml = self.installed()
        self.assertEqual(head, sha)
        self.assertIn("<version>%s</version>" % version, xml)
        self.assertIn("Hexilator %s" % version, res.stdout)

    def test_branch_follows_latest(self):
        self.assertInstalled(self.install("main"), self.c2, "1.2.4")

    def test_tag(self):
        self.assertInstalled(self.install("v1.2.3"), self.c1, "1.2.3")

    def test_full_sha_pins(self):
        self.assertInstalled(self.install(self.c1), self.c1, "1.2.3")
        res = self.install(self.c1[:12])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("full 40-character", res.stderr)

    def test_bad_ref(self):
        res = self.install("no-such-ref")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("no branch, tag or commit 'no-such-ref'", res.stderr)

    def test_rerun_and_switch(self):
        self.assertInstalled(self.install("v1.2.3"), self.c1, "1.2.3")
        self.assertInstalled(self.install("v1.2.3"), self.c1, "1.2.3")
        self.assertInstalled(self.install("main"), self.c2, "1.2.4")

    def test_git_hook_environment(self):
        """Issue #3: with GIT_DIR etc. pointing at another repo (as in a git hook), the install
        still works on the Mod checkout and leaves the other repo alone."""
        caller = os.path.join(self.tmp, "caller")
        git("init", "-q", caller)
        git("remote", "add", "origin", "https://example.invalid/caller.git", cwd=caller)
        gitdir = os.path.join(caller, ".git")
        hook_env = {"GIT_DIR": gitdir, "GIT_WORK_TREE": caller,
                    "GIT_INDEX_FILE": os.path.join(gitdir, "index")}
        self.assertInstalled(self.install("v1.2.3", **hook_env), self.c1, "1.2.3")
        self.assertInstalled(self.install("main", **hook_env), self.c2, "1.2.4")  # existing
        self.assertEqual(git("remote", "get-url", "origin", cwd=caller),
                         "https://example.invalid/caller.git")
        self.assertEqual(git("for-each-ref", cwd=caller), "")
        self.assertEqual(os.path.realpath(git("remote", "get-url", "origin", cwd=self.dest)),
                         os.path.realpath(self.src))

    def test_from_a_real_hook(self):
        """Issue #3 as reported: the install run by a pre-merge-commit hook during a merge in a
        worktree, where git hands the hook GIT_DIR and GIT_INDEX_FILE of the worktree."""
        caller = os.path.join(self.tmp, "caller")
        wt = os.path.join(self.tmp, "caller-wt")
        git("init", "-q", caller)
        git("remote", "add", "origin", "https://example.invalid/caller.git", cwd=caller)
        self.write(caller, "a")
        git("worktree", "add", "-q", wt, "-b", "side", cwd=caller)
        self.write(caller, "b")
        self.write(wt, "c")
        hook = os.path.join(caller, ".git", "hooks", "pre-merge-commit")
        with open(hook, "w") as f:
            f.write("#!/bin/sh\nexec bash '%s' v1.2.3\n" % INSTALL)
        os.chmod(hook, 0o755)
        res = subprocess.run(["git", *IDENT, "merge", "-q", "--no-ff", "main", "-m", "merge"],
                             cwd=wt, capture_output=True, text=True,
                             env=clean_env(FREECAD_USER_DATA=self.data, HEXILATOR_SOURCE=self.src))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.installed()[0], self.c1)
        self.assertEqual(git("remote", "get-url", "origin", cwd=caller),
                         "https://example.invalid/caller.git")
        self.assertEqual(git("status", "--porcelain", cwd=wt), "")
        self.assertEqual(git("for-each-ref", "refs/tags", cwd=caller), "")

    @staticmethod
    def write(repo, name):
        with open(os.path.join(repo, name), "w") as f:
            f.write(name + "\n")
        git("add", name, cwd=repo)
        git("commit", "-q", "-m", name, cwd=repo)


if __name__ == "__main__":
    unittest.main()
