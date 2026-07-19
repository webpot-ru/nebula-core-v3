# Project Architecture & Workflow Rules

## GitHub Actions Rate-Limit Avoidance Strategy (Orchestration Pattern)

When managing or dispatching multiple workflow runs or orchestrating batch jobs in GitHub Actions:

1. **Do NOT run dispatchers inside GitHub Actions Runners using `GITHUB_TOKEN`** for high-frequency or batch triggers. Runner installation tokens are rate-limited to 1,000 API requests/hour per repository, causing `HTTP 403: API rate limit exceeded` errors.
2. **Use Local / CLI Dispatchers**: Trigger child workflows directly from the local machine using GitHub CLI (`gh workflow run <workflow.yml> --ref main -f param=val`) or local scripts using developer OAuth tokens (`gh auth status`).
3. **Benefits**:
   - Developer tokens have a 5,000 requests/hour API rate limit (5x higher).
   - Zero local CPU load: heavy lifting (scraping, rendering, video processing) remains 100% in GitHub Actions cloud runners.
   - Eliminates rate limit failures during batch execution across multiple channels/workflows.
