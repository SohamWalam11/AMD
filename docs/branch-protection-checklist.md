# Branch Protection Checklist

Apply this on `main` branch in GitHub settings.

## Required settings

- Require pull request before merging
- Require at least 1 approving review
- Dismiss stale approvals when new commits are pushed
- Require conversation resolution before merge
- Require status checks to pass before merge

## Required CI checks

- `Backend Tests (Python)`
- `Frontend Build (React)`
- `Docker Lint and Build Check`

## Optional recommended settings

- Require signed commits
- Require linear history
- Restrict who can push to matching branches
- Enable merge queue for larger teams
