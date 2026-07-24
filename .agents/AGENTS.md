# Project Architecture & Workflow Rules

## GitHub Actions Rate-Limit Avoidance Strategy (Orchestration Pattern)

When managing or dispatching multiple workflow runs or orchestrating batch jobs in GitHub Actions:

1. **Do NOT run dispatchers inside GitHub Actions Runners using `GITHUB_TOKEN`** for high-frequency or batch triggers. Runner installation tokens are rate-limited to 1,000 API requests/hour per repository, causing `HTTP 403: API rate limit exceeded` errors.
2. **Use Local / CLI Dispatchers**: Trigger child workflows directly from the local machine using GitHub CLI (`gh workflow run <workflow.yml> --ref main -f param=val`) or local scripts using developer OAuth tokens (`gh auth status`).
3. **Benefits**:
   - Developer tokens have a 5,000 requests/hour API rate limit (5x higher).
   - Zero local CPU load: heavy lifting (scraping, rendering, video processing) remains 100% in GitHub Actions cloud runners.
   - Eliminates rate limit failures during batch execution across multiple channels/workflows.

## GitHub-Only Video Verification

- Run MP4 rendering, browser-frame capture, contact sheets and human-review
  video artifacts only in GitHub Actions.
- Local execution is limited to source inspection, unit tests, static
  validation, linting and type/compile checks that do not create media output.
- Reuse retained GitHub artifacts for no-spend recovery tests. Do not download
  review media to the workstation unless the owner explicitly asks for a local
  copy.
- Upload review evidence as a GitHub Actions artifact and report its run URL;
  never use a successful review render as publication authorization.
