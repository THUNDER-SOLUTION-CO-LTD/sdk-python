# Releasing

Merge the release pull request. release-please updates the changelog and version, then creates the version tag and the GitHub Release. The Release workflow then publishes the new version to PyPI with trusted publishing.

If publishing fails, re-run the failed job or run Release on the version tag.
