#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import shutil
import io
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("deploy_production", ROOT / "tools/deploy_production.py")
assert SPEC and SPEC.loader
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)

TEST_SITE_ROOT = "public_html/example-site"
TEST_SSH_ALIAS = "smd-production"
deploy.configure_target(TEST_SITE_ROOT, TEST_SSH_ALIAS)


EXPECTED_PUBLIC_FILES = (
    "index.html",
    "app-3.4.js",
    "history.php",
    "docs.html",
    "benchmark.html",
    "accessibility.html",
    "benchmark-template.json",
    "public-evidence-manifest-v0.1.json",
    "plotly-3.3.1.min.js",
    "satellite-6.0.2.min.js",
    "app/common.js", "app/orbital-input.js", "app/benchmark.js",
    "app/packages.js", "app/detection.js", "app/interface.js",
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_deployment_error(callable_, message: str) -> None:
    try:
        callable_()
    except deploy.DeploymentError:
        return
    raise AssertionError(message)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_configuration_guards() -> None:
    with patch.dict(os.environ, {}, clear=True):
        expect_deployment_error(deploy.configure_target, "missing local deployment root was accepted")
        expect_deployment_error(lambda: deploy.ssh_command(None), "unconfigured SSH target was accepted")
        for root in ("", "/absolute/site", ".", "..", "public_html/../other", "public_html/./site", "public_html//site", "public_html/site/", "public_html/site with spaces", "public_html/$(command)", "-option", "public_html/site;command", "public_html/line\nsite", "public_html/site\x00"):
            expect_deployment_error(lambda: deploy.configure_target(root), "unsafe deployment root was accepted")
        for alias in ("", "-option", "user@host", "host:folder", "host;command", "host name", "host\nname"):
            expect_deployment_error(lambda: deploy.configure_target(TEST_SITE_ROOT, alias), "unsafe SSH alias was accepted")
        deploy.configure_target(TEST_SITE_ROOT)
        check(deploy.SSH_ALIAS == TEST_SSH_ALIAS, "neutral default SSH alias changed")
        deploy.configure_target(TEST_SITE_ROOT, "custom-production")
        check(deploy.SSH_ALIAS == "custom-production", "operator SSH profile was ignored")
        expect_deployment_error(lambda: deploy.configure_target("../unsafe"), "invalid reconfiguration was accepted")
        expect_deployment_error(lambda: deploy.ssh_command(None), "invalid reconfiguration retained a previous target")
        with patch.object(deploy, "run", side_effect=AssertionError("missing configuration reached a command")):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                check(deploy.main(["--dry-run"]) == 1, "CLI did not fail closed without destination configuration")
            check("SMD_REMOTE_SITE_ROOT" in errors.getvalue(), "missing configuration error was unclear")
        with patch.dict(os.environ, {"SMD_REMOTE_SITE_ROOT": TEST_SITE_ROOT, "SMD_SSH_ALIAS": TEST_SSH_ALIAS}):
            deploy.configure_target()
        check(str(deploy.REMOTE_SITE_ROOT) == TEST_SITE_ROOT, "local destination setting was ignored")


def test_repository_guards() -> None:
    original_origins = deploy.EXPECTED_ORIGIN_URLS
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        remote = root / "origin.git"
        repo = root / "repo"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Deployment Test")
        git(repo, "config", "user.email", "deployment-test@example.invalid")
        (repo / "tracked.txt").write_text("clean\n")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-m", "fixture")
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "push", "-u", "origin", "main")
        deploy.EXPECTED_ORIGIN_URLS = {str(remote)}
        branch, commit = deploy.validate_repository(repo, execute=True)
        check(branch == "main" and len(commit) == 40, "clean main repository was rejected")

        (repo / "tracked.txt").write_text("dirty\n")
        expect_deployment_error(
            lambda: deploy.validate_repository(repo, execute=False),
            "dirty working tree was accepted",
        )
        git(repo, "restore", "tracked.txt")
        git(repo, "switch", "-c", "feature")
        expect_deployment_error(
            lambda: deploy.validate_repository(repo, execute=True),
            "production execution from a non-main branch was accepted",
        )
        branch, _ = deploy.validate_repository(repo, execute=False)
        check(branch == "feature", "read-only planning should be available on a clean review branch")
        git(repo, "switch", "main")
        (repo / "tracked.txt").write_text("unpushed\n")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-m", "not reviewed on origin")
        expect_deployment_error(
            lambda: deploy.validate_repository(repo, execute=True),
            "unpublished local main commit was accepted for production",
        )
    deploy.EXPECTED_ORIGIN_URLS = original_origins


