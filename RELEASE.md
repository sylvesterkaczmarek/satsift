# Source releases

## Release scope

SatSift 3.5.0 is a source release for research screening and technical evaluation. It includes the analysis console, the SatSift URL migration, tested compatibility routing, source-only packaging and complete dependency notices. Original source code and documentation use [Apache License 2.0](LICENSE). The public repository starts from a reviewed source snapshot with new Git history; the original development repository and its service records remain private.

The historical physics-ML method failed its confirmatory gate with 0 true positives and 41 false negatives. The consumed holdout, run lock, archived evaluator and result hashes remain intact. Publishing this source does not qualify the workbench for operational use. See [known limitations](KNOWN-ISSUES.md) and [the release verification](review/CLEAN-RELEASE-VERIFICATION.md).

## Release contents

The candidate contains every regular file in the selected reviewed Git tree, plus a generated SOURCE-RELEASE.json inventory. It preserves source, tests, workflows, data attribution, vendored notices and the frozen scientific evidence. The inventory records each file's Git blob identifier, SHA-256, byte length and executable mode, together with the source commit and tree identifiers.

The exporter reads committed Git objects directly. Local deployment configuration, credentials, ignored or untracked data, caches and environments are excluded by construction. Symbolic links, submodules, private configuration paths, unsafe filenames, case collisions and recognised secret or authoring patterns stop the export. A private deny-list can add owner-specific literals without placing them in the repository or printing their matched values.

The package contains no inherited commits, branches, tags, author metadata or GitHub service records. The development repository and its existing metadata must remain private. A clean current tree does not remove information from old commits or pull requests.

## Create a candidate

Start from a clean checkout at the reviewed commit. Uncommitted and untracked files stop the build; ignored local configuration is neither read nor copied. The destination must be a new directory outside the checkout.

~~~sh
python3 tools/source_release.py build --output ../release-candidates/v3.5.0
~~~

The output directory contains:

- source/ with the exact source files and SOURCE-RELEASE.json.
- satsift-source-candidate.tar.gz with deterministic archive metadata.
- satsift-source-candidate.tar.gz.sha256 with the archive checksum.

Use --deny-file with a private, newline-delimited list of additional literals when preparing an owner-specific release. Keep that file outside source control and outside the candidate. It supplements the built-in scan.

Repeated exports of the same commit produce identical archives. The candidate manifest is a release artefact, ignored by Git so it cannot become stale provenance in a later source commit. Published downloads use versioned filenames such as `satsift-3.5.0-source.tar.gz`; their companion checksum names the downloadable file. Renaming the archive does not change its bytes or checksum.

## Verify the exact package

Check the archive checksum against the independently recorded release receipt. For a versioned 3.5.0 download, use:

~~~sh
shasum -a 256 -c satsift-3.5.0-source.tar.gz.sha256
mkdir satsift-3.5.0-check
tar -xzf satsift-3.5.0-source.tar.gz -C satsift-3.5.0-check
~~~

For a locally built candidate, use the exporter's filenames instead:

~~~sh
shasum -a 256 -c satsift-source-candidate.tar.gz.sha256
mkdir ../v3.5.0-check
tar -xzf satsift-source-candidate.tar.gz -C ../v3.5.0-check
~~~

Verify the extracted tree with `tools/source_release.py`, using the extraction directory for the archive you downloaded or built. The example below uses the local candidate directory. Supply the source tree and commit identifiers from the independent receipt rather than relying solely on the manifest shipped inside the archive. The commit claim is checked only when --expected-commit is supplied.

~~~sh
python3 tools/source_release.py verify ../release-candidates/v3.5.0-check/satsift --expected-tree REVIEWED_TREE_HASH --expected-commit REVIEWED_COMMIT_HASH
~~~

Verification requires every declared file, checks its bytes and mode, reconstructs the Git tree identifier without a Git repository, and rejects unexpected files, directories and links. SHA-256 checks detect changes relative to the trusted receipt; they do not provide a digital signature or establish upstream data authenticity.

Run the applicable repository workflows and browser tests from the extracted source. The repository checker can read a verified release inventory when no .git directory exists. That test mode allows generated test outputs, while the release verifier remains strict about the distributable directory. Keep an untouched verified copy for release and use a separate copy for testing.

The offline suite must not fetch new orbital histories or repeat the one-shot confirmatory experiment. Synthetic neural execution checks exercise code with small generated fixtures; they do not retrain the frozen study.

## Licence and attribution decisions

Original SatSift source code and documentation use [Apache License 2.0](LICENSE). The project [NOTICE](NOTICE), README and npm package metadata record the licence and attribution. Build each release from its reviewed commit and verify the exact exported files. Bundled third-party libraries and external data retain their own notices and terms.

[Third-party notices](THIRD-PARTY-NOTICES.md) identify the bundled software and the reviewed notice sources. The [data notice](benchmark/DATA-NOTICE.md) records source attribution and the separate terms for labels and orbital data. A project licence must not be presented as replacing those third-party terms.

## Repository and release provenance

The first public release is created from the verified source snapshot in a new repository with one initial source commit. The private development repository is retained separately. Its Git directory, branches, tags, pull requests, workflow logs and other service metadata are excluded from publication.

The public repository is [sylvesterkaczmarek/satsift](https://github.com/sylvesterkaczmarek/satsift). The release tag identifies the public source commit. Its source archive carries a SOURCE-RELEASE.json inventory, and the accompanying verification receipt records the public commit, source tree, archive checksum and test scope. Older hashes retained in research records identify the original frozen evidence; they do not imply that private development commits are accessible from this repository.

Keep private configuration outside source control. Further releases must retain the project licence, component notices and data attribution, and pass the applicable verification. A source release and a live website deployment are separate actions.

Any later deployment must follow [the deployment procedure](DEPLOYMENT.md), including the updated root routing template and a fresh deployment-specific verification. The release preparation does not update a live server.