def test_alias_guard() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = Path(temporary) / "config"
        config.write_text("Host github.com\n  HostName github.com\n  User git\n")
        expect_deployment_error(
            lambda: deploy.validate_ssh_alias(config),
            "missing smd-production alias was accepted",
        )
        config.write_text("Host smd-production\n  HostName example.invalid\n  User deploy-user\n")
        deploy.validate_ssh_alias(config)
        config.write_text(
            "Host smd-production\n  HostName example.invalid\n  User deploy-user\n"
            "  ProxyCommand /bin/sh -c unsafe\n"
        )
        expect_deployment_error(
            lambda: deploy.validate_ssh_alias(config),
            "SSH alias with ProxyCommand execution was accepted",
        )
        config.write_text(
            "Host smd-production\n  HostName example.invalid\n  User deploy-user\n"
            "  StdinNull yes\n"
        )
        expect_deployment_error(
            lambda: deploy.validate_ssh_alias(config),
            "SSH alias that discards remote-script stdin was accepted",
        )


def test_remote_script_transport() -> None:
    calls: list[tuple[list[str], dict]] = []
    original_run = deploy.run

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    hostile_looking = 'set -eu\nvalue="literal ; false ; $(not-executed)"\nprintf "%s\\n" "$value"\n'
    deploy.run = fake_run
    try:
        deploy.run_remote_script(None, hostile_looking, safe_error="fixture failed")
        command, kwargs = calls[-1]
        check(command[-1] == deploy.REMOTE_SHELL_COMMAND == "sh", "remote SSH command is not fixed")
        check(all("\n" not in argument for argument in command), "multiline content escaped into SSH argv")
        check(hostile_looking not in command, "remote script escaped into SSH argv")
        check(kwargs["input_bytes"] == hostile_looking.encode(), "remote script bytes changed in transport")

        calls.clear()
        deploy.check_remote_paths(None)
        command, kwargs = calls[-1]
        check(command[-1] == "sh", "path checks do not use fixed-shell stdin transport")
        check(kwargs["input_bytes"] == deploy.REMOTE_SANITY_COMMAND.encode(), "path guard script changed in transport")

        calls.clear()
        with tempfile.TemporaryDirectory() as temporary:
            sentinel = Path(temporary) / "injected"
            hostile_path = deploy.PurePosixPath(f'missing/$(touch {sentinel});\'quoted')
            deploy.fetch_remote_file(None, hostile_path)
            command, kwargs = calls[-1]
            remote_script = kwargs["input_bytes"]
            check(command[-1] == "sh", "remote path content escaped into the SSH command")
            check(str(hostile_path) not in command, "hostile remote path entered SSH argv")
            result = subprocess.run(
                ["sh"],
                input=remote_script,
                cwd=temporary,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            check(result.returncode != 0, "hostile missing path unexpectedly succeeded")
            check(not sentinel.exists(), "hostile remote path achieved shell execution")
    finally:
        deploy.run = original_run

    stackcp_style_command = " ".join(deploy.ssh_command(None)[-1].splitlines())
    check(stackcp_style_command == "sh", "StackCP-style argument flattening can alter the fixed command")
    probe = b'set -eu\nvalue="line structure survived"\ntest "$value" = "line structure survived"\n'
    result = subprocess.run([stackcp_style_command], input=probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    check(result.returncode == 0, "stdin script did not survive StackCP-style command flattening")
    try:
        deploy.run(["sh"], input_bytes=b"exit 37\n", safe_error="remote fixture failed")
    except deploy.DeploymentError as exc:
        check("exit status 37" in str(exc), "remote exit status was not propagated")
    else:
        raise AssertionError("nonzero remote script exit was accepted")
    expect_deployment_error(
        lambda: deploy.run_remote_script(None, "bad\x00script", safe_error="fixture failed"),
        "NUL-containing remote script was accepted",
    )



def test_allowlist_and_dry_run_commands() -> None:
    check(deploy.PUBLIC_APP_FILES == EXPECTED_PUBLIC_FILES, "public deployment allowlist changed")
    deploy.validate_allowlist(ROOT)
    forbidden = ("research", "review", "tests", "benchmark-results", "config")
    check(all(not relative.startswith(forbidden) for relative in deploy.PUBLIC_APP_FILES),
          "repository-only directory entered public deployment allowlist")
    check(".space-track-config.php" not in deploy.PUBLIC_APP_FILES, "private config entered allowlist")
    check(all(".satellite-maneuver-cache" not in relative for relative in deploy.PUBLIC_APP_FILES),
          "private cache entered allowlist")
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        site_files = {}
        for name in deploy.SITE_FILES:
            path = staging / name
            path.write_text("fixture\n")
            site_files[name] = path
        app_staging = deploy.stage_public_assets(ROOT, staging / "application")
        commands = deploy.rsync_commands(ROOT, site_files, None, dry_run=True, app_staging=app_staging)
        check(len(commands) == 20, "deployment plan must contain seventeen app and three site-root writes")
        for command in commands:
            check("--dry-run" in command, "dry-run plan contains a writing rsync command")
            check(not any(flag in command for flag in ("--delete", "--delete-excluded", "--relative", "--no-implied-dirs")),
                  "destructive or directory-creating rsync option found")
            check(command[-1].startswith("smd-production:public_html/example-site/"), "unexpected remote destination")
            check(command[-3] == "--", "rsync source is not protected by the option terminator")
            check(Path(command[-2]).is_file(), "planned source was not staged")
        check(commands[-2][-1].endswith('/app-3.4.js'), 'legacy bootstrap must activate after routes and dependencies')
        check(commands[-1][-1].endswith('/index.html'), 'index.html must be the final deployment upload')
        check(commands[-3][-1].endswith('/.htaccess'), '.htaccess must be ready before entry activation')
        immutable_destinations = {f"{deploy.SSH_ALIAS}:{deploy.REMOTE_APP_ROOT}/{asset['target']}"
                                  for asset in deploy.browser_assets(ROOT)}
        immutable_commands = [command for command in commands if command[-1] in immutable_destinations]
        check(len(immutable_commands) == 7, "the complete immutable graph was not planned")
        for command in immutable_commands:
            check(Path(command[-2]).name == command[-1].rsplit('/', 1)[-1],
                  "staged content filename does not match the exact immutable destination")
        absent_commands = deploy.rsync_commands(ROOT, site_files, None, dry_run=True,
                                                app_staging=app_staging, module_directory_exists=False)
        check(len(absent_commands) == 13, "first migration must simulate only destinations whose parents exist")
        check(not any(command[-1] in immutable_destinations for command in absent_commands),
              "first-install dry run attempted a transfer into an absent directory")
        execute_commands = deploy.rsync_commands(ROOT, site_files, None, dry_run=False,
                                                 app_staging=app_staging, module_directory_exists=False)
        check(len(execute_commands) == 20, "real first installation omitted approved immutable assets")
        check(all("--dry-run" not in command for command in execute_commands), "execute plan retained dry-run")
    unusual_config = Path("/tmp/config with ' quote")
    transport = deploy.rsync_transport(unusual_config)
    check(shlex.split(transport)[0:3] == ["ssh", "-F", str(unusual_config)], "SSH config path was not safely quoted")
    check("StrictHostKeyChecking=yes" in transport, "rsync SSH transport permits unknown host keys")
    check("ClearAllForwardings=yes" in transport, "rsync SSH transport permits forwarding")
    check("test ! -L" in deploy.REMOTE_SANITY_COMMAND, "remote symlink guard is missing")
    check("public_html/example-site/tools/satellite-maneuver-detector" in deploy.REMOTE_SANITY_COMMAND, "remote path guard drifted")
    check('test "$smd_site_real" = "$smd_home_real/$site"' in deploy.REMOTE_SANITY_COMMAND, "remote site root is not anchored to the SSH home")



def test_direct_rsync_dry_run_leaves_files_and_directories_unchanged() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = Path(temporary)
        app_staging = deploy.stage_public_assets(ROOT, fixture / 'staging')
        home = fixture / 'remote'
        site = home / TEST_SITE_ROOT
        app = site / 'tools/satellite-maneuver-detector'
        app.mkdir(parents=True)
        for name in deploy.LEGACY_APP_FILES:
            (app / name).write_bytes(b'previous application')
        site_files = {}
        for name in deploy.SITE_FILES:
            (site / name).write_bytes(b'previous site')
            source = fixture / name
            source.write_bytes(b'next site')
            site_files[name] = source
        def snapshot():
            return {str(path.relative_to(home)): path.read_bytes() if path.is_file() else None
                    for path in home.rglob('*')}
        def local_command(command):
            # Exercise the generated flags and filenames with local fixture destinations.
            transport = command.index('-e')
            destination = home / command[-1].split(':', 1)[1]
            return command[:transport] + command[transport + 2:-1] + [str(destination)]
        for directory_present in (False, True):
            if directory_present:
                (app / 'app').mkdir()
            before = snapshot()
            commands = deploy.rsync_commands(ROOT, site_files, None, dry_run=True,
                                             app_staging=app_staging,
                                             module_directory_exists=directory_present)
            for command in commands:
                subprocess.run(local_command(command), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            check(snapshot() == before, 'actual rsync dry run changed a target file or directory')
        asset = deploy.browser_assets(ROOT)[0]
        commands = deploy.rsync_commands(ROOT, site_files, None, dry_run=False, app_staging=app_staging)
        command = next(command for command in commands if command[-1].endswith('/' + asset['target']))
        subprocess.run(local_command(command), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        check((app / asset['target']).read_bytes() == (ROOT / asset['source']).read_bytes(),
              'direct rsync did not preserve the immutable filename and bytes')
        check(not (app / asset['source']).exists(), 'canonical module source became a public target')


def test_remote_path_resolution() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary)
        site = home / TEST_SITE_ROOT
        app = site / "tools/satellite-maneuver-detector"
        app.mkdir(parents=True)
        for source, target in deploy.public_asset_files(ROOT):
            (app / target).parent.mkdir(parents=True, exist_ok=True)
            (app / target).write_bytes((ROOT / source).read_bytes())
        for name in deploy.SITE_FILES:
            (site / name).write_text("fixture\n")
        def run_guard():
            return subprocess.run(["sh"], input=deploy.REMOTE_SANITY_COMMAND.encode(), cwd=home, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        check(run_guard().returncode == 0, "configured legitimate site failed remote path checks")
        relocated = site.with_name("relocated-site")
        site.rename(relocated)
        site.symlink_to(relocated, target_is_directory=True)
        check(run_guard().returncode != 0, "symlinked site destination was accepted")
        site.unlink()
        relocated.rename(site)
        (app / "index.html").unlink()
        (app / "index.html").symlink_to(site / ".htaccess")
        check(run_guard().returncode != 0, "symlinked application target was accepted")


def test_site_file_merges() -> None:
    managed = (ROOT / "deployment/site-root.htaccess").read_text()
    unrelated = "# unrelated host configuration\nRewriteRule ^about$ about.html [L]\n"
    merged = deploy.merge_htaccess(unrelated, managed)
    check(unrelated.strip() in merged, "unrelated .htaccess content was not preserved")
    check(merged.count(deploy.MANAGED_BEGIN) == 1, "managed .htaccess block was not added exactly once")
    updated = deploy.merge_htaccess(merged.replace("Workbench", "obsolete"), managed)
    check(updated.count(deploy.MANAGED_BEGIN) == 1, "managed .htaccess update duplicated the block")
    expect_deployment_error(
        lambda: deploy.merge_htaccess("RewriteRule ^satellite-maneuver-detector old-target [L]\n", managed),
        "ambiguous unmarked detector routing was accepted",
    )
    expect_deployment_error(
        lambda: deploy.merge_htaccess("RewriteRule ^SATELLITE-MANEUVER-DETECTOR old-target [L]\n", managed),
        "case-variant unmarked detector routing was accepted",
    )
    expect_deployment_error(
        lambda: deploy.merge_htaccess(merged + deploy.MANAGED_END + "\n", managed),
        "duplicate .htaccess end marker was accepted",
    )
    expect_deployment_error(
        lambda: deploy.merge_htaccess(merged + "RewriteRule ^satellite-maneuver-detector legacy [L]\n", managed),
        "detector routing outside the managed block was accepted",
    )

    robots = "User-agent: *\nDisallow: /private/\n\nUser-agent: ExampleBot\nDisallow: /\n"
    merged_robots = deploy.merge_robots(robots)
    check("Disallow: /private/" in merged_robots, "unrelated robots policy was removed")
    check("User-agent: ExampleBot\nDisallow: /" in merged_robots, "other crawler group was removed")
    check(merged_robots.count(deploy.ROBOTS_BEGIN) == 1, "robots managed block count is wrong")
    check(merged_robots.count(f"Sitemap: {deploy.SITEMAP_URL}") == 1, "sitemap declaration count is wrong")
    expect_deployment_error(
        lambda: deploy.merge_robots("User-agent: *\nDisallow:\nUser-agent: *\nDisallow: /duplicate\n"),
        "ambiguous duplicate wildcard robots groups were accepted",
    )

    sitemap = b'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.sylvesterkaczmarek.com/unrelated</loc></url>
  <!-- unrelated comment must survive -->
  <url><loc>https://www.sylvesterkaczmarek.com/satellite-maneuver-detector-article</loc></url>
  <url><loc>https://www.sylvesterkaczmarek.com/satellite-maneuver-detector.html</loc></url>
</urlset>'''
    merged_sitemap = deploy.merge_sitemap(sitemap).decode()
    check("/unrelated" in merged_sitemap, "unrelated sitemap URL was removed")
    check("unrelated comment must survive" in merged_sitemap, "unrelated sitemap XML comment was removed")
    check("satellite-maneuver-detector-article" in merged_sitemap, "similarly prefixed unrelated URL was removed")
    check("satellite-maneuver-detector.html" not in merged_sitemap, "stale detector sitemap URL survived")
    for url in deploy.PUBLIC_URLS:
        check(merged_sitemap.count(f"<loc>{url}</loc>") == 1, f"public detector URL missing or duplicated: {url}")


def test_backup_restore_and_hash_contract() -> None:
    calls: list[tuple[list[str], dict]] = []
    original_run = deploy.run

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    deploy.run = fake_run
    try:
        site_hashes = {name: "a" * 64 for name in deploy.SITE_FILES}
        rollback = deploy.retain_immutable_routes("# unrelated host policy\\n", (ROOT / "deployment/site-root.htaccess").read_text()).encode()
        backup_dir = deploy.backup_release(None, "b" * 40, site_hashes, rollback_htaccess=rollback)
        check(str(backup_dir).startswith(".satellite-maneuver-deploy-backups/bbbbbbbbbbbb-"), "backup path is unsafe")
        check(calls[-1][0][-1] == "sh", "backup does not use fixed-shell stdin transport")
        backup_command = calls[-1][1]["input_bytes"].decode()
        subprocess.run(["sh", "-n", "-c", backup_command], check=True)
        check(backup_command.count("cp -p --") == 13, "backup does not cover every mutable deployment target")
        check("sha256sum" in backup_command, "site-root optimistic-concurrency check is missing")
        check("retained-routes.htaccess" in backup_command, "compatible rollback routing was not backed up")
        check(str(deploy.REMOTE_LOCK_PATH) in backup_command, "remote deployment lock is missing")
        deploy.restore_release(None, backup_dir, "b" * 40)
        check(calls[-1][0][-1] == "sh", "rollback does not use fixed-shell stdin transport")
        restore_command = calls[-1][1]["input_bytes"].decode()
        subprocess.run(["sh", "-n", "-c", restore_command], check=True)
        check(restore_command.count("cp -p --") == 13, "rollback does not restore every mutable deployment target")
        expected = {deploy.REMOTE_APP_ROOT / "index.html": "c" * 64}
        deploy.verify_remote_hashes(None, expected)
        check("sha256sum" in calls[-1][1]["input_bytes"].decode(), "post-upload hash verification is missing")
        deploy.release_deployment_lock(None)
        lock_script = calls[-1][1]["input_bytes"].decode()
        check(lock_script == f"set -eu\nrmdir -- {deploy.REMOTE_LOCK_PATH}\n", "deployment lock cleanup drifted")
    finally:
        deploy.run = original_run




def test_new_immutable_assets_and_rollback() -> None:
    original_remote = deploy.run_remote_script
    template = (ROOT / 'deployment/site-root.htaccess').read_text()
    legacy_main, immutable_block = deploy._separate_immutable_routes(template, required=True)
    unrelated = '# unrelated host rules\nRewriteRule ^about$ about.html [L]\n'
    previous_htaccess = unrelated + legacy_main
    for previous_assets in (False, True):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            site = home / TEST_SITE_ROOT
            app = site / 'tools/satellite-maneuver-detector'
            app.mkdir(parents=True)
            originals = {}
            for name in deploy.LEGACY_APP_FILES:
                content = ('previous installation ' + name).encode()
                (app / name).write_bytes(content)
                originals[app / name] = content
            old_routes = (deploy.retain_immutable_routes(previous_htaccess, template)
                          if previous_assets else previous_htaccess)
            site_hashes = {}
            for name in deploy.SITE_FILES:
                content = old_routes.encode() if name == '.htaccess' else ('previous site ' + name).encode()
                (site / name).write_bytes(content)
                originals[site / name] = content
                site_hashes[name] = hashlib.sha256(content).hexdigest()
            expected_rollback_routes = deploy.retain_immutable_routes(old_routes, template).encode()
            prior_asset = app / 'app/common-0123456789ab.js'
            if previous_assets:
                prior_asset.parent.mkdir()
                prior_asset.write_bytes(b'previous immutable asset')
            def remote(_config, script, *, safe_error):
                result = subprocess.run(['sh'], input=script.encode(), cwd=home,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode:
                    raise deploy.DeploymentError(safe_error)
                return result
            deploy.run_remote_script = remote
            try:
                remote(None, deploy.REMOTE_SANITY_COMMAND, safe_error='valid legacy install rejected')
                check(deploy.remote_module_directory_exists(None) == previous_assets,
                      'read-only asset directory status is wrong')
                asset = deploy.browser_assets(ROOT)[0]
                target = app / asset['target']
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(b'incorrect bytes under a valid hash name')
                expect_deployment_error(lambda: remote(None, deploy.REMOTE_SANITY_COMMAND, safe_error='collision'),
                                        'immutable hash collision was accepted')
                target.unlink()
                target.symlink_to(app / 'index.html')
                expect_deployment_error(lambda: remote(None, deploy.REMOTE_SANITY_COMMAND, safe_error='symlink'),
                                        'symlinked immutable asset was accepted')
                target.unlink()
                if not previous_assets:
                    target.parent.rmdir()
                backup = deploy.backup_release(None, 'c' * 40, site_hashes,
                                               rollback_htaccess=expected_rollback_routes)
                check((home / backup / 'site/.htaccess').read_bytes() == originals[site / '.htaccess'],
                      'raw original routing backup changed')
                deploy.ensure_module_directory(None)
                for source, name in deploy.public_asset_files(ROOT):
                    shutil.copy2(ROOT / source, app / name)
                for name in deploy.SITE_FILES:
                    (site / name).write_bytes(b'partially replaced site')
                saved_directory = home / 'uploaded-module-directory'
                (app / 'app').rename(saved_directory)
                linked_directory = home / 'linked-sentinel-directory'
                linked_directory.mkdir()
                linked_sentinel = linked_directory / Path(asset['target']).name
                linked_sentinel.write_bytes(b'untouched linked sentinel')
                (app / 'app').symlink_to(linked_directory, target_is_directory=True)
                entry_before_rejected_restore = (app / 'index.html').read_bytes()
                expect_deployment_error(lambda: deploy.restore_release(None, backup, 'c' * 40),
                                        'rollback accepted a symlinked module parent')
                check(linked_sentinel.read_bytes() == b'untouched linked sentinel',
                      'rollback touched a file outside the permitted module directory')
                check((app / 'index.html').read_bytes() == entry_before_rejected_restore,
                      'rollback wrote files before validating all parents')
                (app / 'app').unlink()
                saved_directory.rename(app / 'app')
                deploy.restore_release(None, backup, 'c' * 40)
                for path, content in originals.items():
                    if path.name != '.htaccess':
                        check(path.read_bytes() == content, 'original mutable bytes were not restored')
                restored_routes = (site / '.htaccess').read_bytes()
                check(restored_routes == expected_rollback_routes, 'compatible routing was not restored')
                cleaned, retained = deploy._separate_immutable_routes(restored_routes.decode(), required=True)
                check(retained == immutable_block, 'rollback changed the reviewed immutable route block')
                check(previous_htaccess in cleaned, 'rollback changed unrelated or legacy routing bytes')
                check(restored_routes.decode().index(deploy.IMMUTABLE_BEGIN) <
                      restored_routes.decode().index(deploy.MANAGED_BEGIN),
                      'retained module routes must precede legacy main rules')
                for item in deploy.browser_assets(ROOT):
                    check((app / item['target']).read_bytes() == (ROOT / item['source']).read_bytes(),
                          'rollback removed or changed approved immutable graph bytes')
                check(not any((app / name).exists() for name in deploy.MODULE_SOURCES),
                      'canonical module files became public rollback targets')
                if previous_assets:
                    check(prior_asset.read_bytes() == b'previous immutable asset',
                          'prior immutable asset was changed during rollback')
                deploy.release_deployment_lock(None)
            finally:
                deploy.run_remote_script = original_remote


def test_partial_upload_rollback_orchestration() -> None:
    names = (
        "expected_release_hashes",
        "backup_release",
        "ensure_module_directory",
        "run",
        "verify_remote_hashes",
        "restore_release",
        "release_deployment_lock",
    )
    originals = {name: getattr(deploy, name) for name in names}
    events: list[str] = []
    upload_count = 0

    def fake_run(command, **_kwargs):
        nonlocal upload_count
        upload_count += 1
        events.append(f"upload-{upload_count}")
        if upload_count == 2:
            raise deploy.DeploymentError("simulated interruption")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    deploy.expected_release_hashes = lambda *_args: {}
    deploy.backup_release = lambda *_args: deploy.PurePosixPath(".satellite-maneuver-deploy-backups/test")
    deploy.run = fake_run
    deploy.ensure_module_directory = lambda *_args: events.append("prepare-directory")
    deploy.verify_remote_hashes = lambda *_args: events.append("verify")
    deploy.restore_release = lambda *_args: events.append("restore")
    deploy.release_deployment_lock = lambda *_args: events.append("unlock")
    try:
        expect_deployment_error(
            lambda: deploy.execute_release(
                ROOT,
                None,
                "d" * 40,
                {"_rollback_htaccess": ROOT / "deployment/site-root.htaccess"},
                {},
                [["rsync", "first"], ["rsync", "second"], ["rsync", "third"]],
            ),
            "partial upload failure did not fail the release",
        )
        check(events == ["prepare-directory", "upload-1", "upload-2", "restore", "unlock"], "partial upload did not restore and unlock")
    finally:
        for name, value in originals.items():
            setattr(deploy, name, value)



def test_immutable_hashes_are_verified_before_entry_activation() -> None:
    for fail_graph in (False, True):
        events = []
        def upload(command, **_kwargs):
            events.append(command[-1].rsplit('/', 1)[-1])
            return subprocess.CompletedProcess(command, 0, b"", b"")
        def verify(_config, hashes):
            if len(hashes) == 7:
                events.append('verify-graph')
                if fail_graph:
                    raise deploy.DeploymentError('simulated immutable hash mismatch')
            else:
                events.append('verify-release')
        mocks = {
            'expected_release_hashes': lambda *_args: {},
            'backup_release': lambda *_args: deploy.PurePosixPath('.satellite-maneuver-deploy-backups/test'),
            'ensure_module_directory': lambda *_args: events.append('prepare-directory'),
            'run': upload,
            'verify_remote_hashes': verify,
            'restore_release': lambda *_args: events.append('restore'),
            'release_deployment_lock': lambda *_args: events.append('unlock'),
        }
        commands = [['rsync', 'remote/' + name] for name in ('module.js', '.htaccess', 'app-3.4.js', 'index.html')]
        with patch.multiple(deploy, **mocks):
            action = lambda: deploy.execute_release(
                ROOT, None, 'd' * 40, {'_rollback_htaccess': ROOT / 'deployment/site-root.htaccess'}, {}, commands)
            if fail_graph:
                expect_deployment_error(action, 'invalid graph was activated')
                expected = ['prepare-directory', 'module.js', '.htaccess', 'verify-graph', 'restore', 'unlock']
            else:
                action()
                expected = ['prepare-directory', 'module.js', '.htaccess', 'verify-graph',
                            'app-3.4.js', 'index.html', 'verify-release', 'unlock']
        check(events == expected, 'immutable hash verification did not gate entry activation')


def test_cache_purge_guard() -> None:
    previous = os.environ.get("SMD_CACHE_PURGE_COMMAND")
    try:
        os.environ.pop("SMD_CACHE_PURGE_COMMAND", None)
        with redirect_stdout(io.StringIO()) as output:
            deploy.maybe_purge_cache(execute=False)
        check("not configured" in output.getvalue(), "missing cache purge was not reported")
        os.environ["SMD_CACHE_PURGE_COMMAND"] = "/bin/sh -c 'unsafe'"
        expect_deployment_error(
            lambda: deploy.maybe_purge_cache(execute=False),
            "shell-style cache purge command was accepted",
        )
        with tempfile.TemporaryDirectory() as temporary:
            wrapper = Path(temporary) / "purge-cache"
            wrapper.write_text("#!/bin/sh\nexit 0\n")
            wrapper.chmod(0o700)
            os.environ["SMD_CACHE_PURGE_COMMAND"] = str(wrapper)
            with redirect_stdout(io.StringIO()) as output:
                deploy.maybe_purge_cache(execute=False)
            check("owned local executable wrapper" in output.getvalue(), "safe purge wrapper was rejected")
            link = Path(temporary) / "purge-link"
            link.symlink_to(wrapper)
            os.environ["SMD_CACHE_PURGE_COMMAND"] = str(link)
            expect_deployment_error(
                lambda: deploy.maybe_purge_cache(execute=False),
                "symlinked cache purge wrapper was accepted",
            )
    finally:
        if previous is None:
            os.environ.pop("SMD_CACHE_PURGE_COMMAND", None)
        else:
            os.environ["SMD_CACHE_PURGE_COMMAND"] = previous


def test_cli_mode_contract() -> None:
    default = deploy.parse_args([])
    check(not default.execute, "default mode unexpectedly enables execution")
    explicit = deploy.parse_args(["--execute"])
    check(explicit.execute, "explicit --execute did not enable execution")


def main() -> None:
    test_configuration_guards()
    test_repository_guards()
    test_alias_guard()
    test_remote_script_transport()
    test_allowlist_and_dry_run_commands()
    test_direct_rsync_dry_run_leaves_files_and_directories_unchanged()
    test_remote_path_resolution()
    test_site_file_merges()
    test_backup_restore_and_hash_contract()
    test_new_immutable_assets_and_rollback()
    test_partial_upload_rollback_orchestration()
    test_immutable_hashes_are_verified_before_entry_activation()
    test_cache_purge_guard()
    test_cli_mode_contract()
    print("Deployment tooling regressions passed: release identity, SSH, allowlist, rollback, purge, and merge guards.")


if __name__ == "__main__":
    main()
